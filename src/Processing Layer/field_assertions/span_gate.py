"""
Span gate for CaseLinker 3.0 field assertions.

Every asserted value must be supported by a span of the *original* case_text.
Normalization (NFKC, casefold, curly apostrophes) is used only for matching;
offsets always map back to the original string. No span, no value.

Typed support:
- age: the span is the age token itself (digits or a word number) and sits in an
  age-shaped context ("N-year-old", "age(d) N", "Name, N,", "N years old",
  word ages). Durations, counts, and bare numbers are never ages.
- sentence: the span is a duration ("240 months", "five years", "life") or a
  dollar amount; the clause around it decides the kind (exposure overrides).
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "′": "'", "`": "'"})
_DASHES = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-"})

_UNITS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}
WORD_NUMBER_RE = (
    r"(?:(?:" + "|".join(_TENS) + r")(?:[-\s](?:" + "|".join(k for k in _UNITS if _UNITS[k] < 10) + r"))?"
    r"|" + "|".join(sorted(_UNITS, key=len, reverse=True)) + r")"
)
# Digits or a spelled-out number, as one capture-friendly alternation.
NUMBER_RE = rf"(?:\d{{1,3}}|{WORD_NUMBER_RE})"


def normalize_surface(s: str) -> str:
    """Straight apostrophes, ASCII hyphens, plain spaces. Length-preserving, so offsets survive."""
    return s.translate(_APOSTROPHES).translate(_DASHES)


def parse_number(token: str) -> Optional[int]:
    """'12' / 'five' / 'twenty-one' → int; anything else → None."""
    if token is None:
        return None
    t = unicodedata.normalize("NFKC", normalize_surface(str(token))).strip().casefold()
    if re.fullmatch(r"\d{1,4}", t):
        return int(t)
    if t in _UNITS:
        return _UNITS[t]
    if t in _TENS:
        return _TENS[t]
    m = re.fullmatch(r"([a-z]+)[-\s]([a-z]+)", t)
    if m and m.group(1) in _TENS and m.group(2) in _UNITS and _UNITS[m.group(2)] < 10:
        return _TENS[m.group(1)] + _UNITS[m.group(2)]
    return None


# ---------------------------------------------------------------------------
# Offset-faithful matching
# ---------------------------------------------------------------------------

def _casefold_map(s: str) -> Tuple[str, List[int]]:
    """Normalized string plus map from normalized index → original index."""
    chars: List[str] = []
    origin: List[int] = []
    for i, ch in enumerate(s):
        for nch in unicodedata.normalize("NFKC", normalize_surface(ch)).casefold():
            chars.append(nch)
            origin.append(i)
    return "".join(chars), origin


def find_all_spans(text: str, needle: str) -> List[Tuple[int, int]]:
    """Every match of needle in text (NFKC/casefold/whitespace-normalized), original offsets."""
    if not text or not needle or not str(needle).strip():
        return []
    needle = str(needle)
    hits: List[Tuple[int, int]] = []
    # Always normalized + whitespace-insensitive, so an exact hit can't hide a
    # line-wrapped duplicate ("three months" vs "three\nmonths").
    norm_text, tmap = _casefold_map(text)
    norm_needle, _ = _casefold_map(needle)
    norm_needle = re.sub(r"\s+", " ", norm_needle).strip()
    if not norm_needle:
        return []
    # Whitespace-insensitive: PDF line wraps put newlines where quotes have spaces.
    pattern = r"\s+".join(re.escape(part) for part in norm_needle.split(" "))
    for m in re.finditer(pattern, norm_text):
        hits.append((tmap[m.start()], tmap[m.end() - 1] + 1))
    return hits


def locate(text: str, quote: str) -> Tuple[Optional[Tuple[int, int]], str]:
    """Find a quoted span: ``ok`` | ``missing`` | ``ambiguous`` (never first-hit)."""
    hits = find_all_spans(text, quote)
    if not hits:
        return None, "missing"
    if len(hits) > 1:
        return None, "ambiguous"
    return hits[0], "ok"


def locate_quote_covering(
    window: str, quote: str, mention_start: int, mention_end: int
) -> Tuple[Optional[Tuple[int, int]], str]:
    """Locate ``quote`` inside one window.

    Offsets are window-relative. A quote that also occurs outside this window is
    not ambiguous. If the quote occurs more than once inside the window, the hit
    that covers ``[mention_start, mention_end)`` is the one used.
    """
    hits = find_all_spans(window, quote)
    if not hits:
        return None, "missing"
    covering = [hit for hit in hits if hit[0] <= mention_start and mention_end <= hit[1]]
    if len(covering) == 1:
        return covering[0], "ok"
    if len(covering) > 1:
        return None, "ambiguous"
    if len(hits) == 1:
        return None, "quote_does_not_contain_mention"
    return None, "ambiguous"


# ---------------------------------------------------------------------------
# Sentences and clauses
# ---------------------------------------------------------------------------

_ABBREV_BEFORE_DOT = re.compile(
    r"(?:\b(?:U\.S|U\.S\.C|Mr|Mrs|Ms|Dr|Jr|Sr|St|No|Nos|Inc|Co|Corp|Ltd|Gen|Gov|Sgt|Lt|Det|Capt|"
    r"Rep|Sen|Hon|Ave|Blvd|Rd|Ft|Mt|vs|v|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|"
    r"Ala|Ariz|Ark|Calif|Colo|Conn|Del|Fla|Ga|Ill|Ind|Kan|Ky|La|Md|Mass|Mich|Minn|Miss|Mo|"
    r"Mont|Neb|Nev|Okla|Ore|Pa|Tenn|Tex|Va|Vt|Wash|Wis|Wyo|N\.C|S\.C|N\.Y|N\.J|D\.C|W\.Va)"
    r"|\b[A-Z])$"
)


_SENTENCE_BREAK_RE = re.compile(
    r"[.!?][\"'\u201d\u2019)]*(?=\s+[\"'\u201c\u2018(A-Z0-9])"
    r"|\n\s*\n"
    r"|\n(?=\s*(?:Publication\s+date|Source|Date\s+Posted|Posted|Updated)\s*:)"
    r"|\n(?=[A-Z][a-z]+\.?\s+\d{1,2},\s+(?:19|20)\d{2}\s*\n)"
    r"|(?<=Source:)|(?<=\d{4}-\d{2}-\d{2})(?=\s)"
)


def header_end(text: str) -> int:
    """Offset where a release's body starts (after the "Source:" line), else 0."""
    m = re.search(r"^\s*Source:", text[:1500], re.M)
    return m.end() if m else 0


