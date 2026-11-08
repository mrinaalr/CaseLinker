"""/api/sources-stats aggregate: one scan of (id, source, date_start) -> per-source counts and spans."""

import ast
import re
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]


def _load_builder(rows):
    """Execute the aggregate helpers from run/main.py against a fake storage."""
    tree = ast.parse((ROOT / "run" / "main.py").read_text(encoding="utf-8"))
    wanted = {"_source_key", "_year_of", "_build_sources_stats", "_SOURCE_YEAR_RE", "_CASE_ID_YEAR_RE"}
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in wanted:
            nodes.append(node)
        elif isinstance(node, ast.Assign) and any(getattr(t, "id", None) in wanted for t in node.targets):
            nodes.append(node)
    assert len(nodes) == len(wanted), [getattr(n, "name", None) for n in nodes]

    class Storage:
        def get_source_date_rows(self):
            return rows

    namespace = {"re": re, "datetime": datetime, "timezone": timezone, "Dict": Dict, "List": List,
                 "Any": Any, "Optional": Optional, "storage": Storage()}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "main_sources_stats", "exec"), namespace)
    return namespace["_build_sources_stats"]


class SourcesStatsTest(unittest.TestCase):
    ROWS = [
        ("newyork_sp_2023_001", "NEWYORK_SP", "2023-01-01"),
        ("newyork_sp_2025_002", "NewYork SP", "2025-06-30"),
        ("ncmec_2024_001", "NCMEC", "2024-03-02"),
        ("ncmec_2024_002", "NCMEC", None),
        ("doj_archives_2005_001", "DOJ_ARCHIVES", "circa 2005"),
        ("odd_001", None, "2010-02-03"),
    ]

    def setUp(self):
        self.stats = _load_builder(self.ROWS)()

    def test_source_keys_are_normalised_and_counts_match(self):
        self.assertEqual(self.stats["case_count"], 6)
        self.assertEqual(self.stats["sources"]["NEWYORK SP"]["count"], 2)
        self.assertEqual(self.stats["sources"]["NCMEC"]["count"], 2)
        self.assertEqual(self.stats["sources"]["UNKNOWN"]["count"], 1)
        self.assertNotIn("NEWYORK_SP", self.stats["sources"])

    def test_year_span_reads_the_calendar_year_not_a_timezone_shifted_one(self):
        ny = self.stats["sources"]["NEWYORK SP"]
        self.assertEqual((ny["min_year"], ny["max_year"]), (2023, 2025))
        self.assertEqual(self.stats["sources"]["DOJ ARCHIVES"]["min_year"], 2005)
        self.assertEqual((self.stats["min_year"], self.stats["max_year"]), (2005, 2025))

    def test_missing_dates_do_not_break_the_span(self):
        nc = self.stats["sources"]["NCMEC"]
        self.assertEqual((nc["min_year"], nc["max_year"]), (2024, 2024))

    def test_per_year_counts_come_from_the_case_id(self):
        self.assertEqual(self.stats["sources"]["NCMEC"]["years_by_id"], {"2024": 2})
        self.assertEqual(self.stats["sources"]["NEWYORK SP"]["years_by_id"], {"2023": 1, "2025": 1})
        self.assertEqual(self.stats["sources"]["UNKNOWN"]["years_by_id"], {})


if __name__ == "__main__":
    unittest.main()
