"""
Temporal tagging (evidence family ``temporal``) for CaseLinker 3.0.

- ``date`` assertions: every explicit date mention with a role — publication,
  biography (born / ordained / hired …), prior_case, or event.
- ``sentence`` assertions with role ``prior``: durations inside clauses about an
  earlier case ("previously arrested in 2018 … sentenced to three months"),
  so a prior sentence never finalizes as this case's sentence.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

_PROCESSING_LAYER = Path(__file__).resolve().parent.parent
_FIELD_LAYER = _PROCESSING_LAYER / "field_assertions"
if str(_FIELD_LAYER) not in sys.path:
    sys.path.insert(0, str(_FIELD_LAYER))
if str(_PROCESSING_LAYER) not in sys.path:
    sys.path.insert(0, str(_PROCESSING_LAYER))

import span_gate as sg  # noqa: E402

TEMPORAL_VERSION = "temporal_1.1.0"

# A program's history is not this case's timeline. "Project Safe Childhood, a nationwide
# initiative launched in May 2006", "Since 2006, the Attorney General's ICAC Task Force has
# been involved in 1,840 arrests", "Since the launch of Operation Predator in 2003": these
# were stored as role=event (May 2006 alone in 2,358 cases of 10,802). They get role
# ``program_boilerplate``.
_PROGRAM_NOUN = re.compile(
    r"\b(?:initiative|program(?:me)?|task\s+force|project\s+safe\s+childhood|operation\s+[A-Z][\w-]+"
    r"|campaign|partnership|coalition|network|unit|cybertipline|tipline|hotline)\b",
    re.I,
)
_LAUNCH_BEFORE_DATE = re.compile(
    r"\b(?:launch(?:ed|ing)?|launch\s+of|establish(?:ed|ment)|creat(?:ed|ion)|form(?:ed|ation)|found(?:ed|ing)"
    r"|began|started|introduced|inception|inaugurated|since)\b[^.;]{0,70}$",
    re.I,
)
_LAUNCH_AFTER_DATE = re.compile(
    r"^[^.;]{0,50}\b(?:launched|established|created|formed|founded|started|introduced|inaugurated)\b", re.I
)
# Aggregate program statistics: "Since 2019 ... has received more than 24,100 CyberTips".
_AGGREGATE_AFTER = re.compile(
    r"^[^.;]{0,140}\b(?:more\s+than|over|nearly|approximately|about)\s+[\d,]+\s+(?:\w+\s+){0,3}"
    r"(?:arrests|cases|tips|cybertips|reports|investigations|children|victims|individuals|people|predators|offenders)\b",
    re.I,
)

_ESTABLISHED_THAT = re.compile(r"\b(?:establish\w*\s+that|evidence\s+(?:\w+\s+){0,4}establish\w*)\b", re.I)
_INVESTIGATION_BEGAN = re.compile(
    r"(?:\b(?:investigation|probe|inquiry|case|undercover\s+operation)\b[^.;]{0,30}\b(?:began|started|was\s+launched)\b"
    r"|\b(?:began|started|launched|opened|initiated)\s+(?:its|an|the|their|a)?\s*(?:\w+\s+)?investigation\b)[^.;]{0,25}$",
    re.I,
)

# What a dated event in this case is, from the nearest cue in its clause.
EVENT_KINDS = ("offense", "investigation", "arrest", "prosecution", "unknown")
_EVENT_KIND_CUES = (
    ("arrest", re.compile(r"\b(?:arrest\w*|taken\s+into\s+custody|apprehend\w*|booked|turned\s+(?:him|her)self\s+in|detained)\b", re.I)),
    ("prosecution", re.compile(
        r"\b(?:indict\w*|charged|charges|plead\w*|pled|guilty|convict\w*|sentenc\w*|trial|hearing|jury|verdict"
        r"|complaint|arraign\w*|scheduled|court)\b", re.I)),
    ("investigation", re.compile(
        r"\b(?:investigat\w*|cybertips?|tips?|search\s+warrants?|warrants?|executed|undercover|forensic\w*"
        r"|identified|reported|referred|referral|discovered|learned|seized|subpoena\w*|located)\b", re.I)),
    ("offense", re.compile(
        r"\b(?:possess\w*|receiv\w*|distribut\w*|produc\w*|communicat\w*|chat\w*|messag\w*|sent|contact\w*"
        r"|abus\w*|assault\w*|groom\w*|entic\w*|solicit\w*|record\w*|upload\w*|download\w*|exploit\w*|met"
        r"|travel\w*|trad(?:ed|ing)|shared|engaged|molest\w*|coerc\w*|extort\w*|began\s+(?:talking|communicating|chatting))\b",
        re.I)),
)
EVENT_KIND_WINDOW = 90

_MONTHS = {
    m: i for i, m in enumerate(
        ["january", "february", "march", "april", "may", "june", "july", "august",
         "september", "october", "november", "december"], start=1)
}
_MONTH_ABBR = {k[:3]: v for k, v in _MONTHS.items()} | {"sept": 9}
_MONTH_RE = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
_DATE_RES = (
    (re.compile(rf"\b({_MONTH_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+((?:19|20)\d{{2}})\b"), "mdy"),
    (re.compile(r"\b((?:19|20)\d{2})-(\d{2})-(\d{2})\b"), "iso"),
    (re.compile(rf"\b({_MONTH_RE})\.?\s+((?:19|20)\d{{2}})\b"), "my"),
    (re.compile(r"\b(?:in|since|during|from|until|by|of)\s+((?:19|20)\d{2})\b", re.I), "y"),  # "In 2008, …"
)
_PUBLICATION_LINE = re.compile(r"^\s*(?:Publication\s+date|Date\s+Posted|Published|Posted|Updated)\s*:?", re.I | re.M)
_LEAD_DATE_PREFIX = re.compile(
    r"^\s*(?:On|For immediate release)\b"
    r"|^\s*(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s*$",
    re.I,
)
_DATELINE_TAIL = re.compile(r"(?:[—–\-]|[(])\s*$")
_BIOGRAPHY_CUES = re.compile(
    r"\b(?:born|ordained|graduated|married|enlisted|hired|joined|retired|served\s+as|appointed|elected|founded)\b", re.I
)
_PRIOR_CUES = re.compile(
    r"\b(?:previously\s+(?:been\s+)?(?:convicted|arrested|sentenced|served|incarcerated|charged)"
    r"|prior\s+(?:\w+\s+)?(?:conviction|case|arrest|sentence|offense)s?|earlier\s+(?:case|conviction|arrest)"
    r"|at\s+the\s+time|was\s+released\s+(?:from|in)|had\s+served|not\s+the\s+first\s+time"
    r"|in\s+a\s+(?:prior|previous|separate)\s+case|(?:convicted|sentenced|arrested)\s+in\s+(?:19|20)\d{2}"
    # a different person's case described in the same release
    r"|the\s+other\s+(?:individual|man|woman|defendant|offender)|co-?defendant|accomplice"
    # a term the defendant is already serving from another case ("consecutive to the four years
    # Dokes is serving after he was convicted in two gun cases")
    r"|consecutive(?:ly)?\s+to\s+(?:the|a|an|his|her)\s+(?:[\w-]+\s+){0,3}?(?:sentences?|terms?|years?|months?)"
    r"|(?:is|was|been)\s+(?:currently\s+|already\s+)?serving\s+(?:a|an|the|his|her|time|that|this|\d+|[\w-]+\s+(?:years?|months?|sentences?|terms?))"
    r"|currently\s+serving)\b",
    re.I,
)
_CURRENT_CUES = re.compile(
    r"\b(?:today|yesterday|this\s+week|on\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday))\b", re.I
)
_SENTENCING_VERBS = re.compile(r"\b(?:sentenced|received\s+a\s+(?:prison\s+)?sentence|imposed)\b", re.I)
# "jailed in August 2022 to 14 years, with five years on licence" is one earlier term.
_PAST_CUSTODY_VERBS = re.compile(r"\b(?:jailed|imprisoned)\b", re.I)
# Convictions / pleas also predate a release, sometimes by two years; only a gap of three or
# more years marks a prior case.
_CONVICTION_VERBS = re.compile(r"\b(?:convicted|pleaded\s+guilty|pled\s+guilty|found\s+guilty)\b", re.I)
PRIOR_CONVICTION_YEARS = 3
# A sentence that names the judge / court / hearing describes this case's sentencing, so it
# never continues a prior-conviction recap ("previously convicted … At sentencing, Judge X imposed").
_CURRENT_SENTENCING_ANCHORS = re.compile(
    r"\b(?:judge|court|u\.s\.|united\s+states|federal|at\s+sentencing|hearing|today|yesterday)\b", re.I
)
# The duration itself, not the whole sentence: "today" later in the sentence is this case's term.
_LOCAL_PRIOR_BEFORE = re.compile(
    r"\b(?:previously|earlier)\s+(?:been\s+)?(?:jailed|imprisoned|sentenced|served|incarcerated)\s+(?:for\s+)?(?:a\s+)?$",
    re.I,
)
_JAILED_IN_YEAR_BEFORE = re.compile(
    r"\b(?:jailed|imprisoned|sentenced)\s+in\s+(?:[A-Za-z]+\s+)?((?:19|20)\d{2})\s+to\s+$",
    re.I,
)
_STATUTE_NAME_BEFORE = re.compile(r"\bAct\s+of\s+$", re.I)
PRIOR_DAYS = 180


def _month_num(tok: str) -> Optional[int]:
    t = tok.lower().rstrip(".")
    return _MONTHS.get(t) or _MONTH_ABBR.get(t[:4] if t.startswith("sept") else t[:3])


def date_mentions(text: str) -> List[Dict]:
    out: List[Dict] = []
    taken: List[tuple] = []
    for rx, kind in _DATE_RES:
        for m in rx.finditer(text):
            span = (m.start(), m.end()) if kind != "y" else (m.start(1), m.end(1))
            if any(span[0] < e and span[1] > s for s, e in taken):
                continue
            if _STATUTE_NAME_BEFORE.search(text[max(0, span[0] - 12) : span[0]]):
                continue  # "Victim Assistance Act of 2018" is a statute name, not an event
            if kind == "mdy":
                mo, day, year = _month_num(m.group(1)), int(m.group(2)), int(m.group(3))
                if not mo or not 1 <= day <= 31:
                    continue
                value = f"{year:04d}-{mo:02d}-{day:02d}"
            elif kind == "iso":
                value = m.group(0)
            elif kind == "my":
                mo = _month_num(m.group(1))
                if not mo:
                    continue
                value = f"{int(m.group(2)):04d}-{mo:02d}"
            else:
                value = m.group(1)
            taken.append(span)
            out.append({"start": span[0], "end": span[1], "value": value, "year": int(value[:4])})
    return sorted(out, key=lambda d: d["start"])


def is_program_boilerplate(text: str, ss: int, se: int, start: int, end: int) -> bool:
    """The date tells when a program, operation or initiative began, or opens its statistics."""
    sentence = text[ss:se]
    nouns = {m.group(0).lower().split()[0] for m in _PROGRAM_NOUN.finditer(sentence)}
    if not nouns:
        return False
    before = text[max(ss, start - 80):start]
    after = text[end:min(se, end + 160)]
    # "the evidence established that from 2015 ...": legal "established", not a founding.
    if _ESTABLISHED_THAT.search(text[max(ss, start - 120):start]):
        return False
    # "The investigation began in February 2017": this case's investigation, an event.
    if _INVESTIGATION_BEGAN.search(before):
        return False
    # A named operation alone is usually the one that caught this defendant ("Operation
    # Nest Egg, launched in February 2008, targeted 26 defendants"). Boilerplate only when
    # program-wide statistics follow ("Since the launch of Operation Predator in 2003, HSI
    # has arrested more than 10,000 individuals").
    if nouns <= {"operation"} and not _AGGREGATE_AFTER.search(after):
        return False
    if _LAUNCH_BEFORE_DATE.search(before):
        # "since" alone needs program statistics after it; "began" needs a program noun near the date.
        if re.search(r"\bsince\s*$", before, re.I):
            return bool(_AGGREGATE_AFTER.search(after)) or bool(_PROGRAM_NOUN.search(after[:60]))
        if re.search(r"\b(?:began|started)\b[^.;]{0,70}$", before, re.I):
            return bool(_PROGRAM_NOUN.search(text[max(ss, start - 80):min(se, end + 40)]))
        return True
    if _LAUNCH_AFTER_DATE.search(after) and _PROGRAM_NOUN.search(after[:120]):
        return True
    return False


def event_kind(text: str, ss: int, se: int, start: int, end: int) -> str:
    """offense / investigation / arrest / prosecution / unknown, by the cue nearest the date."""
    lo, hi = max(ss, start - EVENT_KIND_WINDOW), min(se, end + EVENT_KIND_WINDOW)
    best: Tuple[int, str] = (10 ** 9, "unknown")
    for kind, rx in _EVENT_KIND_CUES:
        for m in rx.finditer(text, lo, hi):
            dist = start - m.end() if m.end() <= start else max(0, m.start() - end)
            if dist < best[0]:
                best = (dist, kind)
    return best[1]


def _publication_prefix(text: str, start: int) -> bool:
    """A date at the head of the release: a labeled line, a blank lead, a dateline, or "On …"."""
    line_start = text.rfind("\n", 0, start) + 1
    prefix = text[line_start:start]
    if _PUBLICATION_LINE.match(prefix):
        return True
    if start >= 500:
        return False
    if prefix.strip() == "" or _LEAD_DATE_PREFIX.match(prefix):
        return True
    return len(prefix) < 80 and bool(_DATELINE_TAIL.search(prefix))


def publication_year(text: str, mentions: List[Dict], fallback: Optional[int]) -> Optional[int]:
    """The release's own year, else the batch year.

    A conduct year in the opening lines ("from 2010") is not the publication
    year. Using it made a later prior sentence look like this case's sentence.
    """
    for d in mentions:
        if _publication_prefix(text, d["start"]):
            return d["year"]
    return fallback


def _raw(field, value, role, s, e, confidence, **extras):
    return {
        "field": field, "method": "temporal", "method_version": TEMPORAL_VERSION, "value": value,
        "role": role, "span_start": s, "span_end": e, "confidence": confidence, "extras": extras,
    }


def _days(value: str) -> Optional[int]:
    """Approximate day number for YYYY / YYYY-MM / YYYY-MM-DD (month-precision → mid-month)."""
    parts = [int(p) for p in value.split("-")]
    if len(parts) == 1:
        return None
    year, month = parts[0], parts[1]
    day = parts[2] if len(parts) > 2 else 15
    return year * 365 + (month - 1) * 30 + day


def _is_earlier(d: Dict, pub_value: Optional[str], pub_year: Optional[int]) -> bool:
    """Clearly before publication: >180 days for dated mentions, ≥2 years for year-only ones."""
    pub_days = _days(pub_value) if pub_value else None
    days = _days(d["value"])
    if days is not None and pub_days is not None:
        return pub_days - days > PRIOR_DAYS
    return bool(pub_year) and d["year"] < pub_year - 1


def _prior_sentence_ids(
    text: str, mentions: List[Dict], pub_value: Optional[str], pub_year: Optional[int], *, for_ages: bool
) -> set:
    """
    Indexes of sentences about an earlier or different case. Offense conduct, pleas, and
    verdicts also predate a release, so an early date counts only next to "sentenced", and
    only for durations. Ages need an explicit cue; "at the time" there is a time qualifier
    ("five years old at the time"), not a prior case.
    """
    spans = sg.sentence_spans(text)
    prior = set()
    for i, (ss, se) in enumerate(spans):
        sentence = text[ss:se]
        if _CURRENT_CUES.search(sentence):
            continue
        cue = _PRIOR_CUES.search(sentence)
        if cue and not (for_ages and cue.group(0).lower().startswith("at the time")):
            prior.add(i)
            continue
        if for_ages:
            continue  # pleas and verdicts in this case also predate the release; ages need a cue
        in_sentence = [d for d in mentions if ss <= d["start"] < se]
        early = any(_is_earlier(d, pub_value, pub_year) for d in in_sentence)
        if early and (_SENTENCING_VERBS.search(sentence) or _PAST_CUSTODY_VERBS.search(sentence)):
            prior.add(i)
            continue
        # "in 1999, Bowers was convicted of … Bowers was sentenced to 20 years in state prison":
        # a conviction two or more years before publication is an earlier case.
        far_early = bool(pub_year) and any(d["year"] <= pub_year - PRIOR_CONVICTION_YEARS for d in in_sentence)
        if far_early and _CONVICTION_VERBS.search(sentence):
            prior.add(i)
            continue
        # "Lacy was sentenced on February 2, 2009 … He received a sentence of 60 months" — the
        # sentence right after a dated earlier sentencing continues it (same paragraph only).
        if not for_ages and i and (i - 1) in prior:
            ps, pe = spans[i - 1]
            prev = text[ps:pe]
            if "\n\n" in text[pe:ss] or in_sentence:
                continue
            if _SENTENCING_VERBS.search(prev):
                prior.add(i)
            elif _CONVICTION_VERBS.search(prev) and not _CURRENT_SENTENCING_ANCHORS.search(sentence):
                # "in 1999, Bowers was convicted … Bowers was sentenced to 20 years in state prison"
                prior.add(i)
    return prior


def temporal_assertions(
    text: str,
    sentence_candidates: List[Dict],
    batch_year: Optional[int] = None,
    age_mentions: Iterable[Tuple[int, int, int, str]] = (),
) -> List[Dict]:
    mentions = date_mentions(text)
    pub_year = publication_year(text, mentions, batch_year)
    out: List[Dict] = []
    pub_value: Optional[str] = None
    for d in mentions:
        ss, se = sg.sentence_at(text, d["start"], d["end"])
        sentence = text[ss:se]
        if _publication_prefix(text, d["start"]):
            role = "publication"
            if pub_value is None and len(d["value"]) == 10:
                pub_value = d["value"]
        elif is_program_boilerplate(text, ss, se, d["start"], d["end"]):
            role = "program_boilerplate"
        elif _BIOGRAPHY_CUES.search(sentence):
            role = "biography"
        elif _is_earlier(d, pub_value, pub_year) and _PRIOR_CUES.search(sentence):
            role = "prior_case"
        else:
            role = "event"
        extras = {"publication_year": pub_year}
        if role == "event":
            extras["event_kind"] = event_kind(text, ss, se, d["start"], d["end"])
        out.append(_raw("date", d["value"], role, d["start"], d["end"], 0.8, **extras))

    spans = sg.sentence_spans(text)
    prior = _prior_sentence_ids(text, mentions, pub_value, pub_year, for_ages=False)
    prior_ages = _prior_sentence_ids(text, mentions, pub_value, pub_year, for_ages=True)

    def sentence_index(pos: int) -> Optional[int]:
        return next((i for i, (ss, se) in enumerate(spans) if ss <= pos < se), None)

    anchor_year = pub_year or batch_year
    for cand in sentence_candidates:
        before = sg.normalize_surface(text[max(0, cand["span_start"] - 60) : cand["span_start"]])
        year_hit = _JAILED_IN_YEAR_BEFORE.search(before)
        earlier_year = bool(
            year_hit and anchor_year and int(year_hit.group(1)) <= anchor_year - PRIOR_CONVICTION_YEARS
        )
        if sentence_index(cand["span_start"]) in prior or _LOCAL_PRIOR_BEFORE.search(before) or earlier_year:
            out.append(_raw("sentence", cand["value"], "prior", cand["span_start"], cand["span_end"], 0.8, prior_cue=True))
    for s, e, age, shape in age_mentions:
        # "Name, 45," and "19-year-old Alex Rivera" name the current defendant even
        # inside a sentence that also says he was previously arrested.
        if shape in ("name_comma", "name_paren"):
            continue
        if shape == "year_old" and re.match(r"^\W*years?\W*olds?\s+[A-Z]", text[e:e + 40]):
            continue
        if sentence_index(s) in prior_ages:
            out.append(_raw("age", age, "prior_case", s, e, 0.8, prior_cue=True))
    return out
