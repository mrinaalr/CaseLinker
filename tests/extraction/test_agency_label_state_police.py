"""Agency labels keep the release wording for state police (#59) and county sheriffs (#60)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PROC = REPO / "src" / "Processing Layer"


def _load(name: str, path: Path):
    # sys.path is set only while loading and restored after: other files in this folder
    # import ``processing`` by path order, and a path left behind here changes which one.
    saved = list(sys.path)
    sys.path[:0] = [str(REPO / "src"), str(PROC)]
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path[:] = saved


@pytest.fixture(scope="module")
def mp():
    return _load("merge_processing_sp_under_test", PROC / "merge_processing.py").MergeProcessing()


@pytest.mark.parametrize(
    "label, stored",
    [
        ("New Jersey State Police", "New Jersey State Police"),
        ("the Kentucky State Police", "Kentucky State Police"),
        ("State Police", "State Police"),
        ("Michigan State Police Department", "Michigan State Police Department"),
    ],
)
def test_state_police_label_is_stored_as_written(mp, label, stored):
    assert mp._normalize_organizations([label]) == [stored]


def test_county_sheriff_split_from_a_partner_list_keeps_its_county(mp):
    glued = "Camden County Sheriff’s Office Cape May County Prosecutor’s Office Collingswood Police Department"
    assert mp._normalize_organizations([glued]) == [
        "Camden County Sheriff's Office",
        "Cape May County Prosecutor's Office",
        "Collingswood Police Department",
    ]


def test_bare_state_police_is_dropped_beside_a_named_one():
    norm = _load("agency_label_normalize_sp_under_test", PROC / "agency_label_normalize.py")

    assert norm.dedupe_generic_state_police(["State Police", "New Jersey State Police"]) == ["New Jersey State Police"]
    assert norm.dedupe_generic_state_police(["State Police"]) == ["State Police"]


def test_two_county_sheriffs_glued_by_a_line_break_are_two_agencies(mp):
    glued = "Forsyth County Sheriff’s Office\nHall County Sheriff’s Office"
    assert mp._normalize_organizations([glued]) == ["Forsyth County Sheriff's Office", "Hall County Sheriff's Office"]
