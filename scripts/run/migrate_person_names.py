#!/usr/bin/env python3
"""
One-time migration: replace stored person names with per-case tokens.

Before this migration, age readers wrote the name they matched next to an age
into ``field_assertions.extras_json`` (``entity``, ``defendant_entity``,
``sentence_subject``) and the resolver copied it into
``field_resolutions.final_json.perpetrator_entities[].entity``.

This script rewrites, per case:
- ``cases.extracted_features``: records ``person_spans`` (offsets from ``--spans``,
  NER output of ``compute_person_spans.py``), and drops a person filed as a location /
  organization / agency (``people_mask.scrub_people``, as extraction now does)
- assertion extras: names -> ``name_key`` / ``defendant_key`` tokens (``people_mask.pseudonymize``)
- resolution finals: ``perpetrator_entities[]`` -> ``{person: "pN", named, age, other_ages}``

Ages, roles, spans and statuses are not touched. ``field_assertions`` is
append-only; its triggers are lifted and restored inside the same transaction.

Default is a dry run that only counts. ``--apply`` writes.

Usage:
  python3 scripts/run/compute_person_spans.py --sqlite caselinker.db --out person_spans.jsonl
  python3 scripts/run/migrate_person_names.py --sqlite caselinker.db --spans person_spans.jsonl   # dry run
  python3 scripts/run/migrate_person_names.py --sqlite caselinker.db --spans person_spans.jsonl --apply
  DATABASE_URL=postgres://... python3 scripts/run/migrate_person_names.py --spans person_spans.jsonl --apply --i-have-a-backup
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src" / "Processing Layer" / "field_assertions"))

import people_mask  # noqa: E402
import resolution  # noqa: E402

NAME_EXTRA_KEYS = tuple(people_mask.NAME_KEYS)


def _connect(args) -> Tuple[Any, str]:
    if args.sqlite:
        return sqlite3.connect(args.sqlite), "sqlite"
    url = args.database_url or os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("pass --sqlite PATH or --database-url / DATABASE_URL")
    import psycopg2
    return psycopg2.connect(url), "postgres"


def _ph(dialect: str) -> str:
    return "?" if dialect == "sqlite" else "%s"


def _lift_triggers(cur, dialect: str) -> None:
    if dialect == "sqlite":
        cur.execute("DROP TRIGGER IF EXISTS field_assertions_append_only_update")
        cur.execute("DROP TRIGGER IF EXISTS field_assertions_append_only_delete")
    else:
        cur.execute("ALTER TABLE field_assertions DISABLE TRIGGER field_assertions_append_only_update")
        cur.execute("ALTER TABLE field_assertions DISABLE TRIGGER field_assertions_append_only_delete")


def _restore_triggers(cur, dialect: str) -> None:
    if dialect == "sqlite":
        for op in ("UPDATE", "DELETE"):
            cur.execute(
                f"""CREATE TRIGGER IF NOT EXISTS field_assertions_append_only_{op.lower()}
                BEFORE {op} ON field_assertions
                BEGIN
                    SELECT RAISE(ABORT, 'field_assertions rows are append-only');
                END"""
            )
    else:
        cur.execute("ALTER TABLE field_assertions ENABLE TRIGGER field_assertions_append_only_update")
        cur.execute("ALTER TABLE field_assertions ENABLE TRIGGER field_assertions_append_only_delete")


def _has_raw_name(extras: Dict) -> bool:
    if any(k in extras for k in ("defendant_entity", "sentence_subject")):
        return True
    return bool(resolution._parse_entity(str(extras.get("entity") or "")))


def migrate_assertions(cur, dialect: str) -> Tuple[List[Tuple[str, int]], int]:
    """(updates as (extras_json, id), rows scanned with a raw name)."""
    like = " OR ".join(f"extras_json LIKE '%\"{k}\"%'" for k in NAME_EXTRA_KEYS)
    cur.execute(f"SELECT DISTINCT case_id FROM field_assertions WHERE {like}")
    case_ids = [r[0] for r in cur.fetchall()]
    updates: List[Tuple[str, int]] = []
    scanned = 0
    ph = _ph(dialect)
    for case_id in case_ids:
        cur.execute(f"SELECT id, span_start, extras_json FROM field_assertions WHERE case_id = {ph} ORDER BY id", (case_id,))
        rows = cur.fetchall()
        items = [{"id": rid, "span_start": s, "extras": json.loads(ex or "{}") or {}} for rid, s, ex in rows]
        before = {it["id"]: json.dumps(it["extras"], sort_keys=True) for it in items}
        scanned += sum(1 for it in items if _has_raw_name(it["extras"]))
        people_mask.pseudonymize(items)
        for it in items:
            after = json.dumps(it["extras"], sort_keys=True)
            if after != before[it["id"]]:
                updates.append((json.dumps(it["extras"]), it["id"]))
    return updates, scanned


# Same keys merge_processing scrubs at extraction time.
FEATURE_KEYS = (
    "locations", "organizations", "agencies_involved", "pathway_agencies_federal",
    "pathway_agencies_state_local", "location_grounds", "agency_grounds", "ml_features", "comparison_values",
)


def load_spans(path: str) -> Dict[str, Dict]:
    """``compute_person_spans.py`` output, keyed by case id (offsets + text hash, no names)."""
    out: Dict[str, Dict] = {}
    for line in Path(path).read_text().splitlines():
        if line.strip():
            rec = json.loads(line)
            out[rec["case_id"]] = rec
    return out


def migrate_features(cur, dialect: str, spans: Dict[str, Dict]) -> Tuple[List[Tuple[str, str]], Dict[str, int]]:
    """Record ``person_spans`` and drop person-name entries from entity lists in ``cases.extracted_features``.

    Offsets come from ``--spans`` (NER, verified against a hash of the stored text);
    a case without a matching entry gets cue-only spans. People are read from those
    offsets in memory. Runs before ``migrate_assertions``.
    """
    import hashlib

    cur.execute("SELECT id, extracted_features, raw_data FROM cases")
    updates: List[Tuple[str, str]] = []
    stats: Dict[str, int] = defaultdict(int)
    for case_id, fj, rd in cur.fetchall():
        feats = json.loads(fj or "{}") or {}
        raw = json.loads(rd or "{}") if isinstance(rd, str) else (rd or {})
        text = (raw or {}).get("case_text") or feats.get("case_text") or ""
        rec = spans.get(case_id)
        if rec and rec.get("text_sha256") == hashlib.sha256(text.encode("utf-8")).hexdigest():
            # Re-derive from the raw NER offsets with the current filters (the file may predate them).
            person_spans = people_mask.person_spans(text, rec.get("ner_person") or [], feats.get("agencies_involved") or [])
            stats["spans_from_ner"] += 1
        else:
            person_spans = people_mask.person_spans(text, (), feats.get("agencies_involved") or [])
            stats["spans_text_changed" if rec else "spans_cue_only"] += 1
        grounded = [g.get(k) for key in ("location_grounds", "agency_grounds") for g in feats.get(key) or []
                    if isinstance(g, dict) and g.get("status") == "grounded" for k in ("mention", "entity_name")]
        grounded += [x for x in (feats.get("agencies_involved") or []) if isinstance(x, str)]
        full, surnames = people_mask.case_people(text, [text[a:b] for a, b in person_spans], grounded)
        new = dict(feats)
        new["person_spans"] = person_spans
        for key in FEATURE_KEYS:
            if key in feats:
                new[key] = people_mask.scrub_people(feats[key], full, surnames)
                if json.dumps(feats[key]) != json.dumps(new[key]):
                    stats[f"scrubbed:{key}"] += 1
        if new != feats:
            updates.append((json.dumps(new), case_id))
    return updates, dict(stats)


def _migrate_final(final: Any) -> Any:
    if not isinstance(final, dict) or not isinstance(final.get("perpetrator_entities"), list):
        return final
    out = dict(final)
    out["perpetrator_entities"] = [
        {"person": f"p{n}", "named": bool(e.get("entity")), "age": e.get("age"), "other_ages": e.get("other_ages", [])}
        if isinstance(e, dict) and "entity" in e else e
        for n, e in enumerate(final["perpetrator_entities"], start=1)
    ]
    return out


def migrate_resolutions(cur) -> List[Tuple[str, int]]:
    cur.execute("SELECT id, final_json FROM field_resolutions WHERE final_json LIKE '%\"entity\"%'")
    updates = []
    for rid, fj in cur.fetchall():
        final = json.loads(fj or "null")
        new = _migrate_final(final)
        if new != final:
            updates.append((json.dumps(new), rid))
    return updates


def verify(cur) -> Dict[str, int]:
    """Counts that must be zero after --apply."""
    cur.execute("SELECT extras_json FROM field_assertions WHERE extras_json LIKE '%entity%' OR extras_json LIKE '%sentence_subject%'")
    raw = sum(1 for (ex,) in cur.fetchall() if _has_raw_name(json.loads(ex or "{}") or {}))
    cur.execute("SELECT count(*) FROM field_resolutions WHERE final_json LIKE '%\"entity\"%'")
    fin = cur.fetchone()[0]
    return {"assertions_with_raw_name": raw, "resolutions_with_entity_key": fin}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sqlite")
    ap.add_argument("--database-url")
    ap.add_argument("--spans", help="compute_person_spans.py output (JSONL of offsets)")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    ap.add_argument("--i-have-a-backup", action="store_true", help="required with --apply on Postgres")
    args = ap.parse_args()

    if args.apply and args.sqlite:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = f"{args.sqlite}.bak-{stamp}"
        shutil.copy2(args.sqlite, backup)
        print(f"backup: {backup}")
    if args.apply and not args.sqlite and not args.i_have_a_backup:
        sys.exit("Postgres --apply needs --i-have-a-backup (take a snapshot first)")

    conn, dialect = _connect(args)
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM field_assertions")
    total_assertions = cur.fetchone()[0]
    f_updates, f_dropped = migrate_features(cur, dialect, load_spans(args.spans) if args.spans else {})
    a_updates, scanned = migrate_assertions(cur, dialect)
    r_updates = migrate_resolutions(cur)
    print(f"cases.extracted_features: {len(f_updates)} cases would change; by key {f_dropped}")
    print(f"field_assertions: {total_assertions} rows; {scanned} hold a raw name; {len(a_updates)} would change")
    print(f"field_resolutions: {len(r_updates)} finals would change")

    if not args.apply:
        print("dry run: nothing written")
        return

    ph = _ph(dialect)
    try:
        cur.executemany(f"UPDATE cases SET extracted_features = {ph} WHERE id = {ph}", f_updates)
        _lift_triggers(cur, dialect)
        cur.executemany(f"UPDATE field_assertions SET extras_json = {ph} WHERE id = {ph}", a_updates)
        cur.executemany(f"UPDATE field_resolutions SET final_json = {ph} WHERE id = {ph}", r_updates)
        _restore_triggers(cur, dialect)
        result = verify(cur)
        cur.execute("SELECT count(*) FROM field_assertions")
        if cur.fetchone()[0] != total_assertions or any(result.values()):
            raise RuntimeError(f"verification failed: {result}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    print(f"applied; verify: {verify(cur)}")


if __name__ == "__main__":
    main()
