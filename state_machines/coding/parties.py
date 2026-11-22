"""Local party-list snapshot. Never calls a network API.

A file named by ``CASELINKER_PARTY_SNAPSHOT`` is a JSON list or JSONL. Each
entry has ``court``, ``docket_number`` and ``parties``. A party has
``party_id``, ``name`` and ``role``. Only ``defendant`` is used. A terminated
defendant still counts. Names are stored as written; they are not run through
the caption parser. The identity is ``party_id``.

``CASELINKER_PARTY_SNAPSHOT_SHA256`` when set must equal the file bytes.
A mismatch stops the run.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Optional

_CACHE: dict = {}
_GENERATION = re.compile(r"\b(?:Jr|Sr|II|III|IV)\.?\b", re.I)
_PARTY_NUMBER = re.compile(r"\(\d+\)")


def party_name(raw: str) -> tuple:
    """``(full, surname)`` from a snapshot name.

    ``LAST, FIRST MIDDLE`` keeps LAST as the surname. A leading ``(1)`` and a
    generational suffix are not part of the name.
    """
    cleaned = _PARTY_NUMBER.sub(" ", raw or "")
    cleaned = _GENERATION.sub(" ", cleaned)
    cleaned = cleaned.replace(".", " ")
    cleaned = " ".join(cleaned.split()).strip(" ,")
    if not cleaned:
        return "", ""
    if "," in cleaned:
        last, rest = cleaned.split(",", 1)
        surname = last.strip().split()[-1] if last.strip() else ""
        given = " ".join(rest.split())
        full = " ".join(part for part in (given, surname) if part)
        return full, surname
    parts = cleaned.split()
    return cleaned, parts[-1]


def _entries(text: str) -> list:
    stripped = text.strip()
    if not stripped:
        return []
    if stripped.startswith("["):
        data = json.loads(stripped)
        return data if isinstance(data, list) else []
    rows = []
    for line in stripped.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def load(path: Optional[str] = None) -> Optional[dict]:
    """``{sha256, index}`` or None when no snapshot is configured.

    ``index`` maps ``(court, docket_number)`` to defendant records.
    """
    target = path if path is not None else os.environ.get("CASELINKER_PARTY_SNAPSHOT")
    if not target:
        return None
    file = Path(target)
    key = str(file.resolve()) if file.exists() else str(file)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    raw = file.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    expected = os.environ.get("CASELINKER_PARTY_SNAPSHOT_SHA256")
    if expected and expected != digest:
        raise SystemExit(f"party snapshot sha256 {digest} does not match {expected}")
    index = {}
    others = {}
    for entry in _entries(raw.decode("utf-8")):
        court = str(entry.get("court") or "")
        docket = str(entry.get("docket_number") or "")
        people = []
        other_names = set()
        for party in entry.get("parties") or []:
            full, surname = party_name(str(party.get("name") or ""))
            name = full
            if not name or not surname or not party.get("party_id"):
                continue
            if str(party.get("role") or "").lower() != "defendant":
                other_names.add(surname.lower())
                continue
            people.append({
                "full": full, "surname": surname, "aliases": [], "alias_surnames": [],
                "key": str(party["party_id"]), "party_id": str(party["party_id"]),
            })
        index[(court, docket)] = people
        others[(court, docket)] = other_names
    loaded = {"sha256": digest, "index": index, "others": others}
    _CACHE[key] = loaded
    return loaded


def snapshot_record() -> Optional[dict]:
    loaded = load()
    if not loaded:
        return None
    return {"sha256": loaded["sha256"]}


def defendants_for(court: str, docket_number: str) -> Optional[list]:
    """Defendant records for this case, or None when the snapshot has no entry."""
    loaded = load()
    if not loaded:
        return None
    return loaded["index"].get((court or "", docket_number or ""))


def other_surnames(court: str, docket_number: str) -> set:
    """Surnames of parties who are not defendants, so a shared surname can be refused."""
    loaded = load()
    if not loaded:
        return set()
    return set(loaded.get("others", {}).get((court or "", docket_number or ""), ()))
