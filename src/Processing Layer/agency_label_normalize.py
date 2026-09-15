"""
Shared agency label normalization for ingest (storage) and stats (read-path).

Pipeline per raw label: apostrophe/unicode normalize → split merge-glued → possessive
tier fixes → canonical map (DOJ/AG/ICAC/acronyms, aligned with stats chart).
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List

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


# Unlabeled buckets — not a distinct named agency.
_BARE_GENERIC_AGENCY_LABELS = frozenset(
    {
        "police department",
        "sheriff's office",
        "sheriff's department",
        "attorney general's office",
        "office of the attorney general",
        "district attorney's office",
        "prosecutor's office",
        "state police department",
        "federal agencies",
        "federal agents",
        "federal and international",
        "federal and state",
        "federal law enforcement partners",
        "investigation division",
        "computer crimes investigation",
        "criminal investigation division",
        "detective bureau",
        "county attorney's office",
        "district attorneys",
        "these task forces",
    }
)
_NON_AGENCY_LABELS = frozenset(
    {
        "federal express",
        "honeywell federal manufacturing and technology",
        "federal crime victims fund",
    }
)
_PERSON_AGENCY_RE = re.compile(
    r"^(Detective|Agent|Officer|Special Agent|Prosecutor|SA)\s+[A-Z][a-z]+\b",
    re.I,
)
_DISTINCT_AGENCY_ALIASES = {
    "u.s. marshals": "U.S. Marshals Service",
    "ice": "U.S. Immigration and Customs Enforcement",
    "dhs": "Department of Homeland Security",
    "dea": "DEA",
    "drug enforcement agency": "DEA",
    "drug enforcement administration": "DEA",
    "atf": "ATF",
    "fbi": "FBI",
    "hsi": "HSI",
}


# Core criminal-justice tokens: police, sheriffs, prosecutors, investigators, custody.
_LE_CORE_RE = re.compile(
    r"(?:"
    r"police|polce|\bpo\s+lice\b|sheriff|sherriff|constable|marshal|marshals|trooper|"
    r"highway\s+patrol|state\s+patrol|state\s+police|"
    r"prosecutors?|prosecuting|prosecution|"
    r"district\s+attorneys?|county\s+attorneys?|state'?s?\s+attorneys?|"
    r"commonwealth(?:'s)?\s+attorneys?|"
    r"attorney\s+genera|"
    r"u\.?s\.?\s+attorneys?|united\s+states\s+attorneys?|"
    r"icac|azicac|task\s*force|fusion\s+center|"
    r"correction(?:s|al)?|paroles?|probation|penitentiary|prisons?|"
    r"detectives?|investigators?|investigations?|investigative|"
    r"narcotics?|"
    r"homeland\s+security|secret\s+service|postal\s+inspection|"
    r"inspector\s+general|internal\s+affairs|"
    r"public\s+safety|campus\s+safety|campus\s+police|"
    r"rangers?|game\s+warden|fish\s+and\s+game|fish\s+&\s+game|wildlife|"
    r"natural\s+resources|border\s+patrol|customs|"
    r"coast\s+guard|criminal\s+apprehension|bureau\s+of\s+apprehension|"
    r"high[\s-]?tech\s+crime|organized\s+crime|special\s+crimes?|"
    r"major\s+crimes?|sex\s+crimes?|child\s+abuse|"
    r"human\s+trafficking|medicaid\s+fraud|community\s+supervision|"
    r"adult\s+correction|juvenile\s+justice|"
    r"national\s+crime\s+agency|national\s+central\s+bureau|interpol|"
    r"national\s+operations|"
    r"child\s+exploitation|obscenity\s+section|"
    r"bureau\s+of\s+investigation|division\s+of\s+criminal|"
    r"department\s+of\s+public\s+safety|department\s+of\s+law|"
    r"department\s+of\s+criminal\s+justice|criminal\s+justice|"
    r"law\s+enforcement|cyber\s*crimes?|computer\s+crimes?|"
    r"special\s+agent|enforcement\s+bureau|enforcement\s+agency|"
    r"special\s+services\s+bureau|"
    r"crime\s+lab|forensic(?:\s+lab|\s+services)?|swat|vice\s+squad|"
    r"bureau\s+of\s+prisons|bureau\s+of\s+indian\s+affairs|"
    r"bureau\s+of\s+alcohol|firearms\s+and\s+explosives|"
    r"office\s+of\s+special\s+investigations|criminal\s+intelligence|"
    r"justice\s+department|pardons\s+and\s+parole"
    r")",
    re.I,
)
_LE_ACRONYM_RE = re.compile(
    r"\b(?:atf|dea|fbi|ice|dhs|dps|hsi|usss|bop|bia|cbp|ncis|cid|osi|"
    r"irs-ci|doj|mcso|bcso|epa|ceos|opta|opia)\b",
    re.I,
)
_LE_RESCUE_RE = re.compile(
    r"federal\s+bureau\s+of|criminal\s+investigation\s+division|"
    r"\bcid\b|\bncis\b|\bosi\b|diplomatic\s+security|"
    r"air\s+force\s+office\s+of\s+special|army\s+criminal|"
    r"naval\s+criminal|marine\s+corps\s+cid|"
    r"immigration\s+and\s+customs|customs\s+and\s+border|"
    r"u\.s\.\s+department\s+of\s+justice|department\s+of\s+justice|"
    r"u\.s\.\s+marshals|secret\s+service",
    re.I,
)

# Non-LE orgs. Overridden when a stronger cop/prosecutor/task-force token is present.
_NON_LE_OVERRIDE_RE = re.compile(
    r"police|sheriff|sherriff|marshal|prosecutor|prosecuting|"
    r"district\s+attorney|attorney\s+general|task\s*force|icac|"
    r"campus\s+police|campus\s+safety|inspector\s+general|"
    r"criminal\s+investigation|criminal\s+intelligence|\bcid\b|\bncis\b|\bosi\b|"
    r"military\s+police|diplomatic\s+security|office\s+of\s+special\s+investigations|"
    r"county\s+attorney|firearms|bureau\s+of\s+prisons|\bfbi\b|\bhsi\b|\batf\b",
    re.I,
)
_NON_LE_DROP_RE = re.compile(
    r"fire\s+(?:department|dept|rescue|protection)|volunteer\s+fire|firefighter|"
    r"child\s+welfare|children\s+(?:and|&)\s+famil|"
    r"department\s+of\s+children|dept\.?\s+of\s+children|"
    r"child\s+protect(?:ive|ion)|(?:^|\s)dcfs(?:\s|$)|child\s+safety|child\s+services|"
    r"family\s+services|human\s+services|social\s+services|youth\s+services|"
    r"children'?s?\s+services|department\s+of\s+family|community\s+based\s+services|"
    r"department\s+of\s+education|school\s+district|board\s+of\s+education|"
    r"cyber\s+security\s+department|"
    r"department\s+of\s+transportation|\bdot\b|"
    r"department\s+of\s+motor\s+vehicle|bureau\s+of\s+motor\s+vehicle|\bdmv\b|\bbmv\b|"
    r"department\s+of\s+health|health\s+department|"
    r"department\s+of\s+labor|department\s+of\s+commerce|"
    r"department\s+of\s+agriculture|department\s+of\s+energy|"
    r"department\s+of\s+housing|department\s+of\s+the\s+interior|"
    r"u\.s\.\s+department\s+of\s+state|united\s+states\s+department\s+of\s+state|"
    r"^state\s+department$|^department\s+of\s+state$|"
    r"department\s+of\s+defense|department\s+of\s+the\s+(?:army|navy|air\s+force)|"
    r"department\s+of\s+veterans|department\s+of\s+revenue|"
    r"department\s+of\s+human\s+resources|department\s+of\s+health\s+and\s+welfare|"
    r"building\s+(?:department|and\s+zoning)|building\s+and\s+inspections|"
    r"code\s+enforcement|public\s+works|neighborhood\s+empowerment|"
    r"department\s+of\s+philosophy|psychiatry\s+department|"
    r"bureau\s+of\s+justice(?:\s+(?:assistance|statistics))?|"
    r"federal\s+express|\bfedex\b|finance\s+administration|"
    r"victim\s+service|advocacy|children'?s?\s+rights|"
    r"agency\s+for\s+international\s+development|\busaid\b|"
    r"defense\s+attorney|public\s+defender|"
    r"investigation\s+fund|ongoing\s+investigation|"
    r"these\s+task\s+forces|task\s+forcethat|justice\s+department\s+announces|"
    r"^office\s+of\s+attorney$|"
    r"hospital|medical\s+center|ministr(?:y|ies)|"
    r"ncmec|national\s+center\s+for\s+missing|"
    r"honeywell|federal\s+crime\s+victims\s+fund",
    re.I,
)


def _is_counted_law_enforcement_agency(label: str) -> bool:
    """True for police, sheriffs, prosecutors, investigators, task forces, custody.

    Fire, child-welfare, education, public-health, and generic cabinet departments
    without a criminal-investigative mandate are excluded from the public count.
    """
    t = (label or "").strip()
    if not t:
        return False
    low = t.casefold()
    if _NON_LE_DROP_RE.search(t) and not _NON_LE_OVERRIDE_RE.search(t):
        return False
    if _LE_CORE_RE.search(t) or _LE_ACRONYM_RE.search(t) or _LE_RESCUE_RE.search(t):
        return True
    if low in {
        "georgia bureau",
        "federal bureau of",
        "federal investigation agency",
        "texas department of safety",
        "u.s. investigation and customs enforcement",
        "drug enforcement agency",
        "illinois high tech crimes bureau",
        "illinois sexually violent persons bureau",
        "financial & computer crimes bureau",
        "financial and computer crimes bureau",
        "human trafficking bureau",
        "gangs & organized crime bureau",
        "westshore enforcement bureau",
        "mississippi bureau of narcotics",
        "bureau of identification",
        "minnesota bureau of apprehension",
        "university of iowa department of campus safety",
        "idaho department of fish and game",
        "georgia department of natural resources",
        "louisiana department of wildlife and fisheries",
        "environmental protection agency",
        "u.s. environmental protection agency",
    }:
        return True
    return False


def _tidy_distinct_agency_label(label: str) -> str | None:
    """Collapse field-office aliases and drop non-LE labels for corpus unique counts."""
    t = (label or "").strip().lstrip("#-_ ").strip()
    if not t:
        return None
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"'s$", "", t)
    t = re.sub(r"\bDivison\b", "Division", t, flags=re.I)
    t = re.sub(r"\blnvestigation\b", "Investigation", t, flags=re.I)
    t = _DISTINCT_AGENCY_ALIASES.get(t.casefold(), t)
    low = t.casefold()
    if "resident agency" in low:
        t = "FBI"
        low = "fbi"
    elif re.search(r"field office", low) and (
        "child exploitation" in low or "fbi" in low or low.endswith("field office")
    ):
        t = "FBI"
        low = "fbi"
    elif "federal bureau of" in low and "investigation" in low:
        t = "FBI"
        low = "fbi"
    elif re.search(r"\bfbi\b", low) and not re.search(
        r"police|sheriff|prosecutor|hsi|task\s*force", low
    ):
        t = "FBI"
        low = "fbi"
    elif (
        (
            "firearms" in low
            and ("alcohol" in low or "tobacco" in low or "explosives" in low)
        )
        or low.startswith("bureau of alcohol")
    ) and not re.search(r"police|sheriff|parole|probation|task\s*force", low):
        t = "ATF"
        low = "atf"
    elif "bureau of prisons" in low:
        t = "Bureau of Prisons"
        low = t.casefold()
    elif re.search(r"\bhsi\b", low) and not re.search(
        r"police|sheriff|\bpd\b|task\s*force", low
    ):
        t = "HSI"
        low = "hsi"
    elif low in {"u.s. dhs", "u.s. department of homeland security"}:
        t = "Department of Homeland Security"
        low = t.casefold()
    elif "immigration and customs" in low or "investigation and customs enforcement" in low:
        t = "U.S. Immigration and Customs Enforcement"
        low = t.casefold()
    elif "justice department" in low and "announce" not in low:
        t = FEDERAL_DOJ_CANONICAL
        low = t.casefold()
    if "announce" in low:
        return None
    if low in _BARE_GENERIC_AGENCY_LABELS or low in _NON_AGENCY_LABELS:
        return None
    if _PERSON_AGENCY_RE.match(t) or re.match(r"^a\s+", t, re.I) or re.match(r"^\d", t):
        return None
    if "court" in low and "marshal" not in low and "police" not in low:
        return None
    if "federal express" in low or "honeywell" in low:
        return None
    if len(t) < 3:
        return None
    if not _is_counted_law_enforcement_agency(t):
        return None
    return t


def distinct_named_agencies(labels: Iterable[str]) -> List[str]:
    """Unique law-enforcement agencies after ingest normalize and alias collapse.

    Splits glued labels, applies storage canonicalization (FBI/ICAC/DOJ/USAO),
    collapses FBI resident/field offices to FBI, and drops unlabeled generics,
    person names, courts, and non-LE orgs (fire, child-welfare, education).
    Used for the public distinct-agency count.
    """
    expanded: List[str] = []
    for label in labels:
        if label and str(label).strip():
            expanded.extend(normalize_agency_label_for_ingest(str(label)))
    expanded = drop_non_le_agencies(dedupe_generic_state_police(expanded))
    kept: Dict[str, str] = {}
    for raw in expanded:
        tidy = _tidy_distinct_agency_label(raw)
        if tidy is None:
            continue
        kept[tidy.casefold()] = tidy
    return sorted(kept.values(), key=str.casefold)


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
