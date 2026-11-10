"""
People masking (CaseLinker 3.x): CaseLinker reads names; it never stores or serves them.

Two halves:

1. **Where people are, never who.** ``person_spans`` finds the people named in a
   release (Stanza ``PERSON`` spans, age cues, repeats of their surnames) and
   returns character offsets, filtered so places, agencies and organization-name
   parts are never included. Extraction stores the offsets as
   ``extracted_features.person_spans``. Every outward surface redacts from them:
   ``public_text`` (the release with ``[PERSON]``), ``mask_admissions``,
   ``mask_feature_strings``, and ``scrub_people`` for entity lists.

2. **Tokens, not names, in structured data.** Readers tie an age to the person
   named next to it ("Smith, 32,"). The resolver needs only the *shape* of that
   name to tell people apart: which mentions share a surname, a first name, a
   generational suffix. ``pseudonymize`` replaces every name a reader recorded
   with per-case tokens before anything is stored: "John Smith" -> "N1 N2",
   "Smith" -> "N2", "John Smith Jr." -> "N1 N2 Jr". The same token string maps to
   the same code everywhere in one case and to nothing outside it, so
   ``_same_named_person`` gives the same answers on codes as on names.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set, Tuple

# Same table as resolution._NAME_SUFFIXES: suffixes are kept, they are not identifying.
NAME_SUFFIXES = {"jr": "Jr", "sr": "Sr", "ii": "II", "iii": "III", "iv": "IV"}

# extras key holding a raw name -> key holding its pseudonymous form
NAME_KEYS = {
    "entity": "name_key",
    "defendant_entity": "defendant_key",
    "sentence_subject": "defendant_key",
}


def _is_name(value: str) -> bool:
    toks = [t.strip(".,") for t in (value or "").split() if t.strip(".,")]
    toks = [t for t in toks if t.lower() not in NAME_SUFFIXES]
    return bool(toks) and toks[-1][:1].isupper()


def _encode(value: str, codes: Dict[str, str]) -> str:
    out: List[str] = []
    for raw in value.split():
        core = raw.strip(".,")
        if not core:
            continue
        suffix = NAME_SUFFIXES.get(core.lower())
        if suffix:
            out.append(suffix)
            continue
        code = codes.get(core)
        if code is None:
            code = f"{'N' if core[:1].isupper() else 'n'}{len(codes) + 1}"
            codes[core] = code
        out.append(code)
    return " ".join(out)


def pseudonymize(assertions: Iterable[Dict]) -> List[Dict]:
    """Replace raw names in ``extras`` with per-case tokens, in place. Returns the list.

    Codes are assigned in text order (span start, then list order), so a re-run
    over the same assertions gives the same codes. Non-name role nouns ("man",
    "girl", "anaphor") are not identifying and stay as ``entity``.
    """
    items = list(assertions)
    codes: Dict[str, str] = {}
    order = sorted(range(len(items)), key=lambda i: (items[i].get("span_start") is None, items[i].get("span_start") or 0, i))
    for i in order:
        extras = items[i].get("extras")
        if not isinstance(extras, dict):
            continue
        for raw_key, key in NAME_KEYS.items():
            value = extras.get(raw_key)
            if not isinstance(value, str) or not value.strip():
                continue
            if raw_key == "entity" and not _is_name(value):
                continue
            extras.pop(raw_key)
            extras[key] = _encode(value, codes)
    return items


# ---------------------------------------------------------------------------
# Masking names in free text (admission quotes and context) for public surfaces
# ---------------------------------------------------------------------------

PERSON_MASK = "[PERSON]"
_GAZETTEER = Path(__file__).resolve().parents[3] / "data" / "gazetteer"

# A run of capitalized tokens, initials allowed ("D.P.", "K."), optional suffix.
_RUN = re.compile(
    r"\b[A-Z][A-Za-z'’\-]+(?:\s+(?:[A-Z]\.){1,3}|\s+[A-Z][A-Za-z'’\-]+){1,4}(?:,?\s+(?:Jr|Sr|II|III|IV)\b\.?)?"
)
# Any of these in a run means an institution, a court, or a program, not a person.
_INSTITUTION = frozenset("""
department police county court office attorney attorneys general agency agencies investigations investigation
security bureau task force homeland federal united states district circuit superior supreme sheriff sheriffs
marshal marshals service services patrol state city town university college school academy center centre
commission council division unit justice prosecutor prosecutors safe childhood project internet crimes
against children icac ncmec cybertipline national international enforcement immigration customs border
protection postal inspection secret army navy air marine corps coast guard fbi hsi doj dhs cbp ice usps
institute hospital church company inc llc corporation group association foundation network program
operation facebook instagram snapchat google microsoft kik discord tiktok twitter telegram whatsapp yahoo
apple android iphone dropbox reddit youtube roblox minecraft xbox playstation
""".split())
# Titles before a name: keep the title, mask the name.
_TITLES = frozenset("""
judge justice officer agent detective det sergeant sgt lieutenant lt captain capt deputy trooper special
investigator inspector chief sheriff marshal attorney prosecutor commissioner director dr mr mrs ms miss
senator governor mayor president secretary assistant acting senior supervisory u.s. us
charge corporal cpl colonel col commander superintendent pastor reverend rev coach
teacher principal defendant ag da
""".split())
# "Bishop", "Major" and "Deacon" are left out: they are names as often as titles, and a title
# read off a name leaves the rest of that name in the public text.
# Capitalized because they start a sentence, not because they are a name.
_LEADING = frozenset("""
the a an and but or if when while after before during since until as at in on of for from by with to into
according he she they his her their it its this that these those there here we our you your i my
on in yesterday today tuesday monday wednesday thursday friday saturday sunday january february march april
may june july august september october november december prosecutors investigators authorities officials
police court records documents
""".split())


@lru_cache(maxsize=1)
def _places() -> Set[str]:
    """US state, county and place names from the pinned Census gazetteer (lowercased)."""
    out: Set[str] = set()
    lsad = re.compile(r"\s+(?:city|town|village|borough|CDP|municipality|township|county|parish|census area|"
                      r"city and borough|consolidated government|unified government|metropolitan government|"
                      r"\(balance\))+$", re.I)
    for fname, col in (("2024_Gaz_state_national.txt", 2), ("2024_Gaz_counties_national.txt", 3),
                       ("2024_Gaz_place_national.txt", 3)):
        try:
            lines = (_GAZETTEER / fname).read_text(encoding="utf-8", errors="ignore").splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            cols = line.split("\t")
            if len(cols) > col:
                name = cols[col].strip()
                out.add(name.lower())
                out.add(lsad.sub("", name).strip().lower())
    return out


def _person_tokens(run: str) -> List[str]:
    """The name part of a capitalized run, or [] when the run is a place or an institution."""
    toks = run.replace(",", " ").split()
    while toks and toks[0].lower().strip(".") in _LEADING:
        toks = toks[1:]
    # "U.S. District Judge James K. Bredar": the name is what follows the last title or institution word.
    cut = max((i for i, t in enumerate(toks) if t.lower().strip(".").removesuffix("'s").removesuffix("’s")
               in _TITLES | _INSTITUTION), default=-1)
    toks = toks[cut + 1:]
    core = [t for t in toks if t.strip(".").lower() not in NAME_SUFFIXES]
    has_suffix = len(core) < len(toks)
    if not core or (len(core) < 2 and not has_suffix):
        return []
    if not has_suffix and " ".join(core).lower() in _places():
        return []
    return toks


_NAME = r"(?:[A-Z][A-Za-z'’\-]+\.?\s+){0,3}[A-Z][A-Za-z'’\-]+"
# People the release ties to an age or a defendant verb: the same evidence the age readers use.
_PERSON_CUES = [
    re.compile(rf"\b({_NAME})(?:,?\s+(?:Jr|Sr|II|III|IV)\.?)?\s*[,(]\s*(?:(?:then|now|age|aged)\s+)?\d{{1,2}}\b"),
    re.compile(rf"\b\d{{1,2}}[- ]years?[- ]old\s+({_NAME})"),
    re.compile(rf"\b({_NAME})\s+(?:,[^,]{{0,60}},\s+)?(?:was|were|has been|had been|is)?\s*"
               r"(?:sentenced|pleaded|pled|convicted|charged|arrested|indicted|admitted|confessed|faces|told|said|"
               r"stated|claimed|explained|allegedly|later|also|described|acknowledged|denied|agreed|used|sent|"
               r"posted|uploaded|downloaded|possessed|distributed|received|messaged|asked|met|traveled|travelled)\b"),
]


# The defendant block newer DOJ releases end with: "The Defendant:\nROWAN BRAMBLETON Age: 39".
_NAME_BEFORE_AGE_LABEL = re.compile(
    r"(?<![A-Za-z])([A-Z][A-Za-z'’\-]+(?:[ \t]+[A-Z]\.?)?(?:[ \t]+[A-Z][A-Za-z'’\-]+){1,3})[ \t]*\n?[ \t]*Age:\s*\d"
)


def person_surnames(text: str) -> Set[str]:
    """Surnames of people the release ties to an age or a defendant verb (read from text, never stored)."""
    out: Set[str] = set()
    for pat in _PERSON_CUES:
        for m in pat.finditer(text or ""):
            run = m.group(1)
            toks = _person_tokens(run)
            core = [t.strip(".,") for t in toks if t.strip(".").lower() not in NAME_SUFFIXES]
            if not core and len(run.split()) == 1:
                core = [run] if run.lower() not in _LEADING | _TITLES | _INSTITUTION and run.lower() not in _places() else []
            if core and len(core[-1]) > 2 and not core[-1].isupper():
                out.add(core[-1])
    return out


def mask_person_names(*texts: str, surnames: Iterable[str] = (), lone: bool = True) -> List[str]:
    """Mask the named people (``surnames``) in related texts (a quote and its context).

    A name run ending in one of the surnames ("John Andrew Smith", "Smith Jr.") and,
    with ``lone``, the bare surname ("Smith said ...") become ``[PERSON]``. Labels
    pass ``lone=False`` so "Smith County Sheriff's Office" keeps its county.
    """
    surnames = {s for s in surnames if s}
    if not surnames:
        return [t or "" for t in texts]

    def full(m: "re.Match[str]") -> str:
        run = m.group(0)
        toks = _person_tokens(run)
        core = [t.strip(".,’'") for t in toks if t.strip(".").lower() not in NAME_SUFFIXES]
        if not core or core[-1].removesuffix("’s").removesuffix("'s") not in surnames:
            return run
        keep = run[: run.find(toks[0])] if toks[0] in run else ""
        return f"{keep}{PERSON_MASK}"

    masked = [_RUN.sub(full, t or "") for t in texts]
    if not lone:
        return masked
    bare = re.compile(r"\b(?:" + "|".join(re.escape(s) for s in sorted(surnames, key=len, reverse=True)) + r")\b(?:'s|’s)?")
    return [bare.sub(PERSON_MASK, t) for t in masked]


# Two-letter abbreviations that end place names ("Boyd Co.", "Port St."), never surnames.
_ABBREV_TAIL = frozenset({"co", "st", "mt", "ft", "pt", "rd", "dr", "ln", "ct", "av", "jr", "sr", "mr", "ms"})


def _surname_ok(tok: str) -> bool:
    """A usable surname: 3+ letters, or a 2-letter one like "Wu" / "Le" (not an acronym or "Co.")."""
    tok = tok.strip(".")
    if tok.lower() in _ABBREV_TAIL:
        return False
    return len(tok) > 2 or (len(tok) == 2 and tok[0].isupper() and tok[1].islower())


def _norm_name(name: str) -> str:
    """A person's name without a trailing possessive or dot: "Smith Jr.'s" -> "Smith Jr"."""
    return re.sub(r"(?:['’]s?)$", "", (name or "").strip()).strip().rstrip(" .,")