@lru_cache(maxsize=256)
def sentence_spans(text: str) -> Tuple[Tuple[int, int], ...]:
    """
    Sentence boundaries: .!? before whitespace + capital/quote/digit, blank lines,
    and press-release header lines (title / date / "Publication date:" / "Source:"),
    so a headline never shares a sentence with the body.
    """
    spans: List[Tuple[int, int]] = []
    start = 0
    for m in _SENTENCE_BREAK_RE.finditer(text):
        end = m.end()
        if m.group(0).startswith(".") and _ABBREV_BEFORE_DOT.search(text[max(0, m.start() - 8) : m.start()]):
            continue
        if text[start:end].strip():
            spans.append((start, end))
        start = end
    if text[start:].strip():
        spans.append((start, len(text)))
    return tuple(spans)


def sentence_at(text: str, start: int, end: int) -> Tuple[int, int]:
    for s, e in sentence_spans(text):
        if s <= start < e:
            return s, max(e, end)
    return 0, len(text)


_CLAUSE_BREAK_RE = re.compile(
    r";|,\s+(?:but|though|although|while|whereas)\b|\s+and\s+(?:now\s+)?faces\b|\s+but\s+",
    re.IGNORECASE,
)


def clause_at(text: str, start: int, end: int) -> Tuple[int, int]:
    """Sentence around the span, narrowed at semicolons and contrastive conjunctions."""
    s, e = sentence_at(text, start, end)
    left, right = s, e
    for m in _CLAUSE_BREAK_RE.finditer(text, s, e):
        if m.end() <= start:
            left = m.start() if m.group(0).lstrip().lower().startswith("and") else m.end()
        elif m.start() >= end:
            right = m.start()
            break
    return left, right


# ---------------------------------------------------------------------------
# Age support
# ---------------------------------------------------------------------------

_YEAR_OLD_AFTER = re.compile(
    r"^\s*(?:-|\s)\s*(?:years?|yrs?)\s*(?:-|\s)\s*olds?\b|^\s*(?:years?|yrs?)\s+of\s+age\b"
    r"|^\s*-?\s*(?:years?|yrs?)-olds?\b|^\s+(?:years?|yrs?)\s+old\b",
    re.IGNORECASE,
)
_DURATION_AFTER = re.compile(r"^\s*-?\s*(?:years?|yrs?|months?|weeks?|days?|hours?)\b", re.IGNORECASE)
_AGE_WORD_BEFORE = re.compile(r"\b(?:aged?|ages|age\s+of|ages\s+of|as\s+young\s+as)\s*$", re.IGNORECASE)
_RANGE_FIRST = re.compile(
    rf"^\s*(?:-|to|and|through|thru)\s*{NUMBER_RE}\s*(?:-\s*)?(?:years?|yrs?)?\s*(?:-|\s)\s*olds?\b"
    rf"|^\s*-?\s*and\s+{NUMBER_RE}\s*-\s*years?\s*-\s*olds?\b",
    re.IGNORECASE,
)
# "8 to 10 years old": the unit after the high end makes the low end an age with no "ages" before it.
_RANGE_LOW_YEARS_OLD = re.compile(
    rf"^\s*(?:-\s*)?(?:to|through|thru)\s+{NUMBER_RE}\s*(?:-\s*)?(?:years?|yrs?)\s*(?:-|\s)\s*olds?\b",
    re.IGNORECASE,
)
_RANGE_SECOND_BEFORE = re.compile(
    rf"\b(?:aged?|ages?(?:\s+of)?|between\s+the\s+ages?\s+of)\s+{NUMBER_RE}\s*"
    r"(?:-|to|and|through|thru)\s*$",
    re.IGNORECASE,
)
_CAP_NAME_COMMA_BEFORE = re.compile(r"[A-Z][\w'\-.]*(?:\s+[A-Z][\w'\-.]*){0,4}\s*,\s*$")
# "a girl, 14, under his supervision": a child noun in apposition, the way a name is (#58).
_CHILD_NOUN_COMMA_BEFORE = re.compile(
    r"\b(?:girl|boy|victim|child|minor|juvenile|teen|teenager|daughter|son|step-?daughter|step-?son|niece|nephew)\s*,\s*$",
    re.IGNORECASE,
)
_CAP_NAME_PAREN_BEFORE = re.compile(r"[A-Z][\w'\-]+(?:\s+[A-Z][\w'\-]+){0,4}\s*\(\s*$")
# "arrested Thomas Meyer (42) for …": after an arrest verb the parenthesis needs no follow-on word
_ARRESTED_NAME_PAREN_BEFORE = re.compile(
    r"\b(?:arrested|charged|indicted|arraigned|booked)\s+[A-Z][\w'\-]+(?:\s+[A-Z][\w'\-.]+){0,4}\s*\(\s*$"
)

