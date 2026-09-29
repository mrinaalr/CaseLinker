#!/usr/bin/env python3
"""
Identify CaseLinker corpus cases likely to have a federal PACER docket.

PACER eligibility heuristic (no single field is definitive):
  A — Federal ingestion source (DOJ CEOS/ARCHIVES, ICE, USSS, US MARSHALS, …)
  B — Federal prosecuting / investigating agency on the case row
  C — Narrative signals: U.S. District Court, federal indictment/sentencing, cr docket pattern

Cases matching any tier are included; confidence is high (A), medium (A+B or B+C), or low (C only).

Output: ontology/PACER/pacer_cases.json

Usage:
  python collector/pacer/corpus2pacer.py
  python collector/pacer/corpus2pacer.py --db /path/to/caselinker.db --min-confidence medium
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = REPO_ROOT / "ontology" / "PACER" / "pacer_cases.json"

sys.path.insert(0, str(REPO_ROOT / "src" / "Storage Layer"))

from storage import CaseStorage  # noqa: E402

# Press-release sources that describe federal prosecutions (strong PACER signal).
FEDERAL_SOURCES: frozenset[str] = frozenset(
    {
        "DOJ CEOS",
        "DOJ ARCHIVES",
        "ICE",
        "USSS",
        "US MARSHALS",
        "NCIS",
        "CBP",
        "ARMY CID",
        "AF OSI",
    }
)

# Substrings matched against agencies_involved / organizations (case-insensitive).
FEDERAL_AGENCY_PATTERNS: Tuple[str, ...] = (
    "fbi",
    "hsi",
    "ice",
    "ceos",
    "u.s. attorney",
    "us attorney",
    "usao",
    "department of justice",
    "u.s. department of justice",
    "homeland security",
    "secret service",
    "u.s. marshals",
    "us marshals",
    "naval criminal investigative",
    "ncis",
    "customs and border protection",
    "army criminal investigation",
    "air force office of special investigations",
    "federal bureau of investigation",
)

# Narrative regexes — federal court / prosecution language.
TEXT_PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    ("district_court", re.compile(r"\bU\.?\s*S\.?\s+District\s+Court\b", re.I)),
    ("federal_district", re.compile(r"\bfederal\s+district\s+court\b", re.I)),
    ("federal_court", re.compile(r"\bfederal\s+court\b", re.I)),
    ("federal_grand_jury", re.compile(r"\bfederal\s+grand\s+jury\b", re.I)),
    ("federal_indictment", re.compile(r"\bindicted\b.{0,40}\bfederal\b|\bfederal\b.{0,40}\bindicted\b", re.I)),
    ("federal_sentencing", re.compile(r"\bsentenced\b.{0,60}\bfederal\b|\bfederal\b.{0,60}\bsentenced\b", re.I)),
    ("us_attorney_mention", re.compile(r"\bU\.?\s*S\.?\s+Attorney\b", re.I)),
    (
        "district_abbrev",
        re.compile(
            r"\b(?:E\.?D\.?|W\.?D\.?|N\.?D\.?|S\.?D\.?|M\.?D\.?|D\.?C\.?)\s+"
            r"(?:of\s+)?(?:Ala|Alaska|Ariz|Ark|Cal|Colo|Conn|Del|Fla|Ga|Haw|Idaho|Ill|Ind|Iowa|"
            r"Kan|Ky|La|Maine|Md|Mass|Mich|Minn|Miss|Mo|Mont|Neb|Nev|NH|NJ|NM|NY|NC|ND|Ohio|Okla|"
            r"Ore|Pa|Puerto Rico|RI|SC|SD|Tenn|Tex|Utah|Vt|Va|Wash|Wis|Wyo)\b",
            re.I,
        ),
    ),
    ("cr_docket", re.compile(r"\b\d+:\d{2}-cr-\d{3,6}\b")),
    ("pacer_docket", re.compile(r"\b\d+:\d{2}-[a-z]{2}-\d{3,6}\b", re.I)),
)

CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}


def _parse_list(val: Any) -> List[str]:
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
            return [str(x) for x in parsed] if isinstance(parsed, list) else [s]
        except json.JSONDecodeError:
            return [s]
    return []


def _case_text(case: Dict[str, Any]) -> str:
    text = case.get("case_text") or ""
    if text:
        return str(text)
    raw = case.get("raw_data")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return raw
    if isinstance(raw, dict):
        return str(raw.get("case_text") or raw.get("text") or "")
    return ""


def _agency_blob(case: Dict[str, Any]) -> str:
    parts: List[str] = []
    for key in ("agencies_involved", "organizations"):
        parts.extend(_parse_list(case.get(key)))
    ef = case.get("extracted_features")
    if isinstance(ef, str):
        try:
            ef = json.loads(ef)
        except json.JSONDecodeError:
            ef = {}
    if isinstance(ef, dict):
        parts.extend(_parse_list(ef.get("agencies_involved")))
    return " | ".join(parts).lower()


def _text_signals(text: str) -> List[str]:
    if not text:
        return []
    return [name for name, pat in TEXT_PATTERNS if pat.search(text)]


def _agency_signals(blob: str) -> List[str]:
    if not blob:
        return []
    hits = []
    for pat in FEDERAL_AGENCY_PATTERNS:
        if pat in blob:
            hits.append(f"agency:{pat}")
    return hits


def assess_case(case: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return eligibility record or None if not PACER-eligible."""
    signals: List[str] = []
    tier_a = False
    tier_b = False
    tier_c = False

    source = (case.get("source") or "").strip()
    if source in FEDERAL_SOURCES:
        tier_a = True
        signals.append(f"federal_source:{source}")

    agency_blob = _agency_blob(case)
    agency_hits = _agency_signals(agency_blob)
    if agency_hits:
        tier_b = True
        signals.extend(agency_hits)

    text_hits = _text_signals(_case_text(case))
    if text_hits:
        tier_c = True
        signals.extend(text_hits)

    prosecution = case.get("prosecution_outcome")
    if isinstance(prosecution, str):
        prosecution = prosecution.lower()
        if prosecution and any(
            k in prosecution for k in ("federal", "u.s. district", "us district", "doj")
        ):
            tier_c = True
            signals.append("prosecution_outcome:federal")

    # Agency mention alone is too noisy (FBI assists on many state ICAC cases).
    strong_text = bool(
        text_hits
        and any(
            h in text_hits
            for h in (
                "district_court",
                "federal_district",
                "cr_docket",
                "pacer_docket",
                "federal_grand_jury",
                "federal_indictment",
            )
        )
    )

    if not (tier_a or strong_text or (tier_b and tier_c)):
        return None

    if tier_a or strong_text:
        confidence = "high"
    elif tier_b and tier_c:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "id": case.get("id"),
        "source": source or None,
        "confidence": confidence,
        "tiers": {
            "federal_source": tier_a,
            "federal_agency": tier_b,
            "federal_narrative": tier_c,
        },
        "signals": sorted(set(signals)),
    }