def _is_person_label(value: str, full_keys: Set[str], surnames: Set[str]) -> bool:
    """A label that *is* a person: a known full name, or a known surname with a suffix ("Smith Jr.'s")."""
    raw = _norm_name((value or "").strip().removeprefix("the ").removeprefix("The "))
    key = _name_key(raw)
    if len(key.split()) >= 2:
        return key in full_keys
    had_suffix = len(raw.split()) > len(key.split())
    return bool(key) and had_suffix and key in surnames


def _name_key(name: str) -> str:
    """Comparison key for dropping entries: no possessive, no suffix, collapsed spaces."""
    toks = [t.strip(".,") for t in _norm_name(name).split()]
    return " ".join(t for t in toks if t and t.lower() not in NAME_SUFFIXES)


def _people_from_spans(text: str, spans: Iterable) -> Tuple[Set[str], Set[str]]:
    """(full names, surnames) read from person spans, in memory only."""
    full: Set[str] = set()
    surnames: Set[str] = set()
    for s, e in spans or ():
        name = _norm_name((text or "")[int(s):int(e)])
        toks = [t.strip(".,’'") for t in name.split() if t.strip(".,").lower() not in NAME_SUFFIXES]
        if len(toks) >= 2:
            full.add(name)
        if toks and _surname_ok(toks[-1]):
            surnames.add(toks[-1])
    return full, surnames


