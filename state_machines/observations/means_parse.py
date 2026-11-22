"""Dependency-parse instrument detector.

Off unless ``CASELINKER_MEANS_PARSER=dep``. The word window in ``observe._means``
stays the default. A caller passes tokens ``{text, start, end, head, deprel}``
with ``head`` an index into the same list. ``pos`` may be ``VERB``.

The walk follows ``appos`` and ``parataxis``, so a term inside parentheses is
still the instrument of the verb outside them. When ``CASELINKER_COREFERENCE=1``
and the verb's subject is ``they``, the resolved actor decides. With
coreference off, ``they`` is not an offender subject.

``tokens_from_spacy`` uses ``en_core_web_sm`` only when that model is already
installed. This module does not download one and does not add a dependency.
Nothing here reads ``state_machines/data``, ``local``, or ``caselinker_oxigraph``.
"""
from __future__ import annotations

import os
import re
from typing import List, Optional, Sequence

_PREPS = {"through", "via", "using", "with", "on", "over", "by"}
_USE = {"utilize", "utilized", "utilizing", "use", "used", "uses", "using",
        "conceal", "concealed", "concealing", "send", "sent", "sending"}
_OFFENDER_WORD = re.compile(r"^(?:defendants?|accused|he)$", re.I)
_THEY = re.compile(r"^(?:they|them|their)$", re.I)
_BLOCKED = ("state_machines/data", "caselinker_oxigraph")


def parser_enabled() -> bool:
    return os.environ.get("CASELINKER_MEANS_PARSER") == "dep"


def refuse_corpus_path(path: str) -> None:
    """A comparison stays on the sentence the caller already holds."""
    text = str(path).replace("\\", "/")
    parts = text.strip("/").split("/")
    if any(piece in text for piece in _BLOCKED) or "local" in parts:
        raise SystemExit(f"refusing a corpus path: {path}")


def tokens_from_spacy(sentence: str) -> Optional[List[dict]]:
    """Token dicts from an already-installed ``en_core_web_sm``. None when it is absent."""
    try:
        import spacy
        nlp = spacy.load("en_core_web_sm")
    except Exception:
        return None
    doc = nlp(sentence)
    return [{"text": t.text, "start": t.idx, "end": t.idx + len(t.text),
             "head": t.head.i, "deprel": t.dep_, "pos": t.pos_} for t in doc]


def _is_verb(tok: dict) -> bool:
    return tok.get("pos") == "VERB" or tok.get("deprel") in ("ROOT", "root")


def _covering(tokens: Sequence[dict], start: int, end: int) -> List[int]:
    return [i for i, t in enumerate(tokens) if t["start"] < end and start < t["end"]]


def _verb_and_cue(tokens: Sequence[dict], start_i: int):
    """(verb index, cue, crossed a parenthesis) for an instrument span, or None."""
    seen = set()
    cur = start_i
    crossed = False
    while cur not in seen and 0 <= cur < len(tokens):
        seen.add(cur)
        tok = tokens[cur]
        rel = tok.get("deprel") or ""
        head_i = tok.get("head", cur)
        if not isinstance(head_i, int) or not (0 <= head_i < len(tokens)):
            return None
        head = tokens[head_i]
        if rel in ("appos", "parataxis"):
            crossed = True
            if head_i == cur:
                return None
            cur = head_i
            continue
        if rel in ("pobj", "pcomp", "obj", "dobj") and head["text"].lower() in _PREPS:
            verb_i = head.get("head")
            if isinstance(verb_i, int) and 0 <= verb_i < len(tokens) and _is_verb(tokens[verb_i]):
                return verb_i, head["text"].lower(), crossed
        if rel in ("obl", "obl:instrument", "npadvmod") and _is_verb(head):
            return head_i, head["text"].lower(), crossed
        if rel in ("dobj", "obj") and _is_verb(head) and head["text"].lower() in _USE:
            return head_i, head["text"].lower(), crossed
        if rel in ("amod", "compound", "flat", "nmod", "nummod") and head_i != cur:
            cur = head_i
            continue
        return None
    return None


def _subject(tokens: Sequence[dict], verb_i: int):
    for i, tok in enumerate(tokens):
        if tok.get("head") == verb_i and tok.get("deprel") in ("nsubj", "nsubjpass"):
            return i, tok
    return None, None


def _subject_is_offender(sentence: str, tokens: Sequence[dict], verb_i: int, actors) -> bool:
    _, subj = _subject(tokens, verb_i)
    if subj is None:
        return False
    if _OFFENDER_WORD.match(subj["text"]):
        return True
    if not _THEY.match(subj["text"]):
        return False
    if os.environ.get("CASELINKER_COREFERENCE") != "1" or not actors:
        return False
    from state_machines.coding.coreference import resolve_mentions, subject_is_offender
    mentions = resolve_mentions(sentence, actors)
    return subject_is_offender(mentions, subj["end"], actors)


def _negated(tokens: Sequence[dict], verb_i: int) -> bool:
    return any(t.get("head") == verb_i and t.get("deprel") == "neg" for t in tokens)


def instrument_means(sentence: str, observation: dict, tokens: Sequence[dict], actors=None) -> Optional[dict]:
    """The instrument of the act, or None.

    Returns None unless ``CASELINKER_MEANS_PARSER=dep``. The dict has
    ``relationship``, ``cue``, ``method`` (``dep``) and ``crossed_parentheses``.
    """
    if not parser_enabled():
        return None
    from state_machines.observations.observe import _GENERIC_DESCRIPTION, _OFFENDER
    if _GENERIC_DESCRIPTION.search(sentence) and not _OFFENDER.search(sentence):
        return None
    term = observation.get("feature_term") or ""
    start = sentence.find(term) if term else -1
    if start < 0:
        return None
    end = start + len(term)
    for i in _covering(tokens, start, end):
        found = _verb_and_cue(tokens, i)
        if not found:
            continue
        verb_i, cue, crossed = found
        if _negated(tokens, verb_i):
            continue
        if not _subject_is_offender(sentence, tokens, verb_i, actors):
            continue
        return {"relationship": "Supports_Action", "cue": cue, "method": "dep",
                "crossed_parentheses": crossed}
    return None


def compare(sentence: str, observation: dict, tokens: Sequence[dict] = (), actors=None) -> dict:
    """The word-window hit and the dependency hit, side by side. Neither is stored."""
    from state_machines.observations.observe import _means
    return {"window": _means("feature", sentence, observation),
            "dep": instrument_means(sentence, observation, tokens, actors=actors)}
