"""Bare city names must not silently ground to the same-named county."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "src" / "Processing Layer" / "location_grounding.py"
GAZ = ROOT / "data" / "gazetteer"


def _load():
    spec = importlib.util.spec_from_file_location("location_grounding", PROC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["location_grounding"] = mod
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def lg():
    if not (GAZ / "2024_Gaz_counties_national.txt").is_file():
        pytest.skip("gazetteer missing")
    return _load()


def test_boise_id_does_not_ground_to_boise_county(lg):
    rows = lg.ground_case_locations(
        ["Boise"],
        source="US MARSHALS",
        case_text="Boise, ID – The U.S. Marshals announced an arrest.",
        case_id="boise_test",
    )
    assert rows[0]["status"] in {"grounded", "ambiguous"}
    if rows[0]["status"] == "grounded":
        assert rows[0]["entity_kind"] == "place"
        assert rows[0]["fips"] != "16015"  # Boise County


def test_peoria_dateline_not_peoria_county(lg):
    rows = lg.ground_case_locations(
        ["Peoria"],
        source="DOJ SAFE CHILDHOOD",
        case_text="Peoria, Ill. — A former resident was sentenced.",
        case_id="peoria_test",
    )
    assert rows[0]["status"] in {"grounded", "ambiguous"}
    if rows[0]["status"] == "grounded":
        assert rows[0]["entity_kind"] != "county"
