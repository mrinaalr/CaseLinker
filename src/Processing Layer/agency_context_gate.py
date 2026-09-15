"""
Agency context gate — program-context DOJ/AG mentions vs case-level involvement.

Mirrors victim_age_gate.py: post-merge filter with keep / reject / relabel / review
and audit log under ml_features.agency_context_gate.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# ── Program-context boilerplate (federal DOJ / ICAC funding copy) ─────────────

_ICAC_MISSION_DOJ_RE = re.compile(
    r"mission\s+of\s+(?:the\s+)?icac\s+task\s+force"
    r".{0,220}?"
    r"(?:united\s+states\s+)?department\s+of\s+justice"
    r".{0,160}?"
    r"(?:administrat(?:ed|ing)|administer(?:ed|ing))\s+by",
    re.IGNORECASE | re.DOTALL,
)

_GRANT_DOJ_ICAC_RE = re.compile(
    r"grant\s+from\s+(?:the\s+)?(?:u\.s\.|united\s+states\s+)?\s*department\s+of\s+justice"
    r".{0,200}?"
    r"(?:runs?|operates?|administers?|oversees?)\s+(?:the\s+)?"
    r"(?:\w+\s+){0,6}?"
    r"(?:icac|internet\s+crimes\s+against\s+children)",
    re.IGNORECASE | re.DOTALL,
)

_GRANT_DOJ_ADMINISTERS_ICAC_RE = re.compile(
    r"(?:grant|funding)\s+from\s+(?:the\s+)?(?:u\.s\.|united\s+states\s+)?department\s+of\s+justice"
    r".{0,200}?"
    r"administers?\s+(?:the\s+)?"
    r"(?:\w+\s+){0,8}?"
    r"(?:icac|internet\s+crimes\s+against\s+children)",
    re.IGNORECASE | re.DOTALL,
)

_FUNDING_US_DOJ_RE = re.compile(
    r"funding\s+from\s+(?:the\s+)?(?:u\.s\.|united\s+states\s+)?department\s+of\s+justice\b",
    re.IGNORECASE,
)

_AG_GRANT_DOJ_RE = re.compile(
    r"attorney\s+general"
    r".{0,80}?"
    r"grant\s+from\s+(?:the\s+)?(?:u\.s\.|united\s+states\s+)?\s*department\s+of\s+justice",
    re.IGNORECASE | re.DOTALL,
)

# Illinois AG ICAC funding copy (PDF line breaks split "U.S." from "Department of Justice").
# Doc-level only; never applied on DOJ ARCHIVES / DOJ CEOS (first-party federal press).
_ILLINOIS_AG_GRANT_ICAC_DOC_RE = re.compile(
    r"(?:\braoul\b|\bmadigan\b|(?:raoul|madigan)['\u2019]?s?\s+office)"
    r".{0,200}?"
    r"grant\s+from\s+(?:the\s+)?"
    r"(?:u\.s\.|united\s+states\s+)?\s*"
    r"department\s+of\s+justice"
    r".{0,240}?"
    r"(?:runs?|operates?|administers?|oversees?)\s+"
    r"(?:the\s+)?(?:illinois\s+)?(?:internet\s+crimes\s+against\s+children|icac)",
    re.IGNORECASE | re.DOTALL,
)

# NCMEC syndicated PSC initiative boilerplate (not case-level federal prosecution on DOJ feeds).
_PSC_INITIATIVE_DOJ_DOC_RE = re.compile(
    r"project\s+safe\s+childhood"
    r".{0,300}?"
    r"(?:nationwide\s+initiative|growing\s+epidemic|launched\s+in\s+\w+\s+\d{4}\s+by)"
    r".{0,220}?"
    r"(?:u\.s\.|united\s+states\s+)?\s*department\s+of\s+justice"
    r"|"
    r"(?:this\s+)?case\s+was\s+(?:brought|prosecuted)\s+as\s+part\s+of\s+"
    r"project\s+safe\s+childhood"
    r".{0,220}?"
    r"nationwide\s+initiative",
    re.IGNORECASE | re.DOTALL,
)

_BOILERPLATE_RES = (
    _ICAC_MISSION_DOJ_RE,
    _GRANT_DOJ_ICAC_RE,
    _GRANT_DOJ_ADMINISTERS_ICAC_RE,
    _FUNDING_US_DOJ_RE,
    _AG_GRANT_DOJ_RE,
    _ILLINOIS_AG_GRANT_ICAC_DOC_RE,
    _PSC_INITIATIVE_DOJ_DOC_RE,
)

# ── Case-action context (keep federal DOJ / AG as involved) ─────────────────

# Strong signals (same sentence as DOJ/AG anchor required to override boilerplate).
_STRONG_CASE_ACTION_RE = re.compile(
    r"\b(?:"
    r"u\.s\.\s+attorneys?(?:\s*['\u2019]s)?(?:\s+office)?|"
    r"united\s+states\s+attorneys?(?:\s*['\u2019]s)?(?:\s+office)?|"
    r"indicted|prosecuted|convicted|sentenced|pleaded\s+guilty|pled\s+guilty"
    r")\b",
    re.IGNORECASE,
)

_BOILERPLATE_REJECT_TEMPLATES = frozenset({
    "icac_mission_doj",
    "grant_doj_icac",
    "grant_doj_administers_icac",
    "funding_us_doj",
    "ag_grant_doj",
    "illinois_ag_grant_icac_doc",
    "project_safe_childhood_initiative_doj",
})

# Weaker signals — only count when not inside a known boilerplate sentence.
_WEAK_CASE_ACTION_RE = re.compile(
    r"\b(?:"
    r"charged|arrested|booked|arraigned|"
    r"joint\s+investigation|in\s+conjunction\s+with|working\s+with|partnered\s+with|"
    r"assisted\s+by|coordinated\s+with"
    r")\b",
    re.IGNORECASE,
)

_DOJ_ANCHOR_RE = re.compile(
    r"(?:"
    r"\b(?:u\.s\.|united\s+states)\s+department\s+of\s+justice\b|"
    r"\bdepartment\s+of\s+justice\b|"
    r"\bdoj\b"
    r")",
    re.IGNORECASE,
)

_AG_ANCHOR_RE = re.compile(
    r"\b(?:"
    r"office\s+of\s+(?:the\s+)?attorney\s+general|"
    r"attorney\s+general'?s?\s+office|"
    r"attorney\s+general\b"
    r")",
    re.IGNORECASE,
)

_STATE_DOJ_RE = re.compile(
    r"\b("
    r"delaware|oregon|montana|new\s+mexico|wisconsin|illinois|"
    r"kentucky|vermont|hawaii|texas|florida|georgia|ohio|michigan"
    r")\s+department\s+of\s+justice\b",
    re.IGNORECASE,
)

_PROGRAM_CONTEXT_LABEL_DOJ = "DOJ (program context)"
_PROGRAM_CONTEXT_LABEL_AG = "AG (program context)"

# First-party federal DOJ press (pathway: generic DOJ labels count as federal).
_FEDERAL_DOJ_PRESS_SOURCES = frozenset({"DOJ ARCHIVES", "DOJ CEOS", "DOJ SAFE CHILDHOOD"})

# Other federal LE publishers (non-DOJ agencies still pathway-federal).
_FEDERAL_LE_PUBLISHER_SOURCES = frozenset({
    "DOJ ARCHIVES",
    "DOJ CEOS",
    "DOJ SAFE CHILDHOOD",
    "CBP",
    "ICE",
    "US MARSHALS",
    "USSS",
    "ARMY CID",
})

_PATHWAY_FEDERAL_AGENCY_RE = re.compile(
    r"\b(?:"
    r"FBI|Federal Bureau of Investigation|"
    r"HSI|Homeland Security Investigations?|"
    r"ICE|Immigration and Customs Enforcement|"
    r"USMS|U\.?S\.?\s*Marshals?|"
    r"USSS|U\.?S\.?\s*Secret Service|"
    r"DEA|Drug Enforcement Administration|"
    r"ATF|"
    r"CBP|Customs and Border Protection|"
    r"CEOS|Child Exploitation and Obscenity Section|"
    r"U\.?S\.?\s*Attorneys?(?:\s*['\u2019]s)?(?:\s+Office)?|"
    r"United States Attorneys?(?:\s*['\u2019]s)?(?:\s+Office)?|"
    r"NCMEC|National Center for Missing"
    r")\b",
    re.IGNORECASE,
)

_WINDOW_CHARS = 320


def _casefold(s: str) -> str:
    return (s or "").casefold()


def is_federal_doj_label(label: str) -> bool:
    low = _casefold(label)
    if low == "doj":
        return True
    if "department of justice" not in low:
        return False
    if _STATE_DOJ_RE.search(label):
        return False
    if low.startswith("delaware department of justice"):
        return False
    return True


def is_state_doj_label(label: str) -> bool:
    low = _casefold(label)
    if "department of justice" not in low:
        return False
    return bool(_STATE_DOJ_RE.search(label)) or low.startswith("delaware department of justice")


def is_agency_ag_label(label: str) -> bool:
    low = _casefold(label)
    if "attorney general" not in low:
        return False
    if "district attorney" in low and "attorney general" not in low.replace("district attorney", ""):
        return False
    if is_state_doj_label(label):
        return False
    return True


def is_federal_le_publisher_source(source: Optional[str]) -> bool:
    return bool(source and source in _FEDERAL_LE_PUBLISHER_SOURCES)


def is_state_local_publisher_source(source: Optional[str]) -> bool:
    """State ICAC / AG / PD / SO press (not first-party federal DOJ feeds)."""
    if not source:
        return False
    return source not in _FEDERAL_DOJ_PRESS_SOURCES


def _federal_doj_has_sentence_strong_action(case_text: str) -> bool:
    """Any DOJ anchor in a sentence with strong (not weak-only) case-action."""
    text = (case_text or "").strip()
    if not text:
        return False
    for start, end, _ in _find_anchors(text, _DOJ_ANCHOR_RE):
        strong, _weak = _sentence_case_action(text, start, end)
        if strong:
            return True
    return False


def pathway_bucket_for_label(
    label: str,
    source: Optional[str],
    case_text: str,
    *,
    gate_decision: str = "keep",
) -> Tuple[str, str]:
    """
    Pathway tier for a kept agency label (Piece 3).

    Returns (bucket, reason) where bucket is one of:
    - ``federal`` — counts toward federal pathway / co-occurrence
    - ``state_local`` — state, local, or ICAC task-force participation
    - ``state_context`` — syndicated program/boilerplate mention; excluded from federal
    - ``exclude`` — rejected by gate (not on pathway lists)
    """
    if gate_decision == "reject":
        return "exclude", "gate_rejected"
    if gate_decision == "review":
        return "state_context", "gate_review_excluded_from_pathway"

    if is_state_doj_label(label):
        return "state_local", "state_qualified_doj"

    if is_federal_doj_label(label):
        if source in _FEDERAL_DOJ_PRESS_SOURCES:
            return "federal", "federal_doj_press_source"
        if is_state_local_publisher_source(source):
            if _federal_doj_has_sentence_strong_action(case_text):
                return "federal", "federal_prosecution_on_state_feed"
            return "state_context", "state_feed_syndicated_federal_doj"
        if is_federal_le_publisher_source(source):
            return "federal", "federal_le_publisher"
        return "state_context", "non_federal_publisher_doj"

    if is_agency_ag_label(label):
        return "state_local", "state_agency"

    if _PATHWAY_FEDERAL_AGENCY_RE.search(label):
        return "federal", "federal_agency_label"

    if re.search(r"\bICAC\b|Internet Crimes Against Children", label, re.I):
        return "state_local", "icac_task_force"
    if re.search(
        r"\b(?:police|sheriff|state police|department of public safety)\b",
        label,
        re.I,
    ):
        return "state_local", "local_le"

    return "state_local", "default_state_local"


def apply_source_aware_gate_overrides(
    ev: Dict[str, Any],
    label: str,
    case_text: str,
    source: Optional[str],
) -> Dict[str, Any]:
    """
    Source-aware adjustments after span-level gate evaluation (Piece 3).

    Does not use prosecution language outside the DOJ/AG anchor sentence.
    """
    if not source:
        return ev

    if (
        source in _FEDERAL_DOJ_PRESS_SOURCES
        and is_federal_doj_label(label)
        and ev["decision"] == "review"
    ):
        return {**ev, "decision": "keep", "reason": "federal_doj_press_source"}

    if (
        source in _FEDERAL_DOJ_PRESS_SOURCES
        and is_federal_doj_label(label)
        and ev["decision"] == "reject"
        and ev.get("template") not in _BOILERPLATE_REJECT_TEMPLATES
    ):
        return {**ev, "decision": "keep", "reason": "federal_doj_press_source"}

    if is_state_local_publisher_source(source) and is_agency_ag_label(label):
        if ev["decision"] == "review":
            return {**ev, "decision": "keep", "reason": "state_ag_press_source"}

    if (
        is_state_local_publisher_source(source)
        and is_federal_doj_label(label)
        and ev["decision"] == "review"
    ):
        if _federal_doj_has_sentence_strong_action(case_text):
            return {**ev, "decision": "keep", "reason": "federal_prosecution_on_state_feed"}
        return {
            **ev,
            "decision": "reject",
            "reason": "state_feed_syndicated_federal_doj",
        }

    return ev


def build_pathway_agency_lists(
    case_text: str,
    agencies: List[str],
    source: Optional[str],
    label_decisions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Split kept agencies into federal vs state/local pathway lists."""
    decision_by_label = {e["label"]: e for e in label_decisions if e.get("label")}
    federal: List[str] = []
    state_local: List[str] = []
    entries: List[Dict[str, Any]] = []
    seen_fed: set = set()
    seen_st: set = set()

    for label in agencies:
        entry = decision_by_label.get(label, {"label": label, "decision": "keep"})
        bucket, bucket_reason = pathway_bucket_for_label(
            label,
            source,
            case_text,
            gate_decision=str(entry.get("decision", "keep")),
        )
        row = {
            "label": label,
            "bucket": bucket,
            "bucket_reason": bucket_reason,
            "gate_decision": entry.get("decision"),
            "gate_reason": entry.get("reason"),
        }
        entries.append(row)
        if bucket == "federal":
            key = label.casefold()
            if key not in seen_fed:
                seen_fed.add(key)
                federal.append(label)
        elif bucket == "state_local":
            key = label.casefold()
            if key not in seen_st:
                seen_st.add(key)
                state_local.append(label)

    federal.sort(key=lambda s: s.lower())
    state_local.sort(key=lambda s: s.lower())
    return {
        "federal": federal,
        "state_local": state_local,
        "entries": entries,
    }