# A bare child noun ("the 11-year-old sisters") identifies a child, not a victim. A victim
# role from a noun alone needs the sentence to show victimization (contact, abuse, material,
# enticement, rescue …); otherwise the evidence is weak and needs a second family.
VICTIMIZATION_CUE_RE = re.compile(
    r"\b(?:victims?|abus\w*|assault\w*|rap(?:e|ed|es|ing)|molest\w*|exploit\w*|traffick\w*|kidnap\w*|entic\w*"
    r"|lur(?:e|ed|es|ing)|solicit\w*|groom\w*|coerc\w*|extort\w*|sextort\w*|threat\w*|harass\w*|sexual\w*|sex"
    r"|nude|naked|explicit|porn\w*|csam|images?|videos?|photo\w*|pictures?|recordings?|communicat\w*|messag\w*"
    r"|chat\w*|contact\w*|met|meet\w*|text(?:ed|ing|s)|touch\w*|fondl\w*|rescu\w*|recover\w*|missing|runaway"
    r"|relationship|intercourse|prostitut\w*|sold|purchas\w*|paid|produc\w*|record(?:ed|ing|ings)|film\w*|expos\w*"
    r"|indecen\w*|lewd|offen[cs]\w*|incest|penetrat\w*|batter\w*|endanger\w*|neglect\w*|injur\w*|hurt|kill\w*"
    r"|murder\w*|death|died|dead|webcam|livestream\w*)\b",
    re.IGNORECASE,
)


def has_victimization_cue(text: str, start: int, end: int) -> bool:
    """True when the sentence holding text[start:end] shows victimization (see VICTIMIZATION_CUE_RE)."""
    ss, se = sentence_at(text, start, end)
    sentence = normalize_surface(text[ss:start] + " " + text[end:se])
    return bool(VICTIMIZATION_CUE_RE.search(sentence))


# Material and production cues. A verb may sit between the noun and the age
# ("videos ... were located molesting a 3 year old"), so this is lexical, not a dependency link.
_MATERIAL_LEFT = re.compile(
    r"\b(?:images?|videos?|photos?|photographs?|pictures?|files?|material|depictions?|depict(?:s|ed|ing)|"
    r"CSAM|content|pornography|movies?|recordings?)\b[^.;:]{0,90}$",
    re.IGNORECASE,
)
_PRODUCTION_LEFT = re.compile(
    r"\b(?:produc\w*|creat\w*|record\w*|film\w*|took|taken|made|photograph(?:ed|ing))\b[^.;]{0,90}$",
    re.IGNORECASE,
)
_PREFERENCE_LEFT = re.compile(
    r"\b(?:attracted\s+to|(?:sexual\s+)?preferences?\s+(?:was|for|of|is))\b[^.;]{0,70}$",
    re.IGNORECASE,
)


def _clause_left_right(text: str, start: int, end: int) -> Tuple[str, str]:
    cs, ce = clause_at(text, start, end)
    left = normalize_surface(text[max(cs, start - 120) : start])
    right = normalize_surface(text[end : min(ce, end + 80)])
    return left, right


def is_depicted_material(text: str, start: int, end: int) -> bool:
    """True when the age sits in material already made ("pictures ... molesting a 3 year old"), not a named victim."""
    left, right = _clause_left_right(text, start, end)
    if re.match(r"^\W*years?\W*olds?\W*victim\b", right, re.IGNORECASE):
        return False
    if not _MATERIAL_LEFT.search(left):
        return False
    if _PRODUCTION_LEFT.search(left):
        return False
    return True


