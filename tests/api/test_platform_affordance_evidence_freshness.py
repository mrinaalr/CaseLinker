"""Platform affordance evidence snapshot disclosures retain uncertainty and preserve returned evidence."""
from __future__ import annotations

import ast
import copy
from pathlib import Path
import sys
import unittest
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "run"))
from platform_affordance_evidence_freshness import (
    corpus_identity_from_groups,
    gap_gate,
    rebuild_decision,
    require_fresh_block,
    snapshot_freshness,
    with_snapshot_freshness,
)


class SnapshotFreshnessTests(unittest.TestCase):
    def test_recorded_build_scope_is_exposed_without_claiming_currentness(self):
        out = snapshot_freshness({
            "generated": "2026-09-15", "cases_processed": 3092,
            "db_gaps": 7308, "text_cap": 6000,
        })
        self.assertEqual(out["generated_at"], "2026-09-15")
        self.assertEqual(out["cases_processed"], 3092)
        self.assertEqual(out["db_gaps"], 7308)
        self.assertEqual(out["text_cap"], 6000)
        self.assertEqual(out["coverage_status"], "reported_gaps")
        self.assertFalse(out["current_corpus_verified"])
        self.assertTrue(out["stale"])
        self.assertIsNone(out["live_case_count"])
        self.assertIsNone(out["coverage_pct"])
        self.assertTrue(out["gaps_exceed_threshold"])

    def test_absent_or_malformed_metadata_remains_unknown(self):
        for meta in (None, {}, [], "missing", {"generated": False}):
            with self.subTest(meta=meta):
                out = snapshot_freshness(meta)
                self.assertEqual(out["status"], "unverified_snapshot")
                self.assertIsNone(out["generated_at"])
                self.assertIsNone(out["cases_processed"])
                self.assertEqual(out["coverage_status"], "unverified")

    def test_invalid_counts_are_not_coerced_into_evidence(self):
        for value in (True, False, -1, 1.5, "3092", float("nan")):
            with self.subTest(value=value):
                out = snapshot_freshness(dict.fromkeys(("cases_processed", "db_gaps", "text_cap"), value))
                for field in ("cases_processed", "db_gaps", "text_cap"):
                    self.assertIsNone(out[field])

    def test_zero_gaps_do_not_certify_a_fresh_or_complete_index(self):
        out = snapshot_freshness({"cases_processed": 0, "db_gaps": 0, "text_cap": 0})
        self.assertEqual(out["cases_processed"], 0)
        self.assertEqual(out["db_gaps"], 0)
        self.assertFalse(out["current_corpus_verified"])
        self.assertTrue(out["stale"])
        self.assertEqual(out["coverage_status"], "unverified")
        self.assertFalse(out["gaps_exceed_threshold"])

    def test_payload_and_metadata_are_not_mutated(self):
        payload = {"cases": [{"case_id": "synthetic_1", "tier": "stated", "evidence_quote": "Synthetic quote"}]}
        meta = {"generated": "2026-09-15", "db_gaps": 1}
        before = copy.deepcopy((payload, meta))
        out = with_snapshot_freshness(payload, meta)
        self.assertEqual((payload, meta), before)
        self.assertEqual(out["cases"], payload["cases"])
        self.assertEqual(out["_meta"], meta)
        self.assertNotIn("freshness", payload)

    def test_equal_counts_without_a_fingerprint_stay_stale(self):
        live = {"case_count": 100, "extraction_run_fingerprint": "abc"}
        out = snapshot_freshness({"corpus_case_count": 100, "cases_processed": 100, "db_gaps": 0}, live)
        self.assertTrue(out["stale"])
        self.assertFalse(out["current_corpus_verified"])
        self.assertEqual(out["live_case_count"], 100)
        self.assertEqual(out["coverage_pct"], 100.0)

    def test_matching_identity_is_current_and_a_mismatch_rebuilds(self):
        groups = [("run-a", 2), ("", 1)]
        live = corpus_identity_from_groups(groups)
        meta = {
            "generated": "2026-10-20",
            "cases_processed": 2,
            "db_gaps": 1,
            "corpus_case_count": live["case_count"],
            "extraction_run_fingerprint": live["extraction_run_fingerprint"],
        }
        out = snapshot_freshness(meta, live)
        self.assertFalse(out["stale"])
        self.assertTrue(out["current_corpus_verified"])
        self.assertEqual(out["status"], "current")
        self.assertEqual(out["live_case_count"], 3)
        self.assertEqual(out["coverage_pct"], 66.7)
        self.assertTrue(out["gaps_exceed_threshold"])
        self.assertEqual(rebuild_decision(meta, live), "current")
        drifted = dict(live)
        drifted["case_count"] = 4
        self.assertEqual(rebuild_decision(meta, drifted), "rebuild")
        self.assertTrue(snapshot_freshness(meta, drifted)["stale"])
        self.assertEqual(rebuild_decision(meta, None), "unknown")

    def test_gap_gate_does_not_coerce_invalid_counts(self):
        self.assertEqual(gap_gate(0), "ok")
        self.assertEqual(gap_gate(1), "warn")
        self.assertEqual(gap_gate(7493), "warn")
        for value in (True, False, -1, 1.5, "0"):
            self.assertEqual(gap_gate(value), "fail")

    def test_require_fresh_rejects_stale_gaps_and_low_coverage(self):
        stale = snapshot_freshness({"cases_processed": 10, "db_gaps": 0})
        self.assertIsNotNone(require_fresh_block(stale))
        current = snapshot_freshness(
            {
                "cases_processed": 50,
                "db_gaps": 0,
                "corpus_case_count": 100,
                "extraction_run_fingerprint": "fp",
            },
            {"case_count": 100, "extraction_run_fingerprint": "fp"},
        )
        self.assertFalse(current["stale"])
        self.assertEqual(current["coverage_pct"], 50.0)
        self.assertIn("below", require_fresh_block(current) or "")
        covered = snapshot_freshness(
            {
                "cases_processed": 100,
                "db_gaps": 0,
                "corpus_case_count": 100,
                "extraction_run_fingerprint": "fp",
            },
            {"case_count": 100, "extraction_run_fingerprint": "fp"},
        )
        self.assertIsNone(require_fresh_block(covered))

    def test_fingerprint_ignores_group_order_and_rejects_bad_counts(self):
        left = corpus_identity_from_groups([("b", 1), ("a", 2)])
        right = corpus_identity_from_groups([("a", 2), ("b", 1)])
        self.assertEqual(left, right)
        self.assertEqual(corpus_identity_from_groups([("a", True), ("b", -1)])["case_count"], 0)


