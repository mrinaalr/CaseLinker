"""Label a passage by the role it plays in a filing.

Cheap rules first: a heading, an affiant's training boilerplate, a technology
definition ("Tor is…", a numbered definition). An optional local model is
consulted only when ``CASELINKER_SECTION_MODEL=1`` and the caller passes a
``complete`` callable. Nothing here calls a model on its own.

The label is stored on the passage dict the new preprocessing path uses. It is
not a schema-2.0 field and it is not written into a release bundle.

Technology-explainer and affiant-background passages produce no offender act
and no means when ``CASELINKER_SECTION_FILTER=1``. The filter is off by
default, and with it off this module changes no published output.
"""
from __future__ import annotations

import os
import re
from typing import Callable, Optional

from state_machines.evidence import evidence as E

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
    ("technology_explainer", re.compile(r"^\s*(?:technology|definitions)\b", re.I)),
    ("affiant_background", re.compile(r"^\s*(?:affiant|background and training|training and experience)\b", re.I)),
)
# Content cues outrank a document heading: an explainer pasted under "statement of facts"
# is still an explainer. The cues are specific so a factual sentence does not trip them.
_CONTENT = (
    ("affiant_background", "training_and_experience",
     re.compile(r"\bI know from my training and experience\b|\bbased on my training and experience\b"
                r"|\bI (?:am|have been) (?:a |an )?(?:special agent|task force officer|police officer)\b", re.I)),
    ("technology_explainer", "technology_definition",
     re.compile(r"(?:^|\n)\s*(?:\d+\.\s+|\([a-z]\)\s+|\([ivx]+\)\s+)?"
                r"(?:Tor|A VPN|VPNs|A virtual private network|The Onion Router)\b[^.]*\b(?:is|are|routes|refers to)\b", re.I)),
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


def section_model_enabled() -> bool:
    return os.environ.get("CASELINKER_SECTION_MODEL") == "1"


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


def _from_model(raw) -> dict:
    if isinstance(raw, dict):
        role, confidence = str(raw.get("role", "")), float(raw.get("confidence", 0.6))
    else:
        role, confidence = str(raw).strip(), 0.6
    if role not in ROLES:
        return _pack("unclassified", "model_rejected", 0.0)
    return _pack(role, "local_model", confidence)


def classify(text: str, heading: Optional[str] = None, model: Optional[Callable] = None) -> dict:
    """The passage's role. ``model`` is called only when the model flag is on and no rule matched.

    A blocked-role content cue wins over a document heading, so a technology
    definition filed inside a statement of facts stays a technology explainer.
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
    if opened:
        return _pack(opened, "heading", 0.9)
    if section_model_enabled() and model is not None:
        return _from_model(model(text))
    return _pack("unclassified", "none", 0.0)


def label_passage(passage: dict, text: str, heading: Optional[str] = None, model: Optional[Callable] = None) -> dict:
    """A copy of ``passage`` with the section label stored on it. The input is not mutated."""
    label = classify(text, heading=heading, model=model)
    out = dict(passage)
    out["section_role"] = label["role"]
    out["section_rule"] = label["rule"]
    out["section_confidence"] = label["confidence"]
    return out


def blocks_offender_products(role: str, *, enabled: Optional[bool] = None) -> bool:
    """True when this role must not yield an offender act or a means.

    Off unless ``CASELINKER_SECTION_FILTER=1`` (or ``enabled`` is passed)."""
    if enabled is None:
        enabled = section_filter_enabled()
    return bool(enabled) and role in BLOCKED_ROLES


def passage_products(text: str, *, heading: Optional[str] = None) -> dict:
    """Acts and stated means in one passage, after the section filter.

    Acts come from the frame extractor, which itself stays empty unless
    ``CASELINKER_EXTRACTOR=frame-1.0``. Means come from the current stated-means
    rule. A blocked role yields neither, and the passage label is still returned
    so the passage stays in the record as context.
    """
    from state_machines.coding.frames import extract_frames
    from state_machines.observations.observe import _means, features_in, platforms_in, sentences

    label = classify(text, heading=heading)
    if blocks_offender_products(label["role"]):
        return {"section": label, "acts": [], "means": []}
    digest = E.sha256_text(text)
    acts, means = [], []
    for start, end in sentences(text):
        sentence = text[start:end]
        acts.extend(extract_frames(sentence, page_text=text, sentence_start=start, passage_hash=digest))
        for _cls, phrase, a, b in features_in(sentence):
            hit = _means("feature", sentence, {"feature_term": phrase})
            if hit:
                means.append({"kind": "feature", "term": phrase, "relationship": hit[0], "cue": hit[1],
                              "start": start + a, "end": start + b, "level": "C"})
        for name, a, b in platforms_in(sentence):
            hit = _means("platform", sentence, {"named_as": name})
            if hit:
                means.append({"kind": "platform", "term": name, "relationship": hit[0], "cue": hit[1],
                              "start": start + a, "end": start + b, "level": "stated-platform"})
    return {"section": label, "acts": acts, "means": means}
