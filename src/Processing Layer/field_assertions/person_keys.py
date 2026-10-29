"""
Per-case pseudonymous name tokens (CaseLinker 3.x).

Readers tie an age to the person named next to it ("Smith, 32,"). The resolver
needs only the *shape* of that name to tell people apart: which mentions share a
surname, a first name, a generational suffix. It never needs the letters.

``pseudonymize`` replaces every name a reader recorded with per-case tokens
before anything is stored: "John Smith" -> "N1 N2", "Smith" -> "N2",
"John Smith Jr." -> "N1 N2 Jr". The same token string maps to the same code
everywhere in one case and to nothing outside it, so ``_same_named_person``
gives the same answers on codes as on names.
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
""".split())
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


def _surname_ok(tok: str) -> bool:
    """A usable surname: 3+ letters, or a 2-letter one like "Wu" / "Le" (not an acronym like "US")."""
    return len(tok) > 2 or (len(tok) == 2 and tok[0].isupper() and tok[1].islower())


def _norm_name(name: str) -> str:
    """A person's name without a trailing possessive or dot: "Smith Jr.'s" -> "Smith Jr"."""
    return re.sub(r"(?:['’]s?)$", "", (name or "").strip()).strip().rstrip(" .,")


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
        key = _name_key(v.strip().removeprefix("the ").removeprefix("The "))
        if len(key.split()) >= 2 and key in full_keys:
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

_PLACE_AFTER = re.compile(r"^\W{0,3}(?:police|county|sheriff|township|city|parish|borough|village|department|"
                          r"fire|school|district|area|region|airport|station|park|mall)\b", re.I)


def _reads_as_place(name: str, text: str, not_people: Set[str]) -> bool:
    """A "name" that is a known place, a grounded place/agency here, or used as one in the text."""
    low = name.lower()
    if low in _places() or name in not_people or any(name in x for x in not_people):
        return True
    return any(_PLACE_AFTER.match(text[m.end():m.end() + 16]) for m in re.finditer(re.escape(name), text or ""))


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
    key = _name_key((value or "").strip().removeprefix("the ").removeprefix("The "))
    return len(key.split()) >= 2 and key in {_name_key(n) for n in full}


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
# "the Attorney General's Child Predator Unit", "Kentucky State Police Electronic Crimes Branch").
_ORG_BEFORE = re.compile(
    r"(?:department|office|bureau|ministry|division|unit|agency|service|services|police|sheriff'?s?|"
    r"attorney\s+general(?:'s|’s)?|marshals?|ksp|icac|fbi|hsi|doj|task\s+force|commission|council|"
    r"university|college|school|hospital|company|inc\.?|corp\.?|operation|project|labor\s+and|court|station|"
    r"registry|church)"
    r"\s*(?:of\s+(?:the\s+)?|for\s+(?:the\s+)?)?$",
    re.I,
)
_ORG_AFTER = re.compile(
    r"^\W{0,3}(?:corporation|corp|inc|llc|ltd|company|unit|branch|section|division|team|office|bureau|agency|"
    r"services?|crimes?|task|force|program|programme|initiative|operation|center|centre|institute|foundation|"
    r"association|network|group|inspectors?|investigations?|commission|council|department|act|law)\b",
    re.I,
)


def _span_is_person(text: str, s: int, e: int) -> bool:
    if _ORG_BEFORE.search(re.sub(r"\s+", " ", text[max(0, s - 40):s])) or _ORG_AFTER.match(text[e:e + 20]):
        return False
    name = text[s:e].strip()
    toks = [t.strip(".,’'") for t in name.split()]
    if not toks or not toks[-1][:1].isupper() or all(t.isupper() for t in toks if t):
        return False
    low = {t.lower() for t in toks}
    if low & _INSTITUTION or (len(toks) == 1 and toks[0].lower() in _LEADING | _TITLES):
        return False
    return not _reads_as_place(name, text, set())


def _trim_span(text: str, s: int, e: int) -> List[List[int]]:
    """A name never crosses a line break or a sentence end: keep the part that is the name."""
    seg_start = s
    for m in re.finditer(r"\n|[.!?;:](?=\s)", text[s:e]):
        before = re.search(r"(\S+)$", text[s:s + m.start()])
        word = before.group(1).strip(".") if before else ""
        # Initials and abbreviations are inside a name ("Hollis K. Wexley", "Corin Ashcombe Jr. was").
        if m.group(0) == "." and (len(word) <= 2 or word.lower() in ("jr", "sr", "dr", "mr", "mrs", "ms", "st")):
            continue
        seg_start = s + m.end()
    while seg_start < e and text[seg_start].isspace():
        seg_start += 1
    end = e
    while end > seg_start and text[end - 1] in " \t\n,.;:":
        end -= 1
    name = text[seg_start:end]
    if not name or not name[:1].isupper():
        return []
    return [[seg_start, end]]


def person_spans(text: str, ner_person_spans: Iterable = ()) -> List[List[int]]:
    """Offsets of person names in ``text``: NER PERSON spans, reader cues, and repeats of their surnames.

    NER spans that read as a place or an institution ("Medicine Hat", "Kik Messenger")
    are dropped. Every later bare mention of a kept person's surname ("Smith said")
    is added. Returns sorted, merged [start, end] pairs.
    """
    text = text or ""
    spans: List[List[int]] = []
    for sp in ner_person_spans or ():
        s, e = int(sp[0]), int(sp[1])
        if 0 <= s < e <= len(text) and _span_is_person(text, s, e):
            spans.append([s, e])
    # Age cues ("Smith, 32," / "32-year-old John Smith") name a person on their own.
    for pat in _PERSON_CUES[:2]:
        for m in pat.finditer(text):
            s, e = m.span(1)
            toks = _person_tokens(m.group(1))
            if toks and toks[0] in m.group(1):
                s += m.group(1).find(toks[0])
                if _span_is_person(text, s, e):
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
            if _span_is_person(text, s, e):
                spans.append([s, e])
    surnames = set()
    for s, e in spans:
        core = [t.strip(".,’'") for t in text[s:e].split() if t.strip(".,").lower() not in NAME_SUFFIXES]
        if core and _surname_ok(core[-1]):
            surnames.add(core[-1])
    for sur in surnames:
        for m in re.finditer(rf"\b{re.escape(sur)}\b", text):
            if _PLACE_AFTER.match(text[m.end():m.end() + 16]):
                continue  # "Smith County" stays
            spans.append([m.start(), m.end()])
    spans = [t for sp in spans for t in _trim_span(text, *sp)]
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
