"""Old-snapshot case id -> current case id, by content.

Before #38 (2026-10-19) case ids were positional ordinals per source and year,
assigned at ingest. Re-splitting or dedup of a source shifted every later
ordinal, so the same id could name a different release in a later corpus.
Since #38 ids are minted from an ``fp-1`` content fingerprint and reused, so
they should hold across rebuilds. The crosswalk below never assumes either:
an id from another snapshot is mapped only through text the old snapshot
recorded for it (its evidence quotes).

Classes, strongest first:

``exact``        every usable quote that matches points at one current case and
                 at least one quote matches verbatim (whitespace-collapsed)
``normalized``   one target, but only after punctuation/case normalization
                 (quote glyph or name-mask differences)
``probable``     a majority target with dissent, or one short quote; review
``ambiguous``    quotes match several cases with no majority
``unmatched``    no usable quote, or no quote found in the current corpus

Outputs hold ids, hashes and counts only, never quote text.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .snapshot import REPO

JUNE_COMMIT = "24b31e9cd"  # AfH 1.0 Q1 outputs (generated 2026-06-18, committed 2026-06-22)
JUNE_EVIDENCE = "ontology/q1/q1_evidence.json"
JUNE_CANDIDATES = "ontology/q1/candidates.json"
OCT20_COMMIT = "833228c39"  # first evidence build after #38 content-locked ids
OCT20_EVIDENCE = "ontology/platform_affordance_evidence/platform_affordance_evidence.json"

MIN_QUOTE = 25   # normalized chars; shorter quotes are too generic to identify a release
STRONG_QUOTE = 40

CLASSES = ("exact", "normalized", "probable", "ambiguous", "unmatched")

_WS = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9]")
_ID = re.compile(r"^(?P<org>.+?)_(?P<year>\d{4})_(?P<num>\d+)$")


def git_json(commit: str, path: str) -> dict:
    out = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{path}"],
                         check=True, capture_output=True)
    return json.loads(out.stdout)


def org_of(case_id: str) -> str:
    m = _ID.match(case_id)
    return m.group("org") if m else case_id


def ws(text: str) -> str:
    return _WS.sub(" ", text or "").strip().lower()


def alnum(text: str) -> str:
    return _NON_ALNUM.sub("", (text or "").lower())


def clean_quote(q: str) -> str:
    q = (q or "").strip()
    if q.endswith("..."):
        q = q[:-3]
    return q.strip()


def quote_sha(q: str) -> str:
    return hashlib.sha256(alnum(clean_quote(q)).encode("utf-8")).hexdigest()[:16]


class CorpusIndex:
    """Whitespace- and alnum-normalized texts, grouped by source org for speed."""

    def __init__(self, texts: Mapping[str, str]):
        self.ws: Dict[str, str] = {cid: ws(t) for cid, t in texts.items()}
        self.al: Dict[str, str] = {cid: alnum(t) for cid, t in texts.items()}
        self.by_org: Dict[str, List[str]] = defaultdict(list)
        for cid in sorted(texts):
            self.by_org[org_of(cid)].append(cid)

    def find(self, quote: str, org: str) -> Tuple[str, List[str]]:
        """Return (kind, ids). Searches the old id's org first, then the whole corpus."""
        q_ws, q_al = ws(clean_quote(quote)), alnum(clean_quote(quote))
        pools = [self.by_org.get(org, []), sorted(self.ws)]
        for pool in pools:
            hits = [cid for cid in pool if q_ws and q_ws in self.ws[cid]]
            if hits:
                return "exact", hits
            hits = [cid for cid in pool if q_al and q_al in self.al[cid]]
            if hits:
                return "normalized", hits
        return "none", []


