"""
Extract explicit perpetrator admissions from ICAC case narrative text.

Identifies attributed offender speech (direct quotes and tight paraphrases) about
harm, recidivism, sexual interest, technology use, or minimization.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

QUOTE_MAX = 250
CONTEXT_MAX = 140
LOOKBACK = 280

_ICAC_TOPICS = frozenset({"csam", "enticement", "sextortion", "trafficking", "ai_csam"})

_ICAC_CONTEXT_RE = re.compile(
    r"\b("
    r"child|children|minor|minors|juvenile|underage|"
    r"csam|pornograph|molest|groom|lure|entic|sextort|traffick|"
    r"sexual\s+(?:abuse|conduct|exploit)|"
    r"predator|icac|cybertip|victim"
    r")\b",
    re.I,
)

_PERP_ROLE = (
    r"(?:the[ ]+)?(?:suspect|defendant|offender|perpetrator|accused|"
    r"teacher|pastor|minister|youth[ ]+minister|coach|"
    r"man|woman|boy|girl)"
)
# Proper names only (4+ chars excludes "The", "And", etc.)
_PERP_NAME = r"[A-Z][a-z]{4,}(?:[ ]+[A-Z][a-z]{2,}){0,2}"
_PERP_NOUN = rf"(?:{_PERP_ROLE}|{_PERP_NAME})"

_AUTHORITY = (
    r"(?:detectives?|investigators?|police|agents?|authorities|"
    r"deputies|troopers|the\s+FBI|FBI|ICE|CBP|prosecutors?)"
)

# Hard reject: victim/family/official attribution in the local window before the match.
_EXCLUSION_RES: Tuple[re.Pattern, ...] = (
    re.compile(
        r"\b(?:victim|survivor|minor|child|girl|boy|"
        r"mother|father|wife|husband|parent|family)\s+(?:said|stated|told)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:Judge|Prosecutor|Attorney|Special\s+Agent|Detective|Officer)\s+"
        r"[A-Z][a-z]+\s+(?:said|stated|wrote)\b",
    ),
    re.compile(r"\bprosecutors?\s+(?:said|stated)\b", re.I),
    re.compile(r"\baccording\s+to\s+(?:the\s+)?(?:affidavit|complaint|court)\b", re.I),
)

# Non-ICAC plea topics — reject when quote/window matches and no ICAC topic on case.
_NON_ICAC_OFFENSE_RE = re.compile(
    r"\b(?:tax(?:able|ation)?|rental\s+income|obscen(?:e|ity)\s+(?:matter|business|"
    r"video\s+arcade)|arcade\s+operations?|credit\s+card\s+billing)\b",
    re.I,
)

_META_QUOTE_RE = re.compile(
    r"\b(?:read\s+a\s+portion|court\s+documents|additional\s+investigations|"
    r"according\s+to|affidavit\s+states|investigation\s+revealed|"
    r"Press\s+Releases?\s+Page)\b",
    re.I,
)

_FIRST_PERSON_RE = re.compile(r"\b(I|my|me|myself)\b")

_THEME_RES: Tuple[Tuple[str, re.Pattern], ...] = (
    (
        "recidivism_escalation",
        re.compile(
            r"\b(out\s+of\s+control|will\s+continue|continue\s+to|habit|addiction|"
            r"can['\u2019]?t\s+stop|dangerous\s+person|again|keep\s+doing)\b",
            re.I | re.S,
        ),
    ),
    (
        "sexual_interest",
        re.compile(
            r"\b(attracted|aroused|lust(?:ing|ed)?|sexually\s+attracted|"
            r"interest\s+in\s+(?:children|minors)|pedophil|prefer(?:red|s)?\s+.*(?:child|minor|girl|boy))\b",
            re.I | re.S,
        ),
    ),
    (
        "tech_use",
        re.compile(
            r"\b(kik|discord|snapchat|instagram|facebook|telegram|whatsapp|"
            r"account|app|download(?:ed|ing)?|upload(?:ed|ing)?|"
            r"dark\s+web|chat(?:ting|ted)?|messenger|wifi|wi-fi|email|internet)\b",
            re.I | re.S,
        ),
    ),
    (
        "harm_conduct",
        re.compile(
            r"\b(molest|abuse[d|s|ing]?|sexual(?:ly)?|lure[d|s|ing]?|groom(?:ed|ing)?|"
            r"possess(?:ed|ing|ion)?|porn(?:ography)?|csam|minor|victim|touch(?:ed|ing)?|"
            r"entic(?:ed|ement|ing)?|exploit)\b",
            re.I | re.S,
        ),
    ),
    (
        "minimization",
        re.compile(
            r"\b(only\s+adult|didn['\u2019]?t\s+know|denied|unaware|"
            r"adult\s+porn(?:ography)?|not\s+guilty|thought\s+(?:she|he)\s+was)\b",
            re.I | re.S,
        ),
    ),
)

_PRON_THAT_WAS = r"(?:that\s+)?(?:(?:he|she)\s+(?:was\s+)?)?"
_PRON_THAT = r"(?:that\s+)?(?:(?:he|she)\s+)?"
_FRAME_PATTERNS: Tuple[Tuple[str, str, re.Pattern], ...] = (
    (
        "told_authority",
        "direct",
        re.compile(
            rf"\b{_PERP_NOUN}\s+told\s+{_AUTHORITY}\s*[:,]?\s*"
            rf'[""\u201c\u2018]([^""\u201d\u2019]{{8,{QUOTE_MAX}}})',
            re.I | re.S,
        ),
    ),
    (
        "perp_proximate_admitted_quote",
        "direct",
        re.compile(
            rf"\b{_PERP_NOUN}\b[^.]{{0,100}}?\badmit(?:ted|s|ting)\s+(?:that\s+)?"
            rf"{_PRON_THAT_WAS}"
            rf'[""\u201c\u2018]([^""\u201d\u2019]{{8,{QUOTE_MAX}}})',
            re.I | re.S,
        ),
    ),
    (
        "admitted_quote",
        "direct",
        re.compile(
            rf"\b{_PERP_NOUN}\s+admit(?:ted|s|ting)\s+{_PRON_THAT_WAS}"
            rf'[""\u201c\u2018]([^""\u201d\u2019]{{8,{QUOTE_MAX}}})',
            re.I | re.S,
        ),
    ),
    (
        "admitted_because_quote",
        "direct",
        re.compile(
            rf"\b{_PERP_NOUN}\s+admit(?:ted|s|ting)\s+{_PRON_THAT}"
            rf"[^.]{{0,160}}?\bbecause\s+"
            rf'[""\u201c\u2018]([^""\u201d\u2019]{{8,{QUOTE_MAX}}})',
            re.I | re.S,
        ),
    ),
    (
        "stated_became_quote",
        "direct",
        re.compile(
            rf"\b{_PERP_NOUN}\b[^.]{{0,220}}?\bstated\b[^.]{{0,100}}?\bbecame\s+a\s+"
            rf'[""\u201c\u2018]([^""\u201d\u2019]{{4,{QUOTE_MAX}}})',
            re.I | re.S,
        ),
    ),
    (
        "stated_quote",
        "direct",
        re.compile(
            rf"\b{_PERP_NOUN}\s+stated\s+{_PRON_THAT}"
            rf'[""\u201c\u2018]([^""\u201d\u2019]{{8,{QUOTE_MAX}}})',
            re.I | re.S,
        ),
    ),
    (
        "confessed_quote",
        "direct",
        re.compile(
            rf"\b{_PERP_NOUN}\s+confess(?:ed|es|ing)\s+{_PRON_THAT}"
            rf'[""\u201c\u2018]([^""\u201d\u2019]{{8,{QUOTE_MAX}}})',
            re.I | re.S,
        ),
    ),
    (
        "post_miranda",
        "direct",
        re.compile(
            r"\bpost[- ]?miranda\b[^.]{0,160}?"
            r"(?:admit(?:ted|s|ting)|confess(?:ed|es|ing)|stated)\b[^.]{0,80}?"
            rf'[""\u201c\u2018]([^""\u201d\u2019]{{8,{QUOTE_MAX}}})',
            re.I | re.S,
        ),
    ),
    (
        "he_admitted_quote",
        "direct",
        re.compile(
            rf"\b(?:He|She)\s+admit(?:ted|s|ting)\s+{_PRON_THAT_WAS}"
            rf'[""\u201c\u2018]([^""\u201d\u2019]{{8,{QUOTE_MAX}}})',
            re.I | re.S,
        ),
    ),
    (
        "admitted_he_she",
        "paraphrase",
        re.compile(
            rf"\b{_PERP_NOUN}\s+admit(?:ted|s|ting)\s+(?:he|she)\s+([^.]{{12,200}})",
            re.I | re.S,
        ),
    ),
    (
        "admitted_to",
        "paraphrase",
        re.compile(
            rf"\b{_PERP_NOUN}\b[^.]{{0,60}}?\badmit(?:ted|s|ting)\s+to\s+([^.]{{12,200}})",
            re.I | re.S,
        ),
    ),
    (
        "admitted_paraphrase",
        "paraphrase",
        re.compile(
            rf"\b{_PERP_NOUN}\s+admit(?:ted|s|ting)\s+{_PRON_THAT}"
            r"((?:was|had|only|would|could|wanted|used|downloaded|uploaded|shared|"
            r"molested|abused|lured|groomed|possessed|viewed|confessed\s+to)[^.]{8,200})",
            re.I | re.S,
        ),
    ),
    (
        "confessed_paraphrase",
        "paraphrase",
        re.compile(
            rf"\b{_PERP_NOUN}\s+confess(?:ed|es|ing)\s+{_PRON_THAT}"
            r"([^.]{12,200})",
            re.I | re.S,
        ),
    ),
    (
        "said_paraphrase",
        "paraphrase",
        re.compile(
            rf"\b{_PERP_NOUN}\s+said\s+(?:that\s+)?(?:he|she)\s+([^.]{{12,200}})",
            re.I | re.S,
        ),
    ),
    (
        "he_admitted_paraphrase",
        "paraphrase",
        re.compile(
            rf"\b(?:He|She)\s+admit(?:ted|s|ting)\s+{_PRON_THAT}"
            r"([^.]{12,200})",
            re.I | re.S,
        ),
    ),
    (
        "he_said_paraphrase",
        "paraphrase",
        re.compile(
            r"\b(?:He|She)\s+(?:also\s+)?said\s+(?:that\s+)?(?:he|she)\s+([^.]{12,200})",
            re.I | re.S,
        ),
    ),
    (
        "interview_admit_quote",
        "direct",
        re.compile(
            r"\b(?:in\s+an?\s+interview|during\s+(?:an?\s+)?interview|while\s+being\s+interviewed)"
            r"[^.]{0,120}?\b(?:admit(?:ted|s|ting)|confess(?:ed|es|ing))\b"
            r"[^.]{0,120}?"
            rf'[""\u201c\u2018]([^""\u201d\u2019]{{4,{QUOTE_MAX}}})',
            re.I | re.S,
        ),
    ),
)

_PERP_LOOKBACK_RE = re.compile(
    rf"\b(?:suspect|defendant|offender|perpetrator|accused|{_PERP_NAME})\b",
    re.I,
)


def _normalize_space(text: str) -> str:
    text = re.sub(r"\s+", " ", text.strip())
    text = text.strip(" \t,;.")
    # Trim journalistic tail clutter from paraphrase captures.
    text = re.split(r"\s+,\s*court records\b", text, maxsplit=1, flags=re.I)[0]
    text = re.split(r"\s+and\s+stated\b", text, maxsplit=1, flags=re.I)[0]
    return text.strip(" \t,;.")


def _trim(text: str, max_len: int) -> str:
    text = _normalize_space(text)
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _case_topics_set(case: Dict[str, Any], case_topics: Optional[List[str]]) -> Set[str]:
    if case_topics is not None:
        return {str(t).lower() for t in case_topics}
    raw = case.get("case_topics") or []
    if isinstance(raw, str):
        return {raw.lower()} if raw else set()
    return {str(t).lower() for t in raw}


def _has_icac_topic(topics: Set[str]) -> bool:
    return bool(topics & _ICAC_TOPICS)


def _icac_context(text: str) -> bool:
    return bool(_ICAC_CONTEXT_RE.search(text))


def _is_excluded_window(window: str) -> bool:
    # Attribution errors: victim/official voice immediately before the admission frame.
    narrow = window[-90:]
    attribution_excl = (
        _EXCLUSION_RES[0],
        _EXCLUSION_RES[1],
        _EXCLUSION_RES[2],
    )
    return any(p.search(narrow) for p in attribution_excl)


def _perp_attributed(window: str, frame: str) -> bool:
    if frame in (
        "told_authority",
        "admitted_quote",
        "admitted_because_quote",
        "perp_proximate_admitted_quote",
        "stated_quote",
        "stated_became_quote",
        "confessed_quote",
        "admitted_paraphrase",
        "confessed_paraphrase",
        "said_paraphrase",
        "admitted_he_she",
        "admitted_to",
        "interview_admit_quote",
    ):
        return True
    if frame.startswith("he_") or frame == "post_miranda":
        return bool(_PERP_LOOKBACK_RE.search(window))
    return False


# --- Speaker check for the "said" frames -------------------------------------
# "<X> said he ..." is an admission only when X is the charged person. The frame
# itself is compiled case-insensitively, so its name slot matches any word
# ("Authorities", "after", "judge"); the speaker is re-read here from the text.

_SAID_FRAMES = frozenset({"said_paraphrase", "he_said_paraphrase"})

_NAME_TOK = r"(?-i:[A-Z][a-zA-Z\u2019'\-]*[a-z])"
_TITLE_WORDS = (
    r"(?-i:Sheriff|Chief|Detective|Det\.|Officer|Agent|Attorney|Judge|Justice|Lt\.|Lieutenant|"
    r"Sgt\.|Sergeant|Deputy|Investigator|Inspector|Trooper|Capt\.|Captain|Cpl\.|Corporal|Prosecutor|"
    r"Director|Commissioner|Mayor|Superintendent|Principal|Councilman|Councilwoman|Sen\.|Rep\.|Gov\.|"
    r"Lt\.|Major|Colonel|Constable|Marshal|Commander|Spokesperson|Spokesman|Spokeswoman)"
)
_CHARGE_VERB = (
    r"(?:arrested|charged|indicted|sentenced|convicted|booked|extradited|jailed|detained|"
    r"accused|arraigned|pleaded|pled|pleads|enters|entered|faces|facing|faced|admitted|admits|"
    r"confessed|allegedly|reportedly|uploaded|distributed|possessed|downloaded|produced|enticed|coerced|told\s+(?:investigators|police|detectives|agents|officers|deputies|"
    r"authorities|troopers))"
)
_CHARGED_RES: Tuple[re.Pattern, ...] = (
    re.compile(
        rf"(?<![\w.])({_NAME_TOK})(?:,?\s+(?:Jr|Sr|II|III|IV)\.?)?"
        rf"(?:,\s*(?:a\s+|age\s+)?\d{{1,2}}(?:-year-old)?,?)?(?:\s+of\s+{_NAME_TOK}(?:\s+{_NAME_TOK})?,?)?\s+"
        rf"(?:(?:was|is|has\s+been|had\s+been|were|also|later|then|previously|further|initially|"
        rf"subsequently|ultimately|now)\s+){{0,2}}{_CHARGE_VERB}\b",
        re.I,
    ),
    re.compile(
        rf"(?<![\w.])({_NAME_TOK})(?:,?\s+(?:Jr|Sr|II|III|IV)\.?)?,\s*(?:age\s+)?\d{{1,2}}(?:,|\s+of\b)", re.I
    ),
    re.compile(
        rf"(?<![\w.])({_NAME_TOK})(?:\u2019s|'s)\s+(?:\w+\s+)?(?:home|residence|house|apartment|phone|iPhone|"
        rf"computer|laptop|devices?|dorm|arrest|bond|bail|attorney|lawyer|defense|sentencing|plea|indictment)\b"
    ),
    re.compile(rf"\b\d{{1,2}}-year-old\s+(?:{_NAME_TOK}\.?\s+){{1,3}}?({_NAME_TOK})\b(?!\s+(?:{_NAME_TOK}))"),
    re.compile(
        rf"\b(?:arrested|charged|indicted|sentenced|convicted|defendant|suspect|accused|booked|"
        rf"identified\s+as)\s+(?:{_NAME_TOK}\.?\s+){{0,3}}({_NAME_TOK})\b",
        re.I,
    ),
)
_TITLED_NAME_RE = re.compile(rf"{_TITLE_WORDS}\s+(?:{_NAME_TOK}\.?\s+){{0,2}}({_NAME_TOK})\b")
_PERP_ROLE_WORDS = frozenset({"suspect", "defendant", "offender", "perpetrator", "accused"})
_SAID_ADVERBS = frozenset({
    "also", "later", "then", "allegedly", "reportedly", "further", "previously", "initially",
    "repeatedly", "once", "first", "again", "eventually", "subsequently", "had", "has", "reportedly,",
})
_LINK_WORDS = frozenset({"and", "but", "who", "where", "he", "she", "him", "her"})
_HEARSAY_ADVERBS = frozenset({"allegedly", "reportedly"})
_SENT_END_RE = re.compile(r"[.!?][\"\u201d\u2019]?\s")
_SPEAKER_POS_RE = re.compile(
    rf"(?:\b({_NAME_TOK})|\b(police|authorities|officials?|investigators?|detectives?|deputies|officers?|"
    rf"agents?|prosecutors?|troopers?|chief|sheriff|judge|attorney|lawyer|spokes\w+|mayor|she|her|"
    rf"woman|mother|wife|daughter|girl|victim|witness(?:es)?|neighbou?rs?|friends?|relatives?|family))"
    rf"\s+(?:also\s+|later\s+|then\s+)?(?:said|says|stated|told|wrote|testified|reported)\b",
)


def _charged_surnames(text: str) -> Set[str]:
    """Surnames the text puts next to an arrest, charge, plea, sentence or age apposition."""
    out: Set[str] = set()
    for pat in _CHARGED_RES:
        for m in pat.finditer(text):
            tok = m.group(1).replace("\u2019s", "").replace("'s", "")
            if len(tok) > 2:
                out.add(tok)
    return out


def _antecedent_is_perp(text: str, pos: int, charged: Set[str], reach: int = 320) -> bool:
    """Is the nearest preceding person the charged one (not an official, witness or victim)?"""
    window = text[max(0, pos - reach) : pos]
    refs: List[Tuple[int, bool]] = []
    for name in charged:
        for m in re.finditer(rf"(?<![\w.]){re.escape(name)}\b", window):
            refs.append((m.start(), True))
    for m in re.finditer(
        r"\b(?:suspect|defendant|offender|perpetrator|accused|interviewed,?\s+(?:he|she)|(?:he|she)\s+(?:also\s+|later\s+)?"
        r"(?:told|admitted|confessed|stated|denied|claimed))\b",
        window,
        re.I,
    ):
        refs.append((m.start(), True))
    for m in _SPEAKER_POS_RE.finditer(window):
        tok = m.group(1) or m.group(2) or ""
        if tok in charged or tok.lower() in ("he", "him"):
            continue
        refs.append((m.start(), False))
    for m in _TITLED_NAME_RE.finditer(window):
        refs.append((m.start(), False))
    if not refs:
        return reach < 1500 and _antecedent_is_perp(text, pos, charged, 1500)
    return max(refs)[1]


_LEAD_WORDS = frozenset({
    "During", "In", "After", "When", "While", "According", "Upon", "On", "At", "Once", "Following",
    "Before", "Later", "However", "Then", "Also", "Additionally", "Further", "Furthermore", "Since",
})


def _mostly_male(text: str) -> bool:
    male = len(re.findall(r"\b(?:he|his|him)\b", text, re.I))
    female = len(re.findall(r"\b(?:she|her|hers)\b", text, re.I))
    return male > 2 * female


def _clause_subject_is_perp(tokens: List[str], text: str, pos: int, charged: Set[str]) -> bool:
    """Subject of "<subject> ... and said he": the last name or pronoun in the clause that a verb follows."""
    subject = None
    for i, tok in enumerate(tokens[:-1]):
        t = tok.strip(",;:\u201c\"(")
        nxt = tokens[i + 1].strip(",;:")
        if t.endswith(("\u2019s", "'s")) or not nxt or not nxt[0].islower() or nxt in _NOT_VERBS:
            continue
        if t.lower() in ("he", "she") or t.lower() in _PERP_ROLE_WORDS or (
            t not in _LEAD_WORDS and re.fullmatch(_NAME_TOK, t)
        ):
            subject = t
    if subject is None:
        return False
    if subject in charged or subject.lower() in _PERP_ROLE_WORDS:
        return True
    if subject.lower() in ("he", "she"):
        return _antecedent_is_perp(text, pos, charged)
    return False  # another named speaker, "His biography describes", "McConnell argued"


_NOT_VERBS = frozenset({"of", "to", "and", "or", "the", "a", "an", "in", "on", "at", "for", "with", "by", "from"})


def _said_speaker_ok(text: str, said_pos: int, inner_pronoun: str, charged: Set[str]) -> bool:
    """True when the speaker of ``... said he|she`` at ``said_pos`` is the charged person."""
    sent_start = 0
    for m in _SENT_END_RE.finditer(text, max(0, said_pos - 400), said_pos):
        sent_start = m.end()
    before = text[sent_start:said_pos].replace("\u201d", " ").replace('"', " ").split()
    hearsay = False
    while before and before[-1].lower().strip(",") in _SAID_ADVERBS:
        hearsay = hearsay or before[-1].lower().strip(",") in _HEARSAY_ADVERBS
        before.pop()
    if not before:
        return False
    head = before[-1].strip(",;:")
    low = head.lower()
    if low in ("he", "she"):
        if low != inner_pronoun.lower():
            return False  # "She said he ..." is someone else talking about him
        if low == "she" and _mostly_male(text):
            return False  # a woman speaking in a case about a man: witness, victim or official
        if hearsay:
            return True  # "He allegedly said he ..." reports the accused, not an official
        return _antecedent_is_perp(text, said_pos, charged)
    if low in _PERP_ROLE_WORDS or re.fullmatch(r"\d{1,2}-year-old", low):
        return True
    if low in _LINK_WORDS:
        if low == "who" and len(before) > 1:
            prev = before[-2].strip(",")
            aged_man = prev in ("man", "woman") and any(re.fullmatch(r"\d{1,2}-year-old", w) for w in before[-6:-2])
            return prev in charged or aged_man
        if low in ("and", "but"):
            return _clause_subject_is_perp(before[:-1], text, said_pos, charged)
        return _antecedent_is_perp(text, said_pos, charged)
    if not re.fullmatch(_NAME_TOK, head):
        return False  # police, judge, attorney, woman, task force, reports ...
    surname = head.replace("\u2019s", "").replace("'s", "")
    if head.endswith(("\u2019s", "'s")):
        return False  # "Kucharski's attorney said"
    if len(before) > 1 and re.fullmatch(_TITLE_WORDS, before[-2].strip(",")):
        return False
    if any(w.lower() == "who" for w in before[:-1]):
        return False  # "A counselor who had been working with <name> said he ..."
    return surname in charged


def _classify_themes(quote: str) -> List[str]:
    themes = [name for name, pat in _THEME_RES if pat.search(quote)]
    return themes or ["other"]


def _confidence(
    frame: str,
    quote_type: str,
    quote: str,
) -> Optional[str]:
    if _META_QUOTE_RE.search(quote):
        return None
    if quote_type == "direct":
        if frame in ("told_authority", "post_miranda", "admitted_because_quote", "stated_became_quote", "perp_proximate_admitted_quote"):
            return "high"
        if _FIRST_PERSON_RE.search(quote):
            return "high"
        return "high"
    # paraphrase
    if frame in ("interview_admit_quote", "admitted_paraphrase", "confessed_paraphrase", "admitted_to", "admitted_he_she"):
        return "medium"
    if frame in ("said_paraphrase", "he_said_paraphrase", "he_admitted_paraphrase"):
        return "medium"
    return "medium"


def _extract_quote_from_match(match: re.Match) -> str:
    for i in range(1, (match.lastindex or 0) + 1):
        g = match.group(i)
        if g and g.strip():
            return _normalize_space(g)
    return ""


def extract_perpetrator_admissions(
    case: Dict[str, Any],
    case_topics: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Extract structured perpetrator admission records from case narrative.

    Args:
        case: Case dict with ``case_text`` (or nested in ``raw_data``).
        case_topics: Optional pre-computed topic list (avoids re-scanning).

    Returns:
        List of admission dicts with quote, frame, themes, confidence, context.
    """
    case_text = case.get("case_text") or ""
    if not case_text:
        raw = case.get("raw_data")
        if isinstance(raw, dict):
            case_text = raw.get("case_text") or ""
    if not case_text or len(case_text) < 80:
        return []

    topics = _case_topics_set(case, case_topics)
    has_topic = _has_icac_topic(topics)

    seen: Set[str] = set()
    results: List[Dict[str, Any]] = []
    charged: Optional[Set[str]] = None

    for frame, quote_type, pattern in _FRAME_PATTERNS:
        for match in pattern.finditer(case_text):
            quote = _trim(_extract_quote_from_match(match), QUOTE_MAX)
            min_len = 4 if quote_type == "direct" else 10
            if len(quote) < min_len:
                continue

            start = match.start()
            window_start = max(0, start - LOOKBACK)
            window_end = min(len(case_text), match.end() + 80)
            window = case_text[window_start:window_end]
            local_before = case_text[max(0, start - 150) : start + 20]

            if _is_excluded_window(local_before):
                continue
            if not _perp_attributed(window, frame):
                continue
            if frame in _SAID_FRAMES:
                said = re.search(r"\bsaid\s+(?:that\s+)?(he|she)\b", match.group(0), re.I)
                if charged is None:
                    charged = _charged_surnames(case_text)
                if not said or not _said_speaker_ok(case_text, start + said.start(), said.group(1), charged):
                    continue
            if _META_QUOTE_RE.search(quote):
                continue

            context_blob = _normalize_space(window)
            icac_ok = has_topic or _icac_context(quote) or _icac_context(context_blob)
            if not icac_ok:
                continue
            if _NON_ICAC_OFFENSE_RE.search(context_blob) and not has_topic:
                continue
            if quote_type == "paraphrase" and not (
                has_topic or _icac_context(quote) or _icac_context(context_blob[:200])
            ):
                continue

            confidence = _confidence(frame, quote_type, quote)
            if confidence is None:
                continue

            dedup_key = quote[:60].lower()
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            context_start = max(0, start - 90)
            context = _trim(case_text[context_start:start] + match.group(0), CONTEXT_MAX)

            results.append(
                {
                    "quote": quote,
                    "quote_type": quote_type,
                    "frame": frame,
                    "themes": _classify_themes(quote),
                    "confidence": confidence,
                    "context": context,
                }
            )

    return results


def perpetrator_admission_themes(admissions: List[Dict[str, Any]]) -> List[str]:
    """Flat deduped theme list for faceting/filter."""
    themes: Set[str] = set()
    for rec in admissions:
        for t in rec.get("themes") or []:
            if t and t != "other":
                themes.add(t)
    return sorted(themes)
