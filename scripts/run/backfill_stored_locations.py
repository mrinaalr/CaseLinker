#!/usr/bin/env python3
"""Re-derive stored location strings from the case text already on disk.

NER used to store a bare district ("the Southern District") and leave
"of Texas" outside the span. ``stored_location`` now keeps the place the
sentence names. This script applies that same function to locations already
stored, on a copy of the database. It does not call the NER model.

    python scripts/run/backfill_stored_locations.py \\
        --dest ~/CaseLinker-backups/location-backfill-2026-10-19/caselinker.db
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
NER_DIR = REPO / "src" / "Processing Layer" / "ML Processing Layer"
ONTOLOGY = REPO / "ontology"
for entry in (NER_DIR, ONTOLOGY / "pipeline", REPO / "src" / "Storage Layer"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from ner_extraction import stored_location  # noqa: E402

_BARE_DISTRICT = re.compile(
    r"^(?:the-)?(?:northern|southern|eastern|western|middle|central)-district$"
)


def _slug(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-") or "unknown"


def _overlaps(span: tuple, consumed: list) -> bool:
    return any(not (span[1] <= used[0] or span[0] >= used[1]) for used in consumed)


def _find_label(text: str, label: str, consumed: list) -> tuple | None:
    parts = [p for p in re.split(r"\s+", label.strip()) if p]
    if not parts or not text:
        return None
    pattern = re.compile(r"\s+".join(re.escape(part) for part in parts), re.IGNORECASE)
    free = []
    overlapped = []
    for match in pattern.finditer(text):
        span = (match.start(), match.end())
        if _overlaps(span, consumed):
            overlapped.append(span)
        else:
            free.append(span)
    pool = free or overlapped
    for span in pool:
        # A later "Eastern District of North Carolina" beats a line-broken bare mention.
        if stored_location(text, span[0], span[1]) != re.sub(r"\s+", " ", text[span[0]:span[1]]).strip():
            return span
    return pool[0] if pool else None


def rederive_locations(text: str, locations: list) -> list:
    """Expand each stored place with ``stored_location`` against ``text``.

    Mentions are matched in list order. A label that is not in the article
    stays as stored. This does not re-run NER.
    """
    if not isinstance(locations, list):
        return locations
    consumed: list = []
    out = []
    article = text or ""
    for raw in locations:
        label = str(raw).strip() if raw is not None else ""
        if len(label) < 2:
            out.append(raw)
            continue
        span = _find_label(article, label, consumed)
        if span is None:
            out.append(label)
            continue
        consumed.append(span)
        out.append(stored_location(article, span[0], span[1]))
    return out


def _locations_of(features: dict) -> list:
    raw = features.get("locations") or []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = [raw]
    return raw if isinstance(raw, list) else []


def apply_backfill(dest: Path) -> dict:
    """Rewrite ``extracted_features.locations`` in ``dest``. Returns the report."""
    conn = sqlite3.connect(dest)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, raw_data, extracted_features FROM cases").fetchall()
    changed_cases = []
    slug_changes = Counter()
    bare_before = Counter()
    bare_after = Counter()
    for row in rows:
        try:
            features = json.loads(row["extracted_features"] or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(features, dict):
            continue
        try:
            text = json.loads(row["raw_data"] or "{}").get("case_text") or ""
        except json.JSONDecodeError:
            text = ""
        before = _locations_of(features)
        after = rederive_locations(text, before)
        old_slugs = [_slug(str(item)) for item in before if str(item).strip()]
        new_slugs = [_slug(str(item)) for item in after if str(item).strip()]
        for slug in old_slugs:
            if _BARE_DISTRICT.match(slug):
                bare_before[slug] += 1
        for slug in new_slugs:
            if _BARE_DISTRICT.match(slug):
                bare_after[slug] += 1
        if before == after:
            continue
        features["locations"] = after
        conn.execute(
            "UPDATE cases SET extracted_features = ? WHERE id = ?",
            (json.dumps(features, ensure_ascii=False), row["id"]),
        )
        changed_cases.append(row["id"])
        for old, new in zip(old_slugs, new_slugs):
            if old != new:
                slug_changes[f"{old} -> {new}"] += 1
    conn.commit()
    conn.close()
    return {
        "cases": len(rows),
        "changed_cases": changed_cases,
        "slug_changes": slug_changes,
        "bare_before": bare_before,
        "bare_after": bare_after,
    }


def write_graphs(dest: Path, case_ids: list, out_dir: Path) -> dict:
    """Map changed cases from ``dest`` and count bare-district location IRIs."""
    from features_to_cac import CaseToCAC, flatten_dataset
    from storage import CaseStorage

    out_dir.mkdir(parents=True, exist_ok=True)
    storage = CaseStorage(db_path=str(dest))
    mapper = CaseToCAC()
    bare = Counter()
    written = 0
    for case_id in case_ids:
        case = storage.get_case(case_id)
        if not case:
            continue
        dataset, _warnings = mapper.map_case(case)
        flat = flatten_dataset(dataset)
        text = flat.serialize(format="turtle")
        (out_dir / f"{case_id}.ttl").write_text(text)
        written += 1
        for slug in re.findall(r"resource/location/([A-Za-z0-9-]+)", text):
            if _BARE_DISTRICT.match(slug):
                bare[slug] += 1
    return {"written": written, "bare": bare}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=REPO / "caselinker.db")
    parser.add_argument("--dest", type=Path, required=True)
    parser.add_argument("--graphs-out", type=Path, default=None, help="TTL for changed cases")
    parser.add_argument("--graph-limit", type=int, default=0, help="0 means every changed case")
    args = parser.parse_args(argv)
    source = args.source.expanduser().resolve()
    dest = args.dest.expanduser().resolve()
    if source == dest:
        raise SystemExit("refusing to rewrite the source database; pass a different --dest")
    if not source.is_file():
        raise SystemExit(f"source database not found: {source}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        shutil.copy2(source, dest)
    report = apply_backfill(dest)
    print(f"cases={report['cases']} changed={len(report['changed_cases'])}")
    print("bare district slugs before:", dict(report["bare_before"]))
    print("bare district slugs after:", dict(report["bare_after"]))
    print("slug changes:")
    for key, count in report["slug_changes"].most_common(40):
        print(f"  {count:5d}  {key}")
    report_path = dest.with_suffix(".backfill.json")
    report_path.write_text(json.dumps({
        "cases": report["cases"],
        "changed_cases": report["changed_cases"],
        "slug_changes": report["slug_changes"].most_common(),
        "bare_before": dict(report["bare_before"]),
        "bare_after": dict(report["bare_after"]),
    }))
    print(f"report={report_path}")
    if args.graphs_out:
        ids = report["changed_cases"]
        if args.graph_limit:
            ids = ids[: args.graph_limit]
        graphs = write_graphs(dest, ids, args.graphs_out.expanduser().resolve())
        print(f"graphs written={graphs['written']} bare_district_iris={dict(graphs['bare'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
