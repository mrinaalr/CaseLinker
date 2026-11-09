"""
Regex assertion producers (evidence family ``surface_pattern``) for CaseLinker 3.0.

Each producer returns raw assertions (field, method, value, role, span) over the
original case_text. Roles come from lexical evidence attached to the mention,
never from the numeric value: a 17 can be a defendant, an 18 a statutory threshold.
All assertions are gated in assertions.gate_assertion before use.

Existing 2.x gates are reused as validators here (comma-age false-positive
filters, URL-junk and sentencing-anchor checks, the victim-age gate v2).
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

_PATTERN_LAYER = Path(__file__).resolve().parent
_PROCESSING_LAYER = _PATTERN_LAYER.parent
for _p in (_PROCESSING_LAYER / "field_assertions", _PROCESSING_LAYER, _PATTERN_LAYER, _PROCESSING_LAYER / "ML Processing Layer"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import span_gate as sg  # noqa: E402

_spec = importlib.util.spec_from_file_location("pattern_processing", _PATTERN_LAYER / "processing.py")
_pp = importlib.util.module_from_spec(_spec)
assert _spec.loader
_spec.loader.exec_module(_pp)

REGEX_VERSION = "regex_3.0.1"
GATE_VERSION = "victim_age_gate_v2"

# ---------------------------------------------------------------------------
# Shared lexicons
# ---------------------------------------------------------------------------

VICTIM_NOUNS = (
    r"victims?|girls?|boys?|child(?:ren)?|minors?|juveniles?|daughters?|sons?|step-?daughters?|step-?sons?|"
    r"nieces?|nephews?|granddaughters?|grandsons?|students?|teens?|teenagers?|toddlers?|infants?|bab(?:y|ies)|"
    r"(?:fe)?male\s+(?:victims?|child(?:ren)?|juveniles?|minors?|students?)|youths?|kids?|preteens?|sisters?|brothers?"
)
ADULT_NOUNS = (
    r"man|men|woman|women|adults?|residents?|defendants?|suspects?|offenders?|teachers?|coach(?:es)?|"
    r"priests?|pastors?|officers?|deputy|deputies|employees?|nurses?|doctors?|stepfathers?|fathers?|"
    r"grandfathers?|uncles?|boyfriends?|husbands?|soldiers?|sailors?|airm[ae]n|marines?|inmates?|"
    r"registered\s+sex\s+offenders?|sex\s+offenders?|predators?|truck\s+drivers?|bus\s+drivers?|youth\s+pastors?"
)
_DEFENDANT_VERBS = (
    r"arrested|charged|sentenced|pleaded|pled|convicted|indicted|admitted|confessed|booked|faces|"
    r"accused|found\s+guilty|received\s+the\s+(?:prison\s+)?(?:term|sentence)|surrendered|extradited|arraigned"
)
_LE_CUES = re.compile(
    r"\b(?:undercover|officers?|agents?|deput(?:y|ies)|detectives?|police|investigators?|sting|task\s+force|"
    r"law\s+enforcement|sheriff'?s?|troopers?|FBI|HSI|ICAC|KCSO|decoys?|special\s+agent|Net\s+Nanny)\b",
    re.IGNORECASE,
)
_NOT_PERSON_FIRST = frozenset(
    t.lower() for t in (
        "The", "A", "An", "He", "She", "They", "His", "Her", "Police", "Officers", "Authorities", "Judge",
        "Attorney", "Court", "County", "State", "District", "Department", "Office", "Sheriff", "Count",
        "Case", "Source", "Publication", "January", "February", "March", "April", "May", "June", "July",
        "August", "September", "October", "November", "December", "Monday", "Tuesday", "Wednesday",
        "Thursday", "Friday", "Saturday", "Sunday", "In", "On", "At", "By", "For", "From", "Of", "And",
        "U.S", "United", "Federal", "This", "That", "These", "Those", "Investigators", "Detectives",
    )
) | _pp._COMMA_AGE_BLOCKLIST_FIRST_TOKEN
_VICTIM_ALIASES = re.compile(r"\b(?:Doe|Victim|Minor|Child|Juvenile)\b")

_NAME_RE = r"[A-Z][\w'’\-]*\.?(?:\s+[A-Z][\w'’\-]*\.?){0,4}"
_DEFENDANT_SUBJECT_RE = re.compile(
    rf"\b([A-Z][a-z'’\-]{{2,}})(?:\s+(?:Jr|Sr|II|III)\.?)?,?\s+(?:(?:[a-z]\w*|\d{{1,3}}),?\s+){{0,3}}?"
    rf"(?:was|were|is|has\s+been|had\s+been|has|had|will\s+be|also|later|then|previously)?\s*"
    rf"(?:{_DEFENDANT_VERBS})\b"
)


def defendant_surnames(text: str) -> Set[str]:
    """Capitalized tokens that appear as the subject of a defendant verb."""
    out: Set[str] = set()
    for m in _DEFENDANT_SUBJECT_RE.finditer(text):
        tok = m.group(1)
        if tok.lower() in _NOT_PERSON_FIRST or tok.isupper():
            continue
        out.add(tok.casefold())
    return out


def _name_tokens(name: str) -> List[str]:
    return [t.strip(".,;:\"'()[]") for t in name.split() if t.strip(".,;:\"'()[]")]


def _entity_is_defendant(name: str, defendants: Set[str]) -> bool:
    toks = [t for t in _name_tokens(name) if t.lower() not in ("jr", "sr", "ii", "iii")]
    return bool(toks) and toks[-1].casefold() in defendants


def _is_person_name(name: str) -> bool:
    toks = _name_tokens(name)
    if not toks:
        return False
    if toks[0].lower().rstrip(".") in _NOT_PERSON_FIRST:
        return False
    if all(t.isupper() and len(t) > 1 for t in toks):
        return False  # ALL-CAPS dateline ("LEXINGTON, Ky.")
    if len(toks) == 1 and len(toks[0]) <= 2:
        return False
    return not _pp._ROMAN_NUMERAL_TOKEN_RE.match(toks[-1])


def _raw(field: str, value, role: str, start: int, end: int, confidence: float,
         method: str = "regex", version: str = REGEX_VERSION, **extras) -> Dict:
    return {
        "field": field,
        "method": method,
        "method_version": version,
        "value": value,
        "role": role,
        "span_start": start,
        "span_end": end,
        "confidence": confidence,
        "extras": {k: v for k, v in extras.items() if v is not None},
    }


# ---------------------------------------------------------------------------
# Ages
# ---------------------------------------------------------------------------

_NUMBER_TOKEN_RE = re.compile(rf"(?<![\w$])({sg.NUMBER_RE})(?![\w])", re.IGNORECASE)


def age_mentions(text: str) -> List[Tuple[int, int, int, str]]:
    """Every age-shaped token: (start, end, age, shape). The candidate set for all families."""
    out = []
    for m in _NUMBER_TOKEN_RE.finditer(text):
        s, e = m.start(1), m.end(1)
        ok, shape = sg.age_support(text, s, e, None)
        if ok:
            out.append((s, e, sg.parse_number(m.group(1)), shape))
    return out


_STATUTORY_LEFT = re.compile(
    r"\b(?:under|younger\s+than|below|less\s+than|over|older\s+than)\s+(?:the\s+)?(?:age\s+of\s+|ages?\s+)?$", re.I
)
_STATUTORY_RIGHT = re.compile(r"^\s*(?:years?\s+(?:of\s+age\s+)?)?or\s+(?:younger|older|under)\b", re.I)
_AGE_OF_CONSENT_LEFT = re.compile(r"\bage\s+of\s+consent\s+(?:is|of)\s+$", re.I)
_PERSONA_LEFT = re.compile(
    r"\b(?P<verb>pos(?:e|es|ed|ing)|pretend(?:s|ed|ing)?\s+to\s+be|portray(?:s|ed|ing)?|purport(?:s|ed|ing)?\s+to\s+be"
    r"|claim(?:s|ed|ing)?\s+to\s+be|profile\s+of|persona\s+of|identif(?:y|ies|ied|ying)\s+(?:him|her|them)sel(?:f|ves)\s+as"
    r"|represent(?:s|ed|ing)?\s+(?:him|her|them)sel(?:f|ves)\s+as|(?:said|told\s+\w+|claimed|claiming|stated|lied\s+that)\s+(?:that\s+)?(?:he|she|they)\s+(?:was|were|is)"
    r"|believ(?:ed|ing)\s+(?:to\s+be|(?:he|she|they)\s+was|was)|thought\s+(?:was|to\s+be|(?:he|she|they)\s+was)"
    r"|fictitious|fictious|fictional|fake|purported|notional|non-?existent|imaginary)"
    r"\s+(?:as\s+)?(?:an?\s+|the\s+)?(?:(?!\d)[\w'’\-]+\s+){0,2}$",
    re.I,
)
_PERSONA_RIGHT = re.compile(r"^\W*(?:years?\W*olds?\W+)?(?:\w+\s+){0,2}?(?:decoys?|personas?|undercover|online\s+profile|fictitious)\b", re.I)
# "in which he believed he was communicating over the Internet with a thirteen-year-old girl":
# a belief verb earlier in the clause plus a sting/undercover cue in the sentence = decoy persona.
_BELIEVED_CLAUSE_LEFT = re.compile(r"\b(?:believ(?:ed|es|ing)|thought|thinking)\b[^.;:]{0,90}$", re.I)
# "whom he believed was the father of a nine-year-old boy" — the age is the persona's child,
# and the two-word persona window stops before "father of a".
_BELIEVED_PARENT_LEFT = re.compile(
    r"\bbeliev(?:ed|es|ing)\s+was\s+the\s+(?:father|mother|parent|dad|mom|guardian)\s+of\s+(?:a|an|the)\s+$",
    re.I,
)
_STING_CUES = re.compile(r"\b(?:undercover|sting|decoys?|posing|posed|pretend\w*|fictitious)\b", re.I)
_VICTIM_NOUN_EXACT = re.compile(r"\bvictims?\b", re.I)
_VICTIM_RIGHT = re.compile(
    rf"^\W*(?:years?\W*olds?\W*|months?\W*olds?\W*)?"
    rf"(?:(?!(?:on|in|of|for|with|at|by|from|to|and|or)\b)[A-Za-z'’\-]+\s+){{0,2}}?(?:{VICTIM_NOUNS})\b",
    re.I,
)
_ADULT_RIGHT = re.compile(rf"^\W*(?:years?\W*olds?\W*)?(?:[\w'’\-,]+\s+){{0,3}}?(?:{ADULT_NOUNS})\b", re.I)
_FEMALE_MALE_RIGHT = re.compile(r"^\W*(?:years?\W*olds?\W*)(?:fe)?male\b(?!\s+(?:suspect|defendant|offender|adult))", re.I)
_VICTIM_LEFT = re.compile(
    rf"\b(?:{VICTIM_NOUNS})(?:\s*,\s*|\s+)(?:an?\s+)?(?:who\s+)?(?:(?:was|is|were)\s+)?(?:then\s+)?(?:only\s+)?"
    r"(?:approximately\s+|about\s+|around\s+|just\s+)?(?:(?:between\s+the\s+)?ages?d?\s+(?:of\s+)?)?"
    rf"(?:{sg.NUMBER_RE}\s*(?:and|to|-|through)\s*)?$",
    re.I,
)
_JUVENILE_DEFENDANT_RIGHT = re.compile(
    rf"^\W*(?:years?\W*olds?\W*)?(?:\w+\s+){{0,2}}?(?:boy|girl|teen|teenager|juvenile|male|female|youth)\s+"
    rf"(?:was|were|has\s+been|is|had\s+been)\s+(?:also\s+)?(?:{_DEFENDANT_VERBS})\b",
    re.I,
)
_NAME_BEFORE_COMMA = re.compile(
    rf"({_NAME_RE})(?:,?\s+(?:Jr|Sr|II|III|IV)\.?)?\s*(?:,|\()\s*(?:(?:then|now|age|aged)\s+)?$"
)
# "charged Cesar Garcia (age 45)" — the verb is before the name, not after the number.
_CHARGED_PAREN_AGE = re.compile(
    rf"\b(?:charged|arrested|indicted|arraigned|booked)\s+{_NAME_RE}\s*\(\s*age[d]?\s*$",
    re.I,
)
_VICTIM_PAREN_AGE = re.compile(
    rf"\b(?:victim|minor|child)\b[^.]{{0,40}}\(\s*age[d]?\s*$",
    re.I,
)
# Adult or child victims named by the crime they suffered: "sexual assault of a 76-year-old woman"
_CRIME_OBJECT_LEFT = re.compile(
    r"\b(?:assault(?:ing)?|abus(?:e|ing)|rap(?:e|ing)|murder(?:ing)?|kill(?:ing)?|kidnapp?(?:ing)?|attack(?:ing)?"
    r"|robb(?:ery|ing)|exploit(?:ation|ing)|molest(?:ation|ing)|homicide|shooting|death|battery|stalking|trafficking)"
    r"\s+(?:of|on|against)\s+(?:a|an|the|his|her)\s+$",
    re.I,
)
# Headlines and ledes naming the arrestee by age: "ARREST OF 18-YEAR-OLD ON 40 COUNTS"
_ARREST_OF_LEFT = re.compile(
    r"\b(?:arrest(?:ed|s)?|charg(?:ed|es)|indict(?:ed|s)?|apprehend(?:ed)?|booked)\s+(?:of\s+)?(?:a|an|the)?\s*$", re.I
)
# "they discovered that the 40 year old dog groomer" / "the suspect was ... a 26 year old"
_DISCOVERED_THE_LEFT = re.compile(
    r"\b(?:discovered|learned|found|identified)\s+that\s+the\s+$", re.I
)
_SUSPECT_WAS_A_LEFT = re.compile(r"\bsuspect\s+was\b[^.]{0,60}\ba\s+$", re.I)
# "arrested two men ages 34 and 35"
_ARRESTED_AGES_LEFT = re.compile(
    r"\b(?:arrested|charged|indicted)\s+(?:(?:two|three|four|\d+)\s+)?"
    r"(?:men|women|males?|females?|suspects|individuals|people|defendants)\s+ages?\s+$",
    re.I,
)
_ARRESTED_AGES_HIGH_LEFT = re.compile(
    r"\b(?:arrested|charged|indicted)\b[^.]{0,50}\bages?\s+\d{1,2}\s+(?:and|to)\s+$",
    re.I,
)
_HAD_CHILD_RIGHT = re.compile(
    r"^\W*(?:years?\W*olds?\W*)(?:and\s+an?\s+\d{1,2}\s+years?\W*olds?\s+)?(?:daughter|son|child|stepdaughter|stepson)\b",
    re.I,
)
_VICTIM_RANGE_HIGH_LEFT = re.compile(
    r"\bvictims?,?\s+ages?\s+\d{1,2}\s+(?:thru|through|to|-)\s+$",
    re.I,
)
# "children and youth between the ages of 13 and 18" is a span, not two victims.
_BETWEEN_AGES_LEFT = re.compile(
    rf"\bbetween\s+the\s+ages?\s+of\s+(?:{sg.NUMBER_RE}\s+(?:and|to|through|thru|-)\s+)?$",
    re.I,
)
_COURT_NATIONAL_RIGHT = re.compile(
    r"years?\W*olds?\s+(?:\w+\s+){0,4}national\b[^.]{0,50}\b(?:court|appear|charged|arrest)",
    re.I,
)
_POTENTIAL_LEFT = re.compile(r"\b(?:access\s+to|potential(?:ly)?|possible|might\s+have|may\s+have)\b[^.;]{0,40}$", re.I)
# A single-letter initial ("Ronnie J. Alexander") is a name token.
_NAME_AFTER_YEAR_OLD = re.compile(r"^\W*years?\W*olds?\s+((?:[A-Z][\w'’\-]*\.?\s+){1,3}[A-Z][\w'’\-]+)")
_ANAPHOR_LEFT = re.compile(r"\b(?:the|this)\s+$", re.I)
_ANAPHOR_RIGHT = re.compile(r"^\W*years?\W*olds?\b(?!\s+(?:[a-z]+\s+){0,2}(?:" + VICTIM_NOUNS + r"|" + ADULT_NOUNS + r")\b)", re.I)
_DEFENDANT_CUE = re.compile(rf"\b(?:allegedly|admitted|confessed|told\s+(?:police|investigators|detectives|officers)|{_DEFENDANT_VERBS})\b", re.I)
_TIME_QUALIFIER_LEFT = re.compile(r"\b(?:then|at\s+the\s+time|when\s+(?:he|she|they)\s+was|was\s+then)\s+(?:\w+\s+)?$", re.I)
# "advised that the “child” was 13" after an undercover pose. The age is the persona, not a child in the case.
_DESCRIBED_CHILD_AGE = re.compile(
    r"\b(?:advised|told|informed)\s+that\s+(?:the\s+)?[\"'“”]?(?:child|minor|girl|boy)[\"'“”]?\s+(?:was|is|were)\s+$",
    re.I,
)


def _sting_within(text: str, s: int, e: int, chars: int = 800) -> bool:
    """A posing / undercover cue in the preceding stretch of this case, not a later one."""
    return bool(_STING_CUES.search(text[max(0, s - chars) : e]))


def _persona_role(text: str, s: int, e: int, verb: str) -> str:
    v = verb.lower()
    if v.startswith(("said", "told", "claim", "stated", "lied", "identif", "represent")):
        return "claimed"
    if v.startswith(("believ", "thought", "fict", "fake", "purport", "notional", "non", "imagin")):
        return "decoy"
    ss, se = sg.sentence_at(text, s, e)
    return "decoy" if _LE_CUES.search(text[ss:se]) else "claimed"


def age_role_lexical(text: str, s: int, e: int, shape: str, defendants: Set[str]) -> Tuple[str, float, Dict]:
    """Role for one age-shaped mention from lexical evidence attached to it."""
    cs, ce = sg.clause_at(text, s, e)
    left = sg.normalize_surface(text[max(cs, s - 120) : s])
    right = sg.normalize_surface(text[e : min(ce, e + 80)])
    extras: Dict = {"shape": shape}
    if _TIME_QUALIFIER_LEFT.search(left[-40:]):
        extras["time_qualifier"] = "then"

    if _STATUTORY_LEFT.search(left[-40:]) or _STATUTORY_RIGHT.match(right) or _AGE_OF_CONSENT_LEFT.search(left[-40:]):
        return "statutory_threshold", 0.9, extras
    persona = _PERSONA_LEFT.search(left[-80:])
    if persona:
        extras["persona_cue"] = persona.group("verb")
        return _persona_role(text, s, e, persona.group("verb")), 0.9, extras
    if _PERSONA_RIGHT.match(right):
        return "decoy", 0.85, extras
    if _BELIEVED_PARENT_LEFT.search(left[-90:]):
        extras["persona_cue"] = "believed_parent_of"
        return "decoy", 0.85, extras
    if _BELIEVED_CLAUSE_LEFT.search(left) and _STING_CUES.search(text[slice(*sg.sentence_at(text, s, e))]):
        extras["persona_cue"] = "believed+sting"
        return "decoy", 0.8, extras
    # "ages 4 thru 10" / "aged 6-9" / "4-6 years old" is one span, not one person per end.
    # Depicted material still excludes; it does not become a victim list.
    if sg.is_closed_age_range(text, s, e):
        if sg.is_depicted_material(text, s, e):
            return "depicted_in_material", 0.8, extras
        extras["weak"] = "age_range"
        return "unknown", 0.5, extras

    # Names: "Bryce Bock, 32," / "Shepherd, then 27 years-old" / "34-year-old Alvaro Rosas of Los Angeles"
    name = None
    after_name = right
    nm = _NAME_BEFORE_COMMA.search(left[-80:])
    if nm and shape in ("name_comma", "name_paren", "year_old", "age_word"):
        name = nm.group(1)
    else:
        am = _NAME_AFTER_YEAR_OLD.match(right)
        if am:
            name = am.group(1)
            after_name = right[am.end():]
    if name and _is_person_name(name):
        extras["entity"] = name.strip()
        if _VICTIM_ALIASES.search(name) or re.match(rf"^\s*,\s*(?:an?|the)\s+(?:{VICTIM_NOUNS})\b", right, re.I):
            return "victim", 0.8, extras
        if _VICTIM_PAREN_AGE.search(left[-90:]):
            return "victim", 0.8, extras
        if _CHARGED_PAREN_AGE.search(left[-120:]):
            return "perpetrator", 0.9, extras
        placed = rf"^\s*,?\s*(?:of|from)\s+[A-Z0-9]|^\s*,?\s*(?:was|were|is|has|had)\s+(?:\w+\s+)?(?:{_DEFENDANT_VERBS})\b"
        # "Smith, 32, of Phoenix" is on `right`. "34-year-old Alvaro Rosas of Los Angeles"
        # has the place after the name, not after the digits.
        if re.match(placed, right, re.I) or re.match(placed, after_name, re.I):
            return "perpetrator", 0.9, extras
        if _entity_is_defendant(name, defendants):
            return "perpetrator", 0.85, extras
        return "unknown", 0.5, extras

    if sg.is_depicted_material(text, s, e):
        return "depicted_in_material", 0.8, extras
    if sg.is_stated_preference(text, s, e):
        extras["weak"] = "stated_preference"
        return "unknown", 0.5, extras
    if _CRIME_OBJECT_LEFT.search(left[-60:]):
        # "assault of a 76-year-old woman" is an adult crime victim, not a CSEA child victim.
        if _ADULT_RIGHT.match(right):
            return "adult_crime_victim", 0.85, extras
        return "victim", 0.8, extras
    if _POTENTIAL_LEFT.search(left[-60:]):
        return "unknown", 0.5, extras  # children the defendant could reach are not established victims
    if _DISCOVERED_THE_LEFT.search(left[-60:]) or _SUSPECT_WAS_A_LEFT.search(left[-80:]):
        return "perpetrator", 0.85, extras
    if _ARRESTED_AGES_LEFT.search(left[-90:]) or (
        shape == "age_range_high" and _ARRESTED_AGES_HIGH_LEFT.search(left[-70:])
    ):
        return "perpetrator", 0.9, extras
    if _COURT_NATIONAL_RIGHT.search(right):
        return "perpetrator", 0.85, extras
    if re.search(r"\b(?:had|has)\s+an?\s+$", left[-24:], re.I) and _HAD_CHILD_RIGHT.match(right):
        return "victim", 0.8, extras
    if _VICTIM_RANGE_HIGH_LEFT.search(left[-40:]):
        return "victim", 0.85, extras
    if _ARREST_OF_LEFT.search(left[-40:]):
        return "perpetrator", 0.8, extras
    if _JUVENILE_DEFENDANT_RIGHT.match(right):
        return "perpetrator", 0.85, extras
    if _ADULT_RIGHT.match(right):
        extras["entity"] = _ADULT_RIGHT.match(right).group(0).strip(" -,")
        return "perpetrator", 0.8, extras
    if _VICTIM_RIGHT.match(right):
        noun = _VICTIM_RIGHT.match(right).group(0).strip(" -,")
        extras["entity"] = noun
        # "his ex-girlfriend's 11-year-old sisters": a child noun alone is identity, not a role.
        if not _VICTIM_NOUN_EXACT.search(noun) and not sg.has_victimization_cue(text, s, e):
            extras["weak"] = "noun_without_victimization_cue"
            return "victim", 0.6, extras
        return "victim", 0.8, extras
    if _VICTIM_LEFT.search(left[-80:]):
        if _BETWEEN_AGES_LEFT.search(left[-60:]):
            extras["weak"] = "age_range"
            return "unknown", 0.5, extras
        if not _VICTIM_NOUN_EXACT.search(left[-80:]) and not sg.has_victimization_cue(text, s, e):
            extras["weak"] = "noun_without_victimization_cue"
            return "victim", 0.6, extras
        return "victim", 0.8, extras
    if _FEMALE_MALE_RIGHT.match(right):
        return "victim", 0.6, extras  # bare "N-year-old female": weak, needs a second family
    if _ANAPHOR_LEFT.search(left[-12:]) and _ANAPHOR_RIGHT.match(right):
        ss, se = sg.sentence_at(text, s, e)
        if _DEFENDANT_CUE.search(text[ss:se]):
            extras["entity"] = "anaphor"
            return "perpetrator", 0.75, extras
    if _DESCRIBED_CHILD_AGE.search(left[-100:]) and _sting_within(text, s, e):
        extras["persona_cue"] = "described_child"
        return "decoy", 0.85, extras
    return "unknown", 0.5, extras


def age_assertions(text: str) -> List[Dict]:
    defendants = defendant_surnames(text)
    out = []
    for s, e, age, shape in age_mentions(text):
        role, conf, extras = age_role_lexical(text, s, e, shape, defendants)
        out.append(_raw("age", age, role, s, e, conf, pattern="age_lexical", **extras))
    return out


# Victim-age gate v2 reasons → roles. Gate runs as a validator on age-shaped mentions only.
_GATE_ROLE = {
    "statutory_threshold": "statutory_threshold",
    "statute_subsection": "statutory_threshold",
    "decoy_he_was_N": "decoy",
    "year_old_man_woman": "perpetrator",
    "defendant_comma_was_arrested": "perpetrator",
    "defendant_comma_charge_context": "perpetrator",
    "defendant_comma_headline_teen": "perpetrator",
    "perp_comma_verb_pattern": "perpetrator",
    "files_images_quantity": "not_age",
    "digit_of_larger_number": "not_age",
    "N_counts": "not_age",
    "count_prefix": "not_age",
    "ip_address_block": "not_age",
    "sentencing_years_to_life": "not_age",
}


def victim_gate_assertions(text: str, mentions: Iterable[Tuple[int, int, int, str]], gate_mod) -> List[Dict]:
    """
    Per-mention rejections from victim_age_gate.evaluate_age_slot_v2 (no value thresholds).

    The gate is a validator: its hard rejects (statutory, decoy, defendant patterns,
    quantities) become role assertions. Its KEEP signal ("victim word nearby") was
    built to filter threshold-bucketed victims and also fires on decoy personas
    ("posing as a 13-year-old girl"), so it never creates a victim role here.
    """
    out = []
    by_value: Dict[int, Dict] = {}
    for s, e, age, _shape in mentions:
        if not text[s:e].isdigit():
            continue  # gate v2 only reads digit spans
        if age not in by_value:
            by_value[age] = gate_mod.evaluate_age_slot_v2(text, age)
        detail = next((d for d in by_value[age]["spans"] if d["start"] == s), None)
        if detail is None:
            continue
        hard = [r for r in detail["reject"] if r in gate_mod._HARD_REJECT]
        role = next((_GATE_ROLE[r] for r in hard if r in _GATE_ROLE), None)
        if role == "perpetrator" and sg.is_closed_age_range(text, s, e):
            continue  # "aged 25-30" is a span; the gate's defendant patterns must not finalize an end
        if role:
            out.append(_raw("age", age, role, s, e, 0.8, method="victim_age_gate",
                            version=GATE_VERSION, gate_reason=hard[0]))
    return out


# ---------------------------------------------------------------------------
# Sentences, custody
# ---------------------------------------------------------------------------

_CUSTODY_RE = re.compile(
    r"\b(?:held|remains?|remained|detained|booked|lodged|incarcerated|jailed|remanded)\s+(?:\w+\s+){0,2}?"
    r"(?:in|into|at|to)\s+(?:the\s+)?(?:[\w'’\-.]+\s+){0,6}?"
    r"(?:custody|jail|correctional\s+(?:facility|center)|detention\s+(?:center|facility)|prison)\b"
    r"|\bheld\s+without\s+(?:bond|bail)\b|\bremains?\s+in\s+custody\b|\bin\s+custody\s+pending\b",
    re.IGNORECASE,
)


def _sentence_display(text: str, s: int, e: int) -> str:
    return re.sub(r"\s+", " ", sg.normalize_surface(text[s:e])).strip()


def sentence_assertions(text: str) -> List[Dict]:
    """Duration / amount / life mentions. The gate assigns the clause kind."""
    surf = sg.normalize_surface(text)
    out: List[Dict] = []
    covered: List[Tuple[int, int]] = []
    candidates = [(m.start(), m.end(), "duration") for m in sg.DURATION_RE.finditer(surf)]
    candidates += [(m.start(), m.end(), "amount") for m in sg.MONEY_RE.finditer(surf)]
    candidates += [(m.start(), m.end(), "life") for m in sg.LIFE_RE.finditer(surf)]
    for s, e, kind in sorted(candidates):
        if any(s < ce and e > cs for cs, ce in covered):
            continue
        if _pp._sentence_match_is_url_junk(text, s, e):
            continue
        phrase = _sentence_display(text, s, e)
        # 2.x anchor rule: bare durations need sentencing / prison language nearby.
        if kind == "duration" and _pp._sentence_duration_requires_anchor(phrase) and not (
            _pp._sentence_match_in_sentencing_clause(text, s, e) or sg._EXPOSURE_CUES.search(text[slice(*sg.clause_at(text, s, e))])
        ):
            continue
        covered.append((s, e))
        out.append(_raw("sentence", phrase, None, s, e, 0.8, pattern=kind))
    for m in _CUSTODY_RE.finditer(text):
        out.append(_raw("sentence", _sentence_display(text, m.start(), m.end()), "custody",
                        m.start(), m.end(), 0.8, pattern="custody"))
    return out


# ---------------------------------------------------------------------------
# CyberTip scope (investigation_type)
# ---------------------------------------------------------------------------

_TIP_TOKEN_RE = re.compile(_pp._CYBERTIP_PATTERN + r"|Cyber\s*Tips?|cybertips?", re.IGNORECASE)
_TIP_BOILERPLATE = re.compile(
    r"\b(?:can|may|should)\s+be\s+(?:made|reported|submitted)|\breport(?:s|ed)?\s+(?:it\s+)?(?:to|at|online)\b[^.]{0,60}"
    r"(?:cybertip|missingkids)|1-800|\bmissingkids\.org\b|\bonline\s+reports\s+of\b|\bsteadily\s+increased\b"
    r"|\breceives?\s+(?:thousands\s+of\s+)?CyberTips\b|\bhas\s+received\s+more\s+than\b|\b\d{1,3}(?:,\d{3})+\s+(?:cyber\s*tips?|reports)\b"
    r"|\bmore\s+than\s+[\d,]+\s+(?:cyber\s*tips?|reports)\b|\bnation'?s\s+centralized\b|\bthe\s+public\b|\bincreased\s+by\b|\bin\s+20\d\d,\s+(?:the\s+)?(?:task\s+force|ICAC|NCMEC|reports)\b"
    r"|\b(?:file|submit|make|report)\s+a\s+cyber\s*tip|\breceives?\s+(?:thousands\s+of\s+|hundreds\s+of\s+)?(?:online\s+)?cyber\s*tip"
    r"|\bclearing\s*house\b|\bcan\s+be\s+reported\b|\bif\s+you\s+have\s+(?:a\s+|any\s+)?(?:tip|information)\b|\bplease\s+(?:submit|report|contact)\b",
    re.IGNORECASE,
)
_TIP_CASE_ACTION = re.compile(
    r"\breceiv(?:ed|ing)\b|\b(?:was|were)\s+(?:generated|submitted|sent|made|forwarded|referred|filed)\b|\bsubmitted\s+by\b"
    r"|\bgenerated\s+by\b|\bfrom\s+(?:the\s+)?(?:NCMEC|National\s+Center|Facebook|Google|Snapchat|Kik|Instagram|Microsoft|Dropbox"
    r"|Discord|Twitter|Yahoo|Tumblr|TikTok|Meta|Verizon|Apple|Synchronoss|Imgur|Reddit|Omegle|a\s+social\s+media|an?\s+online|an?\s+electronic)\b"
    r"|\bregarding\b|\brelated\s+to\b|\binvolving\b|\bassociated\s+with\b|\bin\s+connection\s+with\b|\bled\s+(?:to|investigators)\b"
    r"|\bprompted\b|\binitiated\b|\bbegan\b|\bstarted\b|\bafter\s+(?:a|an|the)\b|\breported\s+(?:that|to\s+NCMEC)\b"
    r"|\bthrough\s+(?:a|an|the|multiple|several)?\s*cyber\s*tip|\bcame\s+to\s+the\s+attention\b|\bstemm(?:ed|ing)\s+from\b"
    r"|\bbased\s+(?:on|upon)\b|\bresulted?\s+from\b|\bin\s+regards?\s+to\b|\bfrom\s+(?:a|an|the)\s+cyber\s*tip",
    re.IGNORECASE,
)


def cybertip_assertions(text: str) -> List[Dict]:
    out = []
    for m in _TIP_TOKEN_RE.finditer(text):
        ss, se = sg.sentence_at(text, m.start(), m.end())
        sentence = text[ss:se]
        if _TIP_BOILERPLATE.search(sentence):
            role, conf = "boilerplate", 0.8
        elif _TIP_CASE_ACTION.search(sentence):
            role, conf = "case_action", 0.85
        else:
            role, conf = "unscoped", 0.5
        out.append(_raw("investigation_type", "cybertip", role, m.start(), m.end(), conf, pattern="cybertip_scope"))
    return out


# ---------------------------------------------------------------------------
# CyberTip reporter (#20): who sent the tip, when the release says so
# ---------------------------------------------------------------------------

# Electronic service providers as releases name them: (value, pattern). The value is
# the name CaseLinker stores; the mapper links it to a platform node when one exists.
_ESPS: Tuple[Tuple[str, str], ...] = (
    ("Google", r"Google(?:,?\s+(?:Inc|LLC)\.?)?"),
    ("YouTube", r"YouTube"),
    ("Kik", r"Kik(?:\s+Interactive|\s+Messenger)?"),
    ("Snapchat", r"Snap(?:chat|\s+Inc\.?)"),
    ("Facebook", r"Facebook(?:\s*/\s*Meta(?:\s+Platforms)?(?:,?\s+Inc\.?)?)?"),
    ("Meta", r"Meta(?:\s+Platforms)?(?:,?\s+Inc\.?)?"),
    ("Instagram", r"Instagram"),
    ("WhatsApp", r"WhatsApp"),
    ("Microsoft", r"Microsoft(?:\s+Corporation)?"),
    ("Skype", r"Skype"),
    ("OneDrive", r"OneDrive"),
    ("Dropbox", r"Dropbox"),
    ("Discord", r"Discord"),
    ("Twitter / X", r"Twitter|X\s+Corp\.?"),
    ("Yahoo", r"Yahoo!?"),
    ("AOL", r"AOL|America\s+Online"),
    ("Tumblr", r"Tumblr"),
    ("Reddit", r"Reddit"),
    ("TikTok", r"TikTok|ByteDance"),
    ("iCloud", r"iCloud"),
    ("Apple", r"Apple(?:,?\s+Inc\.?)?"),
    ("Synchronoss", r"Synchronoss(?:\s+Technologies)?"),
    ("Verizon", r"Verizon"),
    ("Comcast", r"Comcast"),
    ("MeetMe", r"MeetMe"),
    ("Imgur", r"Imgur"),
    ("Roblox", r"Roblox"),
    ("Omegle", r"Omegle"),
    ("Telegram", r"Telegram"),
    ("Twitch", r"Twitch"),
    ("Grindr", r"Grindr"),
    ("Yubo", r"Yubo"),
    ("Mega.nz", r"MEGA(?:\.nz)?"),
    ("MediaFire", r"MediaFire"),
    ("Pinterest", r"Pinterest"),
    ("Amazon", r"Amazon(?:\.com)?"),
    ("Zoom", r"Zoom\s+Video"),
    ("Tagged", r"Tagged(?:,?\s+Inc\.?)"),
)
_ESP_RE = "(?:" + "|".join(f"(?P<esp{i}>{p})" for i, (_, p) in enumerate(_ESPS)) + ")"
_REPORT_VERB = r"(?:submitted|filed|sent|made|generated|reported|flagged|forwarded|provided|created)"
_ARTICLE = (
    r"(?:(?:the|a|an)\s+)?(?:(?:social\s+media|messaging|instant\s+messaging|cloud\s+storage|electronic\s+service|online|video|chat)\s+)?"
    r"(?:app(?:lication)?|platform|company|provider|service|site)?\s*(?:\(ESP\)\s*)?,?\s*"
)
# "{ESP} submitted a CyberTip", "Kik, a messaging app, reported … to NCMEC"
_ESP_SUBJECT = re.compile(
    rf"(?<![\w-]){_ESP_RE}\b(?:,[^,.]{{0,60}},)?\s+(?:had\s+|has\s+|later\s+)?(?:{_REPORT_VERB}\b[^.]{{0,80}}?"
    r"(?:cyber\s*tip|tip(?:line)?\b|report|NCMEC|National\s+Center)|reported\s+(?:that|to)\b)",
    re.IGNORECASE,
)
# "a CyberTip sent by Microsoft", "CyberTips from Google", "CyberTipline reports from the app Kik"
_ESP_AFTER_TIP = re.compile(
    rf"(?:cyber\s*tip(?:line)?s?|tips?|reports?)(?:\s+reports?)?(?:\s+\w+){{0,4}}?\s+"
    rf"(?:from|by|sent\s+by|submitted\s+by|made\s+by|generated\s+by|filed\s+by|via)\s+{_ARTICLE}{_ESP_RE}\b",
    re.IGNORECASE,
)
# "NCMEC received [a CyberTip] from Google", "that NCMEC received from Google"
_ESP_TO_NCMEC = re.compile(
    rf"(?:NCMEC|National\s+Center\s+for\s+Missing\s+(?:and|&)\s+Exploited\s+Children)\b[^.]{{0,40}}?"
    rf"\breceived\b[^.]{{0,60}}?\bfrom\s+{_ARTICLE}{_ESP_RE}\b",
    re.IGNORECASE,
)
# Next sentence: "AOL had discovered an e-mail …", "Google detected the upload"
_ESP_DISCOVERED = re.compile(
    rf"^\W*{_ESP_RE}\b\s+(?:had\s+|has\s+)?(?:discovered|detected|identified|flagged|located|found|observed|notified)\b",
    re.IGNORECASE,
)
# The ESP named only as where content sat: "uploaded to a Facebook account" (not a reporter).
_CONTENT_PLACE_AFTER = re.compile(r"^\s*(?:accounts?|users?|profiles?|usernames?|messages?|chats?|servers?|groups?)\b", re.IGNORECASE)

_CATEGORY_BODY = (
    r"(?:online\s+)?social\s+media(?:\s+and\s+messaging)?\s+(?:platforms?|compan(?:y|ies)|app(?:lication)?s?|sites?|providers?)"
    r"|(?:instant\s+)?messaging\s+(?:apps?|applications?|platforms?|services?)"
    r"|cloud\s+storage\s+(?:providers?|services?|compan(?:y|ies))"
    r"|electronic\s+service\s+providers?|internet\s+service\s+providers?"
    r"|file[- ]sharing\s+(?:services?|sites?|platforms?)|online\s+platforms?|video\s+(?:sharing\s+)?platforms?"
)
_CATEGORY_RE = re.compile(
    rf"\b(?:an?|the|multiple|several|two|three|various)\s+(?P<cat>{_CATEGORY_BODY})\b", re.IGNORECASE
)
# A category is the reporter only as the source of the tip ("a CyberTip from a social media
# platform", "reported to NCMEC by a cloud storage provider") or the subject of a reporting
# verb. "Account information from the ESP" is a subpoena return, not a report.
_CATEGORY_SOURCE = re.compile(
    rf"(?:cyber\s*tip\w*|tips?|reports?|CTRs?)\b[^.]{{0,60}}?\b(?:from|by)\s+$|\b{_REPORT_VERB}\s+(?:by|from)\s+$"
    r"|\breported\s+to\b[^.]{0,110}?\bby\s+$",
    re.IGNORECASE,
)
_CATEGORY_VERB_AFTER = re.compile(
    rf"\s*(?:,[^,.]{{0,40}},\s*)?(?:had\s+|has\s+)?(?:{_REPORT_VERB}|notified|alerted)\b", re.IGNORECASE
)
_CONTENT_GAP = re.compile(
    r"upload|download|shar|post|distribut|transferr|obtain|informat|gather|identif|subpoena|stor|discover", re.IGNORECASE
)
_INCLUDING = re.compile(r"^[^.]{0,20}?\bincluding\b(?P<list>[^.]*)", re.IGNORECASE)
_PUBLIC_RE = re.compile(
    r"\b(?:a|an|the\s+(?:child|victim)'?s?)\s+(?:concerned\s+)?"
    r"(?P<who>citizen|parent|mother|father|relative|family\s+member|member\s+of\s+the\s+public|witness|neighbor|teacher|tipster)\b"
    rf"[^.]{{0,40}}\b(?:submitted|made|filed|reported)\b[^.]{{0,40}}cyber\s*tip",
    re.IGNORECASE,
)


def _category_slug(text: str) -> str:
    t = re.sub(r"\s+", " ", text.lower())
    for key, slug in (("social media", "social_media"), ("messaging", "messaging_app"),
                      ("cloud storage", "cloud_storage"), ("internet service", "internet_service_provider"),
                      ("electronic service", "electronic_service_provider"), ("file", "file_sharing"),
                      ("video", "video_platform"), ("online platform", "online_platform")):
        if key in t:
            return slug
    return "electronic_service_provider"


def _esp_hits(m: re.Match) -> Tuple[str, int, int]:
    for i, (value, _) in enumerate(_ESPS):
        if m.group(f"esp{i}"):
            return value, m.start(f"esp{i}"), m.end(f"esp{i}")
    raise ValueError("no ESP group matched")


def reporter_span_supports(span: str, role, value) -> bool:
    """The span gate for ``cybertip_reporter``: the span is exactly the ESP, category or person named."""
    span = span.strip()
    if role == "named_esp":
        m = re.fullmatch(_ESP_RE, span, re.IGNORECASE)
        return bool(m) and _esp_hits(m)[0] == value
    if role == "category":
        return bool(re.fullmatch(_CATEGORY_BODY, span, re.IGNORECASE)) and _category_slug(span) == value
    if role == "public":
        return value == "public" and bool(span)
    return False


def cybertip_reporter_assertions(text: str) -> List[Dict]:
    """Who sent a case-scoped CyberTip, read from the tip sentence and the one after it.

    NCMEC receives every CyberTip, so NCMEC, ICAC and the agencies that relay a
    tip are never the reporter. An ESP named only as where the content was
    ("uploaded to a Snapchat account") is not one either. Roles: ``named_esp``
    (value = the ESP), ``category`` (value = the kind of provider), ``public``.
    No assertion means the release does not say who reported.
    """
    out: List[Dict] = []
    seen: Set[Tuple[int, int]] = set()
    spans = sg.sentence_spans(text)
    for m in _TIP_TOKEN_RE.finditer(text):
        ss, se = sg.sentence_at(text, m.start(), m.end())
        sentence = text[ss:se]
        if _TIP_BOILERPLATE.search(sentence) or not _TIP_CASE_ACTION.search(sentence):
            continue
        following = next(((s, e) for s, e in spans if s >= se), None)
        named_patterns = (_ESP_SUBJECT, _ESP_AFTER_TIP, _ESP_TO_NCMEC)
        windows = [(ss, sentence, named_patterns)]
        if following:
            windows.append((following[0], text[following[0]:following[1]], named_patterns + (_ESP_DISCOVERED,)))
        named = False
        for base, chunk, patterns in windows:
            for pat in patterns:
                for hit in pat.finditer(chunk):
                    value, s, e = _esp_hits(hit)
                    if _CONTENT_PLACE_AFTER.match(chunk[e:]):
                        continue
                    key = (base + s, base + e)
                    if key in seen:
                        continue
                    seen.add(key)
                    named = True
                    out.append(_raw("cybertip_reporter", value, "named_esp", base + s, base + e, 0.9,
                                    pattern="cybertip_reporter"))
        if named:
            continue
        for base, chunk, _patterns in windows:
            for hit in _CATEGORY_RE.finditer(chunk):
                before, after = chunk[max(0, hit.start() - 140):hit.start()], chunk[hit.end():]
                source = _CATEGORY_SOURCE.search(before)
                if source and _CONTENT_GAP.search(source.group(0)):
                    source = None
                if not (source or _CATEGORY_VERB_AFTER.match(after)):
                    continue
                appositive = re.match(rf"\s*,\s*{_ESP_RE}\b", after, re.IGNORECASE)
                if appositive:
                    value, s, e = _esp_hits(appositive)
                    out.append(_raw("cybertip_reporter", value, "named_esp", base + hit.end() + s,
                                    base + hit.end() + e, 0.9, pattern="cybertip_reporter"))
                    continue
                listed = _INCLUDING.match(after)
                if listed:
                    offset = base + hit.end() + listed.start("list")
                    names = [(m, *_esp_hits(m)) for m in re.finditer(_ESP_RE, listed.group("list"), re.IGNORECASE)]
                    for _m, value, s, e in names:
                        out.append(_raw("cybertip_reporter", value, "named_esp", offset + s, offset + e, 0.85,
                                        pattern="cybertip_reporter_list"))
                    if names:
                        continue
                key = (base + hit.start("cat"), base + hit.end("cat"))
                if key not in seen:
                    seen.add(key)
                    out.append(_raw("cybertip_reporter", _category_slug(hit.group("cat")), "category",
                                    key[0], key[1], 0.7, pattern="cybertip_reporter"))
        for hit in _PUBLIC_RE.finditer(sentence):
            key = (ss + hit.start("who"), ss + hit.end("who"))
            if key not in seen:
                seen.add(key)
                out.append(_raw("cybertip_reporter", "public", "public", key[0], key[1], 0.7,
                                pattern="cybertip_reporter"))
    return out
