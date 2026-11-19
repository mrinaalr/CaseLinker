"""
Victim-age precision gate v2 (production).

KEEP → pass through merge; REJECT → drop; REVIEW → excluded unless
promoted via config/victim_age_overrides.json (human adjudication).
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

_PROCESSING_LAYER = Path(__file__).resolve().parent
_PATTERN_LAYER = _PROCESSING_LAYER / "Pattern Processing Layer"
_ML_LAYER = _PROCESSING_LAYER / "ML Processing Layer"
if str(_PROCESSING_LAYER) not in sys.path:
    sys.path.insert(0, str(_PROCESSING_LAYER))
if str(_PATTERN_LAYER) not in sys.path:
    sys.path.insert(0, str(_PATTERN_LAYER))
if str(_ML_LAYER) not in sys.path:
    sys.path.insert(0, str(_ML_LAYER))

_spec = importlib.util.spec_from_file_location(
    "pattern_processing", _PATTERN_LAYER / "pattern_processing.py"
)
_pp = importlib.util.module_from_spec(_spec)
assert _spec.loader
_spec.loader.exec_module(_pp)

from ner_extraction import _is_sentencing_context

_CAP_NAME_BEFORE_COMMA = _pp._CAP_NAME_BEFORE_COMMA
_COMMA_AGE_COUNT_PREFIX_RE = _pp._COMMA_AGE_COUNT_PREFIX_RE
_PERP_COMMA_VERB_PATTERNS = _pp._PERP_COMMA_VERB_PATTERNS

_VICTIM_WORDS_RE = re.compile(
    r"\b(?:victim|victims|minor|minors|child|children|girl|boy|boys|girls|"
    r"juvenile|juveniles|underage|daughter|son|infant|baby|toddler|"
    r"pupil|student|brother|sister|family\s+member|"
    r"preteen|preteens|prepubescent|prepubescents|female|male)\b",
    re.I,
)
_YO_HYPHEN_RE = re.compile(
    r"(?<!\d)\d{1,2}\s*[-\s]*(?:year|years|month|months|yr|yrs)\s*[-\s]*olds?\b",
    re.I,
)
_GROOMING_VERB_AGE_RE = re.compile(
    r"\b(?:induce|induced|solicit|solicited|entice|enticed|groom|groomed|"
    r"abuse|abused|assault|assaulted|molest|molested|exploit|exploited|"
    r"traffic|trafficked)\w*\s+(?:a\s+)?(?:\w+\s+){0,4}?"
    rf"(?<!\d)({{age}})\s*[-\s]*(?:year|years)\s*[-\s]*olds?\b",
    re.I,
)
_APPROX_YO_RE = re.compile(
    r"\bapproximately\s+(?P<age>\d{1,2})\s+years?\s+old\b",
    re.I,
)

_QUANTITY_AFTER_RE = re.compile(r"^\s*,\s*\d{2,}\b")
_QUANTITY_BEFORE_RE = re.compile(r"\d,\s*$")
_FILES_IMAGES_RE = re.compile(
    r"\b\d{1,3},?\d*\s+(?:files|file|images|image|pages|page|videos|video|photos|photo)\b",
    re.I,
)
_COUNT_OF_AGE_RE = re.compile(r"\b(\d{1,2})\s+counts?\b", re.I)
_IP_BLOCK_RE = re.compile(r"\bIP\s+address", re.I)

_DEFENDANT_AFTER_COMMA_RE = re.compile(
    r"\b(?:was|were)\s+(?:arrested|charged|indicted|convicted|booked|jailed|"
    r"sentenced|arraigned|transported|held|facing)\b",
    re.I,
)
_DEFENDANT_CHARGE_RE = re.compile(
    r"\b(?:arrested|charged|indicted|convicted|booked|faces?|facing|accused|"
    r"suspect|defendant|offender|perpetrator|pleaded|pled)\b",
    re.I,
)
_YO_PERP_RE = re.compile(
    r"(\d{1,2})\s*-?\s*year\s*-?\s*old\s+(?:man|woman|male|resident|student)\b",
    re.I,
)

_STATUTORY_THRESHOLD_RE = re.compile(
    r"\b(?:person|anyone|any\s+person|individual)\s+under\s+(\d{1,2})\b|"
    r"\b(\d{1,2})\s+years?\s+or\s+younger\b|"
    r"\bunder\s+(\d{1,2})\s+years?\s+of\s+age\b",
    re.I,
)
_STATUTE_SUBSECTION_RE = re.compile(
    r"\b\d+[A-Z]?[.\-]?\d*[A-Z]?[.\-]?\d*\([^\)]{0,12}\b(\d{1,2})\b",
    re.I,
)
_PERP_TARGET_RANGE_RE = re.compile(
    r"\b(?:targeting|targeted)\s+(?:\w+\s+){0,3}?juveniles?\s+age\s+(\d{1,2})\s+through\b",
    re.I,
)
_DECOY_HE_WAS_RE = re.compile(
    r"\b(?:he|she|they)\s+was\s+(\d{1,2})\s+years?\s+old\b",
    re.I,
)
_DECOY_CTX_RE = re.compile(
    r"\b(?:undercover|decoy|pretend|posing|believed\s+to\s+be|thought\s+he\s+was|"
    r"thought\s+she\s+was|persona|alias|\"Jack\"|\"Emily\")\b",
    re.I,
)

_HARD_REJECT = frozenset(
    {
        "files_images_quantity",
        "digit_of_larger_number",
        "defendant_comma_was_arrested",
        "defendant_comma_charge_context",
        "defendant_comma_headline_teen",
        "perp_comma_verb_pattern",
        "perp_target_range",
        "statute_subsection",
        "statutory_threshold",
        "decoy_he_was_N",
        "year_old_man_woman",
        "N_counts",
        "count_prefix",
        "ip_address_block",
        "sentencing_years_to_life",
        "bare_digit_no_age_phrase",
    }
)

_STRONG_SUPPORT = frozenset(
    {
        "year_old_with_victim_word",
        "year_old_with_offense_corpus",
        "plural_N_year_olds",
        "as_young_as",
        "approximately_N_years_old_near_juvenile",
        "grooming_offense_verb_age",
        "hyphenated_range_year_old",
        "victim_age_N",
        "preteen_near_year_old",
        "prepubescent_near_year_old",
        "between_ages_of",
        "between_age_of_N_and_M",
        "ages_N_thru_M",
        "ranging_in_age_from",
        "age_before_year_old",
    }
)


def _age_spans(text: str, age: int) -> List[Tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(rf"(?<!\d){age}(?!\d)", text)]


def _snippet_at(text: str, num_start: int, num_end: int, radius: int = 120) -> str:
    s, e = max(0, num_start - radius), min(len(text), num_end + radius)
    return text[s:e].replace("\n", " ")


def _is_digit_of_larger_number(text: str, num_start: int, num_end: int) -> bool:
    if num_end < len(text) and text[num_end].isdigit():
        return True
    if num_start > 0 and text[num_start - 1].isdigit():
        return True
    if _QUANTITY_AFTER_RE.match(text[num_end : min(len(text), num_end + 12)]):
        return True
    head = text[max(0, num_start - 12) : num_start]
    if _QUANTITY_BEFORE_RE.search(head + text[num_start:num_end]):
        return True
    return False


def _victim_support_signals(
    text: str, num_start: int, num_end: int, age: int
) -> List[str]:
    signals: List[str] = []
    win = text[max(0, num_start - 120) : min(len(text), num_end + 120)]
    local = text[max(0, num_start - 50) : min(len(text), num_end + 60)]
    wide = text[max(0, num_start - 90) : min(len(text), num_end + 90)]

    if re.search(
        rf"(?<!\d){age}\s*[-\s]*(?:year|years|month|months|yr|yrs)\s*[-\s]*olds?\b",
        local,
        re.I,
    ):
        if _VICTIM_WORDS_RE.search(win):
            signals.append("year_old_with_victim_word")
        if re.search(
            r"\b(?:pornography|molest|abus|assault|exploit|traffick|rape|involving)\b",
            wide,
            re.I,
        ):
            signals.append("year_old_with_offense_corpus")

    if re.search(rf"(?<!\d){age}\s*[-\s]*year-olds\b", local, re.I):
        signals.append("plural_N_year_olds")

    if re.search(rf"\bas\s+young\s+as\s+{age}\b", win, re.I):
        signals.append("as_young_as")

    for m in _APPROX_YO_RE.finditer(win):
        if int(m.group("age")) == age and _VICTIM_WORDS_RE.search(
            text[m.start() : min(len(text), m.end() + 80)]
        ):
            signals.append("approximately_N_years_old_near_juvenile")

    gv = _GROOMING_VERB_AGE_RE.pattern.replace("{age}", str(age))
    if re.search(gv, wide, re.I):
        signals.append("grooming_offense_verb_age")

    if re.search(rf"(?:and\s+)?a\s+\d+\s*-\s*and\s+{age}\s*-\s*year\s*old", local, re.I):
        signals.append("hyphenated_range_year_old")

    if re.search(rf"\b(?:age|aged)\s+{age}\b", win, re.I) and _VICTIM_WORDS_RE.search(win):
        signals.append("age_N_with_victim_word")

    if re.search(rf"\bvictim,?\s+age\s+{age}\b", win, re.I):
        signals.append("victim_age_N")

    narrow = text[max(0, num_start - 55) : min(len(text), num_end + 55)]
    if _VICTIM_WORDS_RE.search(narrow):
        if re.search(
            rf"\b(?:minor|child|children|girl|boy|victim|preteen|prepubescent|juvenile|"
            rf"female|male)\b.{{0,45}}(?<!\d){age}\b",
            narrow,
            re.I | re.S,
        ):
            signals.append("victim_word_before_age")
        if re.search(
            rf"(?<!\d){age}\b.{{0,45}}\b(?:year|years|month)?[-\s]*olds?\b",
            narrow,
            re.I | re.S,
        ):
            signals.append("age_before_year_old")

    for m in re.finditer(r"\bages?\s+(\d+)\s+thru\s+(\d+)\b", win, re.I):
        if int(m.group(1)) <= age <= int(m.group(2)):
            signals.append("ages_N_thru_M")
    if re.search(
        rf"\bbetween\s+(?:the\s+)?ages?\s+of\s+(\d+)\s+and\s+{age}\b", win, re.I
    ):
        signals.append("between_ages_of")
    if re.search(rf"\bbetween\s+the\s+age\s+of\s+{age}\s+and\s+\d+", narrow, re.I):
        signals.append("between_age_of_N_and_M")
    if re.search(rf"\bbetween\s+the\s+age\s+of\s+\d+\s+and\s+{age}\b", narrow, re.I):
        signals.append("between_age_of_N_and_M")
    if re.search(rf"\branging\s+in\s+age\s+from\s+{age}\b", win, re.I):
        signals.append("ranging_in_age_from")

    if re.search(r"\bpreteen\b", win, re.I) and re.search(
        rf"(?<!\d){age}\s*[-\s]*year", local, re.I
    ):
        signals.append("preteen_near_year_old")
    if re.search(r"\bprepubescent\b", win, re.I) and re.search(
        rf"(?<!\d){age}\s*[-\s]*year", local, re.I
    ):
        signals.append("prepubescent_near_year_old")

    return list(dict.fromkeys(signals))


def _leakage_reject_signals(
    text: str, num_start: int, num_end: int, age: int
) -> List[str]:
    signals: List[str] = []
    left = text[max(0, num_start - 80) : num_end]
    local = text[max(0, num_start - 12) : num_end + 50]
    win = text[max(0, num_start - 120) : min(len(text), num_end + 120)]

    if re.search(rf"\b{age}\s+years?\s+to\s+life\b", local, re.I):
        signals.append("sentencing_years_to_life")
    elif _is_sentencing_context(text, num_start, num_end):
        signals.append("sentencing_context")
    if _is_digit_of_larger_number(text, num_start, num_end):
        signals.append("digit_of_larger_number")
    if _COMMA_AGE_COUNT_PREFIX_RE.search(left):
        signals.append("count_prefix")
    if _COUNT_OF_AGE_RE.search(local):
        m = _COUNT_OF_AGE_RE.search(local)
        if m and int(m.group(1)) == age:
            signals.append("N_counts")
    chunk = text[max(0, num_start - 12) : num_end + 40]
    if _FILES_IMAGES_RE.search(chunk) and re.search(rf"(?<!\d){age}[,\d]", chunk):
        signals.append("files_images_quantity")
    if _IP_BLOCK_RE.search(win) and re.search(
        rf"(?<!\d){age}[,\d]", text[max(0, num_start - 6) : num_end + 12]
    ):
        signals.append("ip_address_block")

    for m in _STATUTORY_THRESHOLD_RE.finditer(text):
        for g in m.groups():
            if g and int(g) == age and m.start() <= num_start < m.end() + 30:
                signals.append("statutory_threshold")
    for m in _STATUTE_SUBSECTION_RE.finditer(text):
        if m.start(1) <= num_start < m.end(1) and int(m.group(1)) == age:
            signals.append("statute_subsection")
    for m in _PERP_TARGET_RANGE_RE.finditer(text):
        if int(m.group(1)) == age and abs(m.start(1) - num_start) < 30:
            signals.append("perp_target_range")
    for m in _DECOY_HE_WAS_RE.finditer(text):
        if int(m.group(1)) == age and m.start(1) == num_start:
            ctx = text[max(0, m.start() - 100) : m.end() + 80]
            if _DECOY_CTX_RE.search(ctx) or re.search(r'"[A-Z][a-z]+"', ctx):
                signals.append("decoy_he_was_N")

    signals.extend(_defendant_routed_signals(text, num_start, num_end, age))

    if not _YO_HYPHEN_RE.search(
        text[max(0, num_start - 35) : min(len(text), num_end + 35)]
    ) and not re.search(
        r"age\s+\d|aged\s+\d|thru|between\s+the\s+ages|ranging|approximately",
        text[max(0, num_start - 35) : min(len(text), num_end + 35)],
        re.I,
    ):
        if not _VICTIM_WORDS_RE.search(win):
            signals.append("bare_digit_no_age_phrase")

    return list(dict.fromkeys(signals))


def _defendant_routed_signals(
    text: str, num_start: int, num_end: int, age: int
) -> List[str]:
    out: List[str] = []
    for m in _YO_PERP_RE.finditer(text):
        if m.start(1) == num_start and m.end(1) == num_end:
            out.append("year_old_man_woman")
    for m in _CAP_NAME_BEFORE_COMMA.finditer(text):
        if m.start(2) != num_start or m.end(2) != num_end:
            continue
        if not (10 <= age <= 99):
            continue
        after = text[m.end() : min(len(text), m.end() + 320)]
        before = text[max(0, m.start() - 100) : m.start()]
        if _DEFENDANT_AFTER_COMMA_RE.search(after):
            out.append("defendant_comma_was_arrested")
        elif _DEFENDANT_CHARGE_RE.search(after[:160]):
            out.append("defendant_comma_charge_context")
        elif re.search(r"\bteen\b", before, re.I):
            out.append("defendant_comma_headline_teen")
    for pat in _PERP_COMMA_VERB_PATTERNS:
        for m in pat.finditer(text):
            if m.start(1) == num_start and m.end(1) == num_end and age >= 10:
                out.append("perp_comma_verb_pattern")
    return out


def _borderline_support_only(support: List[str]) -> bool:
    weak = {
        "approximately_N_years_old_near_juvenile",
        "victim_word_before_age",
        "year_old_with_offense_corpus",
    }
    return bool(support) and all(s in weak for s in support)


def evaluate_age_slot_v2(text: str, age: int) -> Dict[str, Any]:
    """Returns decision: keep | reject | review."""
    spans = _age_spans(text, age)
    if not spans:
        return {
            "decision": "reject",
            "reason": "no_span_in_text",
            "support": [],
            "reject": ["no_span_in_text"],
            "spans": [],
        }

    span_details: List[Dict[str, Any]] = []
    any_strong_keep = False
    any_hard_reject = False
    any_soft_conflict = False

    for ns, ne in spans:
        sup = _victim_support_signals(text, ns, ne, age)
        rej = _leakage_reject_signals(text, ns, ne, age)
        hard = [r for r in rej if r in _HARD_REJECT]
        soft = [r for r in rej if r not in _HARD_REJECT]
        strong_sup = [s for s in sup if s in _STRONG_SUPPORT]
        span_details.append(
            {
                "start": ns,
                "support": sup,
                "reject": rej,
                "snippet": _snippet_at(text, ns, ne),
            }
        )
        if hard:
            any_hard_reject = True
        if strong_sup and not hard:
            any_strong_keep = True
        if sup and soft and not strong_sup:
            any_soft_conflict = True
        elif sup and soft and strong_sup:
            any_soft_conflict = True

    all_sup = [s for d in span_details for s in d["support"]]
    all_rej = [r for d in span_details for r in d["reject"]]

    if any_strong_keep and any_hard_reject:
        return {
            "decision": "review",
            "reason": "victim_anchor_and_leakage_on_different_spans",
            "support": all_sup,
            "reject": all_rej,
            "spans": span_details,
        }

    if any_strong_keep:
        return {
            "decision": "keep",
            "reason": "clear_victim_anchor",
            "support": all_sup,
            "reject": [r for d in span_details for r in d["reject"] if r not in _HARD_REJECT],
            "spans": span_details,
        }

    if any_hard_reject and not any_strong_keep:
        hard_reasons = [r for d in span_details for r in d["reject"] if r in _HARD_REJECT]
        return {
            "decision": "reject",
            "reason": hard_reasons[0],
            "support": all_sup,
            "reject": all_rej,
            "spans": span_details,
        }

    if any_soft_conflict or (all_sup and all_rej):
        return {
            "decision": "review",
            "reason": "support_and_reject_both_fire",
            "support": all_sup,
            "reject": all_rej,
            "spans": span_details,
        }

    if all_sup and not all_rej and _borderline_support_only(all_sup):
        return {
            "decision": "review",
            "reason": "borderline_weak_support_only",
            "support": all_sup,
            "reject": all_rej,
            "spans": span_details,
        }

    primary = all_rej[0] if all_rej else "no_victim_context_anchor"
    return {
        "decision": "reject",
        "reason": primary,
        "support": all_sup,
        "reject": all_rej,
        "spans": span_details,
    }


def apply_victim_age_gate(
    case_id: str,
    case_text: str,
    candidate_ages: Iterable[int],
    overrides: Optional[Dict[Tuple[str, int], str]] = None,
) -> Tuple[List[int], Dict[str, Any]]:
    """
    Filter victim age slots through gate v2 + optional human overrides.

    Overrides map (case_id, age) -> "keep" | "drop". Override drop beats keep.
    Without override: keep→pass, reject/review→drop.
    """
    if overrides is None:
        from victim_age_overrides import load_victim_age_overrides

        overrides = load_victim_age_overrides()

    text = (case_text or "").strip()
    kept: List[int] = []
    log: Dict[str, Any] = {"kept": [], "dropped": [], "review_excluded": []}

    for age in sorted(set(int(a) for a in candidate_ages if 1 <= int(a) <= 17)):
        key = (case_id or "", age)
        ovr = overrides.get(key)

        if ovr == "drop":
            log["dropped"].append({"age": age, "decision": "override_drop"})
            continue
        if ovr == "keep":
            kept.append(age)
            log["kept"].append({"age": age, "decision": "override_keep"})
            continue

        if not text:
            log["dropped"].append({"age": age, "decision": "reject", "reason": "no_case_text"})
            continue

        ev = evaluate_age_slot_v2(text, age)
        decision = ev["decision"]
        entry = {"age": age, "decision": decision, "reason": ev.get("reason")}

        if decision == "keep":
            kept.append(age)
            log["kept"].append(entry)
        elif decision == "review":
            log["review_excluded"].append(entry)
        else:
            log["dropped"].append(entry)

    kept.sort()
    return kept, log
