"""Wilson intervals for the phase-3 error rates."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify" / "phase_3" / "phase3_paired_results.py"
_spec = importlib.util.spec_from_file_location("phase3_paired_results", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
wilson_interval = _mod.wilson_interval


def test_wilson_interval_matches_the_score_formula():
    # 10 errors in 100 stored finals. Computed independently of the helper.
    low, high = wilson_interval(10, 100)
    assert round(low, 4) == 0.0552
    assert round(high, 4) == 0.1744


def test_wilson_interval_for_zero_errors_is_not_a_point():
    low, high = wilson_interval(0, 179)
    assert low == 0.0
    assert high > 0.0
    assert high < 0.03


def test_wilson_interval_refuses_an_impossible_count():
    try:
        wilson_interval(3, 2)
    except ValueError:
        return
    raise AssertionError("expected ValueError")
