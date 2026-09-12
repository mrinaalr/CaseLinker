"""
Shared agency label normalization for ingest (storage) and stats (read-path).

Pipeline per raw label: apostrophe/unicode normalize → split merge-glued → possessive
tier fixes → canonical map (DOJ/AG/ICAC/acronyms, aligned with stats chart).
"""

from __future__ import annotations

import re
from typing import Dict, List

from agency_possessive_repair import apply_possessive_tier_fixes

_APOS_CLASS = r"[''\u2018\u2019`\u00b4\u02bc]"
# Unicode + ASCII quote marks NER/PDF copy uses before possessive s (→ ASCII ' for weld regexes).
_APOSTROPHE_NORMALIZE_RE = re.compile(r"[\u2018\u2019`\u00b4\u02bc]")

FEDERAL_DOJ_CANONICAL = "U.S. Department of Justice"
GENERIC_STATE_POLICE_LABEL = "State Police Department"
_PREFIXED_STATE_POLICE_RE = re.compile(r"^.+\s+State Police Department$", re.IGNORECASE)

# Canonical alias table (ingest only; stats reads stored labels as-is).
AGENCY_CANONICAL_ALIASES_CASEFOLD: Dict[str, str] = {
    "office of attorney general": "Office of the Attorney General",
    "office of the attorney general": "Office of the Attorney General",
    "office of attorney general's": "Office of the Attorney General",
    "office of attorney general's office": "Office of the Attorney General",
    "attorney general''s office": "Attorney General's Office",
    "attorney general\u2019's office": "Attorney General's Office",
    "attorney general\u2019\u2019s office": "Attorney General's Office",
    "attorney generals office": "Attorney General's Office",
    "attorney general office": "Attorney General's Office",
    "attorney general's": "Attorney General's Office",
    "attorney general's office": "Attorney General's Office",
    "doj": FEDERAL_DOJ_CANONICAL,
    "usss": "U.S. Secret Service",
    "u.s. secret service": "U.S. Secret Service",
    "united states secret service": "U.S. Secret Service",
    "usms": "U.S. Marshals Service",
    "u.s. marshals service": "U.S. Marshals Service",
    "united states marshals service": "U.S. Marshals Service",
    "raoul's high tech crimes bureau": "Illinois High Tech Crimes Bureau",
    "raoul\u2019s high tech crimes bureau": "Illinois High Tech Crimes Bureau",
    "raoul's sexually violent persons bureau": "Illinois Sexually Violent Persons Bureau",
    "madigan's high tech crimes bureau": "Illinois High Tech Crimes Bureau",
    "madigan\u2019s high tech crimes bureau": "Illinois High Tech Crimes Bureau",
    "murrill's louisiana bureau of investigation": "Louisiana Bureau of Investigation",
    "yost's bureau of criminal investigation": "Ohio Bureau of Criminal Investigation",
    "general's high tech crimes bureau": "Illinois High Tech Crimes Bureau",
    "general\u2019s high tech crimes bureau": "Illinois High Tech Crimes Bureau",
    "general's bureau of criminal investigation": "Ohio Bureau of Criminal Investigation",
    "illinois attorney general's office high tech crimes bureau": "Illinois High Tech Crimes Bureau",
    "illinois attorney general\u2019s office high tech crimes bureau": "Illinois High Tech Crimes Bureau",
    "justice department's child exploitation and obscenity section": "CEOS",
    "justice department\u2019s child exploitation and obscenity section": "CEOS",
    "u.s. attorney's office": "U.S. Attorney's Office",
    "u.s. attorneys office": "U.S. Attorney's Office",
    "u.s. attorney’s office": "U.S. Attorney's Office",
    "united states attorney's office": "U.S. Attorney's Office",
    "united states attorneys office": "U.S. Attorney's Office",
    "office of the united states attorney": "U.S. Attorney's Office",
    "office of the u.s. attorney": "U.S. Attorney's Office",
    "usao": "U.S. Attorney's Office",
}

