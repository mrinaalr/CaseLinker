"""Compare a platform-affordance evidence snapshot to the live corpus.

Equal case counts do not prove freshness. ``stale`` is false only when the
snapshot recorded, and the live side still reproduces, all of:

- the corpus case count and extraction-run fingerprint;
- ``platform_pairs_sha256``: every ``(case_id, platform)`` pair in
  ``cases.platforms_used``. Re-resolving platforms in place keeps the
  extraction-run fingerprint but changes the candidate pool; this catches it;
- ``code_versions``: sha256 of the candidate builder, the evidence builder and
  the Gen AI patterns they import, so a rule change also forces a rebuild.

The 2026-11-12 snapshot passed the old two-key check while its candidate list
was 23 days older than the corpus (3,183 listed vs 3,083 live). That is the
case the extra keys exist for.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

# Any positive recorded gap is a coverage warning. Zero gaps still do not
# prove the snapshot matches the live corpus.
DB_GAPS_WARN_ABOVE = 0
REQUIRE_FRESH_MIN_COVERAGE_PCT = 95.0

_CORPUS_SQL = (
    "SELECT COALESCE(extraction_run_id, ''), COUNT(*) FROM cases "
    "GROUP BY COALESCE(extraction_run_id, '')"
)


def _count(metadata: Mapping[str, Any], name: str) -> int | None:
    value = metadata.get(name)
    return value if type(value) is int and value >= 0 else None


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def corpus_identity_from_groups(rows: object) -> dict[str, Any]:
    """Fingerprint ``(extraction_run_id, count)`` groups from ``cases``."""
    pairs: list[tuple[str, int]] = []
    if isinstance(rows, list) or isinstance(rows, tuple):
        sequence = rows
    else:
        sequence = []
    for row in sequence:
        if isinstance(row, Mapping):
            run_id = row.get("extraction_run_id", row.get("run_id", ""))
            count = row.get("count", row.get("n"))
        elif isinstance(row, (list, tuple)) and len(row) >= 2:
            run_id, count = row[0], row[1]
        else:
            continue
        if type(count) is not int or count < 0:
            continue
        pairs.append((str(run_id or ""), count))
    pairs.sort()
    payload = "\n".join(f"{run_id}\t{count}" for run_id, count in pairs)
    return {
        "case_count": sum(count for _, count in pairs),
        "extraction_run_fingerprint": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }


def read_corpus_identity(connection: Any) -> dict[str, Any] | None:
    """Read the live corpus identity. The caller owns ``connection``."""
    cursor = connection.cursor()
    try:
        cursor.execute(_CORPUS_SQL)
        rows = cursor.fetchall()
    finally:
        cursor.close()
    return corpus_identity_from_groups(rows)


CODE_FILES = (
    "ontology/platform_affordance_evidence/build_candidates.py",
    "ontology/platform_affordance_evidence/platform_affordance_evidence.py",
    "src/Processing Layer/Pattern Processing Layer/ai_extraction_patterns.py",
)
_REPO = Path(__file__).resolve().parents[1]


def platform_pairs_identity(rows: object) -> dict[str, Any]:
    """sha256 over sorted ``case_id<TAB>platform`` from ``(case_id, platforms_used_json)`` rows."""
    pairs: set[tuple[str, str]] = set()
    for row in rows if isinstance(rows, (list, tuple)) else []:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        case_id, raw = row[0], row[1]
        if isinstance(raw, str):
            try:
                raw = json.loads(raw) if raw.strip() else []
            except ValueError:
                raw = []
        for platform in raw if isinstance(raw, list) else []:
            if isinstance(platform, str) and platform:
                pairs.add((str(case_id), platform))
    payload = "\n".join(f"{c}\t{p}" for c, p in sorted(pairs))
    return {"platform_pairs": len(pairs),
            "platform_pairs_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest()}


def read_platform_pairs_identity(connection: Any) -> dict[str, Any]:
    """Portable (SQLite and Postgres): parse ``platforms_used`` in Python."""
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT id, platforms_used FROM cases")
        rows = [tuple(r) for r in cursor.fetchall()]
    finally:
        cursor.close()
    return platform_pairs_identity(rows)


def code_versions(root: Path | None = None) -> dict[str, str]:
    root = root or _REPO
    out = {}
    for rel in CODE_FILES:
        path = root / rel
        out[rel] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "missing"
    return out


def read_live_identity(connection: Any, root: Path | None = None) -> dict[str, Any]:
    """Everything ``identity_matches`` compares: corpus, platform pairs, code."""
    live = dict(read_corpus_identity(connection) or {})
    live.update(read_platform_pairs_identity(connection))
    live["code_versions"] = code_versions(root)
    return live


def identity_matches(meta: object, live: object) -> bool:
    """True only when corpus identity, platform pairs and code versions all match."""
    if not isinstance(meta, Mapping) or not isinstance(live, Mapping):
        return False
    recorded_count = _count(meta, "corpus_case_count")
    recorded_fp = _text(meta.get("extraction_run_fingerprint"))
    live_count = live.get("case_count")
    live_fp = _text(live.get("extraction_run_fingerprint"))
    if recorded_count is None or type(live_count) is not int or recorded_fp is None or live_fp is None:
        return False
    if recorded_count != live_count or recorded_fp != live_fp:
        return False
    recorded_pairs = _text(meta.get("platform_pairs_sha256"))
    live_pairs = _text(live.get("platform_pairs_sha256"))
    if recorded_pairs is None or live_pairs is None or recorded_pairs != live_pairs:
        return False
    recorded_code = meta.get("code_versions")
    live_code = live.get("code_versions")
    if not isinstance(recorded_code, Mapping) or not isinstance(live_code, Mapping) or not recorded_code:
        return False
    return dict(recorded_code) == dict(live_code)


def mismatched_inputs(meta: object, live: object) -> list[str]:
    """Which recorded inputs differ from live, for the rebuild log."""
    m = meta if isinstance(meta, Mapping) else {}
    lv = live if isinstance(live, Mapping) else {}
    out = []
    if m.get("corpus_case_count") != lv.get("case_count"):
        out.append("corpus_case_count")
    if m.get("extraction_run_fingerprint") != lv.get("extraction_run_fingerprint"):
        out.append("extraction_run_fingerprint")
    if m.get("platform_pairs_sha256") != lv.get("platform_pairs_sha256"):
        out.append("platform_pairs_sha256")
    rc, lc = m.get("code_versions") or {}, lv.get("code_versions") or {}
    out.extend(f"code:{k}" for k in sorted(set(rc) | set(lc)) if rc.get(k) != lc.get(k))
    return out


def candidate_pool_sha256(candidates: object) -> str | None:
    """sha256 of the ``(case_id, platform)`` pool in a candidates.json payload."""
    if not isinstance(candidates, Mapping) or not isinstance(candidates.get("flat"), list):
        return None
    pairs = sorted(
        (str(cid), str(e.get("platform")))
        for e in candidates["flat"] if isinstance(e, Mapping)
        for cid in (e.get("case_ids") or [])
    )
    return hashlib.sha256("\n".join(f"{c}\t{p}" for c, p in pairs).encode("utf-8")).hexdigest()


def coverage_percent(cases_processed: int | None, live_case_count: int | None) -> float | None:
    if cases_processed is None or live_case_count is None or live_case_count <= 0:
        return None
    return round(100.0 * cases_processed / live_case_count, 1)


def gap_gate(db_gaps: object, *, threshold: int = DB_GAPS_WARN_ABOVE) -> str:
    """``ok`` at or under the threshold, ``warn`` above it, ``fail`` if not a count."""
    if type(db_gaps) is not int or db_gaps < 0 or type(threshold) is not int:
        return "fail"
    if db_gaps > threshold:
        return "warn"
    return "ok"


def rebuild_decision(meta: object, live: object) -> str:
    """``current`` when the snapshot identity matches, else ``rebuild`` or ``unknown``."""
    if not isinstance(live, Mapping) or type(live.get("case_count")) is not int:
        return "unknown"
    if not _text(live.get("extraction_run_fingerprint")):
        return "unknown"
    if identity_matches(meta, live):
        return "current"
    return "rebuild"


def snapshot_freshness(meta: object, live: object = None) -> dict[str, Any]:
    """Declare build scope and whether this process verified the live corpus."""
    metadata = meta if isinstance(meta, Mapping) else {}
    generated = metadata.get("generated")
    generated_at = generated if isinstance(generated, str) and generated.strip() else None
    cases_processed = _count(metadata, "cases_processed")
    db_gaps = _count(metadata, "db_gaps")
    live_case_count = None
    if isinstance(live, Mapping) and type(live.get("case_count")) is int and live["case_count"] >= 0:
        live_case_count = live["case_count"]
    verified = identity_matches(metadata, live)
    if verified:
        status = "current"
    elif live_case_count is not None:
        status = "stale"
    else:
        status = "unverified_snapshot"
    gaps = gap_gate(db_gaps) if db_gaps is not None else "fail"
    if verified:
        warning = (
            "This snapshot's recorded corpus count and extraction-run fingerprint "
            "match the database being served. db_gaps still describe the build, "
            "not a guarantee that every case names a platform."
        )
    else:
        warning = (
            "This is a precomputed platform affordance evidence snapshot, not a live corpus query. "
            "stale is true unless the recorded corpus count and extraction-run fingerprint "
            "both match the database being served. Equal case counts alone do not establish freshness. "
            "Prefer filter_cases_by_tags for a current cohort."
        )
    return {
        "status": status,
        "artifact_kind": "precomputed_platform_affordance_evidence_index",
        "generated_at": generated_at,
        "cases_processed": cases_processed,
        "db_gaps": db_gaps,
        "text_cap": _count(metadata, "text_cap"),
        "coverage_status": "reported_gaps" if db_gaps is not None and db_gaps > 0 else "unverified",
        "current_corpus_verified": verified,
        "live_case_count": live_case_count,
        "coverage_pct": coverage_percent(cases_processed, live_case_count),
        "stale": not verified,
        "gaps_exceed_threshold": gaps == "warn",
        "db_gaps_warn_above": DB_GAPS_WARN_ABOVE,
        "require_fresh_min_coverage_pct": REQUIRE_FRESH_MIN_COVERAGE_PCT,
        "warning": warning,
    }


def require_fresh_block(
    freshness: Mapping[str, Any],
    *,
    min_coverage: float = REQUIRE_FRESH_MIN_COVERAGE_PCT,
) -> str | None:
    """Reason to refuse the snapshot, or None when require_fresh may proceed."""
    if freshness.get("stale") is not False:
        return "platform affordance evidence snapshot is stale or unverified"
    if freshness.get("gaps_exceed_threshold") is True:
        return "platform affordance evidence db_gaps exceed the warning threshold"
    coverage = freshness.get("coverage_pct")
    if type(coverage) not in (int, float) or isinstance(coverage, bool) or coverage < min_coverage:
        return f"platform affordance evidence coverage is below {min_coverage}"
    return None


def with_snapshot_freshness(
    payload: Mapping[str, Any],
    meta: object,
    live: object = None,
) -> dict[str, Any]:
    """Add the same disclosure to index and filtered responses without mutation."""
    return {**payload, "_meta": meta, "freshness": snapshot_freshness(meta, live)}