def spans_for(features: Dict, case_text: str) -> List[List[int]]:
    """Stored ``person_spans`` when extraction recorded them; otherwise computed from the text (no NER)."""
    stored = (features or {}).get("person_spans")
    if isinstance(stored, list):
        return stored
    return person_spans(case_text, ())


def public_text(case_text: str, spans: Iterable) -> str:
    """The release with people masked: what public callers get instead of raw text."""
    return redact(case_text, spans)


def mask_admissions(records: Iterable[Dict], case_text: str = "", spans: Iterable = None) -> List[Dict]:
    """Public copy of ``perpetrator_admissions``: quote and context with people masked, everything else kept.

    Each excerpt is located in the case text and redacted from the person spans;
    the surname masker runs after as a backstop.
    """
    spans = person_spans(case_text, ()) if spans is None else list(spans)
    full, surnames = _people_from_spans(case_text, spans)
    surnames |= person_surnames(case_text)
    # Excerpts can come from a differently normalized copy of the text, so offsets may not
    # place them; the case's known names are also replaced directly, whitespace-tolerant.
    known = [re.compile(r"\s+".join(re.escape(t) for t in n.split()) + r"(?:['’]s)?") for n in
             sorted(full, key=len, reverse=True)]
    out: List[Dict] = []
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        rec = dict(rec)
        for key in ("quote", "context"):
            if rec.get(key) is not None:
                masked = redact_excerpt(str(rec[key]), case_text, spans)
                for pat in known:
                    masked = pat.sub(PERSON_MASK, masked)
                rec[key] = mask_person_names(masked, surnames=surnames)[0]
        out.append(rec)
    return out


