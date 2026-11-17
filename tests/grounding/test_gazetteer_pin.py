"""Pinned Census gazetteer is required; missing/corrupt input must raise."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "src" / "Processing Layer" / "location_grounding.py"


def _load():
    spec = importlib.util.spec_from_file_location("location_grounding", PROC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["location_grounding"] = mod
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_missing_gazetteer_raises(tmp_path, monkeypatch):
    lg = _load()
    empty = tmp_path / "empty_gaz"
    empty.mkdir()
    monkeypatch.setenv("CASELINKER_GAZETTEER_DIR", str(empty))
    # Reload module paths that read env at call time
    with pytest.raises(lg.GazetteerError):
        lg.require_gazetteer(empty)


def test_corrupt_checksum_raises(tmp_path):
    lg = _load()
    gaz = tmp_path / "gaz"
    gaz.mkdir()
    # Minimal fake files with wrong hashes
    (gaz / "MANIFEST.json").write_text(
        '{"id":"x","version":"bad","files":{'
        '"2024_Gaz_state_national.txt":{"sha256":"0"*64,"bytes":1},'
        '"2024_Gaz_counties_national.txt":{"sha256":"0"*64,"bytes":1},'
        '"2024_Gaz_place_national.txt":{"sha256":"0"*64,"bytes":1}}}'
    )
    for name in (
        "2024_Gaz_state_national.txt",
        "2024_Gaz_counties_national.txt",
        "2024_Gaz_place_national.txt",
    ):
        (gaz / name).write_text("nope\n")
    with pytest.raises(lg.GazetteerError):
        lg.require_gazetteer(gaz)


def test_pinned_gazetteer_loads():
    lg = _load()
    meta = lg.require_gazetteer()
    assert meta["version"] == "2024.1"
    assert "2024_Gaz_counties_national.txt" in meta["files"]


def test_ground_case_locations_no_silent_slug_without_gazetteer(tmp_path, monkeypatch):
    lg = _load()
    monkeypatch.setenv("CASELINKER_GAZETTEER_DIR", str(tmp_path / "missing"))
    with pytest.raises(lg.GazetteerError):
        lg.ground_case_locations(["Trenton"], source="NJ AG", case_text="Trenton, N.J.")
