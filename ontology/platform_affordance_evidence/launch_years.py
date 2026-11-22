"""Launch year of each platform in the capability registry.

The table sits next to the capability sources and is not read by observation,
resolution, or release. A blank year is unknown: ``generation`` returns None,
and ``unknowns`` lists those platform ids.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Optional

REPO = Path(__file__).resolve().parents[2]
DEFAULT_TABLE = (
    REPO
    / "ontology"
    / "platform_affordance_evidence"
    / "afh_manifest"
    / "config"
    / "platform_launch_years.csv"
)

# Inclusive bounds. An unknown year is not a member of any of these.
GENERATIONS = ("<=2003", "2004-2010", "2011-2016", ">=2017")


def generation(year: Optional[int]) -> Optional[str]:
    """The generation label for a launch year, or None when the year is unknown."""
    if year is None:
        return None
    if year <= 2003:
        return "<=2003"
    if year <= 2010:
        return "2004-2010"
    if year <= 2016:
        return "2011-2016"
    return ">=2017"


def load(path: Path = DEFAULT_TABLE) -> List[dict]:
    """Rows in file order. ``launch_year`` is an int or None."""
    rows = []
    with path.open(encoding="utf-8", newline="") as handle:
        for record in csv.DictReader(handle):
            raw = (record.get("launch_year") or "").strip()
            rows.append({
                "platform_id": record["platform_id"],
                "launch_year": int(raw) if raw else None,
                "source_url": (record.get("source_url") or "").strip(),
                "note": (record.get("note") or "").strip(),
            })
    return rows


def unknowns(rows: List[dict]) -> List[str]:
    """Platform ids whose launch year is blank, in table order."""
    return [row["platform_id"] for row in rows if row["launch_year"] is None]


def by_generation(rows: List[dict]) -> Dict[str, List[str]]:
    """Platform ids in each generation. Unknown years are left out."""
    grouped = {label: [] for label in GENERATIONS}
    for row in rows:
        label = generation(row["launch_year"])
        if label is not None:
            grouped[label].append(row["platform_id"])
    return grouped
