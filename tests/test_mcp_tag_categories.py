"""MCP tag category resolver — fail closed for unknown topics (#22)."""

from __future__ import annotations

import pytest

from caselinker_mcp.tag_categories import (
    UnknownTagError,
    clear_live_tag_categories,
    infer_tag_category,
    ingest_unique_tags,
    normalize_tag,
    resolve_tags,
    unknown_tag_error_payload,
)


@pytest.fixture(autouse=True)
def _reset_live_cache():
    clear_live_tag_categories()
    yield
    clear_live_tag_categories()


def test_sextortion_is_case_topic_not_platform():
    assert infer_tag_category("sextortion") == "case_topics"
    assert infer_tag_category("Sextortion") == "case_topics"


def test_missing_topics_resolve_as_case_topics():
    for tag in (
        "distribution",
        "trafficking",
        "ai_csam",
        "project_safe_childhood",
    ):
        assert infer_tag_category(tag) == "case_topics"


def test_cybertipline_aliases_to_cybertip():
    assert normalize_tag("cybertipline") == "cybertip"
    assert normalize_tag("CyberTipline") == "cybertip"
    payload = resolve_tags(["cybertipline", "snapchat"])
    assert payload == [
        {"tag": "cybertip", "category": "investigation_type"},
        {"tag": "snapchat", "category": "platforms_used"},
    ]


def test_unknown_tag_fails_closed():
    with pytest.raises(UnknownTagError) as exc:
        resolve_tags(["sextortion", "not_a_real_tag_xyz"])
    assert "not_a_real_tag_xyz" in exc.value.unknown
    err = unknown_tag_error_payload(exc.value)
    assert err["cases"] == []
    assert err["count"] == 0
    assert "not_a_real_tag_xyz" in err["unknown_tags"]


def test_sextortion_snapchat_payload():
    assert resolve_tags(["sextortion", "snapchat"]) == [
        {"tag": "sextortion", "category": "case_topics"},
        {"tag": "snapchat", "category": "platforms_used"},
    ]


def test_live_tags_fill_platform_gaps():
    ingest_unique_tags(
        {
            "case_topics": ["sextortion"],
            "platforms_used": ["WhatsApp", "Wizard 101"],
            "investigation_types": ["cybertip"],
            "severity_indicators": [],
            "relationships": [],
            "status": [],
        }
    )
    assert infer_tag_category("whatsapp") == "platforms_used"
    assert infer_tag_category("wizard 101") == "platforms_used"


def test_live_priority_keeps_online_as_investigation():
    ingest_unique_tags(
        {
            "case_topics": [],
            "severity_indicators": [],
            "investigation_types": ["online"],
            "relationships": [],
            "status": [],
            "platforms_used": ["online"],
        }
    )
    # Static map already prefers investigation_type; live must not flip it.
    assert infer_tag_category("online") == "investigation_type"


def test_severity_and_relationship_static():
    assert infer_tag_category("grooming") == "severity_indicators"
    assert infer_tag_category("sexual_abuse") == "severity_indicators"
    assert infer_tag_category("father") == "relationship_to_victim"


def test_twitter_aliases_to_stored_label():
    """Stored platform is 'Twitter / X'; bare 'twitter' must not query as 'twitter'."""
    assert normalize_tag("twitter") == "twitter / x"
    assert resolve_tags(["twitter"]) == [
        {"tag": "twitter / x", "category": "platforms_used"}
    ]