# Feature keys that hold source free text or URLs, not entity labels.
_SKIP_FEATURE_KEYS = frozenset({"perpetrator_admissions", "source_url", "case_text", "raw_data", "document_version_id",
                                "extraction_run_id", "person_spans"})


def mask_feature_strings(features: Dict, case_text: str = "") -> Dict:
    """Public copy of ``extracted_features``: people masked, places / agencies / facts untouched.

    Entity labels that are a person's name (a reader filed a person as a location or
    organization) become ``[PERSON]``; a name inside a longer label is masked unless
    it names an institution's place ("Medicine Hat Police"). Admissions get
    ``mask_admissions``. ``person_spans`` (offsets) is not served.
    """
    spans = spans_for(features, case_text)
    full, surnames = _people_from_spans(case_text, spans)
    full_keys = {_name_key(n) for n in full}
    inst = "|".join(sorted(_INSTITUTION))

    def label(v: str) -> str:
        if _is_person_label(v, full_keys, surnames):
            return PERSON_MASK
        for name in sorted(full, key=len, reverse=True):
            if name in v:
                v = re.sub(re.escape(name) + rf"(?!\s{{1,3}}(?:{inst})\b)", PERSON_MASK, v, flags=re.I)
        return v

    def walk(v):
        if isinstance(v, dict):
            return {k: (v[k] if k in _SKIP_FEATURE_KEYS else walk(v[k])) for k in v}
        if isinstance(v, list):
            return [walk(x) for x in v]
        return label(v) if isinstance(v, str) else v

    out = walk(dict(features or {}))
    out.pop("person_spans", None)
    if isinstance((features or {}).get("perpetrator_admissions"), list):
        out["perpetrator_admissions"] = mask_admissions(features["perpetrator_admissions"], case_text, spans)
    return out


# ---------------------------------------------------------------------------
# Dropping misreads at the source (a person filed as a location / organization)
# ---------------------------------------------------------------------------

_PLACE_AFTER = re.compile(r"^(?:['’]s)?\s{1,3}(?:police|county|sheriff|township|city|parish|borough|village|department|"
                          r"fire|school|district|area|region|airport|station|park|mall)\b", re.I)


# "of Hudson Falls, NY" / "a Hudson Falls man": what follows a town, never a person.
# The two letters have to be a state: "Wexley, II," and "Wexley, EU Commissioner" are people.
_USPS = (
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND "
    "OH OK OR PA PR RI SC SD TN TX UT VT VA WA WV WI WY"
).replace(" ", "|")
_TOWN_AFTER = re.compile(
    rf"^(?:,\s*(?:(?:{_USPS})|N\.\s?Y\.|Pa\.|Ky\.|Ga\.|Fla\.|Ohio|Texas|Calif\.)(?=[\s,.;)])"
    r"|\s+(?:man|woman|men|women|teen|teenager|resident|residents|native|couple|area|-based)\b)"
)


def _reads_as_place(name: str, text: str, not_people: Set[str], gazetteer: bool = True) -> bool:
    """A "name" that is a known place, a grounded place/agency here, or used as one in the text.

    ``gazetteer=False`` leaves out the bare gazetteer lookup, for callers that weigh it
    against evidence that this mention is a person.
    """
    name = _norm_name(name)  # "Spring Grove's police" is still Spring Grove
    low = name.lower()
    if (gazetteer and low in _places()) or name in not_people:
        return True
    if any(re.search(re.escape(name) + r"\s+(?:" + "|".join(sorted(_INSTITUTION)) + r")\b", x or "", re.I)
           for x in not_people):
        return True  # "Spring Grove" in "Spring Grove Police Department"
    return any(_PLACE_AFTER.match(text[m.end():m.end() + 16]) or _TOWN_AFTER.match(text[m.end():m.end() + 16])
               for m in re.finditer(re.escape(name), text or ""))


