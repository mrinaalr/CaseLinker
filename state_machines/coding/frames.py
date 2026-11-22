"""Event frames: one pass from a sentence to actor, act, means, object and time.

Selected with ``CASELINKER_EXTRACTOR=frame-1.0``. Unset, ``extract_frames``
returns nothing, so the current act path and the current means path stay as
they are.

Each filled slot carries the exact characters it cites and the page-text hash.
``verify_frame`` rejects a frame whose hash is stale or whose slot text is not
those characters. A means is level C only when it is a codebook feature the
stated-means rule ties inside the act's own sentence. A platform name is a
stated platform means, never an affordance and never ``documented_feature_use``
(codebook rule B0).
"""
from __future__ import annotations

import os
import re
from typing import List, Optional

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
    """
    if E.sha256_text(page_text) != frame.get("passage_hash"):
        return ["passage hash does not match the page"]
    problems = []
    for name in ("sentence", "actor", "act", "means", "object", "time"):
        slot = frame.get(name)
        if not slot:
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
