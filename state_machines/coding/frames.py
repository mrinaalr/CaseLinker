"""Event frames: one pass from a sentence to actor, act, means, object and time.

Selected with ``CASELINKER_EXTRACTOR=frame-1.0``. With the flag unset, coding
does not call this module, so the current act path and the current means path
stay as they are.

Each filled slot carries the exact characters it cites and the page-text hash.
``verify_frame`` rejects a frame whose hash is stale or whose slot text is not
those characters. The means slot is the instrument of the act. PropBank's ArgM-MNR is manner,
not that instrument (Palmer, Gildea and Kingsbury 2005). The element that names
it is FrameNet's Instrument (Baker, Fillmore and Lowe 1998). A means is level C
only when it is a codebook feature the stated-means rule ties inside the act's
own sentence. A platform name is a stated platform means, never an affordance
and never ``documented_feature_use`` (codebook rule B0).
"""
from __future__ import annotations

import re
import unicodedata
from typing import List, Optional, Tuple

from state_machines.evidence import evidence as E

EXTRACTOR_ID = "frame-1.0"


def verify_frame(frame: dict, page_text: str) -> List[str]:
    """Problems with a frame. Empty means every filled slot is verbatim on the page.

    A paraphrased slot, an offset that has slipped, and a hash that is not the
    hash of ``page_text`` are all reported. An empty slot is not a problem.
    A code with no span (the act code the model named) is not a span.
    """
    if E.sha256_text(E.normalize(page_text)) != frame.get("passage_hash"):
        return ["passage hash does not match the page"]
    problems = []
    for name in ("sentence", "actor", "act", "means", "object", "time"):
        slot = frame.get(name)
        if not slot or not slot.get("text"):
            continue
        start, end = slot.get("start"), slot.get("end")
        text = slot.get("text")
        if not isinstance(start, int) or not isinstance(end, int) or not (0 <= start <= end <= len(page_text)):
            problems.append(f"{name} span does not match the page text")
            continue
        if page_text[start:end] != text:
            problems.append(f"{name} span does not match the page text")
    means = frame.get("means")
    sentence = frame.get("sentence") or {}
    if frame.get("level_c"):
        if not means or means.get("level") != "C":
            problems.append("level C is set without a feature means in the act sentence")
        elif not (sentence.get("start", 0) <= means["start"] and means["end"] <= sentence.get("end", -1)):
            problems.append("level C means is outside the act sentence")
    if means and means.get("kind") == "platform" and means.get("level") == "C":
        problems.append("a platform name is not a level-C affordance")
    return problems


_QUOTES = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u00a0": " "})
_SENTENCE_END = re.compile(r"[.;!?](?=\s|$)")


def _break_hyphen(text: str, i: int) -> Optional[int]:
    """Index after a line-break hyphen at ``i``, or None when this hyphen is not one."""
    if text[i] != "-" or i == 0 or not text[i - 1].isalnum():
        return None
    j = i + 1
    if j < len(text) and text[j] == "\r":
        j += 1
    if j >= len(text) or text[j] != "\n":
        return None
    k = j + 1
    while k < len(text) and text[k] in " \t":
        k += 1
    if k < len(text) and text[k].isalnum():
        return k
    return None


# Separate from evidence.normalize: that function keeps a line-break hyphen and turns the break into a space, which flags-off hashes and quote offsets use. This map is only for frame spans.
def _normalize_map(text: str, *, join_break_hyphen: bool) -> Tuple[str, List[Tuple[int, int]]]:
    """Normalized text and, for each output character, the original ``[start, end)`` it covers.

    Both the span and the page go through this before a match: NFKC, curly quotes
    and apostrophes to straight, soft hyphens removed, whitespace collapsed.
    A hyphen at a line break is either dropped (``distrib-\\nution`` becomes
    ``distribution``) or kept and the break dropped (``end-to-\\nend`` stays
    ``end-to-end``). Callers search both.
    """
    pieces: List[Tuple[str, int, int]] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "\u00ad":
            i += 1
            continue
        nxt = _break_hyphen(text, i)
        if nxt is not None:
            if join_break_hyphen:
                i = nxt
                continue
            pieces.append(("-", i, i + 1))
            i = nxt
            continue
        j = i + 1
        while j < n and unicodedata.combining(text[j]):
            j += 1
        chunk = unicodedata.normalize("NFKC", text[i:j]).translate(_QUOTES).replace("\u00ad", "")
        for c in chunk:
            pieces.append((c, i, j))
        i = j
    out: List[str] = []
    spans: List[Tuple[int, int]] = []
    for c, a, b in pieces:
        if c.isspace():
            if out and out[-1] == " ":
                spans[-1] = (spans[-1][0], b)
                continue
            out.append(" ")
            spans.append((a, b))
        else:
            out.append(c)
            spans.append((a, b))
    while out and out[0] == " ":
        out.pop(0)
        spans.pop(0)
    while out and out[-1] == " ":
        out.pop()
        spans.pop()
    return "".join(out), spans


def _locate_one(page: str, needle: str, *, join_break_hyphen: bool, ignore_case: bool = False) -> List[Tuple[int, int]]:
    page_n, spans = _normalize_map(page, join_break_hyphen=join_break_hyphen)
    needle_n, _needle_spans = _normalize_map(needle, join_break_hyphen=join_break_hyphen)
    if not needle_n:
        return []
    hits = []
    start = 0
    while True:
        if ignore_case:
            found = re.search(re.escape(needle_n), page_n[start:], re.I)
            i = start + found.start() if found else -1
        else:
            i = page_n.find(needle_n, start)
        if i < 0:
            break
        a = spans[i][0]
        b = spans[i + len(needle_n) - 1][1]
        if (a == 0 or not page[a - 1].isalnum()) and (b >= len(page) or not page[b].isalnum()):
            hits.append((a, b))
        start = i + max(1, len(needle_n))
    return hits


