"""Resolve mentions to a closed list of case actors.

Stanza's neural coreference is a poor fit here: the actors are already a closed
list (the defendant from the caption, co-offenders, victims by the record's own
label, the affiant, agents, and the platforms and accounts the inventory names).
A deterministic linker over that list is the same on every run. Names match
without regard to case. The flag does not call out on its own.

The flag is off by default. With it off, ``resolve_mentions`` returns nothing
and the current subject test in ``observe._means`` is untouched.

Names stay on the inventory the caller holds in memory. A mention stores an
actor id and the character span, not a name copied into a bundle.

The adjacent-sentence level (``CASELINKER_ADJACENT_LEVEL=1``, default off) is a
separate list. It is labelled ``adjacent-sentence``, it fires only when the
later sentence has an explicit anaphor with an antecedent in the sentence
before it, and it is never merged into same-sentence level C.
"""
from __future__ import annotations

import os
import re
from typing import Callable, Iterable, List, Optional, Sequence

from state_machines.coding.workflow import PRONOUN_WORDS

_PRONOUN = re.compile(r"\b(" + "|".join(PRONOUN_WORDS) + r"|me|my)\b|\b(I)\b", re.I)
_AND = re.compile(r"\band\b", re.I)
_ACCOUNT = re.compile(r"\b(?:that|this|the same|the)\s+(account|app|application)\b", re.I)
_ANAPHOR = re.compile(
    r"\b(?:that|this|the same)\s+(?:account|app|application|platform|service|channel)\b|\b(?:he|she|they|him|her|them)\b",
    re.I)
_AFFIANT_VOICE = re.compile(r"\bI know from my training and experience\b|\bbased on my training and experience\b", re.I)
_PERSON = re.compile(r"\b(?:he|she|the defendant|the affiant|the agent|agents)\b", re.I)


def coreference_enabled() -> bool:
    return os.environ.get("CASELINKER_COREFERENCE") == "1"


def adjacent_level_enabled() -> bool:
    return os.environ.get("CASELINKER_ADJACENT_LEVEL") == "1"


class Actor:
    """One case actor. ``names`` are the surface forms the linker may see, held in memory."""

    def __init__(self, actor_id: str, kind: str, names: Sequence[str]):
        self.actor_id = actor_id
        self.kind = kind
        self.names = tuple(names)

    def __repr__(self) -> str:
        return f"Actor({self.actor_id!r}, {self.kind!r})"


def make_inventory(*, defendant: str = "the defendant", defendant_names: Iterable[str] = (),
                   co_offenders: Iterable[str] = (),
                   victims: Iterable[str] = (), platforms: Iterable[str] = (),
                   accounts: Iterable[str] = ()) -> List[Actor]:
    """The closed list. The defendant id is ``defendant``; the caption string is only a name.

    ``defendant_names`` are the caption forms. A multi-word name also contributes its
    last word, so a surname on the page resolves to the same actor.
    """
    forms = [defendant, "the defendant", "the accused"]
    for name in defendant_names:
        cleaned = " ".join(str(name).split())
        if not cleaned:
            continue
        forms.append(cleaned)
        parts = cleaned.split()
        if len(parts) > 1:
            forms.append(parts[-1])
    seen = []
    for form in forms:
        if form not in seen:
            seen.append(form)
    actors = [Actor("defendant", "defendant", tuple(seen))]
    for i, name in enumerate(co_offenders, 1):
        actors.append(Actor(f"co_offender:{i}", "co_offender", (name,)))
    for i, label in enumerate(victims, 1):
        actors.append(Actor(f"victim:{i}", "victim", (label,)))
    actors.append(Actor("affiant", "affiant", ("the affiant", "this affiant")))
    actors.append(Actor("agent", "agent", ("the agent", "agents", "law enforcement")))
    for i, name in enumerate(platforms, 1):
        actors.append(Actor(f"platform:{i}", "platform", (name, "that app", "the app")))
    for i, name in enumerate(accounts, 1):
        actors.append(Actor(f"account:{i}", "account", (name, "the account", "that account")))
    if not accounts:
        actors.append(Actor("account:1", "account", ("the account", "that account")))
    return actors


def _offender_ids(actors: Sequence[Actor]) -> set:
    return {a.actor_id for a in actors if a.kind in ("defendant", "co_offender")}