def _sentence_span(text: str, pos: int) -> Tuple[int, int]:
    """Bounds of the sentence containing ``pos`` (fallback: ±280 chars)."""
    n = len(text)
    left = text.rfind(".", 0, pos)
    left = max(left, text.rfind("!", 0, pos), text.rfind("?", 0, pos))
    right_candidates = [text.find(".", pos), text.find("!", pos), text.find("?", pos)]
    right_candidates = [r for r in right_candidates if r != -1]
    start = (left + 1) if left != -1 else max(0, pos - 280)
    end = (min(right_candidates) + 1) if right_candidates else min(n, pos + 280)
    return start, end


def _doc_level_doj_boilerplate(text: str, source: Optional[str]) -> Optional[str]:
    """
    Document-level program-context templates (newline-split grant / PSC initiative copy).

    Not used on DOJ ARCHIVES / DOJ CEOS. Does not consider prosecution language outside
    the DOJ anchor sentence — callers still require same-sentence strong action to keep.
    """
    if source in _FEDERAL_DOJ_PRESS_SOURCES:
        return None
    if _ILLINOIS_AG_GRANT_ICAC_DOC_RE.search(text):
        return "illinois_ag_grant_icac_doc"
    if source == "NCMEC" and _PSC_INITIATIVE_DOJ_DOC_RE.search(text):
        return "project_safe_childhood_initiative_doj"
    return None


