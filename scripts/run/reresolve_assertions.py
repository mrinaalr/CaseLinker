#!/usr/bin/env python3
"""
Re-run CaseLinker 3.0 field resolution over stored assertions (no re-extraction).

Reads each case's current-run assertions, adds any new human verdicts from
config/victim_age_overrides.json as ``human`` assertions and any assertions a
detector added since the run (``cybertip_reporter``, #20), appends fresh
field_resolutions / review_queue rows, and re-derives the legacy columns
(perpetrator_age, victim ages, sentences, investigation_types) from the result.
Stored assertions are never edited.

Usage (repo root):
  python3 scripts/run/reresolve_assertions.py                     # every case with assertions
  python3 scripts/run/reresolve_assertions.py --case-ids ncmec_2024_1175 azicac_2011_001
  python3 scripts/run/reresolve_assertions.py --resolutions-only  # leave legacy columns alone
  DATABASE_URL=... python3 scripts/run/reresolve_assertions.py    # Postgres
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for sub in ("src", "src/Processing Layer", "src/Storage Layer", "src/Ingestion Layer"):
    sys.path.insert(0, str(REPO / sub))

import processing  # noqa: E402

_COLUMNS = (
    "id", "source", "source_url", "date_range", "victim_count", "relationship_to_victim", "platforms_used",
    "severity_indicators", "case_topics", "tags", "notes", "raw_data", "case_text", "created_at",
    "document_version_id", "extraction_run_id",
)


def _storage():
    if os.getenv("DATABASE_URL"):
        from storage_postgres import CaseStorage
        return CaseStorage()
    from storage import CaseStorage
    try:
        from config import DATABASE_PATH
    except ImportError:
        DATABASE_PATH = "caselinker.db"
    return CaseStorage(os.environ.get("CASELINKER_DB", DATABASE_PATH))


def _case_ids(storage) -> list[str]:
    return [c["id"] for c in storage.get_all_cases(include_raw_data=False)]


def _new_human(stored, text, case_id):
    amod = processing.assertions_module
    mentions = amod.patterns.age_mentions(text)
    from victim_age_overrides import load_victim_age_overrides

    have = {(a["value"], a["role"], a["span_start"]) for a in stored if a["method"] == "human"}
    fresh = [amod.gate_assertion(text, a) for a in amod._human_assertions(text, case_id, mentions, load_victim_age_overrides())]
    return [a for a in fresh if (a["value"], a["role"], a["span_start"]) not in have]


# Detectors added after a case's run; their assertions are appended to that run.
_NEW_DETECTORS = ("cybertip_reporter",)


def _new_detected(stored, text):
    amod = processing.assertions_module
    have = {(a["field"], a["value"], a["role"], a["span_start"]) for a in stored}
    fresh = [amod.gate_assertion(text, a) for a in amod.patterns.cybertip_reporter_assertions(text)]
    return [a for a in fresh if a["field"] in _NEW_DETECTORS
            and (a["field"], a["value"], a["role"], a["span_start"]) not in have]


def _rederive_case(case: dict, assertions: list, resolutions: dict) -> dict:
    """Legacy columns from a resolution. The returned dict does not carry assertion rows."""
    feats = case.get("extracted_features") if isinstance(case.get("extracted_features"), dict) else {}
    rebuilt = {**feats, **{k: case.get(k) for k in _COLUMNS if k in case}}
    merger = processing.MergeProcessing()
    rebuilt.setdefault("ml_features", {})
    rebuilt["assertions"] = assertions
    merger._apply_resolved_ages(rebuilt, resolutions.get("age") or {})
    merger._apply_resolved_sentences(rebuilt, resolutions.get("sentence") or {})
    merger._apply_resolved_cybertip(rebuilt, resolutions.get("investigation_type") or {})
    merger._apply_resolved_cybertip_reporter(rebuilt, resolutions.get("cybertip_reporter") or {})
    merger._apply_resolved_dates(rebuilt, resolutions.get("date") or {})
    rebuilt.pop("assertions", None)
    rebuilt.pop("resolutions", None)
    return processing.assign_comparison_values(rebuilt)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case-ids", nargs="*", help="limit to these cases (default: all)")
    ap.add_argument("--resolutions-only", action="store_true", help="append resolutions; do not touch legacy columns")
    ap.add_argument("--batch-size", type=int, default=100, help="cases per transaction (default 100)")
    args = ap.parse_args()
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be at least 1")

    storage = _storage()
    amod = processing.assertions_module
    ids = args.case_ids or _case_ids(storage)
    changed = skipped = 0
    pending: list = []

    def flush() -> None:
        nonlocal pending
        if pending:
            storage.apply_reresolve_batch(pending)
            pending = []

    for cid in ids:
        run_id, stored = storage.load_case_assertions(cid)
        if not run_id:
            skipped += 1
            continue
        case = storage.get_case(cid) or {}
        text = case.get("case_text") or ""
        human = _new_human(stored, text, cid) + _new_detected(stored, text)
        resolutions = amod.resolve(
            stored + human,
            batch_date=(case.get("date_range") or {}).get("start"),
            text=text,
        )
        item = {
            "case_id": cid,
            "run_id": run_id,
            "resolutions": resolutions,
            "new_assertions": human or None,
        }
        if not args.resolutions_only and case:
            item["case"] = _rederive_case(case, stored + human, resolutions)
        pending.append(item)
        changed += 1
        if len(pending) >= args.batch_size:
            flush()
    flush()
    print(f"re-resolved {changed} case(s) with rule set {amod.resolution.RULE_SET_VERSION}; "
          f"{skipped} without stored assertions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
