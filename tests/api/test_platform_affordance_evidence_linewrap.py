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


def _promoted(text: str, platforms):
    published = pe.process_case("synthetic_2024_004", platforms, text)["records"]
    return {r["platform"]: r["stated_vs_inferred"] for r in published}, \
        pe.linewrap_tiers("synthetic_2024_004", platforms, text, published)


def test_news_attribution_to_an_agency_post_cannot_earn_a_promotion():
    for text in (
        "Synthetic Man Arrested\n\nIn a Facebook post, the sheriff's office said\n"
        "the man was arrested for possessing child sexual abuse material.\n",
        "Synthetic Man Arrested\n\nOfficers found images, according to a Facebook post from the\n"
        "police department, and the man was arrested for possessing child sexual abuse material.\n",
        "Synthetic Man Arrested\n\nThe tips came from a national center, the sheriff's office said on Facebook\n"
        "after the man was arrested for possessing child sexual abuse material.\n",
    ):
        base, lw = _promoted(text, ["Facebook"])
        repaired = pe.process_case("s", ["Facebook"], pe.repair_line_wraps(text))["records"][0]["stated_vs_inferred"]
        assert base["Facebook"] == "named_only" and repaired != "named_only", text  # a promotion was on offer
        assert lw["Facebook"] == "named_only", text


def test_reporting_duty_statement_is_boilerplate_for_the_companies_it_lists():
    s = ("Through different companies google, Facebook, Instagram who are required by law to report any "
         "concerning activity or illegal contraband they find on their servers, a sergeant said.")
    assert pe.boilerplate_names_platform(s, "Facebook")
    assert pe.boilerplate_names_platform(s, "Instagram")
    assert not pe.boilerplate_names_platform(
        "Facebook reported the account, and the man was charged with sending images to a child on Instagram.",
        "Instagram")


def test_agency_post_refuses_only_the_platform_it_names():
    text = ("Synthetic Man Arrested\n\nIn a Facebook post, the sheriff's office said they got a tip about criminal "
            "activity on Kik,\nand after conducting a search warrant, investigators arrested the man for distributing "
            "child sexual abuse material.\n")
    base, lw = _promoted(text, ["Facebook", "Kik"])
    assert base == {"Facebook": "named_only", "Kik": "named_only"}
    assert lw == {"Facebook": "named_only", "Kik": "stated"}


def test_footer_link_list_refuses_every_platform_it_lists():
    assert pe.boilerplate_names_platform("Troop F Headquarters Facebook X (formerly Twitter) YouTube", "YouTube")
    assert not pe.boilerplate_names_platform("He shared the videos on YouTube, the police department said.", "YouTube")
