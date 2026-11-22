"""Label a passage by the role it plays in a filing.

Cheap rules first: a real heading, an affiant's training boilerplate, a technology
definition ("Tor is a…", a numbered definition). A sentence that merely starts
with those words is not a heading. Nothing here calls a model.

The label is stored on the passage dict the new preprocessing path uses. It is
not a schema-2.0 field and it is not written into a release bundle.

A technology-explainer or affiant-background sentence produces no offender act
and no means when ``CASELINKER_SECTION_FILTER=1``. Another sentence on the
same page still can. The filter is off by default, and with it off this module
changes no published output.
"""
from __future__ import annotations

import os
import re
from typing import Optional

ROLES = (
    "statement_of_offense",
    "factual_basis",
    "plea_admissions",
    "charging_allegations",
    "affiant_background",
    "technology_explainer",
    "legal_standard",
    "sentencing_argument",
)
# These two describe the technology or the affiant, not the offender's conduct.
BLOCKED_ROLES = frozenset({"technology_explainer", "affiant_background"})

_HEADING = (
    ("statement_of_offense", re.compile(r"^\s*statement of offense\b", re.I)),
    ("factual_basis", re.compile(r"^\s*(?:factual basis|factual proffer|statement of facts|stipulation of facts)\b", re.I)),
    ("plea_admissions", re.compile(r"^\s*plea (?:agreement|admissions?)\b", re.I)),
    ("charging_allegations", re.compile(r"^\s*(?:indictment|criminal complaint|information|the grand jury charges)\b", re.I)),
    ("sentencing_argument", re.compile(r"^\s*sentencing\b", re.I)),
    ("legal_standard", re.compile(r"^\s*(?:legal standard|applicable law)\b", re.I)),
    ("technology_explainer", re.compile(r"^\s*(?:technology|definitions)\s*\.?\s*$", re.I)),
    ("affiant_background", re.compile(r"^\s*(?:affiant|background and training|training and experience)\s*\.?\s*$", re.I)),
)
# Content cues outrank a document heading: an explainer pasted under "statement of facts"
# is still an explainer. The cues are specific so a factual sentence does not trip them.
_CONTENT = (
    ("affiant_background", "training_and_experience",
     re.compile(r"\bI know from my training and experience\b|\bbased on my training and experience\b"
                r"|\bI (?:am|have been) (?:a |an )?(?:special agent|task force officer|police officer)\b", re.I)),
    ("technology_explainer", "technology_definition",
     re.compile(r"(?:^|\n)\s*(?:\d+\.\s+|\([a-z]\)\s+|\([ivx]+\)\s+)?"
                r"(?:Tor|A VPN|VPNs|A virtual private network|The Onion Router)\b[^.]*\b(?:is an?|are|routes|refers to)\b", re.I)),
    ("technology_explainer", "routes_packets", re.compile(r"\b(?:Tor|VPN) routes packets\b", re.I)),
    ("legal_standard", "legal_standard",
     re.compile(r"\bprobable cause to believe\b|\belements of the offense\b|\bthe government must prove\b|\bas a matter of law\b", re.I)),
    ("sentencing_argument", "sentencing_argument",
     re.compile(r"\bthe court should impose\b|\bguideline range\b|\b3553\(a\)\b", re.I)),
    ("plea_admissions", "plea_admission",
     re.compile(r"\bthe defendant admits\b|\bthe defendant pleads guilty\b|\bI plead guilty\b", re.I)),
    ("charging_allegations", "charging_language",
     re.compile(r"\bthe defendant did knowingly\b|\bthe grand jury charges\b", re.I)),
)


def section_filter_enabled() -> bool:
    return os.environ.get("CASELINKER_SECTION_FILTER") == "1"


def _is_heading(text: str) -> bool:
    """A heading line, not a sentence that happens to start with a heading word."""
    stripped = (text or "").strip()
    if not stripped or len(stripped) > 80 or re.search(r"[.!?]", stripped):
        return False
    return True


def _pack(role: str, rule: str, confidence: float) -> dict:
    return {"role": role, "rule": rule, "confidence": confidence}


def _heading_role(text: str) -> Optional[str]:
    for role, pat in _HEADING:
        if pat.search(text or ""):
            return role
    return None


def _content_hit(text: str) -> Optional[tuple]:
    for role, rule, pat in _CONTENT:
        if pat.search(text or ""):
            return role, rule
    return None


def classify(text: str, heading: Optional[str] = None) -> dict:
    """The passage's role.

    Heading rules apply to a heading argument or to a heading line, not to a
    sentence. A blocked-role content cue still wins over a document heading, so
    a technology definition filed inside a statement of facts stays an explainer.
    """
    content = _content_hit(text)
    if content and content[0] in BLOCKED_ROLES:
        return _pack(content[0], content[1], 0.9)
    headed = _heading_role(heading) if heading else None
    if headed:
        return _pack(headed, "heading", 0.9)
    if content:
        return _pack(content[0], content[1], 0.9)
    opened = _heading_role(text)
    # A document heading may open a longer passage. The short blocked headings
    # match only when the line is the heading itself.
    if opened and (opened not in BLOCKED_ROLES or _is_heading(text)):
        return _pack(opened, "heading", 0.9)
    return _pack("unclassified", "none", 0.0)


def blocks_offender_products(role: str, *, enabled: Optional[bool] = None) -> bool:
    """True when this role must not yield an offender act or a means.

    Off unless ``CASELINKER_SECTION_FILTER=1`` (or ``enabled`` is passed)."""
    if enabled is None:
        enabled = section_filter_enabled()
    return bool(enabled) and role in BLOCKED_ROLES


