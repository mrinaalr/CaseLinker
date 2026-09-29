#!/usr/bin/env python3
"""Append rows to ontology/PACER/BULK_FOLDER/pacer_cost.csv (manual PACER log format)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
BULK_DIR = REPO_ROOT / "ontology" / "PACER" / "BULK_FOLDER"
DEFAULT_CSV = BULK_DIR / "pacer_cost.csv"

CostRow = Tuple[str, str, str, float]


def format_row(case_id: str, docket_number: str, action: str, cost: float) -> str:
    return f"{case_id}, {docket_number}, {action}, {cost:.2f}"


def _icac_total_index(lines: List[str]) -> int:
    """Line index of the ICAC section TOTAL row (before Outside block)."""
    for i, line in enumerate(lines):
        if ", , TOTAL," in line:
            # First TOTAL is ICAC; second is Outside.
            return i
    raise ValueError(f"No ICAC TOTAL row found in {DEFAULT_CSV}")


def append_cost_rows(rows: List[CostRow], csv_path: Path = DEFAULT_CSV) -> None:
    """Insert cost rows before the ICAC TOTAL line."""
    if not rows:
        return
    text = csv_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    insert_at = _icac_total_index(lines)
    new_lines = [format_row(*r) for r in rows]
    lines[insert_at:insert_at] = new_lines

    # Recompute ICAC section total (rows after header until TOTAL).
    section_total = 0.0
    for line in lines[2:insert_at + len(new_lines)]:
        if not line.strip() or line.startswith("case id"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 4:
            try:
                section_total += float(parts[-1])
            except ValueError:
                pass
    total_idx = insert_at + len(new_lines)
    lines[total_idx] = re.sub(
        r"(, , TOTAL,)\s*[\d.]+",
        rf"\g<1> {section_total:.2f}",
        lines[total_idx],
    )
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def append_cost_row(
    case_id: str,
    docket_number: str,
    action: str,
    cost: float,
    csv_path: Path = DEFAULT_CSV,
) -> None:
    append_cost_rows([(case_id, docket_number, action, cost)], csv_path=csv_path)


def estimate_pacer_pdf_cost(page_count: Optional[int] = None) -> float:
    """PACER: $0.10/page, cap $3.00 per document (estimate when actual unknown)."""
    if page_count and page_count > 0:
        return min(page_count * 0.10, 3.00)
    return 3.00  # conservative default when pages unknown


def estimate_transcript_pacer_cost(page_count: Optional[int] = None) -> Optional[float]:
    """Transcript PDFs are $0.10/page with no $3 cap.

    Unknown page count returns None. Do not substitute the $3 default:
    transcripts are often longer than 30 pages.
    """
    if page_count is None:
        return None
    try:
        pages = int(page_count)
    except (TypeError, ValueError):
        return None
    if pages <= 0:
        return None
    return round(pages * 0.10, 2)