def is_stated_preference(text: str, start: int, end: int) -> bool:
    """True for an age someone said they were attracted to, not a child in this case."""
    left, _right = _clause_left_right(text, start, end)
    return bool(_PREFERENCE_LEFT.search(left))


def is_age_shaped(text: str, start: int, end: int) -> Tuple[bool, str]:
    """
    True only for age-shaped contexts. ``20 years in prison`` / ``four counts`` /
    a bare ``32`` are not ages.
    """
    right = normalize_surface(text[end : end + 30])
    left = normalize_surface(text[max(0, start - 60) : start])
    if _YEAR_OLD_AFTER.match(right):
        return True, "year_old"
    if _DURATION_AFTER.match(right):
        return False, "duration_not_age"
    if _AGE_WORD_BEFORE.search(left):
        return True, "age_word"
    if _RANGE_FIRST.match(right) and re.search(r"\b(?:aged?|ages?|between)\b[^.]{0,30}$", left, re.I):
        return True, "age_range_low"
    if _RANGE_FIRST.match(right) and re.search(r"-\s*and\s", right[:8]):
        return True, "hyphen_range_low"
    if _RANGE_LOW_YEARS_OLD.match(right):
        return True, "age_range_low"
    if _RANGE_SECOND_BEFORE.search(left):
        return True, "age_range_high"
    # Appositive: "Bryce Bock, 32, of …" / "Smith, 32." / "Smith, 32 was …"
    # "Playpen, one of the world's largest" is the idiom, not an age of 1.
    if _CAP_NAME_COMMA_BEFORE.search(left) and re.match(r"^\s*(?:,|\.|\)|;|$|\s+(?:was|were|is|of|from|who|has|had|pleaded|pled)\b)", right):
        if re.match(r"^\s+of\s+the\b", right, re.I):
            return False, "one_of_idiom"
        return True, "name_comma"
    if _CHILD_NOUN_COMMA_BEFORE.search(left) and re.match(r"^\s*(?:[,.;)]|$|\s+(?:who|whom|was|and)\b)", right):
        return True, "noun_comma"
    # "John Smith (32), of Leeds" / "Thomas Meyer (42, Riverview)"; not "Trafficking in Persons (4)"
    if _CAP_NAME_PAREN_BEFORE.search(left) and (
        re.match(r"^\s*,\s*[A-Z][\w.\- ]{1,40}\)", right)
        or re.match(r"^\s*\)\s*(?:,|(?:of|from|was|were|has|is|who|appeared|pleaded|pled|admitted|and)\b)", right)
    ):
        return True, "name_paren"
    if _ARRESTED_NAME_PAREN_BEFORE.search(left) and re.match(r"^\s*\)", right):
        return True, "name_paren"
    return False, "not_age_shaped"


def is_closed_age_range(text: str, start: int, end: int) -> bool:
    """
    True when this age token is an endpoint of a span: "ages 4 thru 10",
    "aged 6 to 9", "aged 6-9", "4-6 years old", "5- to 8-year-old".
    A list joined by and ("ages 6 and 9") is not a span. "34-year-old" is not a span.
    """
    right = normalize_surface(text[end : end + 48])
    left = normalize_surface(text[max(0, start - 48) : start])
    if re.match(
        rf"^\s*(?:-\s*)?(?:to|through|thru)\s+{NUMBER_RE}\b|^\s*-\s*{NUMBER_RE}\b",
        right,
        re.IGNORECASE,
    ):
        return True
    if re.search(
        rf"(?:(?:ages?|aged)\s+)?{NUMBER_RE}\s*-\s*(?:to\s+)?$",
        left,
        re.IGNORECASE,
    ):
        return True
    if re.search(
        rf"(?:ages?|aged)\s+{NUMBER_RE}\s+(?:to|through|thru)\s+$",
        left,
        re.IGNORECASE,
    ):
        return True
    # "8 to 10 years old": the high end, with the unit after it
    if re.search(rf"(?<![\w$]){NUMBER_RE}\s+(?:to|through|thru)\s+$", left, re.IGNORECASE) and _YEAR_OLD_AFTER.match(right):
        return True
    return False


_AGE_RANGE_RES = (
    re.compile(
        rf"(?<![\w$])(?P<lo>{NUMBER_RE})(?:\s*-\s*(?:to\s+)?|\s+(?:to|through|thru)\s+)(?P<hi>{NUMBER_RE})(?![\w])",
        re.IGNORECASE,
    ),
    # "between the ages of 8 and 13": "and" joins a span only after "between"
    re.compile(
        rf"\bbetween\s+(?:the\s+)?(?:ages?\s+(?:of\s+)?)?(?P<lo>{NUMBER_RE})\s+and\s+(?P<hi>{NUMBER_RE})(?![\w])",
        re.IGNORECASE,
    ),
)


