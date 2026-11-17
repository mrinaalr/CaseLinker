"""Line-wrap repair for Q1 evidence tiers (Decision 1). Synthetic text only."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "q1_builder", ROOT / "ontology" / "platform_affordance_evidence" / "platform_affordance_evidence.py")
pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pe)

WRAPPED = (
    "Synthetic Man Sentenced\n\n"
    "According to court documents, the defendant communicated with a 15-year-old\n"
    "girl via Discord and requested explicit images.\n\n"
    "The case was investigated by the synthetic county sheriff."
)


def test_mid_sentence_wraps_join_and_paragraphs_stay():
    out = pe.repair_line_wraps(WRAPPED)
    assert "15-year-old girl via Discord" in out
    assert "Synthetic Man Sentenced\n\nAccording" in out
    assert "images.\n\nThe case" in out


def test_sentence_final_and_colon_breaks_stay():
    text = "He was charged.\nShe was not.\nDefendant:\nAge 40"
    assert pe.repair_line_wraps(text) == text


def test_wrapped_sentence_is_named_only_before_and_stated_after():
    rec_raw = pe.process_case("synthetic_2024_001", ["Discord"], WRAPPED)["records"][0]
    rec_fix = pe.process_case("synthetic_2024_001", ["Discord"], pe.repair_line_wraps(WRAPPED))["records"][0]
    assert rec_raw["stated_vs_inferred"] == "named_only"
    assert rec_fix["stated_vs_inferred"] == "stated"


def test_repair_is_idempotent():
    once = pe.repair_line_wraps(WRAPPED)
    assert pe.repair_line_wraps(once) == once


def test_published_tier_rules_version_unchanged():
    assert pe.TIER_RULES_VERSION == "tiers-1"


def test_linewrap_tier_is_additive(monkeypatch):
    """If the repaired text scores lower (joined lines can trip the comma-list heuristic),
    the line-wrap tier keeps the published tier."""
    published = [{"platform": "Dropbox", "stated_vs_inferred": "stated"},
                 {"platform": "Kik", "stated_vs_inferred": "named_only"}]
    monkeypatch.setattr(pe, "process_case", lambda cid, plats, text: {"records": [
        {"platform": "Dropbox", "stated_vs_inferred": "named_only"},
        {"platform": "Kik", "stated_vs_inferred": "inferred"}]})
    lw = pe.linewrap_tiers("synthetic_2024_002", ["Dropbox", "Kik"], "text", published)
    assert lw == {"Dropbox": "stated", "Kik": "inferred"}


def test_linewrap_tier_recovers_wrapped_use():
    published = pe.process_case("synthetic_2024_001", ["Discord"], WRAPPED)["records"]
    assert pe.linewrap_tiers("synthetic_2024_001", ["Discord"], WRAPPED, published)["Discord"] == "stated"


def test_agency_social_boilerplate_cannot_earn_a_promotion():
    text = ("Synthetic Man Arrested\n\n"
            "The man was arrested for possession of child sexual abuse material, the sheriff's office\n"
            "posted on its Facebook page.\n")
    published = pe.process_case("synthetic_2024_003", ["Facebook"], text)["records"]
    assert published[0]["stated_vs_inferred"] == "named_only"
    assert pe.linewrap_tiers("synthetic_2024_003", ["Facebook"], text, published)["Facebook"] == "named_only"
    for footer in ("Troop F Headquarters Facebook X (formerly Twitter) YouTube",
                   "Source: facebook.com/somecounty/posts/123", "Mugshots are available on the Attorney General's Twitter page"):
        assert pe.AGENCY_SOCIAL_BOILERPLATE.search(footer), footer
    assert not pe.AGENCY_SOCIAL_BOILERPLATE.search("He messaged the girl on Facebook and asked for photos.")
