"""Labels that name a kind of platform, not an app.

``online``, ``internet``, ``social media`` and ``chat`` stay in ``platforms_used``
and on the affordance map. They are not named platforms: analysis rankings,
event channels, and SPARQL for apps leave them out.
"""

from __future__ import annotations

GENERIC_PLATFORM_TAGS = frozenset({"online", "internet", "social media", "chat"})


def is_generic_platform_tag(label: object) -> bool:
    return isinstance(label, str) and label.strip().lower() in GENERIC_PLATFORM_TAGS
