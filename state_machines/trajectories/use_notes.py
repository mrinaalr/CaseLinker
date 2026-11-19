"""Researcher judgments of affordance use. They sit beside a step and never enter O_i.

A note may say that a capability was used, was not used, or is unclear. The author is a
person. A model draft is not a note: ``basis`` has one legal value, ``researcher_inference``.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from state_machines.evidence import vocab as V

BASIS = "researcher_inference"
JUDGMENTS = ("used", "not_used", "unclear")
_KEYS = {"case_id", "event_id", "affordance", "judgment", "basis", "author", "note"}
_AUTHOR = re.compile(r"^[A-Za-z][A-Za-z .'-]{0,79}$")
_NOTE_MAX = 240


class NoteError(ValueError):
    """A use note cannot be applied."""


def load(path: Path) -> List[dict]:
    """Read a notes file. A missing file is an empty set of judgments."""
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise NoteError("use notes are a list")
    return data


def validate(notes: Iterable[dict], offered: Dict[Tuple[str, str], set]) -> List[dict]:
    """Keep notes whose capability is already on that step or stated in that case.

    ``offered[(case_id, event_id)]`` is the set of affordance classes the digest will show
    for that step, including feature phrases stated anywhere in the case. A judgment outside
    that set would be a new claim the machine frame does not contain.
    """
    clean = []
    for n in notes:
        if set(n) != _KEYS:
            raise NoteError("a use note has a fixed set of fields")
        if n["basis"] != BASIS:
            raise NoteError("a published use note is a researcher inference")
        if n["judgment"] not in JUDGMENTS:
            raise NoteError("judgment is used, not_used, or unclear")
        if n["affordance"] not in V.AFFORDANCES:
            raise NoteError("affordance is a codebook class")
        if not _AUTHOR.match(n["author"] or ""):
            raise NoteError("author is a person's name, not a model id")
        note = n["note"]
        if not isinstance(note, str) or len(note) > _NOTE_MAX or "\n" in note:
            raise NoteError("the note is one short line")
        if n["judgment"] == "used" and len(note.strip()) < 8:
            raise NoteError("a used judgment says how, in one short line")
        key = (n["case_id"], n["event_id"])
        if key not in offered:
            raise NoteError("the note names a step the digest does not contain")
        if n["affordance"] not in offered[key]:
            raise NoteError("the note names a capability the step does not offer and the case does not state")
        clean.append(dict(n))
    return clean


def by_step(notes: Iterable[dict]) -> Dict[Tuple[str, str], List[dict]]:
    grouped: Dict[Tuple[str, str], List[dict]] = {}
    for n in notes:
        grouped.setdefault((n["case_id"], n["event_id"]), []).append({
            "affordance": n["affordance"], "judgment": n["judgment"], "author": n["author"], "note": n["note"],
        })
    return grouped
