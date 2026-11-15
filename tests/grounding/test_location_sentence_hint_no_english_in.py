"""Sentence state hints must not treat English 'in' as Indiana (or similar)."""

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


def test_in_preposition_is_not_indiana(lg):
    assert lg.state_in_sentence("police discovered the images in Norway.") is None
    assert lg.state_in_sentence("a school in Brooklyn pleaded guilty") is None
    assert lg.state_in_sentence("Kenilworth in Waverly after a tip") is None


def test_cybertip_ct_prefix_is_not_connecticut(lg):
    sent = "CRYSTAL LAKE MAN ARRESTED\nMcHenry County Sheriff\nCT 190503924\nIn April"
    # Must not return CT solely from cybertip id
    usps = lg.state_in_sentence(sent)
    assert usps != "CT"


def test_waverly_ne_sp_grounds_nebraska(lg):
    rows = lg.ground_case_locations(
        ["Waverly"],
        source="NE SP",
        case_text="a residence at 13850 Kenilworth in Waverly after receiving a cyber-tip",
        case_id="ne_waverly",
    )
    assert rows[0]["status"] == "grounded"
    assert rows[0]["state_hint"] == "NE"
    assert rows[0]["fips"] == "3151770"  # Waverly city, NE


def test_norway_not_indiana_cdp(lg):
    rows = lg.ground_case_locations(
        ["Norway"],
        source="DOJ CEOS",
        case_text="originally discovered by police in Norway.",
        case_id="norway",
    )
    assert rows[0].get("fips") != "1855350"
    assert rows[0]["status"] in {"ungrounded", "ambiguous", "international"}


def test_washington_dc_not_washington_state(lg):
    rows = lg.ground_case_locations(
        ["Washington"],
        source="NCMEC",
        case_text="A 48-year-old man Washington, D.C. was charged in Fairfax Case.",
        case_id="dc_wash",
    )
    assert rows[0]["status"] == "grounded"
    assert rows[0]["state_hint"] == "DC" or rows[0]["fips"] == "11"
