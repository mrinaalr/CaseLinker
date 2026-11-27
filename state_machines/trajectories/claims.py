"""Three claims about one derived trajectory step. They stay in separate fields.

``stated_platform_means`` holds the platforms the act's coding records it as going through
(``platform_interactions``, from coder A's coding of an act both coders agreed on; coder B's
platform is not compared). It is not the observation layer's stated-means tie (observations
``relations``), and it does not say which of that platform's capabilities the offender used. The registry can say what the platform
offered. Only a sentence that states the feature as the means is documented use,
and only that list is O_i.

``how_used`` is left empty. A person may later write how the capability was used
in the act. The machine never fills it, and the note is not an affordance class.
"""
from __future__ import annotations

from typing import Dict


def claims(step: dict) -> Dict[str, object]:
    """Split one derived step into coded platform interactions, registry candidates, and documented use."""
    stated = list(step.get("platforms") or [])
    candidates = list(step.get("action_relevant_affordances") or [])
    documented = list(step.get("affordances") or [])
    available = [a for a in (step.get("available_affordances") or []) if a not in candidates]
    return {
        "stated_platform_means": stated,
        "candidate_capabilities": candidates,
        "available_on_platform": available,
        "documented_feature_use": documented,
        "how_used": None,
    }
