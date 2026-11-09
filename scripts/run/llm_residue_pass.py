#!/usr/bin/env python3
"""
LLM pass over stored open mentions. Does not re-extract.

For each case whose deterministic resolution left a mention open, call the same
LLM layer ingest uses (sentence windows, span gate, confidence 0.6, shared cache).
Append the new assertions and a fresh resolution. Skip a case when this model
digest already wrote an llm assertion on its current run.

Usage (repo root):
  CASELINKER_LLM=1 python3 scripts/run/llm_residue_pass.py
  CASELINKER_LLM=1 python3 scripts/run/llm_residue_pass.py --case-ids azicac_2011_001
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[2]
for sub in ("src", "src/Processing Layer", "src/Storage Layer", "src/Ingestion Layer",
            "src/Processing Layer/ML Processing Layer", "src/Processing Layer/field_assertions"):
    sys.path.insert(0, str(REPO / sub))

import processing  # noqa: E402
import llm_extraction as LLM  # noqa: E402

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


def already_done(assertions: List[Dict[str, Any]], digest: str) -> bool:
    """True when this model digest already appended an llm assertion on the current run."""
    for assertion in assertions:
        if assertion.get("method") != "llm":
            continue
        if (assertion.get("extras") or {}).get("model_digest") == digest:
            return True
    return False


def _bucket(resolutions: Dict[str, Dict[str, Any]]) -> Dict[str, set]:
    age = (resolutions.get("age") or {}).get("final_value") or {}
    sentence = (resolutions.get("sentence") or {}).get("final_value") or {}
    contested = set()
    for item in (age.get("contested") or {}).values():
        if item.get("value") is not None:
            contested.add(("age", item["value"]))
    for item in ((resolutions.get("sentence") or {}).get("disagreement") or {}).get("contested", {}).values():
        contested.add(("sentence", str(item.get("value"))))
    return {
        "victims": set(age.get("victims") or []),
        "perpetrators": set(age.get("perpetrators") or []),
        "imposed": set(sentence.get("imposed") or []),
        "contested": contested,
    }


def compare_finals(before: Dict[str, Dict], after: Dict[str, Dict]) -> Tuple[int, int, List[Tuple[str, str]], List[Tuple[str, str]]]:
    """(added count, veto count, added (bucket, value) pairs, vetoed pairs)."""
    old, new = _bucket(before), _bucket(after)
    added_pairs: List[Tuple[str, str]] = []
    vetoed_pairs: List[Tuple[str, str]] = []
    for key in ("victims", "perpetrators", "imposed"):
        added_pairs.extend((key, str(value)) for value in sorted(new[key] - old[key], key=str))
        vetoed_pairs.extend((key, str(value)) for value in sorted(old[key] - new[key], key=str))
    return len(added_pairs), len(vetoed_pairs), added_pairs, vetoed_pairs


def _rederive_legacy(storage, case: dict, assertions: list, resolutions: dict) -> None:
    feats = case.get("extracted_features") if isinstance(case.get("extracted_features"), dict) else {}
    rebuilt = {**feats, **{k: case.get(k) for k in _COLUMNS if k in case}}
    merger = processing.MergeProcessing()
    rebuilt.setdefault("ml_features", {})
    merger._apply_resolved_ages(rebuilt, resolutions.get("age") or {})
    merger._apply_resolved_sentences(rebuilt, resolutions.get("sentence") or {})
    merger._apply_resolved_cybertip(rebuilt, resolutions.get("investigation_type") or {})
    merger._apply_resolved_cybertip_reporter(rebuilt, resolutions.get("cybertip_reporter") or {})
    merger._apply_resolved_dates(rebuilt, resolutions.get("date") or {})
    storage.store_case(processing.assign_comparison_values(rebuilt))


def pass_case(storage, case_id: str, *, cfg: dict, cache, digest: str) -> Dict[str, Any]:
    """One case. Returns a count record. Does not call the model when already done or nothing is open."""
    amod = processing.assertions_module
    run_id, stored = storage.load_case_assertions(case_id)
    if not run_id:
        return {"status": "no_assertions"}
    if already_done(stored, digest):
        return {"status": "skipped_done"}
    case = storage.get_case(case_id) or {}
    text = case.get("case_text") or ""
    batch_date = (case.get("date_range") or {}).get("start")
    before = amod.resolve(list(stored), batch_date=batch_date, text=text)
    if not LLM.targets_from(before, stored):
        return {"status": "skipped_closed"}
    fresh, meta = LLM.run_llm(
        text, before, stored, amod.gate_assertion, cfg=cfg, cache=cache, digest=digest,
    )
    grounded = [a for a in fresh if a.get("span_ok")]
    rejected = len(fresh) - len(grounded)
    if not grounded:
        return {"status": "called_empty", "meta": meta, "added": 0, "vetoed": 0, "rejected": rejected}
    after = amod.resolve(list(stored) + grounded, batch_date=batch_date, text=text)
    added, vetoed, added_pairs, vetoed_pairs = compare_finals(before, after)
    storage.append_resolutions(case_id, run_id, after, grounded)
    if case:
        _rederive_legacy(storage, case, list(stored) + grounded, after)
    return {
        "status": "called", "meta": meta, "added": added, "vetoed": vetoed, "rejected": rejected,
        "added_pairs": added_pairs, "vetoed_pairs": vetoed_pairs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case-ids", nargs="*", help="limit to these cases (default: all)")
    parser.add_argument("--detail-out", type=Path, help="write one JSON object per case that added or vetoed a final")
    args = parser.parse_args()
    if not LLM.llm_enabled():
        print("CASELINKER_LLM is not set. Refusing to call the model.", file=sys.stderr)
        return 2
    cfg = LLM.llm_config()
    digest = LLM.model_digest(cfg)
    if digest.startswith("unreachable") or digest == "model_not_pulled":
        print(f"LLM model is not available ({digest}).", file=sys.stderr)
        return 2
    storage = _storage()
    cache = LLM.LLMCache(cfg["cache_path"])
    ids = args.case_ids or [c["id"] for c in storage.get_all_cases(include_raw_data=False)]
    counts = {"skipped_done": 0, "skipped_closed": 0, "called": 0, "called_empty": 0, "no_assertions": 0}
    added = vetoed = rejected = 0
    details = []
    for case_id in ids:
        result = pass_case(storage, case_id, cfg=cfg, cache=cache, digest=digest)
        counts[result["status"]] = counts.get(result["status"], 0) + 1
        added += result.get("added") or 0
        vetoed += result.get("vetoed") or 0
        rejected += result.get("rejected") or 0
        if result.get("added_pairs") or result.get("vetoed_pairs"):
            details.append({
                "case_id": case_id,
                "added": result.get("added_pairs") or [],
                "vetoed": result.get("vetoed_pairs") or [],
            })
    if args.detail_out:
        args.detail_out.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in details) + ("\n" if details else ""),
            encoding="utf-8",
        )
    print(
        f"llm residue pass digest={digest} cases={len(ids)} "
        f"skipped_done={counts['skipped_done']} skipped_closed={counts['skipped_closed']} "
        f"called={counts['called']} called_empty={counts['called_empty']} "
        f"added_finals={added} vetoes={vetoed} quotes_rejected={rejected}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