def case_people(case_text: str, person_names: Iterable[str] = (),
                not_people: Iterable[str] = ()) -> Tuple[Set[str], Set[str]]:
    """(full names, surnames) of people in a release: NER PERSON spans plus age / defendant-verb cues.

    ``not_people``: mentions already grounded to a place or agency in this case.
    Readers sometimes take a city for a person ("Medicine Hat, 32,"); those stay out.
    """
    full: Set[str] = set()
    not_people = {x for x in not_people if x}
    surnames = {s for s in person_surnames(case_text) if not _reads_as_place(s, case_text, not_people)}
    for name in person_names or ():
        name = (name or "").strip()
        toks = [t.strip(".,") for t in name.split() if t.strip(".,").lower() not in NAME_SUFFIXES]
        if not toks or not toks[-1][:1].isupper() or toks[-1].isupper():
            continue
        if _reads_as_place(name, case_text, not_people):
            continue
        full.add(_norm_name(name))
        if len(toks) >= 2 and _surname_ok(toks[-1]):
            surnames.add(toks[-1])
    return full, surnames


def _is_person_value(value: str, full: Set[str], surnames: Set[str]) -> bool:
    """An entity-list entry is a person only when it *is* a full name NER or an age reader saw.

    Surnames alone are not enough here: "Boston" or "Marshals" can be a cue-word
    surname and a real place or agency. (Free text uses the broader surname set.)
    """
    return _is_person_label(value, {_name_key(n) for n in full}, surnames)


# Dict keys whose value names the entity a grounding / gate row is about.
_ENTRY_LABEL_KEYS = ("mention", "label", "entity_name", "name", "text")


def scrub_people(value: Any, full: Set[str], surnames: Set[str]) -> Any:
    """Drop list entries that are a person's name; mask names inside longer labels. Returns a copy.

    Applies to entity lists (``locations``, ``organizations``, ``agencies_involved``,
    NER entities, grounding and gate rows). Free text (``perpetrator_admissions``,
    ``case_text``) is never passed here; it is masked on the way out instead.
    """
    if isinstance(value, dict):
        return {k: (value[k] if k in _SKIP_FEATURE_KEYS else scrub_people(value[k], full, surnames)) for k in value}
    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, str) and _is_person_value(item, full, surnames):
                continue
            if isinstance(item, dict) and any(isinstance(item.get(k), str) and _is_person_value(item[k], full, surnames)
                                              for k in _ENTRY_LABEL_KEYS):
                continue
            out.append(scrub_people(item, full, surnames))
        return out
    if isinstance(value, str) and len(value.split()) >= 3 and any(n in value for n in full):
        inst = "|".join(sorted(_INSTITUTION))
        for name in sorted(full, key=len, reverse=True):
            if len(name.split()) >= 2:
                # "Medicine Hat Police Department": a name before an institution word is its place, not a person.
                value = re.sub(re.escape(name) + rf"(?!\s{{1,3}}(?:{inst})\b)", PERSON_MASK, value, flags=re.I)
    return value


# ---------------------------------------------------------------------------
# Person spans: where names are, never what they are
# ---------------------------------------------------------------------------
#
# Extraction records ``person_spans`` = [[start, end], ...] character offsets into
# the case text. Offsets are not names; the raw text they point into is internal.
# Every public surface redacts from them (``redact``), so CaseLinker serves the
# full release with people masked and places, agencies and facts intact.

# A span right after these is part of an organization's name ("Department of Internal Affairs",
# "the Attorney General's Child Predator Unit", "Operation Broken Heart"). The agency word has to
# be joined to the span by "of" / "for" or a possessive: a bare one is a title or the end of the
# previous phrase, and what follows is the person ("Attorney General Corin Ashcombe",
# "Sheriff Reese Thistlewood", "told police Ashcombe had").
_ORG_BEFORE = re.compile(
    r"(?:(?:department|office|bureau|ministry|division|unit|agency|service|services|police|sheriffs?|"
    r"attorney\s+general|marshals?|ksp|icac|fbi|hsi|doj|commission|council|university|college|school|"
    r"hospital|court|station|registry|church)(?:['’]s?\s+|\s+(?:of|for)\s+(?:the\s+)?)"
    r"|(?:task\s+force|company|inc\.?|corp\.?|operation|project|labor\s+and)\s*(?:(?:of|for)\s+(?:the\s+)?)?)$",
    re.I,
)
# Same sentence only: "... Attorney Corin Ashcombe. “Crimes against children ..." is a person.
_ORG_AFTER = re.compile(
    r"^(?:['’]s)?[\s,\-]{0,3}(?:corporation|corp|inc|llc|ltd|company|unit|branch|section|division|team|office|bureau|agency|"
    r"services?|crimes?|task|force|program|programme|initiative|operation|center|centre|institute|foundation|"
    r"association|network|group|inspectors?|investigations?|commission|council|department|act|law)\b",
    re.I,
)


