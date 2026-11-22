"""Event frames: one pass from a sentence to actor, act, means, object and time.

Selected with ``CASELINKER_EXTRACTOR=frame-1.0``. Unset, ``extract_frames``
returns nothing, so the current act path and the current means path stay as
they are.

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

import os
import re
import unicodedata
from typing import List, Optional, Tuple

from state_machines.coding.cues import CUES
from state_machines.evidence import evidence as E
from state_machines.evidence import vocab as V
from state_machines.observations import observe as O

EXTRACTOR_ID = "frame-1.0"
_ACTOR = re.compile(r"\bthe defendant\b|\bthe accused\b", re.I)
_VICTIM = re.compile(r"\b(?:Minor Victim|Victim|MV|Minor|Child Victim|CV)[\s-]?\d+\b|\bthe (?:minor|child|victim)\b", re.I)


def extractor_enabled() -> bool:
    return os.environ.get("CASELINKER_EXTRACTOR") == EXTRACTOR_ID


def _slot(text: str, start: int, end: int, **extra) -> dict:
    return {"text": text[start:end], "start": start, "end": end, **extra}


def _means_slot(sentence: str, sentence_start: int) -> Optional[dict]:
    """The means the current rule ties inside this sentence, or None when it ties none.

    A feature tie is level C. A platform tie is a stated platform means and is
    not level C. The platform name is not copied into an affordance field.
    """
    feature_hit = None
    for cls, phrase, a, b in O.features_in(sentence):
        hit = O._means("feature", sentence, {"feature_term": phrase})
        if hit:
            feature_hit = _slot(sentence, a, b, kind="feature", feature_class=cls, relationship=hit[0],
                                cue=hit[1], level="C")
            break
    if feature_hit:
        feature_hit["start"] += sentence_start
        feature_hit["end"] += sentence_start
        return feature_hit
    for name, a, b in O.platforms_in(sentence):
        hit = O._means("platform", sentence, {"named_as": name})
        if hit:
            slot = _slot(sentence, a, b, kind="platform", relationship=hit[0], cue=hit[1], level="stated-platform")
            slot["start"] += sentence_start
            slot["end"] += sentence_start
            return slot
    return None


def _object_slot(sentence: str, sentence_start: int) -> Optional[dict]:
    m = _VICTIM.search(sentence)
    if not m:
        return None
    slot = _slot(sentence, m.start(), m.end(), kind="victim")
    slot["start"] += sentence_start
    slot["end"] += sentence_start
    return slot


def _time_slot(sentence: str, sentence_start: int) -> Optional[dict]:
    from state_machines.coding.enrich import find_date

    found = find_date(sentence)
    if not found:
        return None
    at = sentence.find(found["x"])
    if at < 0:
        return None
    slot = _slot(sentence, at, at + len(found["x"]), earliest=found["from"], latest=found["to"], precision=found["p"])
    slot["start"] += sentence_start
    slot["end"] += sentence_start
    return slot


def _actor_slot(sentence: str, sentence_start: int) -> Optional[dict]:
    m = _ACTOR.search(sentence)
    if not m:
        return None
    slot = _slot(sentence, m.start(), m.end(), id="defendant")
    slot["start"] += sentence_start
    slot["end"] += sentence_start
    return slot


def extract_frames(sentence: str, *, page_text: str, sentence_start: int, passage_hash: Optional[str] = None) -> List[dict]:
    """Zero or more frames for ``sentence``, which begins at ``sentence_start`` on ``page_text``.

    Returns nothing unless the frame extractor is selected. One frame per cued
    action code. A sentence the cue table does not read yields no frame.
    """
    if not extractor_enabled():
        return []
    if passage_hash is None:
        passage_hash = E.sha256_text(page_text)
    end = sentence_start + len(sentence)
    if page_text[sentence_start:end] != sentence:
        return []
    codes = sorted(c for c in CUES if V.FAMILY_OF.get(c) == "offender" and CUES[c].search(sentence))
    if not codes:
        return []
    shared_means = _means_slot(sentence, sentence_start)
    shared = {
        "extractor": EXTRACTOR_ID,
        "passage_hash": passage_hash,
        "sentence": {"text": sentence, "start": sentence_start, "end": end},
        "actor": _actor_slot(sentence, sentence_start),
        "means": shared_means,
        "object": _object_slot(sentence, sentence_start),
        "time": _time_slot(sentence, sentence_start),
        "level_c": bool(shared_means and shared_means.get("level") == "C"),
    }
    frames = []
    for code in codes:
        m = CUES[code].search(sentence)
        act = _slot(sentence, m.start(), m.end(), code=code)
        act["start"] += sentence_start
        act["end"] += sentence_start
        frames.append({**shared, "act": act, "frame_id": f"{sentence_start}:{code}"})
    return frames


def verify_frame(frame: dict, page_text: str) -> List[str]:
    """Problems with a frame. Empty means every filled slot is verbatim on the page.

    A paraphrased slot, an offset that has slipped, and a hash that is not the
    hash of ``page_text`` are all reported. An empty slot is not a problem.
    A code with no span (the act code the model named) is not a span.
    """
    if E.sha256_text(page_text) != frame.get("passage_hash"):
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


def _normalize_map(text: str) -> Tuple[str, List[Tuple[int, int]]]:
    """Normalized text and, for each output character, the original ``[start, end)`` it covers.

    Both the span and the page go through this before a match: NFKC, curly quotes
    and apostrophes to straight, soft hyphens removed, a hyphen at a line break
    joined (``distrib-\\nution`` becomes ``distribution``), and whitespace collapsed.
    """
    pieces: List[Tuple[str, int, int]] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "\u00ad":
            i += 1
            continue
        if ch == "-" and i > 0 and text[i - 1].isalnum():
            j = i + 1
            if j < n and text[j] == "\r":
                j += 1
            if j < n and text[j] == "\n":
                k = j + 1
                while k < n and text[k] in " \t":
                    k += 1
                if k < n and text[k].isalnum():
                    i = k
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


def locate_span(page: str, needle: str) -> List[Tuple[int, int]]:
    """Original-page offsets of ``needle`` after the shared normalization. Empty if it is not there."""
    page_n, spans = _normalize_map(page)
    needle_n, _needle_spans = _normalize_map(needle)
    if not needle_n:
        return []
    hits = []
    start = 0
    while True:
        i = page_n.find(needle_n, start)
        if i < 0:
            break
        a = spans[i][0]
        b = spans[i + len(needle_n) - 1][1]
        if (a == 0 or not page[a - 1].isalnum()) and (b >= len(page) or not page[b].isalnum()) and not (
                b < len(page) and page[b] in "'\u2019"):
            hits.append((a, b))
        start = i + max(1, len(needle_n))
    return hits


def choose_occurrence(hits: List[Tuple[int, int]], hint: Optional[int]) -> Tuple[Optional[Tuple[int, int]], bool]:
    """The occurrence nearest ``hint``. A tie, or no hint when there are several, is ambiguous.

    The earliest of a tie is kept, and the ambiguity is reported. It is not a silent first hit.
    """
    if not hits:
        return None, False
    if len(hits) == 1:
        return hits[0], False
    if hint is None:
        return hits[0], True
    best = min(abs(start - hint) for start, _end in hits)
    nearest = [hit for hit in hits if abs(hit[0] - hint) == best]
    nearest.sort(key=lambda hit: hit[0])
    return nearest[0], len(nearest) > 1


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


def ground_frame(page: str, frame: dict) -> Tuple[Optional[dict], str, int]:
    """Place a model's plain-text frame on ``page``.

    Returns ``(frame, "", ambiguous)`` or ``(None, reason, ambiguous)``. ``reason``
    is ``not_found`` when a span is not on the page, and ``other`` when the frame
    has no quote or code. The hash and the offsets are computed here. A number the
    model included is only a hint for which copy of a repeated span to keep.
    """
    quote = _plain(frame, "quote") or _plain(frame, "sentence")
    code = frame.get("act") if isinstance(frame.get("act"), str) else (frame.get("act") or {}).get("code")
    actor = _plain(frame, "actor")
    means = _plain(frame, "means")
    obj = _plain(frame, "object")
    level = _plain(frame, "means_level").upper()
    if not quote or not code:
        return None, "other", 0
    hint = frame.get("start") if isinstance(frame.get("start"), int) else None
    ambiguous = 0
    hits = locate_span(page, quote)
    chosen, amb = choose_occurrence(hits, hint)
    ambiguous += int(amb)
    if chosen is None:
        return None, "not_found", ambiguous
    sent_start, sent_end = _sentence_bounds(page, *chosen)
    sentence = page[sent_start:sent_end]

    def _inside(needle: str) -> Optional[Tuple[int, int]]:
        nonlocal ambiguous
        if not needle:
            return None
        inner = [(a, b) for a, b in locate_span(page, needle) if sent_start <= a and b <= sent_end]
        pick, was_amb = choose_occurrence(inner, hint)
        ambiguous += int(was_amb)
        return pick

    actor_at = _inside(actor) if actor else None
    if actor and actor_at is None:
        return None, "not_found", ambiguous
    means_at = _inside(means) if means else None
    if means and means_at is None:
        return None, "not_found", ambiguous
    object_at = _inside(obj) if obj else None
    if obj and object_at is None:
        return None, "not_found", ambiguous
    grounded = {
        "passage_hash": E.sha256_text(page),
        "sentence": {"text": sentence, "start": sent_start, "end": sent_end},
        "act": {"code": code},
        "means_level": level,
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
        return None, "other", ambiguous
    return grounded, "", ambiguous