def age_range_at(text: str, start: int, end: int) -> Optional[Tuple[int, int, int]]:
    """``(low, high, end of the span)`` when this age token is one end of a stated span of ages.

    Covers what ``is_closed_age_range`` covers plus "between the ages of 8 and 13".
    None when the token is not an end, or the ends do not parse as low < high.
    """
    lo_at = max(0, start - 60)
    window = normalize_surface(text[lo_at : end + 60])
    for rx in _AGE_RANGE_RES:
        for m in rx.finditer(window):
            if (lo_at + m.start("lo"), lo_at + m.end("lo")) != (start, end) and (
                lo_at + m.start("hi"), lo_at + m.end("hi")
            ) != (start, end):
                continue
            low, high = parse_number(m.group("lo")), parse_number(m.group("hi"))
            if low is not None and high is not None and low < high:
                return low, high, lo_at + m.end("hi")
    return None


def age_support(text: str, start: Optional[int], end: Optional[int], value) -> Tuple[bool, str]:
    """Typed age validation on an original-text span (the age token)."""
    if start is None or end is None or not (0 <= start < end <= len(text)):
        return False, "bad_offsets"
    token = text[start:end]
    age = parse_number(token)
    if age is None:
        return False, "token_not_a_number"
    if value is not None and parse_number(str(value)) != age:
        return False, "value_not_in_span"
    if 1900 <= age <= 2099:
        return False, "year_like_rejected"
    if not 1 <= age <= 120:
        return False, "age_out_of_range"
    if token.isdigit():
        if (start > 0 and (text[start - 1].isdigit() or text[start - 1] in ".,$")
                and start > 1 and text[start - 2].isdigit()):
            return False, "digit_of_larger_number"
        if end < len(text) and (text[end].isdigit() or (text[end] in ",." and end + 1 < len(text) and text[end + 1].isdigit())):
            return False, "digit_of_larger_number"
    shaped, why = is_age_shaped(text, start, end)
    if not shaped:
        return False, why
    return True, why


_AGE_TOKEN_RE = re.compile(rf"(?<![\w$.,])({NUMBER_RE})(?![\w])", re.IGNORECASE)


def age_token_in(text: str, start: int, end: int, value) -> Tuple[Optional[Tuple[int, int]], str]:
    """Locate the single token for ``value`` inside text[start:end] (LLM quotes)."""
    target = parse_number(str(value))
    if target is None:
        return None, "unparseable_value"
    hits = [
        (start + m.start(1), start + m.end(1))
        for m in _AGE_TOKEN_RE.finditer(text[start:end])
        if parse_number(m.group(1)) == target
    ]
    if not hits:
        return None, "value_not_in_quote"
    if len(hits) > 1:
        return None, "ambiguous_value_in_quote"
    return hits[0], "ok"


# ---------------------------------------------------------------------------
# Sentence support
# ---------------------------------------------------------------------------

DURATION_RE = re.compile(
    # No digit or decimal point before the number: "13.3 years" must not yield "3 years".
    rf"(?<![\d.,/])\b(?P<approx>(?:over|more\s+than|nearly|almost|about|approximately)\s+)?"
    rf"(?:(?P<low>{NUMBER_RE})\s*(?:-|to|and)\s*)?"
    rf"(?P<n>{NUMBER_RE})(?P<half>[\s-]+and[\s-]+(?:a[\s-]+)?half)?\s*-?\s*"
    r"(?P<unit>years?|yrs?|months?|weeks?|days?)\b(?!\s*-?\s*olds?\b)(?!\s+of\s+age\b)"
    # One term written in two units: "five years and three months", "14 years, two months"
    rf"(?:,?\s+(?:and\s+)?(?P<n2>{NUMBER_RE})\s*-?\s*months?\b)?",
    re.IGNORECASE,
)
# No lookaheads: the gate re-matches the bare span, so the whole phrase must be inside it.
# Bare "of life" ("all walks of life") is never a sentence.
LIFE_RE = re.compile(
    r"\blife(?:time)?\s+(?:in\s+(?:federal\s+)?prison|imprisonment|sentences?|term)\b"
    r"|\b(?:to|of)\s+life\s+(?:in\s+(?:federal\s+)?prison|imprisonment|without\s+(?:the\s+possibility\s+of\s+)?parole|plus)\b"
    r"|\bup\s+to\s+life\b|\byears\s+to\s+life\b|\bsentenced\s+(?:\w+\s+){0,3}?to\s+life\b",
    re.IGNORECASE,
)
MONEY_RE = re.compile(
    r"\$\s?\d(?:[\d,]*\d)?(?:\.\d{2})?(?:\s*(?:million|thousand))?(?:-thousand(?:-dollars)?)?", re.IGNORECASE
)

_UNIT_MONTHS = {"year": 12, "yr": 12, "month": 1, "week": 0, "day": 0}


def duration_months(match: re.Match) -> Optional[float]:
    """Months for a DURATION_RE match (upper bound of ranges); weeks/days → fractional months."""
    n = parse_number(match.group("n"))
    if n is None:
        return None
    unit = match.group("unit").lower().rstrip("s")
    if unit in ("week", "day"):
        return round(n / (4.345 if unit == "week" else 30.44), 2)
    months = n * _UNIT_MONTHS[unit]
    if match.group("half") and unit == "year":
        months += 6
    if match.group("n2") and unit in ("year", "yr"):
        months += parse_number(match.group("n2")) or 0
    return months


