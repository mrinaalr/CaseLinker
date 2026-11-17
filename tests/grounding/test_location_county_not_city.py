"""Mentions that say County must ground to the county, not a same-name city/CDP."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GAZ = ROOT / "data" / "gazetteer"
PROC = ROOT / "src" / "Processing Layer" / "location_grounding.py"


def _load():
    spec = importlib.util.spec_from_file_location("location_grounding", PROC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["location_grounding"] = mod
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def lg():
    if not (GAZ / "MANIFEST.json").is_file():
        pytest.skip("gazetteer missing")
    return _load()


def test_buffalo_county_not_buffalo_city(lg):
    rows = lg.ground_case_locations(
        ["BUFFALO COUNTY"],
        source="WI AG",
        case_text="A BUFFALO COUNTY MAN was accused in Alma, Wis., WEAU reported.",
        case_id="wi_buffalo",
    )
    assert rows[0]["status"] == "grounded"
    assert rows[0]["entity_name"] == "Buffalo County"
    assert rows[0]["entity_kind"] == "county"
    assert rows[0]["fips"] == "55011"


def test_whitley_county_not_whitley_city_cdp(lg):
    rows = lg.ground_case_locations(
        ["Whitley County"],
        source="KY SP",
        case_text="Kentucky State Police Charges Whitley County Man. WILLIAMSBURG, Ky.",
        case_id="ky_whitley",
    )
    assert rows[0]["status"] == "grounded"
    assert rows[0]["entity_name"] == "Whitley County"
    assert rows[0]["entity_kind"] == "county"


def test_lancaster_county_not_lancaster_city(lg):
    rows = lg.ground_case_locations(
        ["LANCASTER COUNTY"],
        source="PA AG",
        case_text="LANCASTER COUNTY MAN ACCUSED. HARRISBURG, Pa.",
        case_id="pa_lancaster",
    )
    assert rows[0]["status"] == "grounded"
    assert rows[0]["entity_name"] == "Lancaster County"
    assert rows[0]["entity_kind"] == "county"


def test_bare_county_without_state_does_not_guess_city(lg):
    """Without a state, prefer abstain over grounding a same-name city."""
    rows = lg.ground_case_locations(
        ["BUFFALO COUNTY"], source="UNKNOWN", case_id="no_hint"
    )
    assert rows[0]["status"] in {"ambiguous", "ungrounded"}
    assert "City" not in (rows[0].get("entity_name") or "")
