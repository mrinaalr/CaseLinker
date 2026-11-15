"""NER stores the place the sentence names, so the location slug can be that string."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
NER_DIR = REPO / "src" / "Processing Layer" / "ML Processing Layer"
sys.path.insert(0, str(NER_DIR))

from ner_extraction import stored_location  # noqa: E402


def test_district_span_keeps_the_state_that_follows_it():
    text = "The charge was filed in the Southern District of Texas yesterday."
    start = text.index("Southern")
    end = start + len("Southern District")
    assert stored_location(text, start, end) == "Southern District of Texas"


def test_each_district_keeps_its_own_state():
    text = "the Western District of Missouri and the Western District of Wisconsin"
    first = text.index("Western")
    second = text.index("Western", first + 1)
    assert stored_location(text, first, first + len("Western District")) == "Western District of Missouri"
    assert stored_location(text, second, second + len("Western District")) == "Western District of Wisconsin"


def test_a_line_break_does_not_drop_the_state():
    text = "in the Southern District\nof Texas."
    start = text.index("Southern")
    end = start + len("Southern District")
    assert stored_location(text, start, end) == "Southern District of Texas"


def test_stanza_stores_each_district_with_its_state():
    import pytest
    from ner_extraction import NERExtractor

    ner = NERExtractor()
    if ner.backend != "stanza" or not ner.stanza_pipeline:
        pytest.skip("Stanza NER is not the active backend")
    text = "The charge was filed in the Southern District of Texas and the Western District of Missouri."
    locations = ner.extract_entities(text)["locations"]
    assert "Southern District of Texas" in locations
    assert "Western District of Missouri" in locations
    assert "the Southern District" not in locations
    assert "Southern District" not in locations


def test_leading_the_is_not_part_of_the_stored_place():
    text = "the Washington County sheriff's office"
    start = text.index("Washington")
    end = start + len("Washington County")
    assert stored_location(text, start, end) == "Washington County"
