"""Research citations that cannot silently follow a reassigned case id.

A citation records the case id *and* the ``fp-1`` content fingerprint the id
held when it was cited. ``verify`` re-reads the corpus: if that id now holds
different text the citation is ``id_reassigned`` (and, when the fingerprint
still exists under another id, ``moved_to`` names it). A bare id is never
accepted as proof of identity across snapshots.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional

STATUSES = ("ok", "id_reassigned", "moved", "missing", "no_fingerprint")


@dataclass(frozen=True)
class Citation:
    case_id: str
    fingerprint: str
    purpose: str = ""          # e.g. "manifest:Kik:harm_vector:0"
    platform: str = ""         # platform the citation is meant to evidence, if any

    def to_json(self) -> dict:
        return asdict(self)


@dataclass
class Verdict:
    citation: Citation
    status: str
    current_id: Optional[str]

    def as_row(self) -> dict:
        return {**self.citation.to_json(), "status": self.status, "current_id": self.current_id}


def verify(citations: Iterable[Citation], fingerprints: Mapping[str, str]) -> List[Verdict]:
    """``fingerprints``: current case_id -> fp-1 fingerprint."""
    by_fp: Dict[str, List[str]] = {}
    for cid, fp in fingerprints.items():
        by_fp.setdefault(fp, []).append(cid)
    out = []
    for c in citations:
        if not c.fingerprint:
            out.append(Verdict(c, "no_fingerprint", None))
            continue
        now = fingerprints.get(c.case_id)
        if now == c.fingerprint:
            out.append(Verdict(c, "ok", c.case_id))
            continue
        moved = sorted(by_fp.get(c.fingerprint, []))
        if moved:
            out.append(Verdict(c, "moved" if now is None else "id_reassigned", moved[0]))
        else:
            out.append(Verdict(c, "missing" if now is None else "id_reassigned", None))
    return out


def load(path: Path) -> List[Citation]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = doc["citations"] if isinstance(doc, dict) else doc      # dict since AfH 2.0 (carries afh_inputs)
    return [Citation(**{k: r[k] for k in ("case_id", "fingerprint", "purpose", "platform") if k in r})
            for r in rows]


def dump(citations: Iterable[Citation], path: Path) -> None:
    rows = sorted((c.to_json() for c in citations), key=lambda r: (r["purpose"], r["case_id"]))
    path.write_text(json.dumps(rows, indent=1, sort_keys=True) + "\n", encoding="utf-8")