def locate_span(page: str, needle: str, *, ignore_case: bool = False) -> List[Tuple[int, int]]:
    """Original-page offsets of ``needle``. A line-break hyphen matches either joined or kept.

    A match followed by an apostrophe is still a match. The actor check, not this
    search, decides whether a possessive phrase is the defendant. ``ignore_case``
    is for an actor phrase such as ``the defendant``.
    """
    found = []
    seen = set()
    for join in (True, False):
        for hit in _locate_one(page, needle, join_break_hyphen=join, ignore_case=ignore_case):
            if hit not in seen:
                seen.add(hit)
                found.append(hit)
    found.sort()
    return found


def _sentence_bounds(page: str, start: int, end: int) -> Tuple[int, int]:
    begin = 0
    for m in _SENTENCE_END.finditer(page[:start]):
        begin = m.end()
    while begin < len(page) and page[begin].isspace():
        begin += 1
    if begin > start:
        begin = start
    finish = len(page)
    for m in _SENTENCE_END.finditer(page[start:]):
        finish = start + m.end()
        if finish >= end:
            break
    return begin, max(finish, end)


def _plain(frame: dict, key: str) -> str:
    value = frame.get(key)
    if isinstance(value, str):
        return value.strip()
    return ""


def _inside(page: str, needle: str, sent_start: int, sent_end: int, *, ignore_case: bool = False) -> Optional[Tuple[int, int]]:
    if not needle:
        return None
    inner = [span for span in locate_span(page, needle, ignore_case=ignore_case)
             if sent_start <= span[0] and span[1] <= sent_end]
    return inner[0] if inner else None


def _occurrence_actor(page: str, sentence: str, sent_start: int, sent_end: int, actor: str, records: List[dict]):
    """Who this copy of the quote is about: the model's actor if it sits here, else the clause subject."""
    from state_machines.coding.workflow import clause_subject, match_actor
    def _label(found, fallback):
        if not found:
            return fallback
        if found.get("ambiguous"):
            return "ambiguous"
        return found.get("canonical") or fallback

    if actor and _inside(page, actor, sent_start, sent_end, ignore_case=True):
        return _label(match_actor(actor, records), actor)
    return _label(match_actor(clause_subject(sentence), records), clause_subject(sentence))


def ground_frame(page: str, frame: dict, records: Optional[List[dict]] = None) -> Tuple[Optional[dict], str, List[str]]:
    """Place a model's plain-text frame on ``page``.

    Returns ``(frame, "", [])`` or ``(None, reason, problems)``. The hash and the
    offsets are computed here. When the quote occurs more than once, each copy's
    section verdict and resolved actor are compared. Copies that disagree are
    ``ambiguous`` and the frame is dropped. Copies that agree keep the earliest.
    """
    from state_machines.coding.sections import blocks_offender_products, classify
    quote = _plain(frame, "quote") or _plain(frame, "sentence")
    code = frame.get("act") if isinstance(frame.get("act"), str) else ""
    actor = _plain(frame, "actor")
    means = _plain(frame, "means")
    obj = _plain(frame, "object")
    level = _plain(frame, "means_level").upper()
    records = records or []
    if not quote or not code:
        return None, "not_found", []
    hits = locate_span(page, quote)
    if not hits:
        return None, "not_found", []
    views = []
    for hit in hits:
        sent_start, sent_end = _sentence_bounds(page, *hit)
        sentence = page[sent_start:sent_end]
        blocked = blocks_offender_products(classify(sentence)["role"])
        label = _occurrence_actor(page, sentence, sent_start, sent_end, actor, records)
        views.append((blocked, label, sent_start, sent_end, sentence))
    labels = {(blocked, label) for blocked, label, *_rest in views}
    if len(views) > 1 and len(labels) > 1:
        return None, "ambiguous", []
    if any(label == "ambiguous" for _blocked, label, *_rest in views):
        return None, "ambiguous", []
    blocked, _label, sent_start, sent_end, sentence = views[0]
    if blocked:
        return None, "section_filtered", []
    keep_earliest = len(views) > 1
    actor_at = _inside(page, actor, sent_start, sent_end, ignore_case=True) if actor else None
    if actor and actor_at is None:
        return None, "not_found", []
    means_at = _inside(page, means, sent_start, sent_end) if means else None
    if means and means_at is None:
        return None, "not_found", []
    object_at = _inside(page, obj, sent_start, sent_end) if obj else None
    if obj and object_at is None:
        return None, "not_found", []
    grounded = {
        "passage_hash": E.sha256_text(E.normalize(page)),
        "sentence": {"text": sentence, "start": sent_start, "end": sent_end},
        "act": {"code": code},
        "means_level": level,
        "keep_earliest": keep_earliest,
    }
    if actor_at:
        a, b = actor_at
        grounded["actor"] = {"text": page[a:b], "start": a, "end": b}
    if object_at:
        a, b = object_at
        grounded["object"] = {"text": page[a:b], "start": a, "end": b}
    if means_at:
        a, b = means_at
        slot = {"text": page[a:b], "start": a, "end": b}
        if level == "C":
            slot["level"] = "C"
            slot["kind"] = "feature"
            grounded["level_c"] = True
        grounded["means"] = slot
    problems = verify_frame(grounded, page)
    if problems:
        return None, "verify_failed", problems
    return grounded, "", []