def _boilerplate_template_id(
    text: str, start: int, end: int, source: Optional[str] = None
) -> Optional[str]:
    """Return template id if span sits inside program-context boilerplate."""
    s_start, s_end = _sentence_span(text, start)
    chunk = text[s_start:s_end]
    if _ICAC_MISSION_DOJ_RE.search(chunk):
        return "icac_mission_doj"
    if _GRANT_DOJ_ICAC_RE.search(chunk):
        return "grant_doj_icac"
    if _GRANT_DOJ_ADMINISTERS_ICAC_RE.search(chunk):
        return "grant_doj_administers_icac"
    if _FUNDING_US_DOJ_RE.search(chunk):
        return "funding_us_doj"
    if _AG_GRANT_DOJ_RE.search(chunk):
        return "ag_grant_doj"
    doc_tpl = _doc_level_doj_boilerplate(text, source)
    if doc_tpl:
        return doc_tpl
    return None


def _sentence_case_action(text: str, start: int, end: int) -> Tuple[bool, bool]:
    """
    Return (strong_action, weak_action) within the sentence containing the anchor.
    """
    s_start, s_end = _sentence_span(text, start)
    sentence = text[s_start:s_end]
    strong = bool(_STRONG_CASE_ACTION_RE.search(sentence))
    weak = bool(_WEAK_CASE_ACTION_RE.search(sentence))
    return strong, weak


