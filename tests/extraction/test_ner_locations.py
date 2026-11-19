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


# --- organizations: county sheriff in a run-on partner list (#60) ---------------

from ner_extraction import stored_organization  # noqa: E402

NJ_LIST = (
    "Camden County\nProsecutor’s Office Camden County Sheriff’s Office Cape May County "
    "Prosecutor’s Office Collingswood\nPolice Department ... Ocean County Prosecutor’s\n"
    "Office Passaic County Sheriff’s Department Passaic County Prosecutor’s Office"
)


def test_sheriff_span_takes_the_county_written_before_it():
    start = NJ_LIST.index("Sheriff’s Office")
    end = NJ_LIST.index("Collingswood\nPolice Department") + len("Collingswood\nPolice Department")
    assert stored_organization(NJ_LIST, start, end).startswith("Camden County Sheriff’s Office Cape May")
    start = NJ_LIST.index("Sheriff’s Department")
    assert stored_organization(NJ_LIST, start, start + len("Sheriff’s Department")) == (
        "Passaic County Sheriff’s Department"
    )


def test_sheriff_span_takes_no_county_across_punctuation_or_from_an_agency_word():
    for text in ("the County Sheriff's Office said", "Prosecutor's Office, Sheriff's Office", "the Sheriff's Office"):
        start = text.index("Sheriff")
        assert not stored_organization(text, start, len(text)).lower().startswith(("county", "the", "prosecutor"))


def test_sheriff_span_keeps_a_parish_name():
    text = "St. Mary Parish Sheriff's Office"
    start = text.index("Sheriff")
    assert stored_organization(text, start, len(text)) == "St. Mary Parish Sheriff's Office"


def test_non_sheriff_span_is_unchanged():
    text = "Camden County Prosecutor's Office"
    start = text.index("Prosecutor")
    assert stored_organization(text, start, len(text)) == "Prosecutor's Office"


def test_secretary_of_state_police_is_not_read_as_the_state_police():
    text = "investigators, along with officers from the Secretary of State Police and the St. Clair County"
    start = text.index("State Police")
    assert stored_organization(text, start, start + len("State Police")) == "Secretary of State Police"


def test_sheriff_span_takes_no_words_from_another_agency_on_the_line_or_the_line_above():
    text = "Henry County Police Department\nHomeland Security Investigations Houston County Sheriff’s Office"
    start = text.index("Sheriff")
    assert stored_organization(text, start, len(text)) == "Houston County Sheriff’s Office"
    text = "Cuyahoga Co. Dept. of Child & Family Services Ottawa County Sheriff's Office"
    start = text.index("Sheriff")
    assert stored_organization(text, start, len(text)) == "Ottawa County Sheriff's Office"


def test_sheriff_span_takes_only_a_census_county_name():
    for text, want in [
        ("led by Sgt. Chris Hyatt-Coweta County Sheriff's Office", "Coweta County Sheriff's Office"),
        ("the Police Department. San Diego County Sheriff's Department", "San Diego County Sheriff's Department"),
        ("West Baton Rouge Parish Sheriff's Office", "West Baton Rouge Parish Sheriff's Office"),
        ("Atlantis County Sheriff's Office", "Sheriff's Office"),
        ("Miami-Dade County Sheriff's Office", "Miami-Dade County Sheriff's Office"),
    ]:
        start = text.index("Sheriff")
        assert stored_organization(text, start, len(text)) == want, text