# Merge-glued split patterns (deterministic).
_MERGE_ENUM_SPLIT = re.compile(r"\s+\d+\.\s+")
_AG_MURRILL_REPEAT = re.compile(r"\s+(?=AG\s+Murrill's\s+)", re.IGNORECASE)
# Second agency: "... Sheriff's Office <Name> Police Department"
_OFFICE_THEN_PD = re.compile(
    r"^(.+?Sheriff's Office)\s+(.+Police Department.*)$",
    re.IGNORECASE,
)
_OFFICE_ONLY_THEN_PD = re.compile(
    r"^(Sheriff's Office)\s+(.+Police Department.*)$",
    re.IGNORECASE,
)
# "... Office <Words> Police Department" without county in between
_PROSECUTOR_GLUE = re.compile(
    r"^(.+?(?:Prosecutor's Office|District Attorney's Office))\s+"
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+Police Department.*)$",
    re.IGNORECASE,
)
_MURRILL_CHARGE_TAIL = re.compile(
    r"^(AG\s+Murrill's\s+Louisiana Bureau of Investigation)(?:\s+for\b.*)?$",
    re.IGNORECASE,
)
# Truncated LBI in scraper/NCMEC digest (ellipsis mid-phrase; full name recoverable)
_MURRILL_LBI_TRUNC_RE = re.compile(
    r"^(?:AG\s+(?:Liz\s+)?Murrill's\s+)?Louisiana Bureau o\.?…(?:\s+Source)?$",
    re.IGNORECASE,
)
_LBI_CANONICAL = "Louisiana Bureau of Investigation"
# Sheriff's Office + duplicate county sheriff (junk prefix weld)
_SHERIFF_DUP_RE = re.compile(
    r"^Sheriff's Office\s+(.+Sheriff's Office)$",
    re.IGNORECASE,
)
# Sheriff/Prosecutor/DA office + city PD (second agency)
_SHERIFF_DEPT_THEN_PD = re.compile(
    r"^(.+?Sheriff's Department)\s+(.+Police Department.*)$",
    re.IGNORECASE,
)
_COUNTY_PROSECUTOR_THEN_PD = re.compile(
    r"^(.+Prosecutor's Office)\s+(.+Police Department.*)$",
    re.IGNORECASE,
)
_BARE_PROSECUTOR_THEN_PD = re.compile(
    r"^Prosecutor's Office\s+(.+Police Department.*)$",
    re.IGNORECASE,
)
_DA_OFFICE_THEN_PD = re.compile(
    r"^(District Attorney's Office)\s+(.+Police Department.*)$",
    re.IGNORECASE,
)
# Triple: bare Sheriff's Office + county prosecutor + city PD
_SHERIFF_PROSECUTOR_PD = re.compile(
    r"^Sheriff's Office\s+(.+Prosecutor's Office)\s+(.+Police Department.*)$",
    re.IGNORECASE,
)
# Sheriff's Office + Rahab Ministries (non-LE) + city PD run-on (Ohio Op participant lists)
_RAHAB_SHERIFF_PD_RE = re.compile(
    r"^(.+Sheriff's Office)\s+Rahab Ministries\s+(.+Police Department.*)$",
    re.IGNORECASE,
)
_RAHAB_PREFIX_PD_RE = re.compile(
    r"^Rahab Ministries\s+(.+Police Department.*)$",
    re.IGNORECASE,
)
# Non-law-enforcement org names dropped after split (participant-list noise)
_NON_LE_AGENCY_LABELS = frozenset({"Rahab Ministries"})