@dataclass
class Mapping_:
    old_id: str
    current_id: Optional[str]
    cls: str
    quotes_used: int = 0
    quotes_agreeing: int = 0
    exact_hits: int = 0
    candidates: List[str] = field(default_factory=list)
    old_id_exists_now: bool = False

    @property
    def reassigned(self) -> Optional[bool]:
        if self.current_id is None:
            return None
        return self.current_id != self.old_id

    def as_row(self) -> dict:
        return {
            "old_id": self.old_id, "current_id": self.current_id, "class": self.cls,
            "quotes_used": self.quotes_used, "quotes_agreeing": self.quotes_agreeing,
            "exact_hits": self.exact_hits, "candidates": self.candidates[:5],
            "old_id_exists_now": self.old_id_exists_now, "reassigned": self.reassigned,
        }


def classify(old_id: str, quote_hits: Sequence[Tuple[str, List[str], int]],
             current_ids: Iterable[str]) -> Mapping_:
    """``quote_hits``: (kind, matching ids, normalized quote length) per usable quote."""
    exists = old_id in set(current_ids)
    found = [(k, ids, n) for k, ids, n in quote_hits if ids]
    if not found:
        return Mapping_(old_id, None, "unmatched", quotes_used=len(quote_hits), old_id_exists_now=exists)
    votes: Counter = Counter()
    unique_votes: Counter = Counter()
    exact_for: Counter = Counter()
    for kind, ids, _ in found:
        for cid in ids:
            votes[cid] += 1
            if kind == "exact":
                exact_for[cid] += 1
        if len(ids) == 1:
            unique_votes[ids[0]] += 1
    if unique_votes:
        ranked = unique_votes.most_common()
        top, top_n = ranked[0]
        tie = len(ranked) > 1 and ranked[1][1] == top_n
    else:
        ranked = votes.most_common()
        top, top_n = ranked[0]
        tie = len(ranked) > 1 and ranked[1][1] == top_n
    m = Mapping_(old_id, None, "ambiguous", quotes_used=len(quote_hits),
                 quotes_agreeing=votes[top], exact_hits=exact_for[top],
                 candidates=[c for c, _ in ranked], old_id_exists_now=exists)
    if tie or not unique_votes:
        return m
    m.current_id = top
    dissent = [ids for _, ids, _ in found if top not in ids]
    longest = max(n for _, ids, n in found if top in ids)
    if dissent or (votes[top] == 1 and longest < STRONG_QUOTE):
        m.cls = "probable"
    elif exact_for[top]:
        m.cls = "exact"
    else:
        m.cls = "normalized"
    return m


def build_crosswalk(old_records: Iterable[Mapping], old_ids: Iterable[str],
                    texts: Mapping[str, str]) -> List[Mapping_]:
    index = CorpusIndex(texts)
    quotes: Dict[str, List[str]] = defaultdict(list)
    for r in old_records:
        q = clean_quote(r.get("evidence_quote", ""))
        if len(alnum(q)) >= MIN_QUOTE and q not in quotes[r["case_id"]]:
            quotes[r["case_id"]].append(q)
    out = []
    for oid in sorted(set(old_ids)):
        hits = []
        for q in quotes.get(oid, []):
            kind, ids = index.find(q, org_of(oid))
            hits.append((kind, ids, len(alnum(q))))
        out.append(classify(oid, hits, texts.keys()))
    return out


def summarize(maps: Sequence[Mapping_]) -> dict:
    by_org: Dict[str, Counter] = defaultdict(Counter)
    for m in maps:
        c = by_org[org_of(m.old_id)]
        c[m.cls] += 1
        if m.current_id is not None:
            c["same_id" if not m.reassigned else "reassigned"] += 1
    total: Counter = Counter()
    for c in by_org.values():
        total.update(c)
    return {"total": dict(sorted(total.items())), "old_ids": len(maps),
            "by_org": {k: dict(sorted(v.items())) for k, v in sorted(by_org.items())}}


def resolve(old_id: str, crosswalk: Mapping[str, Mapping_]) -> Tuple[Optional[str], str]:
    """Current id for a historical citation, and how it was established. Never echoes ids blindly."""
    m = crosswalk.get(old_id)
    if m is None:
        return None, "not_in_crosswalk"
    if m.cls in ("exact", "normalized"):
        return m.current_id, m.cls
    return None, m.cls