def money_value(token: str) -> Optional[float]:
    s = normalize_surface(token).lower().replace(" ", "")
    m = re.match(r"\$([\d,]+(?:\.\d{2})?)", s)
    if not m:
        return None
    try:
        amount = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    if "million" in s:
        amount *= 1_000_000
    elif "thousand" in s:
        amount *= 1_000
    return amount


_EXPOSURE_CUES = re.compile(
    r"\bfaces?\b|\bfacing\b|\bcould\s+(?:face|receive|get)\b|\bwill\s+face\b|\bpunishable\s+by\b"
    r"|\bcarr(?:y|ies)\s+(?:a\s+)?(?:(?:maximum|minimum|potential|possible|mandatory|statutory)\s+)*"
    r"(?:penalty|penalties|sentence|term|prison\s+term|punishment|minimum|maximum)\b"
    r"|\bcarr(?:y|ies)\s+up\s+to\b"
    r"|\b(?:statutory\s+)?maximum\s+(?:penalty|sentence|of|term)\b|\bmaximum\s+possible\b"
    r"|\bmandatory\s+minimum\s+(?:penalty|sentence|term|of)\b|\bminimum\s+(?:of|mandatory)\b"
    r"|\bif\s+convicted\b|\bupon\s+conviction\b|\bpotential\s+(?:penalty|sentence|maximum)\b"
    r"|\bpossible\s+(?:penalty|sentence|maximum)\b|\bup\s+to\b|\bpenalt(?:y|ies)\s+(?:of|include|for)\b"
    r"|\bmaximum\s+sentences\b|\b(?:will|would|agreed\s+to|to)\s+recommend\b|\brecommend(?:s|ed)?\s+that\b"
    r"|\b(?:will|may|could|might|can|would)\s+be\s+sentenced\b|\bif\s+the\s+court\s+accepts\b"
    r"|\b(?:seek|seeks|seeking|sought)\s+(?:a\s+)?(?:sentence|term|prison)\b|\bscheduled\s+to\s+be\s+sentenced\b"
    # a term stipulated in a plea agreement is not imposed until the court sentences
    r"|\b(?:has|have|had)?\s*agreed\s+to\s+(?:serve|accept)\b",
    re.IGNORECASE,
)
# "could be sentenced to up to 50 years" is conditional even though "sentenced to up to" also
# describes an imposed indeterminate term ("was sentenced to up to 50 years").
_CONDITIONAL_SENTENCING = re.compile(
    r"\b(?:could|may|might|would|can|will)\s+be\s+(?:sentenced|ordered)\b|\bif\s+convicted\b|\bupon\s+conviction\b",
    re.IGNORECASE,
)
# "a term of supervised release of between 5 years and life" before sentencing = statutory range.
_RANGE_EXPOSURE = re.compile(r"\bbetween\s+[\w-]+\s+(?:years?\s+)?and\s+(?:life|[\w-]+\s+years?)\b", re.IGNORECASE)
_IMPOSED_CUES = re.compile(
    r"\bsentenced\b|\bordered\s+(?:today\s+)?to\s+(?:serve|pay)\b|\breceived\s+(?:an?\s+|the\s+)?"
    r"(?:\w+\s+){0,2}(?:sentence|prison\s+term|term)\b|\bwas\s+given\b|\bwill\s+serve\b|\bmust\s+serve\b"
    r"|\bimprisonment\b|\bimposed\b|\bto\s+be\s+followed\s+by\b|\bfollowed\s+by\b|\bserve\b"
    r"|\bjailed\s+for\b|\bimprisoned\s+for\b|\b(?:has\s+been|was|been)\s+given\b"
    r"|\btotal\s+(?:prison\s+)?(?:sentence|term)\s+of\b|\bsentences?\s+to\s+run\b"
    r"|\b(?:ordered|imposed|gave)\s+(?:\w+\s+)?the\s+(?:statutory\s+)?maximum\b",
    re.IGNORECASE,
)
_SENTENCED_TO_UP_TO = re.compile(
    r"\b(?:sentenced|ordered)\s+(?:\w+\s+){0,3}?to\s+(?:serve\s+)?up\s+to\b"
    # "ordered the maximum sentence for each offense … total sentence of 400 months" was imposed
    r"|\b(?:ordered|imposed|gave)\s+(?:\w+\s+)?the\s+(?:statutory\s+)?maximum\b",
    re.IGNORECASE,
)
# Hyphenated compounds ("post-incarceration") count as one word; "releases" (sic) is still release.
_SUPERVISED_AFTER = re.compile(r"^\W{0,3}(?:[\w-]+\W+){0,3}?(?:supervised\s+releases?|supervision)\b", re.IGNORECASE)
_PROBATION_NEAR = re.compile(r"^\W{0,3}(?:\w+\W+){0,2}?probation\b", re.IGNORECASE)
_PROBATION_BEFORE = re.compile(r"\bprobation\s+for\s+(?:a\s+(?:term|period)\s+of\s+)?$", re.IGNORECASE)
# UK "six years on licence" / "five years on an extended licence" is supervision, not a prison term.
_LICENCE_AFTER = re.compile(
    r"^\W{0,8}on\s+(?:an?\s+)?(?:extended\s+)?licen[cs]e\b",
    re.IGNORECASE,
)
_SUPERVISED_BEFORE = re.compile(
    r"\bsupervised\s+releases?\s+(?:for\s+|of\s+)?(?:a\s+(?:term|period)\s+of\s+)?(?:between\s+|at\s+least\s+|up\s+to\s+)?$",
    re.IGNORECASE,
)
_FINE_CUES = re.compile(r"\bfine[ds]?\b|\bassessments?\b|\brestitution\b|\bforfeit\w*\b|\bpenalty\b|\bto\s+pay\b|\bpay\b", re.IGNORECASE)
_BAIL_CUES = re.compile(r"\bbail\b|\bbond\b|\breward\b|\bgrant\b|\bfunding\b|\bsettlement\b|\bworth\b|\bsold\b|\bpaid\s+(?:the\s+)?(?:victim|minor)\b", re.IGNORECASE)
# Durations that describe something other than a term: parole eligibility, a rider,
# an age threshold ("less than 13 years"), how long conduct lasted, a life term's minimum.
_NOT_SENTENCE_BEFORE = re.compile(
    r"(?:\beligible\s+for\s+parole\s+after|\bparole\s+(?:eligibility|ineligibility)\s+(?:of|after)"
    r"|\bretained\s+jurisdiction\b[^.]{0,40}|(?<!not\s)\b(?:less|younger|older)\s+than|\bunder\s+the\s+age\s+of"
    r"|\bover\s+the\s+course\s+of|\bfor\s+the\s+(?:past|last)|\b(?:a\s+)?(?:period|span)\s+of|\blasting|\bspanning"
    r"|\blife\s+(?:term|sentence)\s+(?:of|with\s+a\s+minimum(?:\s+term)?\s+of))"
    r"\s+(?:at\s+least\s+|about\s+|approximately\s+|nearly\s+|more\s+than\s+|up\s+to\s+)?$",
    re.IGNORECASE,
)
_NOT_SENTENCE_AFTER = re.compile(
    r"^\s*(?:ago|earlier|later|old|of\s+age|after|before|prior|since)\b"
    r"|^\s*(?:of|in)\s+(?:age|the\s+(?:investigation|relationship|abuse))\b",
    re.IGNORECASE,
)
# "a nine-month, multi-agency investigation" / "an 18-month undercover operation" / "a two-day
# trial" is how long the work took, not a term (#58). Read from the text after the span: the
# clause can end at the comma.
_ACTIVITY_NOUNS = r"(?:investigations?|operations?|initiatives?|probes?|sweeps?|stings?|inquir(?:y|ies)|crackdowns?|(?:jury\s+|bench\s+)?trials?)"
_ACTIVITY_AFTER_HYPHENATED = re.compile(
    r"^(?:-?long)?[\s,]+(?:(?!(?:sentence|term|prison|jail|after|following|for|in|of|and|to|the|an?|by|from|with|was|were)\b)"
    rf"[\w-]+[\s,]+){{0,4}}?{_ACTIVITY_NOUNS}\b",
    re.IGNORECASE,
)
_ACTIVITY_AFTER_BARE = re.compile(rf"^(?:-?long)?\s+{_ACTIVITY_NOUNS}\b", re.IGNORECASE)
_HYPHENATED_UNIT = re.compile(r"-\s*(?:years?|yrs?|months?|weeks?|days?)$", re.IGNORECASE)