def collapse_double_apostrophes(label: str) -> str:
    """
    Deterministic apostrophe cleanup (Tier: double-apostrophe class).

    Normalizes unicode/grave/acute quotes to ASCII `'`, collapses doubles, and
    repairs ``Sheriff's 's`` → ``Sheriff's``. Safe to call before weld-split.
    """
    s = (label or "").strip()
    if not s:
        return s
    # Unicode / typographic apostrophes → ASCII possessive marker
    s = _APOSTROPHE_NORMALIZE_RE.sub("'", s)
    s = re.sub(r"''+", "'", s)
    # 's 's / 's's / quote runs before s
    s = re.sub(rf"'s\s*{_APOS_CLASS}+\s*s\b", "'s", s, flags=re.IGNORECASE)
    s = re.sub(rf"'s{_APOS_CLASS}+s\b", "'s", s, flags=re.IGNORECASE)
    s = re.sub(rf"\s*{_APOS_CLASS}+\s*{_APOS_CLASS}*\s*s\b", "'s", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _split_one_merge_glued(s: str) -> List[str]:
    """Apply one split pass; return multiple parts only when a rule matches."""
    if _MERGE_ENUM_SPLIT.search(s):
        chunks = [c.strip() for c in _MERGE_ENUM_SPLIT.split(s) if c.strip()]
        if len(chunks) > 1:
            return chunks

    if _AG_MURRILL_REPEAT.search(s):
        chunks = [c.strip() for c in _AG_MURRILL_REPEAT.split(s) if c.strip()]
        if len(chunks) > 1:
            return chunks

    m = _MURRILL_CHARGE_TAIL.match(s)
    if m:
        return [m.group(1).strip()]

    m = _RAHAB_SHERIFF_PD_RE.match(s)
    if m:
        return [m.group(1).strip(), m.group(2).strip()]

    m = _RAHAB_PREFIX_PD_RE.match(s)
    if m:
        return [m.group(1).strip()]

    m = _SHERIFF_PROSECUTOR_PD.match(s)
    if m:
        return [
            "Sheriff's Office",
            m.group(1).strip(),
            m.group(2).strip(),
        ]

    m = _SHERIFF_DUP_RE.match(s)
    if m:
        return [m.group(1).strip()]

    m = _OFFICE_THEN_PD.match(s)
    if m:
        return [m.group(1).strip(), m.group(2).strip()]

    m = _OFFICE_ONLY_THEN_PD.match(s)
    if m:
        return [m.group(1).strip(), m.group(2).strip()]

    m = _SHERIFF_DEPT_THEN_PD.match(s)
    if m:
        return [m.group(1).strip(), m.group(2).strip()]

    m = _COUNTY_PROSECUTOR_THEN_PD.match(s)
    if m:
        return [m.group(1).strip(), m.group(2).strip()]

    m = _BARE_PROSECUTOR_THEN_PD.match(s)
    if m:
        return ["Prosecutor's Office", m.group(1).strip()]

    m = _DA_OFFICE_THEN_PD.match(s)
    if m:
        return [m.group(1).strip(), m.group(2).strip()]

    m = _PROSECUTOR_GLUE.match(s)
    if m:
        return [m.group(1).strip(), m.group(2).strip()]

    return [s]


def split_merge_glued_agencies(label: str) -> List[str]:
    """
    Split known merge-glued multi-agency spans into separate labels.

    Iterates until no rule matches. Does not split single-org names like
    ``Sheriff's Office Detective Bureau`` or ``Attorney General's Bureau of …``.
    """
    s = collapse_double_apostrophes((label or "").strip())
    if not s:
        return []

    queue: List[str] = [s]
    out: List[str] = []
    while queue:
        part = queue.pop(0)
        pieces = _split_one_merge_glued(part)
        if len(pieces) > 1:
            queue.extend(pieces)
        elif pieces[0] != part:
            queue.append(pieces[0])
        else:
            out.append(part)
    return out if out else [s]


def _normalize_apostrophes_and_the(label: str) -> str:
    s = collapse_double_apostrophes(label)
    if s.lower().startswith("the "):
        s = s[4:].strip()
    return s


def canonicalize_agency_label_for_storage(label: str) -> str:
    """
    Canonical label aligned with stats chart (run/main.py).

    Apply after possessive tier fixes.
    """
    from agency_context_gate import is_federal_doj_label

    s = _normalize_apostrophes_and_the(label)
    if not s:
        return s

    s = re.sub(r"\s+Source\s*$", "", s, flags=re.IGNORECASE).strip()
    if _MURRILL_LBI_TRUNC_RE.match(s) or re.search(
        r"murrill'?s\s+louisiana bureau o\.?…", s, re.IGNORECASE
    ):
        return _LBI_CANONICAL

    s = apply_possessive_tier_fixes(s)

    alias = AGENCY_CANONICAL_ALIASES_CASEFOLD.get(s.casefold())
    if alias:
        s = alias

    if s.casefold() == "doj" or is_federal_doj_label(s):
        return FEDERAL_DOJ_CANONICAL

    low = s.casefold()

    # ICAC (same as ingest ICAC rule / stats)
    if ("icac" in low and "azicac" not in low) or (
        "internet crimes against children" in low and "arizona" not in low
    ):
        return "ICAC"

    if low == "ncmec" or "national center for missing and exploited children" in low:
        return "NCMEC"

    if re.match(r"^office of (the )?attorney general\b", low):
        return "Office of the Attorney General"

    if re.search(r"attorney general's office$", low):
        prefix_m = re.match(r"^(.+?)\s+attorney general's office$", low)
        if prefix_m and prefix_m.group(1).strip():
            return f"{prefix_m.group(1).strip().title()} Attorney General's Office"
        return "Attorney General's Office"

    # USAO / Assistant U.S. Attorney (person bylines) → office singleton
    if re.match(
        r"^(?:assistant\s+)?(?:u\.s\.|united\s+states)\s+attorneys?(?:['\u2019]?s)?(?:\s+office)?\b",
        low,
    ) or low == "usao":
        return "U.S. Attorney's Office"
    if re.match(r"^office of the (?:u\.s\.|united states) attorney\b", low):
        return "U.S. Attorney's Office"

    return s


def dedupe_generic_state_police(agencies: List[str]) -> List[str]:
    """
    Drop bare ``State Police Department`` when a prefixed sibling exists on the same case.

    Does not infer state for generic-only cases (no prefixed sibling).
    """
    if GENERIC_STATE_POLICE_LABEL not in agencies:
        return agencies
    has_prefixed = any(
        isinstance(a, str)
        and a.strip() != GENERIC_STATE_POLICE_LABEL
        and _PREFIXED_STATE_POLICE_RE.match(a.strip())
        for a in agencies
    )
    if not has_prefixed:
        return agencies
    return [a for a in agencies if a != GENERIC_STATE_POLICE_LABEL]


def drop_non_le_agencies(agencies: List[str]) -> List[str]:
    """Remove known non-LE participant-list orgs (e.g. Rahab Ministries)."""
    return [a for a in agencies if (a or "").strip() not in _NON_LE_AGENCY_LABELS]


def normalize_agency_label_for_ingest(label: str) -> List[str]:
    """
    Full ingest pipeline for one raw agency string → list of normalized labels.
    """
    if not label or len(str(label).strip()) < 2:
        return []

    normalized = collapse_double_apostrophes(str(label).strip())
    out: List[str] = []
    for part in split_merge_glued_agencies(normalized):
        canon = canonicalize_agency_label_for_storage(part)
        if canon and len(canon) >= 2:
            out.append(canon)
    return out