def build_pacer_pool(
    cases: List[Dict[str, Any]],
    min_confidence: str = "low",
) -> Dict[str, Any]:
    min_rank = CONFIDENCE_RANK.get(min_confidence, 1)
    eligible: List[Dict[str, Any]] = []
    by_confidence: Dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    by_source: Dict[str, int] = {}

    for case in cases:
        rec = assess_case(case)
        if rec is None:
            continue
        if CONFIDENCE_RANK[rec["confidence"]] < min_rank:
            continue
        eligible.append(rec)
        by_confidence[rec["confidence"]] += 1
        src = rec.get("source") or "unknown"
        by_source[src] = by_source.get(src, 0) + 1

    eligible.sort(key=lambda r: (-CONFIDENCE_RANK[r["confidence"]], r["id"] or ""))
    ids = [r["id"] for r in eligible if r.get("id")]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_corpus": len(cases),
        "eligible_count": len(eligible),
        "case_ids": ids,
        "min_confidence": min_confidence,
        "criteria": {
            "federal_sources": sorted(FEDERAL_SOURCES),
            "agency_patterns": list(FEDERAL_AGENCY_PATTERNS),
            "text_patterns": [name for name, _ in TEXT_PATTERNS],
            "note": (
                "Heuristic pool for PACER lookup — not every ID is guaranteed to have a "
                "public docket; downstream filters (facet tree, manual review) refine further."
            ),
        },
        "by_confidence": by_confidence,
        "by_source": dict(sorted(by_source.items(), key=lambda kv: (-kv[1], kv[0]))),
        "cases": eligible,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build PACER-eligible case pool from CaseLinker DB.")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(os.environ.get("CASELINKER_DB", REPO_ROOT / "caselinker.db")),
        help="Path to caselinker.db",
    )
    parser.add_argument(
        "--min-confidence",
        choices=("low", "medium", "high"),
        default="low",
        help="Minimum confidence tier to include (default: low)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_PATH,
        help="Output JSON path (default: ontology/PACER/pacer_cases.json)",
    )
    args = parser.parse_args()

    if not args.db.exists():
        print(f"Database not found: {args.db}", file=sys.stderr)
        return 1

    storage = CaseStorage(str(args.db))
    cases = storage.get_all_cases(include_raw_data=False) or []
    payload = build_pacer_pool(cases, min_confidence=args.min_confidence)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Wrote {args.output}")
    print(f"  corpus: {payload['total_corpus']} cases")
    print(f"  eligible: {payload['eligible_count']} ({payload['by_confidence']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