# A title right before a name settles that it is a person, whatever else the word can mean
# ("Governor Lincoln signed", "Judge Madison").
_PERSON_TITLE_BEFORE = re.compile(
    r"\b(?:judge|justice|officer|agent|detective|det\.?|sergeant|sgt\.?|lieutenant|lt\.?|captain|capt\.?|trooper|"
    r"investigator|inspector|chief|sheriff|marshal|commissioner|director|dr\.?|mr\.?|mrs\.?|ms\.?|miss|senator|"
    r"governor|gov\.?|mayor|president|secretary|colonel|col\.?|superintendent|prosecutor|general|attorney|"
    r"constable|corporal|cpl\.?|major|commander|deputy)\s+$",
    re.I,
)
# What a person does, right after the name.
_PERSON_VERB_AFTER = re.compile(
    r"^(?:['’]s)?,?\s+(?:said|says|told|stated|added|was|is|has|had|will|would|could|did|also|allegedly|admitted|"
    r"pleaded|pled|faces|testified|wrote|explained|noted|announced|thanked|sentenced|ordered|[a-z]{3,}ed)\b"
)


_AGE_AFTER = re.compile(r"^,?\s*(?:(?:age|aged)\s*:?\s*)?\d{1,2}\b", re.I)
_HEADLINE_WORDS = frozenset("man woman men women teen teenager resident residents couple arrested charged sentenced".split())


def _all_caps_name(text: str, s: int, e: int) -> bool:
    """ "ROWAN Q. BRAMBLETON, age 27" in an older release is a name. A dateline, an acronym or a
    headline ("TRENTON", "ICAC", "BOARDMAN MAN ARRESTED") is not: an all-caps run counts only
    with a title before it, or an age or a verb after it."""
    toks = text[s:e].split()
    words = [t.strip(".,") for t in toks if len(t.strip(".,")) > 1]
    if len(words) < 2 or len(toks) > 5 or not all(re.fullmatch(r"[A-Z][A-Z'’\-]*[.,]?", t) for t in toks):
        return False
    if {w.lower() for w in words} & (_LEADING | _TITLES | _INSTITUTION | _HEADLINE_WORDS):
        return False
    after = text[e:e + 24]
    before = re.sub(r"\s+", " ", text[max(0, s - 24):s])
    return bool(_AGE_AFTER.match(after) or _PERSON_VERB_AFTER.match(after) or _PERSON_TITLE_BEFORE.search(before))


def _span_is_person(text: str, s: int, e: int, not_people: Set[str] = frozenset()) -> bool:
    name = text[s:e].strip()
    possessive = name.endswith(("'s", "’s"))  # "Ashcombe's office said" is still Ashcombe
    if _ORG_BEFORE.search(re.sub(r"\s+", " ", text[max(0, s - 40):s])) or (
        not possessive and _ORG_AFTER.match(text[e:e + 20])
    ):
        return False
    toks = [t.strip(".,’'“”\"") for t in name.split()]  # a nickname in quotes is part of the name
    while len(toks) > 1 and re.fullmatch(r"#\d+", toks[-1]):
        toks.pop()  # "Detective Wexley #4576": a badge number after the name
    if not toks or not toks[-1][:1].isupper():
        return False
    if all(t.isupper() for t in toks if t) and not _all_caps_name(text, s, e):
        return False
    low = {t.lower() for t in toks}
    if low & _INSTITUTION or (len(toks) == 1 and toks[0].lower() in _LEADING | _TITLES):
        return False
    if toks[-1].lower() in _ABBREV_TAIL - {"jr", "sr"}:
        return False  # "Boyd Co." is a county
    if _reads_as_place(name, text, set(not_people), gazetteer=False):
        return False
    if _norm_name(name).lower() not in _places():
        return True
    # A name that is also on the map ("Lincoln", "Jackson"): a person only where the text treats
    # it as one, so a town NER mistook for a person stays readable.
    before = re.sub(r"\s+", " ", text[max(0, s - 24):s])
    return bool(_PERSON_TITLE_BEFORE.search(before) or _PERSON_VERB_AFTER.match(text[e:e + 24]))


