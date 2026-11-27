"""Claims about one derived trajectory step. They stay in separate fields.

Five things are kept apart and never inferred from one another:

1. ``stated_platform_means``: the platforms the act's coding records it as going through
   (``platform_interactions``). On a machine release this is coder A's attribute on an act both
   coders agreed on; coder B's platform is not compared (``resolve.FIELD_STANDING``). It is not
   the observation layer's stated-means tie (observations ``relations``).
2. Supported availability: the registry documents the capability on that platform and the act's
   cited dates fall inside its period (``*_supported``).
3. Uncertain availability: the registry lists the capability, but the act is undated, the date is
   approximate, or the period is uncertain (``*_uncertain``). This is not established access.
4. ``documented_feature_use``: the act's own sentence states the feature as the means. Only this
   list is O_i (level C).
5. Dependence: whether the offence depended on the capability. Never stated here; it is a
   question for the theory layer, and ``how_used`` (a person's later note) is not it either.

``candidate_capabilities`` and ``available_on_platform`` are the union of 2 and 3, kept for the
counts that already use them; read the split lists before treating any class as available.
``capability_status`` on the step carries each entry's availability and registry ``default_on``.
"""
from __future__ import annotations

from typing import Dict


def candidate_status(claims_: dict) -> str:
    """'supported', 'uncertain' or 'unknown' for a step's registry candidates (one step occurrence).

    'unknown' when the step was derived before availability status was recorded (no split lists):
    a missing status is never read as uncertain. 'none' when the step has no candidate."""
    if not claims_.get("candidate_capabilities"):
        return "none"
    if "candidate_capabilities_supported" not in claims_:
        return "unknown"
    return "supported" if claims_["candidate_capabilities_supported"] else "uncertain"


def claims(step: dict) -> Dict[str, object]:
    """Split one derived step into coded platform interactions, registry availability by status, and documented use."""
    stated = list(step.get("platforms") or [])
    candidates = list(step.get("action_relevant_affordances") or [])
    documented = list(step.get("affordances") or [])
    available = [a for a in (step.get("available_affordances") or []) if a not in candidates]
    status = {}
    for s in step.get("capability_status") or []:      # a class on several platforms is supported if any entry is
        status[s["affordance"]] = "supported" if "supported" in (status.get(s["affordance"]), s["availability"]) else s["availability"]
    by = lambda names, want: [a for a in names if status.get(a) == want]  # noqa: E731
    return {
        "stated_platform_means": stated,
        "candidate_capabilities": candidates,
        "candidate_capabilities_supported": by(candidates, "supported"),
        "candidate_capabilities_uncertain": by(candidates, "uncertain"),
        "available_on_platform": available,
        "available_on_platform_supported": by(available, "supported"),
        "available_on_platform_uncertain": by(available, "uncertain"),
        "documented_feature_use": documented,
        "how_used": None,
    }