def _find_anchors(text: str, pattern: re.Pattern) -> List[Tuple[int, int, str]]:
    return [(m.start(), m.end(), m.group(0)) for m in pattern.finditer(text)]


def evaluate_federal_doj_label(
    case_text: str, label: str, source: Optional[str] = None
) -> Dict[str, Any]:
    text = (case_text or "").strip()
    if not text:
        return {
            "decision": "review",
            "reason": "no_case_text",
            "template": None,
            "anchors": [],
        }

    anchors = _find_anchors(text, _DOJ_ANCHOR_RE)
    if not anchors:
        return {
            "decision": "keep",
            "reason": "no_doj_anchor_in_text",
            "template": None,
            "anchors": [],
        }

    span_details: List[Dict[str, Any]] = []
    has_boilerplate = False
    has_action = False
    has_neutral = False

    for start, end, snippet in anchors:
        tpl = _boilerplate_template_id(text, start, end, source=source)
        strong, weak = _sentence_case_action(text, start, end)
        if strong or (weak and not tpl):
            has_action = True
            span_details.append(
                {
                    "snippet": snippet[:120],
                    "context": "case_action",
                    "template": tpl,
                    "strong": strong,
                    "weak": weak,
                }
            )
        elif tpl:
            has_boilerplate = True
            span_details.append(
                {"snippet": snippet[:120], "context": "boilerplate", "template": tpl}
            )
        else:
            has_neutral = True
            span_details.append(
                {"snippet": snippet[:120], "context": "neutral", "template": None}
            )

    if has_action:
        return {
            "decision": "keep",
            "reason": "case_action_context",
            "template": None,
            "anchors": span_details,
        }
    if has_boilerplate and not has_neutral:
        tpls = [s["template"] for s in span_details if s.get("template")]
        return {
            "decision": "reject",
            "reason": "program_context_only",
            "template": tpls[0] if tpls else "boilerplate",
            "anchors": span_details,
        }
    if has_boilerplate and has_neutral:
        return {
            "decision": "review",
            "reason": "mixed_boilerplate_and_neutral",
            "template": None,
            "anchors": span_details,
        }
    if has_neutral and not has_boilerplate:
        return {
            "decision": "review",
            "reason": "doj_present_no_clear_boilerplate_or_action",
            "template": None,
            "anchors": span_details,
        }
    return {
        "decision": "review",
        "reason": "unclassified",
        "template": None,
        "anchors": span_details,
    }