# NER sometimes takes the title with the name ("Pastor Reese Thistlewood", "Charge Corin Ashcombe"
# from "Special Agent in Charge ..."). The title is a fact about the case and stays readable.
def _after_titles(text: str, s: int, e: int) -> int:
    """Start of the name inside ``text[s:e]``, past any leading title words."""
    while True:
        m = re.match(r"([A-Za-z.]+)\s+(?=\S)", text[s:e])
        if not m or m.group(1).strip(".").lower() not in _TITLES:
            return s
        s += m.end()


# "van Wexley said": a surname can start with a lowercase particle.
_PARTICLE_FIRST = re.compile(r"(?:van|von|de|del|della|di|da|dos|du|la|le|bin|al|el|ter|ten|den|der)\s+[A-Z]")


def _wrapped_name(text: str, newline: int, end: int) -> bool:
    """A line wrap between two parts of one name ("Reese\\nThistlewood"), not the end of a line of text."""
    # Letters are any script's letters: "José\nThístlewood" wraps like "Reese\nThistlewood".
    left = re.search(r"((?:[^\W\d_]|['’\-])+\.?),?[ \t]*$", text[max(0, newline - 30):newline])
    right = re.match(
        r"[ \t]*([^\W\d_](?:[^\W\d_]|['’\-])+|[A-Z]\.?(?=[ \t]+[^\W\d_](?:[^\W\d_]|['’])))(?![\w:])",
        text[newline + 1:],
    )
    if not left or not right or not left.group(1)[:1].isupper() or not right.group(1)[:1].isupper():
        return False  # a blank line, lowercase text, or a field label ("Source:") on the next one
    nxt = right.group(1).strip(".")
    if len(nxt) == 1:
        return True  # a middle initial
    if nxt.isupper():
        return False  # the next line is a dateline or a heading
    return nxt.lower() not in _TITLES | _INSTITUTION | _LEADING


def _trim_span(text: str, s: int, e: int) -> List[List[int]]:
    """A name never crosses a line break or a sentence end: keep the part that is the name."""
    seg_start = s
    for m in re.finditer(r"\n|[.!?;:](?=\s)", text[s:e]):
        before = re.search(r"(\S+)$", text[s:s + m.start()])
        word = before.group(1).strip(".") if before else ""
        # Initials and abbreviations are inside a name ("Hollis K. Wexley", "R.L. Wexley",
        # "Corin Ashcombe Jr. was").
        if m.group(0) == "." and (
            len(word) <= 2
            or re.fullmatch(r"(?:[A-Z]\.)*[A-Z]", word)
            or word.lower() in ("jr", "sr", "dr", "mr", "mrs", "ms", "st")
        ):
            continue
        if m.group(0) == "\n":
            if _wrapped_name(text, s + m.start(), e):
                continue
            if text[seg_start:s + m.start()].strip():
                e = s + m.start()  # the name ended with its line; the next line is something else
                break
        seg_start = s + m.end()
    while seg_start < e and text[seg_start].isspace():
        seg_start += 1
    end = e
    while end > seg_start and text[end - 1] in " \t\n,.;:":
        end -= 1
    name = text[seg_start:end]
    if not name or not (name[:1].isupper() or _PARTICLE_FIRST.match(name)):
        return []
    return [[seg_start, end]]


