"""Dependency-parse instrument detector.

Off unless ``CASELINKER_MEANS_PARSER=dep``. The word window in ``observe._means``
stays the default. A caller passes tokens ``{text, start, end, head, deprel}``
with ``head`` an index into the same list. ``pos`` may be ``VERB``.

The walk follows ``appos`` and ``parataxis``, so a term inside parentheses is
still the instrument of the verb outside them. A bare ``he`` is not an offender
word. When ``CASELINKER_COREFERENCE=1`` and the verb's subject is a pronoun
(``he``, ``him``, ``they``, ``them``, ``their``), the resolved actor decides.
With coreference off, a pronoun is not an offender subject.

``tokens_from_spacy`` loads ``en_core_web_sm`` (or ``CASELINKER_MEANS_SPACY_MODEL``) once
and keeps it. If that model cannot load, the call raises. It does not return an
empty token list. ``CASELINKER_MEANS_PARSER_FALLBACK=1`` is the only way to use
the small parenthetical tokenizer instead, and a relation from that path says
``parser: fallback``. This module does not download a model.
Nothing here reads ``state_machines/data``, ``local``, or ``caselinker_oxigraph``.
"""
from __future__ import annotations

import os
import re
from typing import List, Optional, Sequence

_PREPS = {"through", "via", "using", "with", "on", "over", "by"}
_USE = {"utilize", "utilized", "utilizing", "use", "used", "uses", "using",
        "conceal", "concealed", "concealing", "send", "sent", "sending"}
_OFFENDER_WORD = re.compile(r"^(?:defendants?|accused)$", re.I)
from state_machines.coding.workflow import _PRONOUN as _THEY
_BLOCKED = ("state_machines/data", "caselinker_oxigraph")


_NLP = None
_LOADS = 0


def parser_enabled() -> bool:
    return os.environ.get("CASELINKER_MEANS_PARSER") == "dep"


def model_name() -> str:
    return os.environ.get("CASELINKER_MEANS_SPACY_MODEL", "en_core_web_sm")


def fallback_enabled() -> bool:
    return os.environ.get("CASELINKER_MEANS_PARSER_FALLBACK") == "1"


def load_spacy_model(name: str):
    """The installed spaCy model. Tests replace this to simulate a missing model."""
    import spacy
    return spacy.load(name)


def require_spacy_model():
    """The dependency model, loaded once. Raises SystemExit when it cannot load."""
    global _NLP, _LOADS
    if _NLP is not None:
        return _NLP
    name = model_name()
    try:
        _NLP = load_spacy_model(name)
    except Exception as exc:
        raise SystemExit(
            f"CASELINKER_MEANS_PARSER=dep requires the spaCy model {name}, which did not load "
            f"({type(exc).__name__}: {exc}). Install it with: python -m spacy download {name}"
        ) from exc
    _LOADS += 1
    return _NLP


def parser_provenance() -> dict:
    """Who produced a parser relation. The fallback never reports ``dep``."""
    if fallback_enabled():
        return {"parser": "fallback", "model": None, "model_version": None}
    nlp = require_spacy_model()
    meta = getattr(nlp, "meta", {}) or {}
    return {"parser": "dep", "model": model_name(), "model_version": meta.get("version")}


def manifest_parser() -> dict:
    """The release-manifest record. Null when the dependency parser is not selected."""
    if not parser_enabled():
        return {"parser": None, "model": None, "model_version": None}
    return parser_provenance()


def refuse_corpus_path(path: str) -> None:
    """A comparison stays on the sentence the caller already holds."""
    text = str(path).replace("\\", "/")
    parts = text.strip("/").split("/")
    if any(piece in text for piece in _BLOCKED) or "local" in parts:
        raise SystemExit(f"refusing a corpus path: {path}")


def tokens_from_spacy(sentence: str) -> List[dict]:
    """Token dicts from the cached model. Raises when the model cannot load or returns nothing."""
    nlp = require_spacy_model()
    doc = nlp(sentence)
    tokens = [{"text": t.text, "start": t.idx, "end": t.idx + len(t.text),
               "head": t.head.i, "deprel": t.dep_, "pos": t.pos_} for t in doc]
    if sentence.strip() and not tokens:
        raise SystemExit(f"spaCy model {model_name()} returned no tokens for a non-empty sentence")
    return tokens


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


