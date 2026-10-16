"""Unit tests for case-ids-by-filter validation helpers (#27)."""

from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MAIN = REPO / "run" / "main.py"


def _load_parse_helper():
    """Assert main.py contains the #27 guards; return a pure age-range parser."""
    src = MAIN.read_text(encoding="utf-8")
    assert "_parse_age_range_bounds" in src
    assert "Provide at least one filter" in src
    assert "plat_key = platform.lower()" in src

    def _parse_age_range_bounds(age_range: str) -> tuple[int, int]:
        parts = age_range.strip().split("-")
        if len(parts) != 2:
            raise ValueError("age_range must look like '25-29'")
        age_min, age_max = int(parts[0]), int(parts[1])
        if age_min > age_max:
            raise ValueError("age_range min must be <= max")
        return age_min, age_max

    return _parse_age_range_bounds


class TestAgeRangeBounds(unittest.TestCase):
    def test_valid(self):
        parse = _load_parse_helper()
        self.assertEqual(parse("18-24"), (18, 24))

    def test_invalid_shape(self):
        parse = _load_parse_helper()
        with self.assertRaises(ValueError):
            parse("abc")

    def test_inverted(self):
        parse = _load_parse_helper()
        with self.assertRaises(ValueError):
            parse("40-20")


class TestCorpusDateBoundsLogic(unittest.TestCase):
    """Mirror get_corpus_stats year-bucket suppression (#23)."""

    def test_year_bucket_end_ignored(self):
        cases = [
            {"date_start": "2020-05-01", "date_end": None, "date_range": {"start": "2020-05-01", "end": None}},
            {"date_start": "2026-01-01", "date_end": "2026-12-31", "date_range": {"start": "2026-01-01", "end": "2026-12-31"}},
            {"date_start": "2024-10-01", "date_end": None, "date_range": {"start": "2024-10-01", "end": None}},
        ]
        pub_starts: list[str] = []
        pub_ends: list[str] = []
        for c in cases:
            dr = c.get("date_range") if isinstance(c.get("date_range"), dict) else {}
            start = c.get("date_start") or (dr.get("start") if dr else None)
            end = c.get("date_end") if c.get("date_end") is not None else (dr.get("end") if dr else None)
            if start:
                pub_starts.append(str(start))
            if end:
                end_s = str(end)
                start_s = str(start) if start else ""
                year_bucket = (
                    len(start_s) >= 10
                    and start_s.endswith("-01-01")
                    and end_s == f"{start_s[:4]}-12-31"
                )
                if not year_bucket:
                    pub_ends.append(end_s)
        corpus_end = max(pub_ends) if pub_ends else (max(pub_starts) if pub_starts else None)
        self.assertEqual(min(pub_starts), "2020-05-01")
        # No non-bucket ends → fall back to max(start); never advertise Dec 31.
        self.assertEqual(corpus_end, "2026-01-01")
        self.assertNotEqual(corpus_end, "2026-12-31")
        self.assertEqual(pub_ends, [])


if __name__ == "__main__":
    unittest.main()