_EMAIL_LOCAL = re.compile(r"(?<![\w.])([A-Za-z][A-Za-z0-9._%+\-]*)@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def person_spans(text: str, ner_person_spans: Iterable = (), not_people: Iterable[str] = ()) -> List[List[int]]:
    """Offsets of person names in ``text``: NER PERSON spans, reader cues, and repeats of their surnames.

    NER spans that read as a place or an institution ("Medicine Hat", "Kik Messenger")
    are dropped. Every later bare mention of a kept person's surname ("Smith said")
    is added. Returns sorted, merged [start, end] pairs.
    """
    text = text or ""
    not_people = frozenset(x for x in not_people if isinstance(x, str) and x)
    spans: List[List[int]] = []
    for sp in ner_person_spans or ():
        s, e = int(sp[0]), int(sp[1])
        if not 0 <= s < e <= len(text):
            continue
        s = _after_titles(text, s, e)
        if _span_is_person(text, s, e, not_people):
            spans.append([s, e])
    # Age cues ("Smith, 32," / "32-year-old John Smith") name a person on their own.
    for pat in _PERSON_CUES[:2]:
        for m in pat.finditer(text):
            s, e = m.span(1)
            toks = _person_tokens(m.group(1))
            if toks and toks[0] in m.group(1):
                s += m.group(1).find(toks[0])
                if _span_is_person(text, s, e, not_people):
                    spans.append([s, e])
    for m in _NAME_BEFORE_AGE_LABEL.finditer(text):
        s, e = m.span(1)
        if _span_is_person(text, s, e, not_people):
            spans.append([s, e])
    # A verb cue ("... said", "... admitted") only confirms someone NER or an age cue already found:
    # on its own it also fires on "Workforce Development said".
    known = {text[a:b].split()[-1].strip(".,’'") for a, b in spans if text[a:b].split()}
    for m in _PERSON_CUES[2].finditer(text):
        s, e = m.span(1)
        toks = _person_tokens(m.group(1))
        core = [t.strip(".,’'") for t in toks if t.strip(".").lower() not in NAME_SUFFIXES]
        if core and core[-1] in known and toks[0] in m.group(1):
            s += m.group(1).find(toks[0])
            if _span_is_person(text, s, e, not_people):
                spans.append([s, e])
    # Trim first: a surname is read off the end of a span, and a span that ran on into the
    # next line ("Thistlewood\nSource:") would make "Source" one.
    spans = [t for sp in spans for t in _trim_span(text, *sp)]
    surnames = set()
    for s, e in spans:
        core = [t.strip(".,’'") for t in text[s:e].split() if t.strip(".,").lower() not in NAME_SUFFIXES]
        if core and _surname_ok(core[-1]):
            surnames.add(core[-1])
    glue = r"(?:\b|(?=(?:is|was|has|had|and|who|will|were|faces|pleaded|allegedly)\b))"
    names = {_norm_name(text[a:b]) for a, b in spans if len(text[a:b].split()) >= 2} | surnames
    for name in sorted(names, key=len, reverse=True):
        # "Smithhas been arraigned": PDF text sometimes drops the space after a name.
        for m in re.finditer(r"\b" + r"\s+".join(re.escape(t) for t in name.split()) + glue, text):
            if _PLACE_AFTER.match(text[m.end():m.end() + 16]):
                continue  # "Smith County" stays
            spans.append([m.start(), m.end()])
    # "corin.ashcombe@usdoj.gov": the part before the @ is the person again. The domain stays.
    lowered = {n.lower() for n in surnames if len(n) >= 4}
    emails = [[m.start(1), m.end(1)] for m in _EMAIL_LOCAL.finditer(text)
              if any(n in m.group(1).lower() for n in lowered)]
    spans = [t for sp in spans for t in _trim_span(text, *sp)] + emails
    spans.sort()
    merged: List[List[int]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return merged


def redact(text: str, spans: Iterable, offset: int = 0) -> str:
    """``text`` with every person span replaced by ``[PERSON]``. ``offset``: where ``text`` starts in the case text."""
    text = text or ""
    out, pos = [], 0
    for s, e in sorted((int(a) - offset, int(b) - offset) for a, b in spans or ()):
        if e <= 0 or s >= len(text):
            continue
        s, e = max(s, 0), min(e, len(text))
        if s < pos:
            s = pos
        if s >= e:
            continue
        out.append(text[pos:s])
        out.append(PERSON_MASK)
        pos = e
    out.append(text[pos:])
    return "".join(out)


def redact_excerpt(excerpt: str, case_text: str, spans: Iterable) -> str:
    """Redact a stored excerpt (an admission quote or context) by locating it in the case text."""
    excerpt = excerpt or ""
    if not excerpt:
        return excerpt
    at = (case_text or "").find(excerpt)
    if at < 0:
        # Excerpts can be whitespace-normalized; match on a normalized copy.
        norm = re.sub(r"\s+", " ", case_text or "")
        at = norm.find(re.sub(r"\s+", " ", excerpt))
        if at < 0:
            return mask_person_names(excerpt, surnames=person_surnames(case_text))[0]
        return redact(re.sub(r"\s+", " ", excerpt), person_spans(norm, ()), at) if not spans else \
            redact(re.sub(r"\s+", " ", excerpt), _spans_in_normalized(case_text, spans), at)
    return redact(excerpt, spans, at)


def _spans_in_normalized(text: str, spans: Iterable) -> List[List[int]]:
    """Map spans on ``text`` to the whitespace-collapsed copy of it."""
    mapping, j, prev_space = [], 0, False
    for ch in text or "":
        mapping.append(j)
        is_space = ch.isspace()
        if not (is_space and prev_space):
            j += 1
        prev_space = is_space
    mapping.append(j)
    return [[mapping[min(s, len(mapping) - 1)], mapping[min(e, len(mapping) - 1)]] for s, e in spans or ()]
