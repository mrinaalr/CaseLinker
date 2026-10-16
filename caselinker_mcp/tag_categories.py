"""Resolve plain MCP tag strings into API {tag, category} payloads.

POST /api/return-tagged-cases requires an explicit category. The MCP tools accept
plain strings and must infer categories without silently mapping unknown topic
tags (e.g. sextortion) onto platforms_used.
"""

from __future__ import annotations

from typing import Any, Iterable

# Tag aliases → canonical stored values (API match is case-insensitive for most
# facets; investigation/topic tags are stored lowercase).
_TAG_ALIASES: dict[str, str] = {
    "cybertipline": "cybertip",
    "cyber_tipline": "cybertip",
    "cyber tip": "cybertip",
    "cyber_tip": "cybertip",
    # Stored platform label is "Twitter / X" (API match is case-insensitive).
    "twitter": "twitter / x",
    "twitter/x": "twitter / x",
    "x": "twitter / x",
    "gen ai": "gen ai",
    "genai": "gen ai",
    "chatgpt": "gen ai",
    "aol instant messenger": "aol instant messenger",
    "aim": "aim",
    "playstation network": "playstation network",
    "psn": "psn",
    "xbox live": "xbox live",
    "google drive": "google drive",
    "mega.nz": "mega.nz",
}

# Static non-platform / known-platform map. Live /api/tags fills gaps at runtime.
_TAG_CATEGORIES: dict[str, str] = {
    # case_topics (must stay ahead of any platform fallback)
    "ai_csam": "case_topics",
    "csam": "case_topics",
    "distribution": "case_topics",
    "family": "case_topics",
    "hands_on": "case_topics",
    "international": "case_topics",
    "multi_state": "case_topics",
    "online_only": "case_topics",
    "possession": "case_topics",
    "production": "case_topics",
    "project_safe_childhood": "case_topics",
    "sextortion": "case_topics",
    "stranger": "case_topics",
    "trafficking": "case_topics",
    # severity_indicators
    "grooming": "severity_indicators",
    "infant": "severity_indicators",
    "multiple_perpetrators": "severity_indicators",
    "sexual_abuse": "severity_indicators",
    "under_10": "severity_indicators",
    "under_12": "severity_indicators",
    "very_young": "severity_indicators",
    "rape": "severity_indicators",
    "physical_abuse": "severity_indicators",
    # investigation_type (API category is singular; /api/tags key is plural)
    "proactive": "investigation_type",
    "reactive": "investigation_type",
    "undercover": "investigation_type",
    "cybertip": "investigation_type",
    "cybertipline": "investigation_type",
    "online": "investigation_type",
    "unknown": "investigation_type",
    # perpetrator_status
    "registered_sex_offender": "registered_sex_offender",
    # relationship_to_victim
    "father": "relationship_to_victim",
    "mother": "relationship_to_victim",
    "parent": "relationship_to_victim",
    "brother": "relationship_to_victim",
    "sister": "relationship_to_victim",
    "sibling": "relationship_to_victim",
    "uncle": "relationship_to_victim",
    "aunt": "relationship_to_victim",
    "cousin": "relationship_to_victim",
    "teacher": "relationship_to_victim",
    "coach": "relationship_to_victim",
    "neighbor": "relationship_to_victim",
    "babysitter": "relationship_to_victim",
    "stepfather": "relationship_to_victim",
    "stepmother": "relationship_to_victim",
    # common platforms (examples; live map + PLATFORM_LIKE cover the rest)
    "facebook": "platforms_used",
    "discord": "platforms_used",
    "kik": "platforms_used",
    "telegram": "platforms_used",
    "roblox": "platforms_used",
    "snapchat": "platforms_used",
    "instagram": "platforms_used",
    "tiktok": "platforms_used",
    "twitter": "platforms_used",
    "twitter / x": "platforms_used",
    "skype": "platforms_used",
    "omegle": "platforms_used",
    "minecraft": "platforms_used",
    "tor": "platforms_used",
    "dark_web": "platforms_used",
    "dropbox": "platforms_used",
    "youtube": "platforms_used",
    "twitch": "platforms_used",
    "whatsapp": "platforms_used",
    "reddit": "platforms_used",
    "grindr": "platforms_used",
    "steam": "platforms_used",
    "gen ai": "platforms_used",
}

_PLATFORM_LIKE = {
    "facebook",
    "discord",
    "kik",
    "telegram",
    "roblox",
    "snapchat",
    "instagram",
    "tiktok",
    "twitter",
    "twitter / x",
    "skype",
    "omegle",
    "minecraft",
    "tor",
    "dark_web",
    "dropbox",
    "youtube",
    "twitch",
    "mewe",
    "fortnite",
    "xbox",
    "xbox live",
    "psn",
    "playstation network",
    "irc",
    "aim",
    "aol instant messenger",
    "myspace",
    "craigslist",
    "mega",
    "mega.nz",
    "onedrive",
    "googledrive",
    "google drive",
    "limewire",
    "bittorrent",
    "kazaa",
    "whatsapp",
    "reddit",
    "grindr",
    "steam",
    "tumblr",
    "whisper",
    "wickr",
    "yubo",
    "skout",
    "imvu",
    "monkey",
    "oculus",
    "icloud",
    "cash app",
    "chat avenue",
    "chatroulette",
    "call of duty",
    "cs:go",
    "facebook messenger",
    "gen ai",
    "stable diffusion",
    "yahoo chat",
    "webcam platform",
    "wizard 101",
    "chat",
    "internet",
    "social media",
    "online",  # also investigation_type — static map wins first
}