def evaluate_ag_label(
    case_text: str, label: str, source: Optional[str] = None
) -> Dict[str, Any]:
    """AG labels: grant/ICAC boilerplate vs case-action; state-qualified names usually kept."""
    text = (case_text or "").strip()
    low_label = _casefold(label)

    if not text:
        return {
            "decision": "review",
            "reason": "no_case_text",
            "template": None,
            "anchors": [],
        }

    # State-qualified AG office names on their own source narrative → keep unless pure grant copy only
    if any(
        x in low_label
        for x in (
            "illinois attorney",
            "delaware department",
            "south carolina attorney",
            "washington attorney",
        )
    ):
        anchors = _find_anchors(text, _AG_ANCHOR_RE)
        if not anchors:
            return {
                "decision": "keep",
                "reason": "state_qualified_label_no_anchor",
                "template": None,
                "anchors": [],
            }

    anchors = _find_anchors(text, _AG_ANCHOR_RE)
    if not anchors:
        return {
            "decision": "keep",
            "reason": "no_ag_anchor_in_text",
            "template": None,
            "anchors": [],
        }

    span_details: List[Dict[str, Any]] = []
    has_boilerplate = False
    has_action = False
    has_neutral = False

    for start, end, snippet in anchors:
        tpl = _boilerplate_template_id(text, start, end)
        if not tpl and _AG_GRANT_DOJ_RE.search(
            text[max(0, start - 80) : min(len(text), end + 200)]
        ):
            tpl = "ag_grant_doj"
        strong, weak = _sentence_case_action(text, start, end)
        if strong or (weak and not tpl):
            has_action = True
            span_details.append(
                {"snippet": snippet[:120], "context": "case_action", "template": tpl}
            )
        elif tpl:
            has_boilerplate = True
            span_details.append(
                {"snippet": snippet[:120], "context": "boilerplate", "template": tpl}
            )
        else:
            has_neutral = True
            span_details.append(
                {"snippet": snippet[:120], "context": "neutral", "template": None}
            )

    if has_action:
        return {
            "decision": "keep",
            "reason": "case_action_context",
            "template": None,
            "anchors": span_details,
        }
    if has_boilerplate and not has_neutral:
        tpls = [s["template"] for s in span_details if s.get("template")]
        return {
            "decision": "reject",
            "reason": "program_context_only",
            "template": tpls[0] if tpls else "ag_grant_boilerplate",
            "anchors": span_details,
        }
    if has_boilerplate or has_neutral:
        return {
            "decision": "review",
            "reason": "ag_ambiguous_context",
            "template": None,
            "anchors": span_details,
        }
    return {
        "decision": "keep",
        "reason": "default_keep",
        "template": None,
        "anchors": span_details,
    }


