"""Deterministic validation sample and a local, people-masked review sheet.

``sample_rows`` picks rows by sha256(case_id|platform|item) so a rerun picks
the same rows. The committed sample lists ids, fingerprints and offsets only.
``write_sheet`` renders the evidence sentences, with people masked, into
``data/review_sheet.md`` (gitignored) for a human reviewer. Reviewer verdicts
live in ``config/validation_reviews.csv`` (ids, verdict, note: no text).
"""
from __future__ import annotations

import csv
import hashlib
import sys
from pathlib import Path
from typing import Dict, Iterable, List

from .snapshot import DATA, REPO, RESEARCH

sys.path.insert(0, str(REPO / "src" / "Processing Layer" / "field_assertions"))

REVIEWS = RESEARCH / "config" / "validation_reviews.csv"
SAMPLE_PLAN = {
    # item: (selector description, n)
    "tier:stated": 12, "tier:inferred": 10, "tier:named_only": 10,
    "C:Anonymity": 10, "C:ContactDiscovery": 10, "C:UnmonitoredCommunication": 10,
    "C:DistributionInfrastructure": 15, "C:GenerativeSynthesis": 10,
    "review:Ephemerality": 10, "review:Anonymity": 8,
    "alias:Mega.nz": 8,
}


def _key(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def select(records, item: str):
    kind, arg = item.split(":", 1)
    if kind == "tier":
        pool = [r for r in records if r.tier == arg and r.status == "specific" and r.text_found]
    elif kind == "C":
        pool = [r for r in records if r.instrumental.get(arg)]
    elif kind == "review":
        pool = [r for r in records if r.review.get(arg)]
    elif kind == "alias":
        pool = [r for r in records if r.platform == arg and r.text_found]
    else:
        raise ValueError(item)
    return sorted(pool, key=lambda r: _key(r.case_id, r.platform, item))


def sample_rows(records) -> List[Dict]:
    rows = []
    for item, n in SAMPLE_PLAN.items():
        for r in select(records, item)[:n]:
            cls = item.split(":", 1)[1]
            span = r.instrumental_span.get(cls) or (r.sentence_spans[0] if r.sentence_spans else (-1, -1))
            rows.append({"item": item, "case_id": r.case_id, "fingerprint": r.fingerprint,
                         "platform": r.platform, "tier": r.tier, "span": f"{span[0]}-{span[1]}"})
    return rows


def masked(text: str, start: int, end: int) -> str:
    from people_mask import mask_person_names, person_surnames
    if start < 0:
        return "(no sentence: platform not found in capped text)"
    window = text[max(0, start - 160): end + 160].replace("\n", " ")
    return mask_person_names(window, surnames=person_surnames(text))[0]


def write_sheet(rows: Iterable[Dict], texts: Dict[str, str], path: Path = DATA / "review_sheet.md") -> Path:
    lines = ["# Q1 validation sheet (local only, people masked)", ""]
    for i, r in enumerate(rows):
        a, b = (int(x) for x in r["span"].split("-"))
        lines.append(f"## {i:03d} {r['item']} | {r['case_id']} | {r['platform']} | {r['tier']}")
        lines.append(masked(texts[r["case_id"]], a, b))
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def load_reviews() -> Dict[tuple, Dict]:
    if not REVIEWS.is_file():
        return {}
    with REVIEWS.open(encoding="utf-8") as f:
        return {(r["item"], r["case_id"], r["platform"]): r for r in csv.DictReader(f)}
