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
        a, b = _parse_span(r["span"])
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


# ---------------------------------------------------------- 2026-11-17 samples

def named_only_gate(record, text: str) -> str:
    """Which published tier rule kept a record at named_only (first gate hit on its best sentence)."""
    from .pipeline import evidence_module
    pe = evidence_module()
    if not record.text_found:
        return "text_not_found_in_cap"
    offense, _psa, _cap = pe.offense_lines(text)
    gates = []
    for s in pe.sentences_with_platform(offense, record.platform):
        if not pe.generic_platform_mention_valid(s, record.platform):
            gates.append("generic_label_rule")
        elif pe.is_awareness_or_list_framing(s):
            sl = s.lower()
            hit = next((t for t in pe.AWARENESS_TRIGGERS if t in sl), "list_heuristic")
            gates.append(f"awareness:{hit}")
        elif pe.is_enumeration_only(s, record.platform):
            gates.append("enumeration_3plus_commas")
        elif not pe.has_offense_keyword_for_platform(s, record.platform):
            gates.append("no_offense_keyword")
        else:
            gates.append("other")
    return gates[0] if gates else "no_platform_sentence"


def tier_sample_rows(records, texts) -> List[Dict]:
    """Blind tier sample: named_only 40 (all specific platforms), inferred 15, stated 15."""
    plan = {"named_only": 40, "inferred": 15, "stated": 15}
    rows = []
    for tier, n in plan.items():
        pool = [r for r in records if r.tier == tier and r.status == "specific"]
        pool = sorted(pool, key=lambda r: _key(r.case_id, r.platform, "tier2:" + tier))[:n]
        for r in pool:
            span = r.sentence_spans[0] if r.sentence_spans else (-1, -1)
            rows.append({"item": f"tier2:{tier}", "case_id": r.case_id, "fingerprint": r.fingerprint,
                         "platform": r.platform, "tier": r.tier, "span": f"{span[0]}-{span[1]}",
                         "gate": named_only_gate(r, texts[r.case_id]) if tier == "named_only" else ""})
    return rows


HARMS = ("h1_contact_sexual_abuse", "h2_depicted_in_abuse_imagery", "h3_imagery_circulated",
         "h4_coerced_by_exposure_threat", "h5_commercial_sexual_exploitation")


def harm_sample_rows(records) -> List[Dict]:
    """Per harm: 6 direct, 4 case-level only, 4 negatives (use-documented, no cue);
    plus shared-trigger rows: Distribution C with h3 direct (6), GenerativeSynthesis C with h6 direct (4)."""
    rows = []
    used = [r for r in records if r.status in ("specific", "technology", "ambiguous_alias") and r.tier in ("stated", "inferred")]
    for h in HARMS:
        groups = {
            "direct": [r for r in used if r.harm_direct[h]],
            "case_level_only": [r for r in used if r.harm_case[h] and not r.harm_direct[h]],
            "negative": [r for r in used if not r.harm_case[h]],
        }
        for label, n in (("direct", 6), ("case_level_only", 4), ("negative", 4)):
            for r in sorted(groups[label], key=lambda r: _key(r.case_id, r.platform, h, label))[:n]:
                rows.append(_harm_row(r, f"harm:{h}:{label}", h))
    for cls, h, n in (("DistributionInfrastructure", "h3_imagery_circulated", 6),
                      ("GenerativeSynthesis", "h2_depicted_in_abuse_imagery", 4)):
        pool = [r for r in used if r.instrumental[cls] and r.harm_direct[h]]
        for r in sorted(pool, key=lambda r: _key(r.case_id, r.platform, "overlap", h))[:n]:
            rows.append(_harm_row(r, f"overlap:{cls}:{h}", h))
    return rows


def _harm_row(r, item, h):
    span = r.sentence_spans[0] if r.sentence_spans else (-1, -1)
    return {"item": item, "harm": h, "case_id": r.case_id, "fingerprint": r.fingerprint,
            "platform": r.platform, "tier": r.tier, "span": f"{span[0]}-{span[1]}"}


def write_blind_sheet(rows: Iterable[Dict], texts: Dict[str, str], path: Path, question, window: int = 600) -> Path:
    """Masked passage around the platform sentence (marked >> <<), the question, no classifier verdict."""
    from people_mask import mask_person_names, person_surnames
    lines = ["# Blind review sheet (local only, people masked; do not copy names into answers)", ""]
    for i, r in enumerate(rows):
        a, b = _parse_span(r["span"])
        text = texts[r["case_id"]]
        if a < 0:
            body = text[:2 * window]
        else:
            body = text[max(0, a - window):a] + " >>" + text[a:b] + "<< " + text[b:b + window]
        body = mask_person_names(body.replace("\n", " "), surnames=person_surnames(text))[0]
        lines += [f"## {i:03d} | case {r['case_id']} | platform: {r['platform']}", question(r), "", body, ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _parse_span(span: str):
    import re as _re
    m = _re.match(r"^(-?\d+)-(-?\d+)$", span or "")
    return (int(m.group(1)), int(m.group(2))) if m else (-1, -1)


def inferred_sample_rows(records, per_class: int = 6) -> List[Dict]:
    """I-but-not-C rows per class, for a blind plausibility check of the inference rule."""
    from .pipeline import CLASSES
    rows = []
    for c in CLASSES:
        pool = [r for r in records if r.inferred.get(c) and not r.instrumental.get(c)]
        for r in sorted(pool, key=lambda r: _key(r.case_id, r.platform, "I:" + c))[:per_class]:
            span = r.sentence_spans[0] if r.sentence_spans else (-1, -1)
            rows.append({"item": f"I:{c}", "case_id": r.case_id, "fingerprint": r.fingerprint,
                         "platform": r.platform, "tier": r.tier, "span": f"{span[0]}-{span[1]}"})
    return rows
