"""Case dates with the fixed temporal tagger (``temporal_tags`` 1.1.0).

Publication year is the primary timeline and is labelled as such. Typed event
dates (offense / investigation / arrest / prosecution) are reported only for
coverage: most releases do not date the offense.
"""
from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from functools import lru_cache
from typing import Any, Dict

from .snapshot import REPO

_PL = REPO / "src" / "Processing Layer"


@lru_cache(maxsize=1)
def tagger():
    for p in (_PL / "field_assertions", _PL):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    spec = importlib.util.spec_from_file_location(
        "afh_temporal_tags", _PL / "Pattern Processing Layer" / "temporal_tags.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def case_dates(text: str, pub_year) -> Dict[str, Any]:
    tt = tagger()
    roles: Counter = Counter()
    first: Dict[str, int] = {}
    for a in tt.temporal_assertions(text, [], pub_year):
        if a["field"] != "date":
            continue
        role = a["role"]
        if role == "event":
            role = f"event:{a['extras'].get('event_kind', 'unknown')}"
        roles[role] += 1
        y = int(str(a["value"])[:4])
        if pub_year is None or y <= pub_year:
            first[role] = min(first.get(role, y), y)
    return {"roles": dict(roles), "first_year": first, "version": tt.TEMPORAL_VERSION}