def evaluate_agency_label(
    case_text: str, label: str, source: Optional[str] = None
) -> Dict[str, Any]:
    if is_state_doj_label(label):
        return {
            "decision": "keep",
            "reason": "state_doj_label",
            "template": None,
            "anchors": [],
        }
    if is_federal_doj_label(label):
        return evaluate_federal_doj_label(case_text, label, source=source)
    if is_agency_ag_label(label):
        return evaluate_ag_label(case_text, label, source=source)
    return {
        "decision": "keep",
        "reason": "not_doj_or_ag_scope",
        "template": None,
        "anchors": [],
    }


def apply_agency_context_gate(
    case_id: str,
    case_text: str,
    agencies: List[str],
    source: Optional[str] = None,
) -> Tuple[List[str], Dict[str, Any]]:
    """
    Filter/relabel agencies_involved for program-context DOJ/AG mentions.

    Decisions per label:
    - keep: unchanged
    - reject: removed from list (boilerplate-only federal DOJ/AG)
    - relabel: replaced with ``DOJ (program context)`` / ``AG (program context)``
      (not used by default; reject removes instead)
    - review: kept in list, logged for human adjudication
    """
    log: Dict[str, Any] = {
        "case_id": case_id or "",
        "kept": [],
        "rejected": [],
        "relabeled": [],
        "review": [],
    }
    if not agencies:
        return [], log

    out: List[str] = []
    seen: set = set()

    for label in agencies:
        if not label or not str(label).strip():
            continue
        label = str(label).strip()
        ev = evaluate_agency_label(case_text, label, source=source)
        ev = apply_source_aware_gate_overrides(ev, label, case_text, source)
        decision = ev["decision"]
        entry = {
            "label": label,
            "decision": decision,
            "reason": ev.get("reason"),
            "template": ev.get("template"),
        }

        final_label = label
        if decision == "reject":
            log["rejected"].append(entry)
            continue
        if decision == "relabel":
            if is_federal_doj_label(label):
                final_label = _PROGRAM_CONTEXT_LABEL_DOJ
            elif is_agency_ag_label(label):
                final_label = _PROGRAM_CONTEXT_LABEL_AG
            entry["relabeled_to"] = final_label
            log["relabeled"].append(entry)
        elif decision == "review":
            log["review"].append(entry)
        else:
            log["kept"].append(entry)

        key = final_label.casefold()
        if key not in seen:
            seen.add(key)
            out.append(final_label)

    out.sort(key=lambda s: s.lower())
    all_entries = log["kept"] + log["review"] + log["rejected"] + log.get("relabeled", [])
    log["pathway"] = build_pathway_agency_lists(case_text, out, source, all_entries)
    return out, log
