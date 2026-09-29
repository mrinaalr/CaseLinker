#!/usr/bin/env python3
"""
Sample cases for manual age-extraction validation (issue #15).

Corpus-wide manual review is not feasible (10,282 cases / ~4,500 source
pages). This script pulls a stratified, seeded sample of cases where
perpetrator/victim age extraction is most likely to be wrong, and writes a
review sheet (CSV) a human can fill in with a verdict per row.

Strata (a case can match more than one; each case is sampled once):
  - multi_candidate:  >1 perpetrator age candidate in one case (the exact
                       ambiguity in the doj_ai_csam_2023_001 example from #15)
  - digest_pollution: flagged as a press digest / multi-defendant operation,
                       or has an unusually large age list
  - sentence_trap:    text contains "sentenced to N years" near a stored
                       perpetrator age (classic age-vs-sentence-length trap)
  - victim_ambiguous: multiple victim ages, or both an age list and an age
                       range stored for the same case
  - possible_miss:    no perpetrator/victim age stored at all, but the text
                       contains age-shaped language (candidate false negative)
  - control:          plain random sample, unweighted, as a sanity baseline

Usage:
  python scripts/validation/sample_age_cases.py
  python scripts/validation/sample_age_cases.py --sample-size 25 --seed 7
  python scripts/validation/sample_age_cases.py --out scripts/validation/output/my_sample.csv

Output:
  A CSV review sheet with blank verdict/correct_value/notes columns, and a
  companion JSON with the full case text for rows where the trimmed context
  window isn't enough to judge.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STORAGE_DIR = PROJECT_ROOT / "src" / "Storage Layer"
PATTERN_DIR = PROJECT_ROOT / "src" / "Processing Layer" / "Pattern Processing Layer"
sys.path.insert(0, str(STORAGE_DIR))
sys.path.insert(0, str(PATTERN_DIR))

if os.getenv("DATABASE_URL"):
    from storage_postgres import CaseStorage  # type: ignore
else:
    from storage import CaseStorage  # type: ignore

try:
    from processing import PERP_AGE_MULTI_THRESHOLD  # type: ignore
except ImportError:
    PERP_AGE_MULTI_THRESHOLD = 3

WINDOW_RADIUS = 100
MAX_CONTEXT_CHARS = 1200

SENTENCE_LENGTH_RE = re.compile(
    r"sentenced\s+to\s+(?:approximately\s+)?\d{1,3}\s+years?|"
    r"\d{1,3}\s+years?\s+in\s+(?:federal\s+)?prison",
    re.IGNORECASE,
)

# Loose "there might be an age here we didn't extract" detector, used only
# for the possible_miss stratum. Deliberately broader than the real
# extractor patterns in processing.py so it over-flags candidates for a
# human to check, rather than trying to be a second extractor.
AGE_LANGUAGE_RE = re.compile(
    r"\b\d{1,2}\s*[-\s]?year[-\s]old\b|"
    r"\bage[d]?\s+\d{1,2}\b|"
    r",\s*\d{1,2}\s*,\s*of\b",
    re.IGNORECASE,
)


def _to_age_list(value: Any) -> List[int]:
    if value is None:
        return []
    if isinstance(value, (int, float)):
        return [int(value)]
    if isinstance(value, list):
        out = []
        for v in value:
            try:
                out.append(int(v))
            except (TypeError, ValueError):
                continue
        return out
    return []


def _victim_ages(case: Dict[str, Any]) -> List[int]:
    # ``case_demographics`` is the only field the modern extraction pipeline
    # (merge_processing.py) writes ages/age_range to. The SQL-backed
    # ``victim_demographics`` field is a legacy, range-only mirror (no
    # ``ages`` list at all) and get_all_cases() returns it as a list of raw
    # row-dicts, not a demographics dict, so it can't stand in here.
    demo = case.get("case_demographics")
    if not isinstance(demo, dict):
        return []
    return _to_age_list(demo.get("ages"))


def _victim_age_range(case: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    demo = case.get("case_demographics")
    if not isinstance(demo, dict):
        return None
    return demo.get("age_range")


def build_strata(cases: List[Dict[str, Any]]) -> Dict[str, Set[str]]:
    """Compute full stratum membership over the whole corpus (not just a draw)."""
    strata: Dict[str, Set[str]] = {
        "multi_candidate": set(),
        "digest_pollution": set(),
        "sentence_trap": set(),
        "victim_ambiguous": set(),
        "possible_miss": set(),
    }

    for case in cases:
        case_id = case.get("id")
        if not case_id:
            continue
        text = case.get("case_text") or ""
        perp_ages = _to_age_list(case.get("perpetrator_age"))
        vic_ages = _victim_ages(case)
        vic_range = _victim_age_range(case)

        if len(perp_ages) > 1:
            strata["multi_candidate"].add(case_id)

        if (
            case.get("press_digest_pollution")
            or case.get("multi_defendant_operation")
            or len(perp_ages) > PERP_AGE_MULTI_THRESHOLD
        ):
            strata["digest_pollution"].add(case_id)

        if perp_ages and text and SENTENCE_LENGTH_RE.search(text):
            strata["sentence_trap"].add(case_id)

        if len(vic_ages) > 1 or (vic_ages and vic_range):
            strata["victim_ambiguous"].add(case_id)

        if not perp_ages and not vic_ages and text and AGE_LANGUAGE_RE.search(text):
            strata["possible_miss"].add(case_id)

    return strata


def find_value_windows(text: str, value: int, radius: int = WINDOW_RADIUS) -> List[str]:
    windows = []
    for m in re.finditer(rf"(?<!\d){value}(?!\d)", text):
        start = max(0, m.start() - radius)
        end = min(len(text), m.end() + radius)
        windows.append(text[start:end].strip())
    return windows


def find_language_windows(text: str, radius: int = WINDOW_RADIUS) -> List[str]:
    windows = []
    for m in AGE_LANGUAGE_RE.finditer(text):
        start = max(0, m.start() - radius)
        end = min(len(text), m.end() + radius)
        windows.append(text[start:end].strip())
    return windows


def build_context(case: Dict[str, Any], matched_strata: Set[str]) -> str:
    text = case.get("case_text") or ""
    perp_ages = _to_age_list(case.get("perpetrator_age"))
    vic_ages = _victim_ages(case)

    windows: List[str] = []
    seen: Set[str] = set()

    for value in sorted(set(perp_ages) | set(vic_ages)):
        for w in find_value_windows(text, value):
            if w not in seen:
                seen.add(w)
                windows.append(f"[age={value}] ...{w}...")

    if "possible_miss" in matched_strata and not windows:
        for w in find_language_windows(text):
            if w not in seen:
                seen.add(w)
                windows.append(f"[unmatched] ...{w}...")

    joined = " ||| ".join(windows)
    if len(joined) > MAX_CONTEXT_CHARS:
        joined = joined[:MAX_CONTEXT_CHARS] + " ...[truncated, see JSON sidecar]"
    return joined


def sample_cases(
    cases: List[Dict[str, Any]],
    sample_size: int,
    seed: int,
) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    by_id = {c["id"]: c for c in cases if c.get("id")}
    strata = build_strata(cases)

    selected: Dict[str, Set[str]] = {}  # case_id -> matched strata (filled in below)

    for name in ["multi_candidate", "digest_pollution", "sentence_trap", "victim_ambiguous", "possible_miss"]:
        pool = sorted(strata[name])
        rng.shuffle(pool)
        for case_id in pool[:sample_size]:
            selected.setdefault(case_id, set())

    # Control: plain random draw from cases with a case_text, excluding
    # anything already picked, so it's an unweighted baseline.
    control_pool = [
        c["id"]
        for c in cases
        if c.get("id") and c.get("case_text") and c["id"] not in selected
    ]
    rng.shuffle(control_pool)
    for case_id in control_pool[:sample_size]:
        selected.setdefault(case_id, set())

    # Now label every selected case with EVERY stratum it actually belongs
    # to (not just the one that caused it to be drawn).
    for name, members in strata.items():
        for case_id in members:
            if case_id in selected:
                selected[case_id].add(name)
    for case_id in selected:
        if not selected[case_id]:
            selected[case_id].add("control")

    rows = []
    for case_id, matched in selected.items():
        case = by_id.get(case_id)
        if not case:
            continue
        rows.append({"case": case, "strata": matched})

    rng.shuffle(rows)
    return rows


def write_review_sheet(rows: List[Dict[str, Any]], csv_path: Path, json_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "case_id",
                "source",
                "source_url",
                "strata",
                "stored_perpetrator_age",
                "stored_victim_ages",
                "stored_victim_age_range",
                "review_context",
                "verdict",  # human fills in: correct / wrong / unclear
                "correct_value",  # human fills in if verdict == wrong
                "notes",
            ]
        )
        for row in rows:
            case = row["case"]
            writer.writerow(
                [
                    case.get("id", ""),
                    case.get("source", ""),
                    case.get("source_url", ""),
                    ";".join(sorted(row["strata"])),
                    json.dumps(_to_age_list(case.get("perpetrator_age"))),
                    json.dumps(_victim_ages(case)),
                    json.dumps(_victim_age_range(case)),
                    build_context(case, row["strata"]),
                    "",
                    "",
                    "",
                ]
            )

    sidecar = []
    for row in rows:
        case = row["case"]
        sidecar.append(
            {
                "case_id": case.get("id"),
                "source": case.get("source"),
                "source_url": case.get("source_url"),
                "strata": sorted(row["strata"]),
                "stored_perpetrator_age": _to_age_list(case.get("perpetrator_age")),
                "stored_victim_ages": _victim_ages(case),
                "stored_victim_age_range": _victim_age_range(case),
                "case_text": case.get("case_text", ""),
            }
        )
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(sidecar, f, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sample-size",
        type=int,
        default=40,
        help="Max cases to draw per stratum (default: 40; ~5 strata + control -> up to ~240 rows before dedup)",
    )
    parser.add_argument("--seed", type=int, default=42, help="RNG seed, for a reproducible sample")
    parser.add_argument(
        "--out",
        type=Path,
        default=PROJECT_ROOT / "scripts" / "validation" / "output" / "age_review_sample.csv",
        help="Output CSV path (a same-named .json sidecar with full case_text is also written)",
    )
    args = parser.parse_args()

    if os.getenv("DATABASE_URL"):
        storage = CaseStorage()
    else:
        db_path = PROJECT_ROOT / "caselinker.db"
        storage = CaseStorage(str(db_path))

    print("Loading cases from database...")
    cases = storage.get_all_cases(include_raw_data=True)
    print(f"Loaded {len(cases)} cases")
    if not cases:
        print("No cases found - nothing to sample.")
        return

    strata = build_strata(cases)
    print("\nStratum membership (full corpus):")
    for name, members in strata.items():
        print(f"  {name:18} {len(members):5} cases")

    rows = sample_cases(cases, args.sample_size, args.seed)
    print(f"\nSampled {len(rows)} unique cases (seed={args.seed})")

    from collections import Counter

    strata_counts = Counter()
    for row in rows:
        for s in row["strata"]:
            strata_counts[s] += 1
    print("Rows per stratum (a row can count toward more than one):")
    for name, count in strata_counts.most_common():
        print(f"  {name:18} {count:5}")

    json_path = args.out.with_suffix(".json")
    write_review_sheet(rows, args.out, json_path)
    print(f"\nReview sheet written to: {args.out}")
    print(f"Full-text sidecar written to: {json_path}")
    print("\nFill in the 'verdict' / 'correct_value' / 'notes' columns in the CSV by hand.")


if __name__ == "__main__":
    main()