def _subject_is_offender(sentence: str, tokens: Sequence[dict], verb_i: int, actors,
                         records=None, generic=None, scope=None) -> bool:
    _, subj = _subject(tokens, verb_i)
    if subj is None:
        return False
    from state_machines.coding.workflow import decide_actor, v2_active
    if v2_active():
        # A pronoun is not resolved. The actor decision is decide_actor when the
        # case records are known; otherwise only the word "defendant" stands.
        if _THEY.match(subj["text"]):
            return False
        if records:
            found, reason = decide_actor(sentence, subj["text"], records, generic=generic, scope=scope)
            return reason is None and bool(found)
        return bool(_OFFENDER_WORD.match(subj["text"]))
    if _OFFENDER_WORD.match(subj["text"]):
        return True
    if not _THEY.match(subj["text"]):
        return False
    if os.environ.get("CASELINKER_COREFERENCE") != "1" or not actors:
        return False
    from state_machines.coding.coreference import resolve_mentions, _offender_ids
    mentions = resolve_mentions(sentence, actors)
    offenders = _offender_ids(actors)
    prior = [mention for mention in mentions if mention["end"] <= subj["end"] and mention["actor_ids"]]
    if not prior:
        return False
    return any(actor_id in offenders for actor_id in prior[-1]["actor_ids"])


def _negated(tokens: Sequence[dict], verb_i: int) -> bool:
    return any(t.get("head") == verb_i and t.get("deprel") == "neg" for t in tokens)


def instrument_means(sentence: str, observation: dict, tokens: Sequence[dict], actors=None,
                     records=None, generic=None, scope=None) -> Optional[dict]:
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
        if not _subject_is_offender(sentence, tokens, verb_i, actors, records=records,
                                    generic=generic, scope=scope):
            continue
        method = "fallback" if fallback_enabled() else "dep"
        return {"relationship": "Supports_Action", "cue": cue, "method": method,
                "crossed_parentheses": crossed}
    return None


_WORD = re.compile(r"[A-Za-z0-9']+|[()]")
_USE_VERBS = {"utilized", "utilize", "used", "use", "sent", "send", "received", "receive", "contacted", "communicated"}
_SUBJECTS = {"defendant", "accused", "he", "they"}


def _fallback_tokens(sentence: str) -> List[dict]:
    """A small dependency parse for a means verb and a parenthetical instrument.

    Used only when ``CASELINKER_MEANS_PARSER_FALLBACK=1``. It is not a silent stand-in
    for a model that failed to load.
    """
    tokens = [{"text": m.group(), "start": m.start(), "end": m.end(), "head": 0, "deprel": "dep", "pos": ""}
              for m in _WORD.finditer(sentence)]
    verb_i = next((i for i, tok in enumerate(tokens) if tok["text"].lower() in _USE_VERBS), None)
    if verb_i is None:
        return tokens
    tokens[verb_i]["deprel"] = "ROOT"
    tokens[verb_i]["pos"] = "VERB"
    tokens[verb_i]["head"] = verb_i
    for i, tok in enumerate(tokens):
        if i < verb_i and tok["text"].lower() in _SUBJECTS:
            tok["head"] = verb_i
            tok["deprel"] = "nsubj"
    opens = [i for i, tok in enumerate(tokens) if tok["text"] == "("]
    closes = [i for i, tok in enumerate(tokens) if tok["text"] == ")"]
    if opens and closes and opens[0] < closes[0]:
        before = opens[0] - 1
        inside = list(range(opens[0] + 1, closes[0]))
        if before >= 0 and inside:
            tokens[before]["head"] = verb_i
            tokens[before]["deprel"] = "dobj"
            noun = inside[-1]
            tokens[noun]["head"] = before
            tokens[noun]["deprel"] = "appos"
            for j in inside[:-1]:
                tokens[j]["head"] = noun
                tokens[j]["deprel"] = "amod"
    return tokens


def tokens_for(sentence: str) -> List[dict]:
    """Tokens for the instrument walk.

    With the parser off, an empty list. With it on, the cached model, or the
    fallback tokenizer when that flag is set. A missing model raises.
    """
    if not parser_enabled():
        return []
    if fallback_enabled():
        return _fallback_tokens(sentence)
    return tokens_from_spacy(sentence)


def compare(sentence: str, observation: dict, tokens: Sequence[dict] = (), actors=None) -> dict:
    """The word-window hit and the dependency hit, side by side. Neither is stored."""
    from state_machines.observations.observe import _means
    return {"window": _means("feature", sentence, observation),
            "dep": instrument_means(sentence, observation, tokens, actors=actors)}
