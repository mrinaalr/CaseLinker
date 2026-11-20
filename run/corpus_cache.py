"""Corpus identity for caches that must not survive a case-id change.

Phase 4 kept the case count at 10,802 while the ids changed. A cache keyed only
on that count served the previous corpus. The fingerprint is a hash of the
sorted ids. A stored payload is current only when every case id it cites is
still in the corpus, and a group that claims to cover the whole corpus names
exactly those ids.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable, Set

_CASE_ID = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*_\d{4}_\d{3,4}$")

# Stored sentinels. A coverage chart that counts these is counting "not stated".
_UNSTATED = frozenset({"", "unknown", "null", "none", "n/a", "na", "unspecified"})


def corpus_fingerprint(ids: Iterable[str]) -> str:
    clean = sorted({i for i in ids if i})
    return hashlib.sha256("\n".join(clean).encode()).hexdigest()[:16]


def cited_case_ids(obj: Any, out: Set[str] | None = None) -> Set[str]:
    if out is None:
        out = set()
    if isinstance(obj, dict):
        for value in obj.values():
            cited_case_ids(value, out)
    elif isinstance(obj, list):
        for value in obj:
            cited_case_ids(value, out)
    elif isinstance(obj, str) and _CASE_ID.match(obj):
        out.add(obj)
    return out


def payload_matches_corpus(payload: Any, ids: Iterable[str]) -> bool:
    """True when a cluster or analysis payload belongs to this id set."""
    current = set(ids)
    if not current:
        return False
    cited = cited_case_ids(payload)
    if not cited or not cited <= current:
        return False
    for group in _groups(payload):
        members = group.get("cases") or group.get("case_ids")
        if not isinstance(members, list) or not members:
            continue
        if not all(isinstance(item, str) for item in members):
            continue
        member_ids = set(members)
        if not member_ids <= current:
            return False
        size = group.get("size") if isinstance(group.get("size"), int) else group.get("n")
        if isinstance(size, int) and size == len(current) and member_ids != current:
            return False
    return True


def _groups(payload: Any) -> list:
    if isinstance(payload, list):
        return [g for g in payload if isinstance(g, dict)]
    if not isinstance(payload, dict):
        return []
    found = []
    for key in ("case_groups", "groups"):
        raw = payload.get(key)
        if isinstance(raw, list):
            found.extend(g for g in raw if isinstance(g, dict))
    analysis = payload.get("analysis")
    if isinstance(analysis, dict):
        raw = analysis.get("case_groups") or analysis.get("groups") or []
        if isinstance(raw, list):
            found.extend(g for g in raw if isinstance(g, dict))
    return found


def is_stated(value: Any) -> bool:
    """A stored field counts as filled only when it says something other than unknown."""
    if value is None or isinstance(value, bool):
        return bool(value) if isinstance(value, bool) else False
    if isinstance(value, str):
        return value.strip().lower() not in _UNSTATED
    return bool(value)
