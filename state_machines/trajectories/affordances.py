"""Affordance levels A and B for documented events, read from the shared capability registry.

Level A (available) is platform-level knowledge: the platform provided a capability in a
period, according to cited public sources. It never says the capability was used.
Level B (action-relevant) is derived per event: the act went through (or moved to) a
platform, the capability was available at the event's time, and its class is relevant to
that kind of action (``vocab.ACTION_RELEVANCE``). Level C (instrumental) is coded from the
court record and is the only level that enters O_i; nothing here changes it.

One registry for CaseLinker: the dated capability sources of the AfH Q1 work
(``research/afh_q1/config/capability_sources/*.yaml``, PR #95), or the files named by
``CASELINKER_CAPABILITY_SOURCES``. When none is present, levels A and B are empty.

Availability at an event (I4):
  supported    native, documented introduction date, and the event lies wholly inside
               the capability's known period
  uncertain    native or partial, but an approximate or unknown date, an undated event,
               or an event that overlaps the period boundary
  unsupported  not native, or the event lies wholly outside the period
An approximate introduction date never becomes supported availability.

Every output is event-level (``level_unit = "event"``). Case-level registry associations
(Q1) are never promoted to event-level claims.
"""
from __future__ import annotations

import calendar
import os
import re
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from state_machines.evidence import vocab as V

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCES = REPO_ROOT / "research" / "afh_q1" / "config" / "capability_sources"
LEVEL_UNIT = "event"


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip()


def _period_bound(value, end: bool) -> Optional[date]:
    """'2010', '2010-10', '2010-10-19' (or an int year) as the first or last day it covers."""
    if value in (None, "", "null"):
        return None
    m = re.match(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", str(value))
    if not m:
        return None
    y, mo, d = int(m.group(1)), m.group(2), m.group(3)
    if d:
        return date(y, int(mo), int(d))
    if mo:
        return date(y, int(mo), calendar.monthrange(y, int(mo))[1] if end else 1)
    return date(y, 12, 31) if end else date(y, 1, 1)


def load(paths: Optional[Iterable[Path]] = None) -> dict:
    """{normalized platform name: {"name", "capabilities": {class: entry}}} from registry YAML."""
    import yaml

    if paths is None:
        env = os.environ.get("CASELINKER_CAPABILITY_SOURCES")
        paths = [Path(p) for p in env.split(os.pathsep)] if env else sorted(DEFAULT_SOURCES.glob("*.yaml"))
    platforms: Dict[str, dict] = {}
    for path in paths:
        if not Path(path).is_file():
            continue
        doc = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        for name, entry in (doc.get("platforms") or {}).items():
            platforms[_norm(name)] = {"name": name, "capabilities": {
                cls: cap for cls, cap in (entry.get("capabilities") or {}).items() if cls in V.AFFORDANCE_CLASSES}}
    return {"platforms": platforms}


class Registry:
    def __init__(self, data: dict):
        self.data = data

    def platform(self, key: str) -> Optional[dict]:
        if key.startswith("unnamed:"):
            return None
        return self.data["platforms"].get(_norm(key))

    def availability(self, cap: dict, spans: List[Tuple[date, date]]) -> str:
        native = str(cap.get("native", "")).lower()
        if native in ("no", "false"):
            return "unsupported"
        lo, hi = _period_bound(cap.get("first_available"), False), _period_bound(cap.get("ended"), True)
        if spans:
            e_lo, e_hi = min(s for s, _ in spans), max(e for _, e in spans)
            if (lo and e_hi < lo) or (hi and e_lo > hi):
                return "unsupported"
        documented = str(cap.get("confidence", "")).lower() == "documented"
        if not (native in ("yes", "true") and documented and lo and spans):
            return "uncertain"
        lo_known = _period_bound(cap.get("first_available"), True)   # the latest the feature could have arrived
        inside = lo_known <= min(s for s, _ in spans) and (hi is None or max(e for _, e in spans) <= _period_bound(cap.get("ended"), False))
        return "supported" if inside else "uncertain"


def event_levels(event: dict, registry: Registry, admissible: Tuple[str, ...]) -> Dict[str, list]:
    """Levels A and B for one event. C is read from the coded annotations, never from here."""
    from state_machines.trajectories.derive import event_spans

    spans = event_spans(event, admissible)
    relevance = set(V.ACTION_RELEVANCE.get(event["action"], ()))
    available, relevant, unmatched = [], [], []
    for inter in event.get("platform_interactions", []):
        if inter["status"] not in admissible or inter["mode"] not in V.LEVEL_B_MODES:
            continue
        plat = registry.platform(inter["platform_key"])
        if plat is None:
            unmatched.append(inter["platform_key"])
            continue
        coded = {c["feature_term"]: c["setting"] for c in inter.get("configuration", [])}
        for cls, cap in sorted(plat["capabilities"].items()):
            status = registry.availability(cap, spans)
            if status == "unsupported":
                continue
            entry = {"affordance": cls, "platform": plat["name"], "availability": status,
                     "default_on": cap.get("default_on"), "coded_configuration": coded, "level_unit": LEVEL_UNIT}
            available.append(entry)
            if cls in relevance:
                relevant.append(entry)
    return {"available": available, "action_relevant": relevant, "unmatched_platforms": sorted(set(unmatched))}
