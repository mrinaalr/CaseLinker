"""Case-level prosecuting jurisdiction, derived at read time and never stored (#29).

``federal`` / ``state`` / ``unknown`` from the source and the release's prosecutor,
court and charging language. Investigating agencies are not used: FBI, HSI and
NCMEC appear on state prosecutions all the time. Both or neither → ``unknown``;
unknown is never folded into either side. ``basis`` lists signal names only.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

JURISDICTIONS = ("federal", "state", "unknown")

NON_US_SOURCES = frozenset({
    "NZ DIA", "BRAZIL PF", "SCOTLAND POLICE", "EUROPOL", "NBI", "AFP", "NCA", "QPS", "GARDA", "ALERT ICE",
})
DOJ_USAO_SOURCES = frozenset({"DOJ SAFE CHILDHOOD", "DOJ CEOS", "DOJ ARCHIVES", "DOJ AI CSAM"})

_US = r"(?:U\.\s?S\.|United\s+States)"
_USAO = _US + r"\s+Attorney(?:['’]s\s+(?i:office))?"
_DISTRICT = r"(?:\s*,?\s+(?:for\s+the\s+)?(?:[A-Z][\w.]*\s+){0,2}District\s+of\s+(?:[A-Z][\w.]*\s*){1,3})?"
_FEDERAL = {
    "us_district_court": re.compile(_US + r"\s+District\s+(?:Court|Judge)\b", re.I),
    # An Assistant U.S. Attorney is always the prosecutor, even when thanked.
    "assistant_us_attorney": re.compile(r"\b(?i:Assistant)\s+" + _US + r"\s+(?i:Attorney)\b"),
    # The U.S. Attorney's Office only counts in a prosecutor role. A bare mention is often a
    # partner list or a thank-you on a state case (see _PARTNER_CONTEXT).
    "us_attorney": re.compile(
        r"\b(?i:prosecuted|handled|tried|announced|filed|brought|unsealed)\s+by\s+(?:the\s+)?(?:Acting\s+)?" + _USAO
        + r"|\b(?i:according\s+to|release\s+from|information\s+from|agreement\s+with)\s+(?:a\s+release\s+from\s+)?(?:the\s+)?" + _USAO
        + r"|\bFrom\s+the\s+" + _USAO + r"\s*:"
        + r"|\b" + _USAO + _DISTRICT + r"[\s,]*(?:[A-Z][\w.]*\s+){0,3}(?:has\s+|have\s+)?"
        r"(?i:announced|said|says|stated|charged|filed|unsealed|has\s+charged|will\s+prosecute|is\s+prosecuting|prosecuted)\b"
        r"|\b(?i:For\s+Immediate\s+Release|Press\s+Release)\s+" + _USAO
        + r"|\b" + _USAO + _DISTRICT + r"\s*(?i:Press\s+Release)\b"
    ),
    "federal_grand_jury": re.compile(r"\bfederal\s+grand\s+jury\b", re.I),
    "federal_prison": re.compile(r"\bfederal\s+prison\b", re.I),
    # Criminal titles only: "42 U.S.C. § 671" (foster care) is not a prosecution.
    "usc_citation": re.compile(r"\b(?:18|21|8)\s+U\.\s?S\.\s?C\.?", re.I),
}
_STATE = {
    # Apostrophe required and not "United States Attorney" / "U.S. Attorney".
    "states_attorney": re.compile(r"(?<!United\s)(?<!U\.S\.\s)\bState['’]s\s+Attorney\b", re.I),
    "district_attorney": re.compile(r"\bDistrict\s+Attorney\b", re.I),
    "commonwealths_attorney": re.compile(r"\bCommonwealth['’]s\s+Attorney\b", re.I),
    "state_trial_court": re.compile(r"(?<!U\.S\.\s)(?<!Federal\s)\b(?:Superior|Circuit)\s+Court\b(?!\s+of\s+Appeals)|\bCourt\s+of\s+Common\s+Pleas\b", re.I),
    "state_prison": re.compile(r"\bstate\s+prison\b", re.I),
    "penal_code": re.compile(r"\bPenal\s+Code\b", re.I),
}
# A U.S. Attorney's Office mention in a thank-you or an assist is not the prosecutor. Bare
# mentions in partner lists never match the role patterns above.
_PARTNER_CONTEXT = re.compile(
    r"\bthank|\bassist(?!ant)|\bpartner|\bin\s+conjunction\b|\bcoordinat|\bsupport|\bcollaborat|\balong\s+with\b"
    r"|\bmembers?\s+of\b|\btask\s+force\s+(?:officers?|members?)\b|\bfor\s+consideration\b|\breferred\b",
    re.I,
)
# A prison mention about an earlier sentence or someone's job says nothing about this case.
_PRISON_SIGNALS = frozenset({"federal_prison", "state_prison"})
_EARLIER_OR_JOB = re.compile(
    r"\bpreviously\s+(?:been\s+)?(?:sentenced|served|convicted|incarcerated)\b|\bprior\b|\bearlier\b|\bhad\s+(?:been|served)\b"
    r"|(?<!will\sbe\s)\bserv(?:ed|ing)\b(?!\s+as\b)|\breleased\s+from\b|\bspent\b"
    r"|^\W*in\s+(?:\w+\s+)?(?:19|20)\d\d\b|\bconvicted\s+in\s+(?:19|20)\d\d\b"
    r"|\bguard\b|\bworked\b|\bemploy|\bofficer\s+at\b|\bcorrections?\s+officer\b|\bwarden\b",
    re.I,
)
_CURRENT = re.compile(r"\b(?:now|today)\b", re.I)
_CONVICTED_IN_YEAR = re.compile(r"\bconvicted\s+in\s+(?:19|20)\d\d\b", re.I)
_MILITARY = re.compile(r"\bcourt[-\s]martial\b", re.I)
_YEAR = re.compile(r"\b(?:19|20)\d\d\b")
_SENTENCE_END = re.compile(r"(\w*)[.;!?][\"”’)]*\s|\n\s*\n")


def _sentence_bounds(text: str, start: int, end: int) -> tuple:
    """Start and end of the sentence around a match; initials and "U.S." do not end it."""
    lo, hi = 0, len(text)
    for m in _SENTENCE_END.finditer(text):
        word = m.group(1) or ""
        if word and (len(word) == 1 or word in ("Jr", "Sr", "Dr", "Mr", "Mrs", "Ms", "St", "Hon", "Inc", "Co")):
            continue
        if m.end() <= start:
            lo = m.end()
        elif m.end() > end:
            hi = m.end()
            break
    return lo, hi


def _signal_counts(name: str, rx: re.Pattern, text: str) -> bool:
    for m in rx.finditer(text):
        lo, hi = _sentence_bounds(text, m.start(), m.end())
        if name == "us_attorney":
            if _PARTNER_CONTEXT.search(text[max(lo, m.start() - 80) : min(hi, m.end() + 40)]):
                continue
        elif name in _PRISON_SIGNALS:
            before = text[max(lo, m.start() - 120) : m.start()]
            cue = _EARLIER_OR_JOB.search(before)
            # "four prior state convictions … has now been sentenced to ten years in federal prison"
            if cue and _CURRENT.search(before[cue.end() :]):
                cue = None
            if cue or _EARLIER_OR_JOB.search(text[m.end() : min(hi, m.end() + 40)]):
                continue
            # "He was convicted in 2013 … He was sentenced to five years in state prison."
            prev_lo = _sentence_bounds(text, lo - 2, lo - 1)[0] if lo > 1 else lo
            if _CONVICTED_IN_YEAR.search(text[prev_lo:lo]):
                continue
        return True
    return False


def _case_text(case: Dict[str, Any]) -> str:
    text = case.get("case_text")
    if isinstance(text, str) and text:
        return text
    raw = case.get("raw_data")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            raw = None
    return str((raw or {}).get("case_text") or "") if isinstance(raw, dict) else ""


def derive_jurisdiction(case: Dict[str, Any]) -> Dict[str, Any]:
    """``{"jurisdiction": federal|state|unknown, "jurisdiction_basis": [signal names]}``."""
    source = str(case.get("source") or "").strip().upper()
    if source in NON_US_SOURCES:
        return {"jurisdiction": "unknown", "jurisdiction_basis": ["non_us_source"]}
    text = _case_text(case)
    # An earlier court-martial ("his 2017 court-martial", "convicted by court-martial in 1998")
    # is history, not this case's forum.
    if any(not _YEAR.search(text[max(0, m.start() - 25) : m.end() + 25]) for m in _MILITARY.finditer(text)):
        return {"jurisdiction": "unknown", "jurisdiction_basis": ["military_court"]}
    federal: List[str] = ["doj_usao_source"] if source in DOJ_USAO_SOURCES else []
    federal += [name for name, rx in _FEDERAL.items() if _signal_counts(name, rx, text)]
    state = [name for name, rx in _STATE.items() if _signal_counts(name, rx, text)]
    if federal and not state:
        label = "federal"
    elif state and not federal:
        label = "state"
    else:
        label = "unknown"
    basis = [f"federal:{n}" for n in federal] + [f"state:{n}" for n in state]
    return {"jurisdiction": label, "jurisdiction_basis": basis or ["no_signal"]}
