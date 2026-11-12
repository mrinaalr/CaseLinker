"""Content-locked case ids.

The readable id stays ``{org}_{year}_{ordinal}``. A fingerprint of the
normalized case text decides which ordinal that is. The URL is not consulted.

``NORMALIZATION_VERSION`` is stored with every fingerprint. A map that contains
any other version refuses to mint, so a later edit to normalization cannot
silently assign new ordinals.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

NORMALIZATION_VERSION = "fp-1"

_TRANSLATE = str.maketrans({
    "\u2018": "'",
    "\u2019": "'",
    "\u201a": "'",
    "\u201b": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u201e": '"',
    "\u00a0": " ",
    "\u2007": " ",
    "\u2009": " ",
    "\u202f": " ",
    "\u200b": "",
    "\ufeff": "",
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2015": "-",
    "\u00ad": "",
})

# Phrases an extractor sometimes keeps and sometimes drops. They are not the article.
_COSMETIC = re.compile(
    r"\bpublication date:\s*(?:19|20)\d{2}-\d{2}-\d{2}\b"
    r"|\bpage\s+\d+\s+of\s+\d+\b",
    re.IGNORECASE,
)
# Listing chrome the Idaho splitter sometimes keeps and sometimes drops.
_LEADING_CHROME = re.compile(
    r"^(?:(?:newsroom|category:\s*icac)\b[\s,]*)+",
    re.IGNORECASE,
)

_ORDINAL = re.compile(r"^(?P<prefix>.+)_(?P<num>\d{3,})$")


class FingerprintVersionMismatch(RuntimeError):
    """The stored map was built with a different normalization. Do not mint."""

    def __init__(self, versions: Iterable[str]) -> None:
        self.versions = sorted(set(versions))
        super().__init__(
            "case fingerprint map uses normalization "
            f"{self.versions}, not {NORMALIZATION_VERSION}; refusing to mint"
        )


def normalize_case_text(text: str) -> str:
    """The one normalization every fingerprint uses.

    Starts from the usual cleanup (URLs, page numbers, PDF debris), then
    removes only cosmetic differences: line wraps, quote and dash glyphs,
    and header lines the extractor sometimes drops.
    """
    if not text:
        return ""
    from batching import clean_artifacts_from_text

    cleaned = clean_artifacts_from_text(text) or ""
    cleaned = cleaned.translate(_TRANSLATE)
    flat = re.sub(r"\s+", " ", cleaned).strip()
    flat = _COSMETIC.sub(" ", flat)
    flat = _LEADING_CHROME.sub("", flat)
    return re.sub(r"\s+", " ", flat).strip().casefold()


def fingerprint_case_text(text: str) -> str:
    """sha256 of :func:`normalize_case_text`."""
    return hashlib.sha256(normalize_case_text(text).encode("utf-8")).hexdigest()


class FingerprintIndex:
    """In-memory copy of the fingerprint map, plus every case id already used."""

    def __init__(self) -> None:
        self.by_fingerprint: Dict[str, List[Dict[str, str]]] = {}
        self.used: set = set()
        self.versions: set = set()
        self.pending_duplicates: List[Dict[str, Any]] = []

    def remember(
        self,
        case_id: str,
        text: str,
        *,
        source_file: Optional[str] = None,
        version: Optional[str] = None,
        fingerprint: Optional[str] = None,
    ) -> None:
        version = version or NORMALIZATION_VERSION
        digest = fingerprint or fingerprint_case_text(text)
        self.used.add(case_id)
        self.versions.add(version)
        bucket = self.by_fingerprint.setdefault(digest, [])
        if any(row["case_id"] == case_id for row in bucket):
            return
        bucket.append({
            "case_id": case_id,
            "source_file": source_file or "",
            "version": version,
        })

    def note_existing_id(self, case_id: str) -> None:
        """An id with no fingerprint yet still occupies its ordinal."""
        if case_id:
            self.used.add(case_id)

    def next_free(self, provisional_id: str) -> str:
        """Smallest unused ``{prefix}_{ordinal}`` for the provisional id's prefix."""
        match = _ORDINAL.match(provisional_id or "")
        prefix = match.group("prefix") if match else (provisional_id or "case")
        number = 1
        while f"{prefix}_{number:03d}" in self.used:
            number += 1
            if number > 100000:
                raise RuntimeError(f"no free ordinal under {prefix}")
        return f"{prefix}_{number:03d}"


def _canonical(matches: Sequence[Dict[str, str]]) -> str:
    return sorted(row["case_id"] for row in matches)[0]


def assign_content_locked_ids(
    cases: Sequence[Dict[str, Any]],
    index: FingerprintIndex,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Reuse the id of matching text. A second copy is a duplicate article.

    Same text inside one ingest, or the same text already stored from a
    different source file, does not mint a second id and does not reach the
    case-id collision guard. The existing row stays. Re-ingest from the file
    that already holds the text keeps that id so the row can refresh.
    """
    foreign = {version for version in index.versions if version != NORMALIZATION_VERSION}
    if foreign:
        raise FingerprintVersionMismatch(foreign)

    seen: Dict[str, str] = {}
    kept: List[Dict[str, Any]] = []
    duplicates: List[Dict[str, Any]] = []
    for case in cases:
        payload = dict(case)
        text = payload.get("case_text") or ""
        source_file = str(payload.get("source_file") or "")
        digest = fingerprint_case_text(text)
        payload["fingerprint"] = digest
        payload["normalization_version"] = NORMALIZATION_VERSION
        if digest in seen:
            payload["duplicate_of_case_id"] = seen[digest]
            duplicates.append(payload)
            continue
        current = [
            row for row in index.by_fingerprint.get(digest, [])
            if row["version"] == NORMALIZATION_VERSION
        ]
        same_file = [row for row in current if source_file and row["source_file"] == source_file]
        other_file = [row for row in current if row["source_file"] and row["source_file"] != source_file]
        if same_file or (current and not other_file):
            chosen = _canonical(same_file or current)
            payload["case_id"] = chosen
            payload["id"] = chosen
            seen[digest] = chosen
            kept.append(payload)
            continue
        if other_file:
            payload["duplicate_of_case_id"] = _canonical(other_file)
            duplicates.append(payload)
            continue
        provisional = str(payload.get("case_id") or payload.get("id") or "case_0000_001")
        new_id = index.next_free(provisional)
        payload["case_id"] = new_id
        payload["id"] = new_id
        index.remember(new_id, text, source_file=source_file, fingerprint=digest)
        seen[digest] = new_id
        kept.append(payload)
    return kept, duplicates
