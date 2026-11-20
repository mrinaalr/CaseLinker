"""Extractor mistakes a reingest would otherwise store again.

"online" had to sit next to "investigation", a CyberTip is not primary type
unknown, and a Project Safe Childhood footer is not a charge.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATTERN = ROOT / "src" / "Processing Layer" / "Pattern Processing Layer"
for p in (ROOT / "src" / "Processing Layer", PATTERN):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

_spec = importlib.util.spec_from_file_location("pattern_processing", PATTERN / "pattern_processing.py")
proc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(proc)

_tspec = importlib.util.spec_from_file_location("temporal_tags", PATTERN / "temporal_tags.py")
tt = importlib.util.module_from_spec(_tspec)
_tspec.loader.exec_module(tt)


def test_online_must_sit_near_investigation():
    far = (
        "The defendant used an online account. "
        "Months later a federal investigation began."
    )
    info = proc.extract_investigation_info({"case_text": far})
    assert "online" not in (info or {}).get("types", [])

    near = "Following an online investigation, prosecutors announced the charges."
    info = proc.extract_investigation_info({"case_text": near})
    assert "online" in info["types"]


def test_cybertip_is_not_stored_as_unknown():
    text = (
        "NCMEC referred a CyberTip about the account. "
        "The investigation later identified the account holder."
    )
    info = proc.extract_investigation_info({"case_text": text})
    assert "cybertip" in info["types"]
    assert "unknown" not in info["types"]
    assert info["type"] == "cybertip"


def test_footer_is_not_a_charge():
    footer = (
        "This case was brought as part of Project Safe Childhood, a nationwide initiative "
        "to combat the growing epidemic of child sexual exploitation and abuse. "
        "The Child Exploitation and Obscenity Section assisted."
    )
    assert proc._extract_prosecution_charges(footer) == []

    charged = "He was charged with sexual exploitation of a minor."
    labels = [c["charge"] for c in proc._extract_prosecution_charges(charged)]
    assert "sexual exploitation of a minor" in labels


def test_a_longer_charge_is_not_counted_again_as_its_shorter_phrase():
    text = "He was convicted of one count of possession of child pornography."
    labels = [c["charge"] for c in proc._extract_prosecution_charges(text)]
    assert "possession of child pornography" in " ".join(labels)
    assert labels.count("child pornography") == 0


def test_one_city_is_not_multi_state():
    dc = "WASHINGTON — A man in Washington, D.C., pleaded guilty."
    assert "multi_state" not in proc.extract_topics({"case_text": dc})
    vegas = "The arrest was in Las Vegas."
    assert "multi_state" not in proc.extract_topics({"case_text": vegas})
    two = "The investigation ran through Texas and Florida."
    assert "multi_state" in proc.extract_topics({"case_text": two})


def test_a_conduct_year_in_the_lede_is_not_the_publication_year():
    text = "From 2010 he offended.\n\nMarch 3, 2024\n\nProsecutors announced the plea."
    assert tt.publication_year(text, tt.date_mentions(text), 2024) == 2024


def test_dateline_and_on_date_are_publication():
    dateline = "Hallie, Ky. — May 2, 2019\n\nProsecutors announced a plea."
    roles = {a["value"]: a["role"] for a in tt.temporal_assertions(dateline, [])}
    assert roles.get("2019-05-02") == "publication"

    lead = "On May 14, 2025, the office announced the sentence."
    roles = {a["value"]: a["role"] for a in tt.temporal_assertions(lead, [])}
    assert roles.get("2025-05-14") == "publication"


def test_dc_counts_once_however_often_it_is_named():
    twice = (
        "A man from Washington, D.C. was arrested. "
        "He had lived in Washington, D.C. for years."
    )
    assert "multi_state" not in proc.extract_topics({"case_text": twice})
    dateline = "WASHINGTON, D.C. — A man pleaded guilty in Washington, D.C. federal court."
    assert "multi_state" not in proc.extract_topics({"case_text": dateline})
    two_states = "WASHINGTON — He drove from Texas to Florida to meet the victim."
    assert "multi_state" in proc.extract_topics({"case_text": two_states})
    dc_and_state = "He drove from Washington, D.C. to Maryland."
    assert "multi_state" in proc.extract_topics({"case_text": dc_and_state})