def _name_mentions(text: str, actors: Sequence[Actor]) -> List[dict]:
    """Listed surface forms, longest first, no overlaps."""
    forms = sorted(((name, a) for a in actors for name in a.names if name), key=lambda t: len(t[0]), reverse=True)
    taken: List[tuple] = []
    out = []
    for name, actor in forms:
        for m in re.finditer(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", text, re.I):
            surface = text[m.start():m.end()]
            if " " not in name.strip() and not surface[:1].isupper():
                continue
            if any(m.start() < e and s < m.end() for s, e in taken):
                continue
            taken.append(m.span())
            out.append({"text": text[m.start():m.end()], "start": m.start(), "end": m.end(),
                        "actor_ids": [actor.actor_id], "confidence": 0.95, "kind": "description"})
    return out


def _they_includes(text: str, at: int, actors: Sequence[Actor]) -> List[str]:
    """Actor ids a coordinated 'they' includes: a listed name, then 'and', then the pronoun."""
    window = text[:at]
    found = []
    for actor in actors:
        if actor.kind not in ("defendant", "co_offender", "victim"):
            continue
        for name in actor.names:
            pos = window.lower().rfind(name.lower())
            if pos < 0:
                continue
            if _AND.search(window[pos + len(name):]):
                found.append(actor.actor_id)
                break
    return found


def _nearest_offender(mentions: Sequence[dict], at: int, offenders: set) -> List[str]:
    prior = [m for m in mentions if m["end"] <= at and any(i in offenders for i in m["actor_ids"])]
    if not prior:
        return []
    return [i for i in prior[-1]["actor_ids"] if i in offenders]


def _rule_mentions(text: str, actors: Sequence[Actor], voice: str) -> List[dict]:
    named = _name_mentions(text, actors)
    offenders = _offender_ids(actors)
    affiant_voice = voice == "affiant" or bool(_AFFIANT_VOICE.search(text))
    out = list(named)
    for m in _PRONOUN.finditer(text):
        token = m.group(1) or m.group(2)
        low = token.lower()
        if low in ("i", "me", "my"):
            # An affidavit's "I" is the affiant. It is never the defendant.
            # A plea's "I" is the defendant only when the caller says so.
            # Anywhere else, "I" is left unresolved rather than guessed.
            if affiant_voice or voice == "affiant":
                ids, conf = ["affiant"], 0.95
            elif voice == "defendant":
                ids, conf = ["defendant"], 0.7
            else:
                ids, conf = [], 0.0
        elif low in ("they", "them", "their"):
            ids, conf = _they_includes(text, m.start(), actors), 0.75
        elif low in ("he", "him", "his", "she", "her"):
            ids, conf = _nearest_offender(named, m.start(), offenders), 0.8
        else:
            ids, conf = [], 0.0
        out.append({"text": text[m.start():m.end()], "start": m.start(), "end": m.end(),
                    "actor_ids": ids, "confidence": conf if ids else 0.0, "kind": "pronoun"})
    out.sort(key=lambda m: (m["start"], m["end"]))
    return out


def resolve_mentions(text: str, actors: Sequence[Actor], *, voice: str = "narrative") -> List[dict]:
    """Mentions with actor ids. Empty unless coreference is on."""
    if not coreference_enabled():
        return []
    return _rule_mentions(text, actors, voice)


def _previous_grounds(previous: str, anaphor: str, actors: Sequence[Actor]) -> bool:
    noun = re.search(r"(account|app|application|platform|service|channel)", anaphor, re.I)
    if noun:
        return re.search(rf"\b{noun.group(1)}s?\b", previous, re.I) is not None
    if _PERSON.search(previous):
        return True
    return any(re.search(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", previous) for a in actors for name in a.names)


def adjacent_links(sentences: Sequence[str], actors: Sequence[Actor], *, enabled: Optional[bool] = None) -> List[dict]:
    """Links between consecutive sentences, labelled ``adjacent-sentence``.

    Empty unless the adjacent-sentence flag is on. A link needs an explicit
    anaphor in the later sentence and an antecedent in the sentence before it.
    Two sentences that merely follow each other are not linked.
    """
    if enabled is None:
        enabled = adjacent_level_enabled()
    if not enabled:
        return []
    links = []
    for i, (prev, cur) in enumerate(zip(sentences, sentences[1:])):
        m = _ANAPHOR.search(cur)
        if m is None or not _previous_grounds(prev, m.group(0), actors):
            continue
        links.append({
            "level": "adjacent-sentence",
            "anaphor": cur[m.start():m.end()],
            "anaphor_start": m.start(),
            "anaphor_end": m.end(),
            "previous_index": i,
            "sentence_index": i + 1,
            "previous_sentence": prev,
            "sentence": cur,
        })
    return links


def level_c_only(same_sentence: Sequence[dict], adjacent: Sequence[dict]) -> dict:
    """Keep same-sentence level C and the adjacent-sentence level in separate lists.

    An adjacent link is never copied into the level-C list. Passing one there raises.
    """
    leaked = [r for r in same_sentence if r.get("level") == "adjacent-sentence"]
    if leaked:
        raise ValueError("adjacent-sentence level is never merged with same-sentence level C")
    level_c = [dict(r, level="C") for r in same_sentence]
    adj = [dict(r, level="adjacent-sentence") for r in adjacent]
    return {"level_c": level_c, "adjacent_sentence": adj}