def _is_activity_duration(text: str, start: int, end: int) -> bool:
    after = normalize_surface(text[end : end + 90])
    token = normalize_surface(text[start:end])
    if _HYPHENATED_UNIT.search(token):
        return bool(_ACTIVITY_AFTER_HYPHENATED.match(after))
    return bool(_ACTIVITY_AFTER_BARE.match(after))


_REGISTRATION_AFTER = re.compile(r"^[^.]{0,30}\bas\s+a\s+result\b|register", re.IGNORECASE)


def sentence_kind(text: str, start: int, end: int) -> str:
    """
    Deterministic clause-level kind for a duration/amount span.
    Exposure cues in the clause override everything (#24); then sub-kinds.
    """
    cs, ce = clause_at(text, start, end)
    clause = normalize_surface(text[cs:ce])
    rel_s, rel_e = start - cs, end - cs
    before = clause[:rel_s]
    after = clause[rel_e:]
    token = clause[rel_s:rel_e]

    if token.startswith("$") and _BAIL_CUES.search(clause):
        return "not_sentence"  # bond / bail / reward amounts are never sentences, exposure or not
    # "jailed for 20 months after trading" is the term. "two years after the arrest" is a gap.
    time_offset = _NOT_SENTENCE_AFTER.match(after)
    offset_follows_imposed = bool(
        time_offset
        and re.search(r"\bafter\b", time_offset.group(0), re.I)
        and re.search(r"\b(?:jailed|imprisoned)\s+for\s+$|\bsentenced\s+to\s+(?:serve\s+)?$", before, re.I)
    )
    if not token.startswith("$") and (
        _NOT_SENTENCE_BEFORE.search(before)
        or (time_offset and not offset_follows_imposed)
        or re.search(r"\bregister\w*\b[^.]{0,40}$", before, re.I)
        or _is_activity_duration(text, start, end)
        # "abusing a minor for over 5 years" is how long the abuse lasted, not the term.
        or re.search(r"\babus\w*(?:\s+\w+){0,4}\s+for\s+$", before, re.I)
        # "please visit Cloud Man Sentenced To Ten Years" is the next article's title.
        or re.search(r"\b(?:please\s+visit|for\s+more\s+information\s+about)\b", before, re.I)
    ):
        return "not_sentence"
    if _EXPOSURE_CUES.search(clause) and (_CONDITIONAL_SENTENCING.search(clause) or not _SENTENCED_TO_UP_TO.search(clause)):
        # "up to" only signals exposure when no imposed anchor precedes it in the clause.
        only_up_to = all(m.group(0).lower().startswith("up to") for m in _EXPOSURE_CUES.finditer(clause))
        if not (only_up_to and _IMPOSED_CUES.search(before)):
            return "exposure"
    if _RANGE_EXPOSURE.search(clause) and not re.search(r"\bsentenced\b", clause, re.I):
        return "exposure"
    if token.startswith("$"):
        return "fine" if _FINE_CUES.search(clause) else "unknown"
    if _SUPERVISED_AFTER.match(after) or _SUPERVISED_BEFORE.search(before):
        return "supervised_release"
    if _PROBATION_NEAR.match(after) or _PROBATION_BEFORE.search(before):
        return "probation"
    if _LICENCE_AFTER.match(after):
        return "supervised_release"
    # "starting point of 4 years" and "starting point for sentencing, 18 months"
    # and "starting point that he be sentenced to four years" are not the term.
    # A later "sentenced him to" in the same clause is the term, so it stays.
    start_pt = re.search(r"\bstarting\s+point\b(?P<mid>[\s\S]{0,120})$", before, re.I)
    if start_pt:
        mid = start_pt.group("mid")
        hypothetical = re.search(
            r"\b(?:that\s+(?:he|she)\s+be|to\s+be)\s+sentenced\b", mid, re.I
        )
        real_term_later = re.search(r"\b(?:sentenced|jailed|imprisoned)\b", mid, re.I)
        if hypothetical or not real_term_later:
            return "not_sentence"
    if re.search(r"sentencing\s+starting\s+point", after, re.I):
        return "not_sentence"
    if re.search(
        r"\bminimum\s+(?:period\s+of\s+imprisonment|imprisonable\s+period)\s+of\s+$",
        before,
        re.I,
    ):
        return "not_sentence"
    if re.search(r"\baged\s+$", before, re.I):
        return "not_sentence"
    if _IMPOSED_CUES.search(clause):
        return "imposed"
    return "unknown"


