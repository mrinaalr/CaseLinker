"""State DOJ / DCI must not ground to federal U.S. Department of Justice."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REG = ROOT / "data" / "agency_registry"
PROC = ROOT / "src" / "Processing Layer" / "agency_grounding.py"


def _load():
    spec = importlib.util.spec_from_file_location("agency_grounding", PROC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["agency_grounding"] = mod
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ag():
    if not (REG / "MANIFEST.json").is_file():
        pytest.skip("agency registry missing")
    return _load()


def test_wisconsin_doj_dci_not_federal_doj(ag):
    rows = ag.ground_case_agencies(
        ["Wisconsin Department of Justice Division of Criminal Investigation"],
        source="WISCONSIN DOJ",
        case_id="wi_doj",
    )
    assert rows[0].get("code") != "DOJ"
    assert rows[0]["status"] != "grounded" or rows[0].get("agency_kind") != "federal"


def test_us_doj_still_grounds_federal(ag):
    rows = ag.ground_case_agencies(
        ["U.S. Department of Justice"], source="DOJ SAFE CHILDHOOD", case_id="us_doj"
    )
    assert rows[0]["status"] == "grounded"
    assert rows[0]["code"] == "DOJ"
