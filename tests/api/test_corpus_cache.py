"""A cache keyed by case count serves the previous ids after a renumber."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("corpus_cache", ROOT / "run" / "corpus_cache.py")
cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cc)


def test_same_count_different_ids_is_a_different_corpus():
    old = [f"ncmec_2025_{i:04d}" for i in range(3)]
    new = ["cspd_2026_001", "ncmec_2025_0001", "ncmec_2025_0002"]
    assert len(old) == len(new)
    assert cc.corpus_fingerprint(old) != cc.corpus_fingerprint(new)


def test_stale_group_is_refused():
    current = {"cspd_2026_001", "ncmec_2025_0001"}
    stale = {"case_groups": [{"size": 2, "cases": ["ncmec_2025_1028", "ncmec_2025_0001"]}]}
    fresh = {"case_groups": [{"size": 2, "cases": ["cspd_2026_001", "ncmec_2025_0001"]}]}
    assert cc.payload_matches_corpus(stale, current) is False
    assert cc.payload_matches_corpus(fresh, current) is True


def test_unknown_is_not_coverage():
    assert cc.is_stated("unknown") is False
    assert cc.is_stated("Unknown") is False
    assert cc.is_stated("") is False
    assert cc.is_stated(None) is False
    assert cc.is_stated("mother") is True
    assert cc.is_stated("cybertip") is True