SENTENCE_KINDS = ("imposed", "exposure", "supervised_release", "probation", "fine", "custody", "prior")


def sentence_support(text: str, start: Optional[int], end: Optional[int]) -> Tuple[bool, str, Dict]:
    """Typed sentence validation: the span must be a duration, ``life``, or a dollar amount."""
    if start is None or end is None or not (0 <= start < end <= len(text)):
        return False, "bad_offsets", {}
    span = normalize_surface(text[start:end])
    if "%" in span or re.search(r"\bpercent\b", text[end : end + 10], re.I):
        return False, "percent_rejected", {}
    m = DURATION_RE.fullmatch(span.strip())
    if m:
        months = duration_months(m)
        if months is None:
            return False, "unparseable_duration", {}
        info = {"months": months, "approx": bool(m.group("approx")), "range_low": m.group("low") is not None}
        return True, "duration", info
    if LIFE_RE.fullmatch(span.strip()) or span.strip().lower() in ("life", "lifetime"):
        return True, "life", {"months": None, "life": True}
    if MONEY_RE.fullmatch(span.strip()):
        amount = money_value(span)
        if amount is None:
            return False, "unparseable_amount", {}
        return True, "amount", {"amount": amount}
    return False, "not_a_duration_or_amount", {}


def canonical_sentence_span(text: str, start: int, end: int) -> Optional[Tuple[int, int]]:
    """Narrow an asserted span to its single duration / amount / life token."""
    chunk = text[start:end]
    norm = normalize_surface(chunk)
    hits = [(m.start(), m.end()) for m in DURATION_RE.finditer(norm)]
    hits += [(m.start(), m.end()) for m in MONEY_RE.finditer(norm)]
    if not hits:
        hits = [(m.start(), m.end()) for m in LIFE_RE.finditer(norm)]
    if len(hits) != 1:
        return None
    s, e = hits[0]
    return start + s, start + e
