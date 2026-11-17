"""Stored location strings are re-derived from the article already on disk."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
NER_DIR = REPO / "src" / "Processing Layer" / "ML Processing Layer"
sys.path.insert(0, str(NER_DIR))

_SCRIPT = REPO / "scripts" / "run" / "backfill_stored_locations.py"
_spec = importlib.util.spec_from_file_location("backfill_stored_locations", _SCRIPT)
backfill = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backfill)


def test_a_stored_district_grows_to_the_state_named_in_the_article():
    text = "The charge was filed in the Southern District of Texas and the Western District of Missouri."
    stored = ["the Southern District", "Texas", "the Western District", "Missouri"]
    assert backfill.rederive_locations(text, stored) == [
        "Southern District of Texas",
        "Texas",
        "Western District of Missouri",
        "Missouri",
    ]


def test_a_duplicate_district_label_uses_the_same_sentence():
    text = "The plea was announced in the Northern District of Texas."
    stored = ["Northern District", "Texas", "the Northern District"]
    assert backfill.rederive_locations(text, stored) == [
        "Northern District of Texas",
        "Texas",
        "Northern District of Texas",
    ]


def test_a_line_broken_district_prefers_the_mention_that_names_the_state():
    text = (
        "the Eastern\nDistrict announced the plea. "
        "Ellis Boyle, U.S. Attorney for the Eastern District of North Carolina, made the announcement."
    )
    assert backfill.rederive_locations(text, ["Eastern District"]) == ["Eastern District of North Carolina"]


def test_a_place_already_stored_in_full_is_left_alone():
    text = "Filed in the Southern District of Texas."
    assert backfill.rederive_locations(text, ["Southern District of Texas"]) == ["Southern District of Texas"]


def test_a_label_missing_from_the_article_is_kept():
    assert backfill.rederive_locations("No place here.", ["Austin"]) == ["Austin"]