# /api/tags response key → return-tagged-cases category
_API_TAGS_CATEGORY: dict[str, str] = {
    "case_topics": "case_topics",
    "severity_indicators": "severity_indicators",
    "platforms_used": "platforms_used",
    "investigation_types": "investigation_type",
    "relationships": "relationship_to_victim",
    "status": "registered_sex_offender",
}

_VALID_CATEGORIES = (
    "case_topics",
    "severity_indicators",
    "platforms_used",
    "investigation_type",
    "relationship_to_victim",
    "registered_sex_offender",
    "organizations",
)

# Populated from GET /api/tags (lowercase tag → category). Static map still wins.
_live_tag_categories: dict[str, str] = {}


class UnknownTagError(ValueError):
    """Raised when a tag cannot be resolved to an API category."""

    def __init__(self, unknown: list[str], *, hint: str | None = None):
        self.unknown = unknown
        self.hint = hint or (
            "Call get_unique_tags() for valid values, or pass only known tags. "
            f"Categories: {', '.join(_VALID_CATEGORIES)}."
        )
        super().__init__(
            f"Unknown tag(s) with no category: {', '.join(unknown)}. {self.hint}"
        )


def normalize_tag(tag: str) -> str:
    key = tag.strip().lower()
    return _TAG_ALIASES.get(key, key)


def ingest_unique_tags(payload: dict[str, Any] | None) -> dict[str, str]:
    """Build/replace the live tag→category map from GET /api/tags (or get_unique_tags).

    Priority order keeps topics/severity/investigation ahead of platforms when a
    label could appear in more than one facet (e.g. ``online``, ``stranger``).
    """
    global _live_tag_categories
    live: dict[str, str] = {}
    if not isinstance(payload, dict):
        _live_tag_categories = live
        return live

    priority = (
        "case_topics",
        "severity_indicators",
        "investigation_types",
        "relationships",
        "status",
        "platforms_used",
    )
    for api_key in priority:
        category = _API_TAGS_CATEGORY[api_key]
        values = payload.get(api_key) or []
        if not isinstance(values, list):
            continue
        for raw in values:
            if raw is None:
                continue
            key = normalize_tag(str(raw))
            if not key or key in live:
                continue
            live[key] = category

    _live_tag_categories = live
    return live


def clear_live_tag_categories() -> None:
    """Test helper: drop the live cache."""
    global _live_tag_categories
    _live_tag_categories = {}


def live_tag_categories() -> dict[str, str]:
    return dict(_live_tag_categories)


def infer_tag_category(tag: str, *, live: dict[str, str] | None = None) -> str:
    """Return API category for a tag, or raise UnknownTagError."""
    key = normalize_tag(tag)
    if not key:
        raise UnknownTagError([tag], hint="Empty tag.")

    if key in _TAG_CATEGORIES:
        return _TAG_CATEGORIES[key]
    if key in _PLATFORM_LIKE:
        return "platforms_used"

    cache = live if live is not None else _live_tag_categories
    if key in cache:
        return cache[key]

    # Underscore / space variants against live + platform-like
    alt = key.replace("_", " ")
    if alt != key:
        if alt in _TAG_CATEGORIES:
            return _TAG_CATEGORIES[alt]
        if alt in _PLATFORM_LIKE:
            return "platforms_used"
        if alt in cache:
            return cache[alt]
    alt2 = key.replace(" ", "_")
    if alt2 != key:
        if alt2 in _TAG_CATEGORIES:
            return _TAG_CATEGORIES[alt2]
        if alt2 in cache:
            return cache[alt2]

    raise UnknownTagError([tag])


def resolve_tags(
    tags: Iterable[str],
    *,
    live: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    """Convert plain tag strings to API payload entries.

    Raises UnknownTagError if any tag cannot be categorized (fail closed —
    never default unknowns to platforms_used).
    """
    unknown: list[str] = []
    resolved: list[dict[str, str]] = []
    for raw in tags:
        if raw is None:
            continue
        text = str(raw).strip()
        if not text:
            continue
        try:
            category = infer_tag_category(text, live=live)
            resolved.append({"tag": normalize_tag(text), "category": category})
        except UnknownTagError:
            unknown.append(text)
    if unknown:
        raise UnknownTagError(unknown)
    return resolved


def unknown_tag_error_payload(exc: UnknownTagError) -> dict[str, Any]:
    return {
        "error": str(exc),
        "unknown_tags": list(exc.unknown),
        "hint": exc.hint,
        "cases": [],
        "count": 0,
        "resolved_tags": [],
    }