class SnapshotRouteLogicTests(unittest.TestCase):
    """Execute the real route functions without application startup or a database.

    Decorators and the loader are external boundaries; the route, platform
    selection and response construction execute unchanged from run/main.py.
    """
    def setUp(self):
        source = (ROOT / "run" / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        names = {"_platform_affordance_evidence_resolve_platform_name", "_platform_affordance_evidence_index",
                 "_platform_affordance_evidence_cases", "api_platform_affordance_evidence"}
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        self.assertEqual(len(functions), len(names))
        for function in functions:
            function.decorator_list = []
        self.data = {
            "_meta": {"generated": "2026-09-15", "cases_processed": 1, "db_gaps": 2},
            "records": [{"platform": "SyntheticChat", "case_id": "synthetic_1",
                         "stated_vs_inferred": "stated", "evidence_quote": "Synthetic source quote"}],
        }

        class RouteError(Exception):
            def __init__(self, status_code, detail):
                self.status_code, self.detail = status_code, detail

        self.error_type = RouteError
        namespace = {
            "Dict": Dict, "List": List, "Any": Any, "Optional": Optional,
            "Request": object, "Query": lambda default=None: default,
            "HTTPException": RouteError,
            "_PLATFORM_AFFORDANCE_EVIDENCE_VALID_TIERS": frozenset({"stated", "inferred", "named_only"}),
            "_load_platform_affordance_evidence": lambda: self.data,
            "_live_platform_affordance_corpus": lambda: {
                "case_count": 4,
                "extraction_run_fingerprint": "not-the-recorded-build",
            },
            "with_snapshot_freshness": with_snapshot_freshness,
            "require_fresh_block": require_fresh_block,
        }
        module = ast.fix_missing_locations(ast.Module(body=functions, type_ignores=[]))
        exec(compile(module, str(ROOT / "run" / "main.py"), "exec"), namespace)
        self.route = namespace["api_platform_affordance_evidence"]

    def test_index_response_has_snapshot_disclosure(self):
        out = self.route(None, None, None)
        self.assertEqual(out["platforms"][0]["case_count"], 1)
        self.assertEqual(out["freshness"]["cases_processed"], 1)
        self.assertEqual(out["_meta"], self.data["_meta"])

    def test_filtered_response_preserves_evidence_and_disclosure(self):
        out = self.route(None, "syntheticchat", "STATED")
        self.assertEqual(out["tier"], "stated")
        self.assertEqual(out["cases"][0]["evidence_quote"], "Synthetic source quote")
        self.assertEqual(out["freshness"]["coverage_status"], "reported_gaps")

    def test_invalid_tier_still_fails(self):
        with self.assertRaises(self.error_type) as raised:
            self.route(None, None, "unsupported")
        self.assertEqual(raised.exception.status_code, 400)

    def test_unknown_platform_still_fails(self):
        with self.assertRaises(self.error_type) as raised:
            self.route(None, "MissingChat", None)
        self.assertEqual(raised.exception.status_code, 404)

    def test_require_fresh_rejects_the_unmatched_snapshot(self):
        with self.assertRaises(self.error_type) as raised:
            self.route(None, None, None, True)
        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("stale", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
