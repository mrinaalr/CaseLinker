#!/usr/bin/env python3
"""
Big Bang corpus selection v2 — bridge-dense, source-diverse 1000-case demo graph.

TARGET: 1000 cases (down from 2500; 2500 exceeds browser layout ceiling at
~42k merged nodes). Goal is a graph that MERGES CLEANLY and reads as
cross-case linkage, not a star graph or a single mega-hub.

CORPUS: ~5,600 cases in caselinker.db. We select over the ~3,200 SUBSTANTIVE
cases only.

HARD EXCLUSION — NCMEC (default ~2,400 cases):
  NCMEC entries are success press releases, not case reports. They are thin on
  the CAC spine (few Events, few Roles, sparse platform/agency mentions) and
  dilute merged-node quality. EXCLUDE all NCMEC cases EXCEPT where a case is in
  the AI pin set (AI coverage outranks the NCMEC noise penalty for that bucket
  only). Non-NCMEC sources are richer because they are case reports, not PR.

CORE SELECTION PRINCIPLE — bridge yield per case:
  Every admitted case must EITHER (a) introduce a novel bridge URI (a platform
  or agency not yet in the selected graph) OR (b) reinforce an existing bridge
  (a 2nd+ case touching a shared platform/agency node). Selecting purely for
  novelty yields a sparse star graph; selecting purely for density yields one
  mega-hub. Rank by MARGINAL BRIDGE CONTRIBUTION so the merged graph is both
  connected and distributed.

Protected sets (always included when present in DB; exempt from NCMEC rule):
  - selected_200_ids.txt  (stratified OG 200 — Patterns compare chip pool; read-only)
  - all regex AI-CSAM / Gen-AI cases (NCMEC allowed for AI pin)

Buckets (deduplicated union; cases may appear in multiple buckets):
  1. ai_pin       — ALL regex AI cases (NCMEC allowed here only)
  2. seed_200     — all IDs from selected_200_ids.txt present in DB
  3. bridge       — 250 cases maximizing MARGINAL novel bridge URIs
  4. reinforce    — 150 cases that touch an ALREADY-selected bridge shared by
                    >=2 cases, raising bridge DEGREE (spine-rich picks)
  5. platform     — set-cover over named platform groups, capped at 120
  6. rich         — 100 highest feature/spine density
  7. severe       — 80 highest severity
  8. distinct     — 100 maximally unlike already-picked
  9. source_diverse_fill — top up to 1000, NON-NCMEC, spine-rich preference

QUALITY GATE (fill + optional buckets; ai_pin and seed_200 exempt):
  >=1 Event AND >=1 Role (Victim/Offender proxy) AND >=1 platform/agency bridge.

BRIDGE-DEGREE BALANCE:
  No bridge URI touched by >25% of selected cases; cap during reinforce/fill.

Outputs:
  ontology/pools/big_bang_ids.txt
  ontology/big_bang_cases.json

Does NOT modify ontology/pools/selected_200_ids.txt (maintained by select_cases.py).

Usage:
  python ontology/pools/big_bang.py --target 1000
  python ontology/pools/big_bang.py --boom   # TEMP: fill to 3000 — non-NCMEC first, NCMEC last
  python ontology/pools/eval_big_bang_graphs.py   # then generate graph_output + SHACL eval
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY = REPO_ROOT / "ontology"
GRAPH_DIR = ONTOLOGY / "graph_output"
PATTERN_LAYER = REPO_ROOT / "src/Processing Layer/Pattern Processing Layer"

sys.path.insert(0, str(ONTOLOGY / "pipeline"))
sys.path.insert(0, str(PATTERN_LAYER))

from ai_extraction_patterns import AI_CSAM_TOPIC_RE, GEN_AI_TOOL_RE  # noqa: E402
from noise_filter import NoiseFilter  # noqa: E402
from select_cases import (  # noqa: E402
    parse_ef,
    parse_list,
    score_density,
    score_richness,
    score_severity,
)

TARGET_TOTAL = 1000
BOOM_TARGET = 3000  # TEMP local graph explore (~3000 JSON-LD graphs)
SEED_200 = ONTOLOGY / "pools" / "selected_200_ids.txt"

# Bucket quotas (v2)
N_BRIDGE = 250
N_REINFORCE = 150
N_PLATFORM_MAX = 120
N_RICH = 100
N_SEVERE = 80
N_DISTINCT = 100
MAX_PER_SOURCE_DEFAULT = 80
MAX_BRIDGE_SHARE = 0.25  # no single bridge > 25% of selection

EXCLUDE_NCMEC_EXCEPT_AI = True
GENERIC_TOPICS = frozenset(
    {"possession", "csam", "production", "distribution", "online_only", "unknown"}
)

PLATFORM_GROUPS: Dict[str, Dict[str, Any]] = {
    "discord": {
        "labels": ["Discord"],
        "text_re": re.compile(r"\bdiscord\b", re.I),
    },
    "kik": {
        "labels": ["Kik"],
        "text_re": re.compile(r"\bkik\b", re.I),
    },
    "facebook": {
        "labels": ["Facebook", "Facebook Messenger"],
        "text_re": re.compile(r"\bfacebook\b|\bFB\s+Messenger\b", re.I),
    },
    "instagram": {
        "labels": ["Instagram"],
        "text_re": re.compile(r"\binstagram\b", re.I),
    },
    "dropbox": {
        "labels": ["Dropbox"],
        "text_re": re.compile(r"\bdropbox\b", re.I),
    },
    "p2p": {
        "labels": ["BitTorrent", "LimeWire", "Kazaa", "Gigatribe"],
        "text_re": re.compile(
            r"\b(?:p2p|peer[- ]to[- ]peer|bittorrent|limewire|kazaa|emule|gnutella|"
            r"file[- ]sharing\s+network|gigatribe)\b",
            re.I,
        ),
        "ef_field": "p2p_clients",
    },
    "social_media": {
        "labels": ["social media"],
        "text_re": re.compile(r"\bsocial\s+media\b", re.I),
    },
    "chat": {
        "labels": ["chat", "Snapchat", "WhatsApp", "Telegram", "Skype", "Kik"],
        "text_re": re.compile(
            r"(?<![Rr]elay\s)\bchat(?:ting|ted|s)?\b|\bchat\s+app\b|\bchat\s+room\b|"
            r"\bchatroom\b|\bmessaging\s+app\b|\binstant\s+messag",
            re.I,
        ),
    },
}


def case_text(case: Dict[str, Any]) -> str:
    if case.get("case_text"):
        return str(case["case_text"])
    raw = case.get("raw_data")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return ""
    if isinstance(raw, dict):
        return str(raw.get("case_text") or "")
    return ""


def is_ai_case(text: str) -> bool:
    if not text:
        return False
    return bool(AI_CSAM_TOPIC_RE.search(text) or GEN_AI_TOOL_RE.search(text))


def is_ncmec(case: Dict[str, Any]) -> bool:
    return (case.get("source") or "").strip().upper() == "NCMEC"


def is_substantive(case: Dict[str, Any], nf: NoiseFilter) -> bool:
    noisy, _ = nf.is_noisy_case(case)
    return not noisy


def eligible_for_bucket(
    cid: str,
    case: Dict[str, Any],
    ai_pinned: Set[str],
    nf: NoiseFilter,
) -> bool:
    if cid in ai_pinned:
        return True
    if EXCLUDE_NCMEC_EXCEPT_AI and is_ncmec(case):
        return False
    return is_substantive(case, nf)


def matches_platform_group(case: Dict[str, Any], text: str, group: str) -> bool:
    spec = PLATFORM_GROUPS[group]
    labels = set(spec.get("labels") or [])
    plat_labels = set(parse_list(case.get("platforms_used")))
    if labels & plat_labels:
        return True
    ef_field = spec.get("ef_field")
    if ef_field:
        ef = parse_ef(case.get("extracted_features"))
        if parse_list(ef.get(ef_field)):
            return True
    text_re = spec.get("text_re")
    return bool(text_re and text_re.search(text))


def platform_groups_for_case(case: Dict[str, Any], text: str) -> Set[str]:
    return {g for g in PLATFORM_GROUPS if matches_platform_group(case, text, g)}


def predicted_bridges(case: Dict[str, Any]) -> Set[str]:
    ef = parse_ef(case.get("extracted_features"))
    out: Set[str] = set()
    for plat in parse_list(case.get("platforms_used")) or parse_list(ef.get("platforms_used")):
        slug = re.sub(r"[^a-z0-9]+", "-", plat.lower()).strip("-")
        if slug:
            out.add(f"https://w3id.org/caselinker/resource/platform/{slug}")
    agencies = ef.get("agencies_involved") or []
    if isinstance(agencies, list):
        for ag in agencies:
            if isinstance(ag, str):
                slug = re.sub(r"[^a-z0-9]+", "-", ag.lower()).strip("-")
                if slug:
                    out.add(f"https://w3id.org/caselinker/resource/agency/{slug}")
    return out


def spine_node_counts(case: Dict[str, Any]) -> Tuple[int, int, int]:
    """Proxy Event count, Role count (victim+offender), bridge count from DB fields."""
    topics = [
        t
        for t in parse_list(case.get("case_topics"))
        if t.lower() not in GENERIC_TOPICS
    ]
    n_events = min(len(topics), 6)
    if parse_list(case.get("severity_indicators")):
        n_events = max(n_events, 1)
    ef = parse_ef(case.get("extracted_features"))
    if ef.get("investigation_type") and str(ef.get("investigation_type")).lower() != "unknown":
        n_events = max(n_events, 1)

    n_roles = 0
    try:
        if case.get("victim_count") and int(case["victim_count"]) > 0:
            n_roles += 1
    except (TypeError, ValueError):
        pass
    try:
        if case.get("perpetrator_count") and int(case["perpetrator_count"]) > 0:
            n_roles += 1
    except (TypeError, ValueError):
        pass
    if case.get("relationship_to_victim") and str(case["relationship_to_victim"]).strip():
        n_roles = max(n_roles, 1)
    topic_set = {t.lower() for t in parse_list(case.get("case_topics"))}
    if topic_set & {"grooming", "sextortion", "hands_on", "trafficking", "production", "solicitation"}:
        n_roles = max(n_roles, 1)
    if any("offender" in t.lower() or "perpetrator" in t.lower() for t in topics):
        n_roles = max(n_roles, 2)

    n_bridges = len(predicted_bridges(case))
    return n_events, n_roles, n_bridges


def passes_quality_gate(case: Dict[str, Any]) -> bool:
    n_events, n_roles, n_bridges = spine_node_counts(case)
    return n_events >= 1 and n_roles >= 1 and n_bridges >= 1


def spine_richness_score(case: Dict[str, Any]) -> int:
    e, r, b = spine_node_counts(case)
    return e + r + min(b, 5) + score_richness(case)


def case_fingerprint(case: Dict[str, Any]) -> FrozenSet[str]:
    ef = parse_ef(case.get("extracted_features"))
    topics = [t for t in parse_list(case.get("case_topics")) if t.lower() not in GENERIC_TOPICS]
    parts = [
        f"src:{case.get('source') or '?'}",
        *[f"topic:{t}" for t in sorted(topics)[:8]],
        *[f"plat:{p}" for p in sorted(parse_list(case.get("platforms_used")))[:8]],
    ]
    inv = ef.get("investigation_type")
    if inv and str(inv).strip().lower() not in ("unknown", ""):
        parts.append(f"inv:{inv}")
    p2p = parse_list(ef.get("p2p_clients"))
    if p2p:
        parts.append(f"p2p:{','.join(sorted(p2p)[:4])}")
    return frozenset(parts)


def fingerprint_distance(a: FrozenSet[str], b: FrozenSet[str]) -> float:
    if not a and not b:
        return 0.0
    union = len(a | b)
    if union == 0:
        return 0.0
    return 1.0 - (len(a & b) / union)


def load_seed_200() -> List[str]:
    if not SEED_200.is_file():
        print(f"WARN: {SEED_200} missing — run: python ontology/pools/select_cases.py --no-graphs")
        return []
    return [ln.strip() for ln in SEED_200.read_text().splitlines() if ln.strip()]


def source_cap_table(
    cases: Dict[str, Dict[str, Any]],
    target: int,
    hard_max: int,
) -> Dict[str, int]:
    corpus = Counter(c.get("source") or "?" for c in cases.values())
    total = sum(corpus.values()) or 1
    caps: Dict[str, int] = {}
    for src, cnt in corpus.items():
        if src.upper() == "NCMEC":
            caps[src] = 0  # NCMEC only via ai_pin bucket
            continue
        share = max(1, round(target * (cnt / total)))
        caps[src] = min(hard_max, max(3, share))
    return caps


class BridgeTracker:
    """Track bridge URI → case ids for marginal yield + mega-hub cap."""

    def __init__(self, max_share: float) -> None:
        self.case_bridges: Dict[str, Set[str]] = {}
        self.bridge_cases: Dict[str, Set[str]] = defaultdict(set)
        self.max_share = max_share

    def n_selected(self) -> int:
        return len(self.case_bridges)

    def max_allowed_degree(self) -> int:
        n = max(1, self.n_selected())
        return max(2, int(n * self.max_share))

    def add(self, cid: str, bridges: Set[str]) -> None:
        self.case_bridges[cid] = set(bridges)
        for b in bridges:
            self.bridge_cases[b].add(cid)

    def remove(self, cid: str) -> None:
        bridges = self.case_bridges.pop(cid, set())
        for b in bridges:
            self.bridge_cases[b].discard(cid)
            if not self.bridge_cases[b]:
                del self.bridge_cases[b]

    def novel_bridges(self, bridges: Set[str]) -> Set[str]:
        return {b for b in bridges if b not in self.bridge_cases}

    def reinforcing_bridges(self, bridges: Set[str], min_degree: int = 2) -> Set[str]:
        return {
            b
            for b in bridges
            if len(self.bridge_cases.get(b, set())) >= min_degree
        }

    def would_exceed_cap(self, cid: str, bridges: Set[str]) -> bool:
        cap = self.max_allowed_degree()
        n = self.n_selected()
        if cid in self.case_bridges:
            n -= 1
        for b in bridges:
            deg = len(self.bridge_cases.get(b, set()))
            if cid in self.bridge_cases.get(b, set()):
                deg -= 1
            if deg + 1 > cap:
                return True
        return False

    def degree_histogram(self) -> Dict[int, int]:
        hist: Counter = Counter()
        for cases in self.bridge_cases.values():
            hist[len(cases)] += 1
        return dict(sorted(hist.items()))

    def top_bridges(self, n: int = 20) -> List[Dict[str, Any]]:
        ranked = sorted(
            self.bridge_cases.items(),
            key=lambda x: (-len(x[1]), x[0]),
        )[:n]
        return [{"uri": u, "degree": len(cs)} for u, cs in ranked]


def _picked_meta(case: Dict[str, Any], cid: str) -> Dict[str, Any]:
    return {
        "case_id": cid,
        "source": case.get("source"),
        "buckets": [],
        "rationales": {},
        "density": score_density(case),
        "richness": score_richness(case),
        "severity": score_severity(case),
        "spine": dict(zip(("events", "roles", "bridges"), spine_node_counts(case))),
    }


def _write_selection_output(
    *,
    picked: Dict[str, Dict[str, Any]],
    target_n: int,
    mode: str,
    cases: Dict[str, Dict[str, Any]],
    substantive: List[str],
    ai_ids: List[str],
    n_seed: int,
    n_seed_missing: int,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    ids = sorted(picked.keys())
    out: Dict[str, Any] = {
        "mode": mode,
        "n_selected": len(ids),
        "n_target": target_n,
        "n_corpus": len(cases),
        "n_substantive_pool": len(substantive),
        "n_seed_200": n_seed,
        "compare_pool_file": "ontology/pools/selected_200_ids.txt",
        "n_seed_200_missing_from_db": n_seed_missing,
        "ai_pin": {
            "n_union": len(ai_ids),
            "n_ncmec": sum(1 for c in ai_ids if is_ncmec(cases[c])),
        },
        "bucket_counts": dict(
            Counter(b for meta in picked.values() for b in meta["buckets"])
        ),
        "source_distribution": dict(Counter(picked[c]["source"] for c in ids)),
        "selection": [picked[c] for c in ids],
    }
    if extra:
        out.update(extra)
    (ONTOLOGY / "pools" / "big_bang_ids.txt").write_text("\n".join(ids) + "\n")
    (ONTOLOGY / "big_bang_cases.json").write_text(json.dumps(out, indent=2))
    print(f"\nWrote {len(ids)} cases → big_bang_ids.txt (target {target_n}, mode={mode})")
    print("Bucket counts:", out["bucket_counts"])
    print("Top sources:", Counter(picked[c]["source"] for c in ids).most_common(12))


def run_boom_selection(
    cases: Dict[str, Dict[str, Any]],
    *,
    target_n: int,
    ai_ids: List[str],
    nf: NoiseFilter,
) -> None:
    """
    TEMP chill path: reach ``target_n`` (default 3000) with minimal logic.
    Order: seed_200 → ai_pin → all other non-noisy non-NCMEC → NCMEC remainder.
    No bridge buckets, quality gate, or hub trim.
    """
    ai_pinned = set(ai_ids)
    picked: Dict[str, Dict[str, Any]] = {}

    def add(cid: str, bucket: str, rationale: str) -> None:
        if cid not in cases:
            return
        if cid not in picked:
            picked[cid] = _picked_meta(cases[cid], cid)
        if bucket not in picked[cid]["buckets"]:
            picked[cid]["buckets"].append(bucket)
        picked[cid]["rationales"][bucket] = rationale

    seed_ids = load_seed_200()
    n_seed = n_seed_missing = 0
    for cid in seed_ids:
        if cid not in cases:
            n_seed_missing += 1
            continue
        add(cid, "seed_200", "compare pool (selected_200_ids.txt)")
        n_seed += 1
    print(f"Seed 200: {n_seed}/{len(seed_ids)}", flush=True)

    for cid in ai_ids:
        add(cid, "ai_pin", "mandatory AI pin")

    non_ncmec: List[str] = []
    ncmec_pool: List[str] = []
    noisy_skip = 0
    for cid, c in cases.items():
        if cid in picked:
            continue
        noisy, _ = nf.is_noisy_case(c)
        if noisy and cid not in ai_pinned:
            noisy_skip += 1
            continue
        if is_ncmec(c):
            ncmec_pool.append(cid)
        else:
            non_ncmec.append(cid)

    non_ncmec.sort(key=lambda c: (-spine_richness_score(cases[c]), -score_density(cases[c]), c))
    ncmec_pool.sort(key=lambda c: (-spine_richness_score(cases[c]), -score_density(cases[c]), c))

    n_non = 0
    for cid in non_ncmec:
        if len(picked) >= target_n:
            break
        add(cid, "non_ncmec_fill", "non-NCMEC preferred fill")
        n_non += 1

    n_ncmec = 0
    for cid in ncmec_pool:
        if len(picked) >= target_n:
            break
        add(cid, "ncmec_fill", "NCMEC tail fill to target")
        n_ncmec += 1

    print(
        f"BOOM chill fill: target={target_n} selected={len(picked)} "
        f"(non_ncmec={n_non}, ncmec_tail={n_ncmec}, noisy_skipped={noisy_skip})",
        flush=True,
    )
    if len(picked) < target_n:
        print(
            f"WARN: only {len(picked)} cases available (wanted {target_n})",
            flush=True,
        )

    _write_selection_output(
        picked=picked,
        target_n=target_n,
        mode="boom",
        cases=cases,
        substantive=non_ncmec + ncmec_pool,
        ai_ids=ai_ids,
        n_seed=n_seed,
        n_seed_missing=n_seed_missing,
        extra={
            "boom_strategy": "seed_200 + ai_pin + non_ncmec_fill + ncmec_fill",
            "n_non_ncmec_fill": n_non,
            "n_ncmec_fill": n_ncmec,
            "n_noisy_skipped": noisy_skip,
        },
    )


def scale_opts_to_target(opts: Dict[str, int], target_n: int) -> Dict[str, int]:
    """Scale bucket quotas proportionally (1000-case demo baseline)."""
    scale = target_n / TARGET_TOTAL
    out = dict(opts)
    out["target"] = target_n
    for key in ("bridge", "reinforce", "platform_max", "rich", "severe", "distinct"):
        out[key] = max(1, round(opts[key] * scale))
    out["max_per_source"] = max(20, round(opts["max_per_source"] * scale))
    return out


def parse_args(argv: List[str]) -> Tuple[Dict[str, int], bool, Optional[str]]:
    opts: Dict[str, int] = {
        "target": TARGET_TOTAL,
        "bridge": N_BRIDGE,
        "reinforce": N_REINFORCE,
        "platform_max": N_PLATFORM_MAX,
        "rich": N_RICH,
        "severe": N_SEVERE,
        "distinct": N_DISTINCT,
        "max_per_source": MAX_PER_SOURCE_DEFAULT,
    }
    boom = False
    db: Optional[str] = None
    i = 0
    while i < len(argv):
        if argv[i] == "--boom":
            boom = True
            i += 1
        elif argv[i] == "--target" and i + 1 < len(argv):
            opts["target"] = int(argv[i + 1])
            i += 2
        elif argv[i] == "--bridge" and i + 1 < len(argv):
            opts["bridge"] = int(argv[i + 1])
            i += 2
        elif argv[i] == "--reinforce" and i + 1 < len(argv):
            opts["reinforce"] = int(argv[i + 1])
            i += 2
        elif argv[i] == "--db" and i + 1 < len(argv):
            db = argv[i + 1]
            i += 2
        else:
            i += 1
    return opts, boom, db


def main() -> None:
    opts, boom, db_arg = parse_args(sys.argv[1:])
    nf = NoiseFilter()
    quality_gate_rejected = 0
    ncmec_excluded = 0

    db_path = Path(db_arg) if db_arg else REPO_ROOT / "caselinker.db"
    if not db_path.is_file():
        print(f"ERROR: {db_path} not found — run ingest first.")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    cols = [c[1] for c in conn.execute("PRAGMA table_info(cases)").fetchall()]
    cases: Dict[str, Dict[str, Any]] = {
        dict(zip(cols, row))["id"]: dict(zip(cols, row))
        for row in conn.execute("SELECT * FROM cases")
    }
    conn.close()

    text_by_id: Dict[str, str] = {cid: case_text(c) for cid, c in cases.items()}
    # One pass. Bucket scans used to re-parse features inside O(pool × picked) loops.
    bridge_by_id: Dict[str, Set[str]] = {}
    spine_by_id: Dict[str, Tuple[int, int, int]] = {}
    density_by_id: Dict[str, int] = {}
    richness_by_id: Dict[str, int] = {}
    severity_by_id: Dict[str, int] = {}
    fp_by_id: Dict[str, FrozenSet[str]] = {}
    groups_by_id: Dict[str, Set[str]] = {}
    spine_rich_by_id: Dict[str, int] = {}
    quality_by_id: Dict[str, bool] = {}
    for cid, c in cases.items():
        spine = spine_node_counts(c)
        rich = score_richness(c)
        e, r, b = spine
        spine_by_id[cid] = spine
        bridge_by_id[cid] = predicted_bridges(c)
        density_by_id[cid] = score_density(c)
        richness_by_id[cid] = rich
        severity_by_id[cid] = score_severity(c)
        fp_by_id[cid] = case_fingerprint(c)
        groups_by_id[cid] = platform_groups_for_case(c, text_by_id[cid])
        spine_rich_by_id[cid] = e + r + min(b, 5) + rich
        quality_by_id[cid] = e >= 1 and r >= 1 and b >= 1
    ai_ids = sorted(cid for cid, t in text_by_id.items() if is_ai_case(t))
    ai_pinned = set(ai_ids)

    print(f"Corpus: {len(cases)} cases — classifying substantive pool…", flush=True)
    substantive: List[str] = []
    noisy_cache: Dict[str, bool] = {}
    for cid, c in cases.items():
        if is_ncmec(c) and cid not in ai_pinned:
            continue
        if cid not in noisy_cache:
            noisy_cache[cid], _ = nf.is_noisy_case(c)
        if noisy_cache[cid] and cid not in ai_pinned:
            continue
        substantive.append(cid)
    print(f"Substantive pool (non-noisy, NCMEC only if AI): {len(substantive)}", flush=True)
    print(f"AI pin set: {len(ai_ids)} (NCMEC in AI: {sum(1 for c in ai_ids if is_ncmec(cases[c]))})")

    if boom:
        boom_target = opts["target"] if opts["target"] != TARGET_TOTAL else BOOM_TARGET
        print(f"BOOM mode (chill): fill to {boom_target}, non-NCMEC first then NCMEC", flush=True)
        run_boom_selection(cases, target_n=boom_target, ai_ids=ai_ids, nf=nf)
        return

    picked: Dict[str, Dict[str, Any]] = {}
    tracker = BridgeTracker(MAX_BRIDGE_SHARE)

    def is_protected(cid: str) -> bool:
        buckets = picked.get(cid, {}).get("buckets", [])
        return "ai_pin" in buckets or "seed_200" in buckets

    def record(cid: str, bucket: str, rationale: str, **extra: Any) -> None:
        c = cases[cid]
        if cid not in picked:
            picked[cid] = {
                "case_id": cid,
                "source": c.get("source"),
                "buckets": [],
                "rationales": {},
                "density": score_density(c),
                "richness": score_richness(c),
                "severity": score_severity(c),
                "spine": dict(zip(("events", "roles", "bridges"), spine_node_counts(c))),
            }
        if bucket not in picked[cid]["buckets"]:
            picked[cid]["buckets"].append(bucket)
        picked[cid]["rationales"][bucket] = rationale
        for k, v in extra.items():
            picked[cid][k] = v
        if cid not in tracker.case_bridges:
            tracker.add(cid, bridge_by_id[cid])

    def try_admit(
        cid: str,
        bucket: str,
        rationale: str,
        *,
        quality: bool = True,
        cap_check: bool = True,
    ) -> bool:
        nonlocal quality_gate_rejected, ncmec_excluded
        case = cases[cid]
        if cid in picked:
            record(cid, bucket, rationale)
            return True
        if not eligible_for_bucket(cid, case, ai_pinned, nf):
            if is_ncmec(case) and cid not in ai_pinned:
                ncmec_excluded += 1
            return False
        if quality and not is_protected(cid) and bucket not in ("ai_pin", "seed_200"):
            if not quality_by_id[cid]:
                quality_gate_rejected += 1
                return False
        bridges = bridge_by_id[cid]
        if cap_check and tracker.would_exceed_cap(cid, bridges):
            return False
        record(cid, bucket, rationale)
        return True

    # --- seed_200 (read-only compare pool; never written by this script) ---
    seed_ids = load_seed_200()
    n_seed = 0
    n_seed_missing = 0
    for cid in seed_ids:
        if cid not in cases:
            n_seed_missing += 1
            continue
        record(cid, "seed_200", "stratified compare pool (selected_200_ids.txt)")
        n_seed += 1
    print(
        f"Seed 200: pinned {n_seed}/{len(seed_ids)} from selected_200_ids.txt"
        + (f" ({n_seed_missing} not in DB)" if n_seed_missing else ""),
        flush=True,
    )

    # --- ai_pin ---
    for cid in ai_ids:
        flags = []
        if AI_CSAM_TOPIC_RE.search(text_by_id[cid] or ""):
            flags.append("ai_csam")
        if GEN_AI_TOOL_RE.search(text_by_id[cid] or ""):
            flags.append("gen_ai_tool")
        note = " NCMEC" if is_ncmec(cases[cid]) else ""
        try_admit(
            cid,
            "ai_pin",
            f"mandatory AI ({', '.join(flags)}){note}",
            quality=False,
            cap_check=False,
        )

    # --- platform set-cover (cap 120) ---
    group_to_cases: Dict[str, List[str]] = defaultdict(list)
    for cid in substantive:
        for g in groups_by_id[cid]:
            group_to_cases[g].append(cid)

    uncovered = set(PLATFORM_GROUPS.keys())
    for cid in picked:
        uncovered -= groups_by_id[cid]

    platform_n = 0
    while uncovered and platform_n < opts["platform_max"]:
        best_cid: Optional[str] = None
        best_covers: Set[str] = set()
        best_key = (-1, -1, -1)
        for cid in substantive:
            if cid in picked:
                continue
            covers = groups_by_id[cid] & uncovered
            if not covers:
                continue
            key = (
                len(covers),
                spine_rich_by_id[cid],
                density_by_id[cid],
            )
            if key > best_key:
                best_key = key
                best_cid = cid
                best_covers = covers
        if best_cid is None:
            break
        if try_admit(
            best_cid,
            "platform",
            f"covers={sorted(best_covers)}",
            cap_check=True,
        ):
            uncovered -= best_covers
            platform_n += 1
    print(f"Platform bucket: {platform_n}", flush=True)

    # --- bridge (marginal novel URIs) ---
    bridge_n = 0
    bridge_pool = [c for c in substantive if c not in picked]
    while bridge_n < opts["bridge"] and bridge_pool:
        best: Optional[Tuple[int, int, str]] = None
        for cid in bridge_pool:
            novel = tracker.novel_bridges(bridge_by_id[cid])
            if not novel and bridge_n > 0:
                continue
            key = (len(novel), spine_rich_by_id[cid], cid)
            if best is None or key > best:
                best = key
        if best is None or (best[0] < 1 and bridge_n > 0):
            break
        cid = best[2]
        novel = tracker.novel_bridges(bridge_by_id[cid])
        if try_admit(cid, "bridge", f"novel_bridges={len(novel)} sample={list(novel)[:3]}"):
            bridge_n += 1
            bridge_pool = [c for c in bridge_pool if c != cid and c not in picked]
        else:
            bridge_pool = [c for c in bridge_pool if c != cid]
    print(f"Bridge bucket: {bridge_n}", flush=True)

    # --- reinforce (touch bridge with degree >= 2) ---
    reinforce_n = 0
    reinforce_rank = sorted(
        [c for c in substantive if c not in picked],
        key=lambda c: (
            -len(tracker.reinforcing_bridges(bridge_by_id[c], min_degree=2)),
            spine_rich_by_id[c],
            richness_by_id[c],
        ),
        reverse=True,
    )
    for cid in reinforce_rank:
        if reinforce_n >= opts["reinforce"]:
            break
        ref = tracker.reinforcing_bridges(bridge_by_id[cid], min_degree=2)
        if len(ref) < 1:
            continue
        if try_admit(
            cid,
            "reinforce",
            f"reinforces={len(ref)} bridges deg>=2 sample={list(ref)[:3]}",
        ):
            reinforce_n += 1
    print(f"Reinforce bucket: {reinforce_n}", flush=True)

    # --- rich ---
    rich_n = 0
    for cid in sorted(
        substantive,
        key=lambda c: (-spine_rich_by_id[c], -density_by_id[c], c),
    ):
        if rich_n >= opts["rich"]:
            break
        if cid in picked:
            continue
        if try_admit(cid, "rich", f"spine_richness={spine_rich_by_id[cid]}"):
            rich_n += 1
    print(f"Rich bucket: {rich_n}", flush=True)

    # --- severe ---
    sev_n = 0
    for cid in sorted(
        substantive,
        key=lambda c: (-severity_by_id[c], -spine_rich_by_id[c], c),
    ):
        if sev_n >= opts["severe"]:
            break
        if cid in picked:
            continue
        if try_admit(cid, "severe", f"severity={score_severity(cases[cid])}"):
            sev_n += 1
    print(f"Severe bucket: {sev_n}", flush=True)

    # --- distinct ---
    picked_fps = [fp_by_id[cid] for cid in picked]
    distinct_n = 0
    distinct_rank = sorted(
        substantive,
        key=lambda c: (
            min(
                (fingerprint_distance(fp_by_id[c], p) for p in picked_fps),
                default=1.0,
            ),
            richness_by_id[c],
            c,
        ),
        reverse=True,
    )
    for cid in distinct_rank:
        if distinct_n >= opts["distinct"]:
            break
        if cid in picked:
            continue
        fp = fp_by_id[cid]
        dist = min(
            (fingerprint_distance(fp, p) for p in picked_fps),
            default=1.0,
        )
        if try_admit(cid, "distinct", f"min_fp_dist={dist:.2f}"):
            picked_fps.append(fp)
            distinct_n += 1
    print(f"Distinct bucket: {distinct_n}", flush=True)

    # --- spine median for fill preference ---
    non_ncmec_spine = [
        sum(spine_by_id[c][:2])
        for c in substantive
        if not is_ncmec(cases[c])
    ]
    corpus_median_spine = (
        sorted(non_ncmec_spine)[len(non_ncmec_spine) // 2] if non_ncmec_spine else 2
    )

    # --- source_diverse_fill ---
    target_n = opts["target"]
    caps = source_cap_table(cases, target_n, opts["max_per_source"])
    per_src = Counter(picked[c]["source"] for c in picked)
    corpus_src = Counter(c.get("source") or "?" for c in cases.values())
    fill_n = 0

    def fill_key(cid: str) -> Tuple[float, int, int, str]:
        src = cases[cid].get("source") or "?"
        picked_n = per_src.get(src, 0)
        cap = caps.get(src, 50)
        headroom = cap - picked_n
        spine_sum = sum(spine_by_id[cid][:2])
        spine_bonus = 1 if spine_sum >= corpus_median_spine else 0
        rarity = (1.0 / corpus_src.get(src, 1)) * (headroom / max(1, cap))
        bridges = bridge_by_id[cid]
        marginal = len(tracker.novel_bridges(bridges)) + len(
            tracker.reinforcing_bridges(bridges, min_degree=1)
        )
        return (
            rarity if headroom > 0 else -1.0,
            marginal,
            spine_bonus,
            spine_rich_by_id[cid],
            cid,
        )

    fill_pool = [c for c in substantive if c not in picked]
    while len(picked) < target_n and fill_pool:
        ranked = sorted(fill_pool, key=fill_key, reverse=True)
        admitted = False
        for cid in ranked:
            if try_admit(
                cid,
                "source_diverse_fill",
                f"fill src={cases[cid].get('source')} marginal_bridge_yield",
            ):
                per_src[cases[cid].get("source") or "?"] = (
                    per_src.get(cases[cid].get("source") or "?", 0) + 1
                )
                fill_n += 1
                fill_pool = [c for c in fill_pool if c != cid]
                admitted = True
                break
            if fill_key(cid)[0] < 0:
                continue
        if not admitted:
            for cid in ranked[:500]:
                if cid in picked:
                    continue
                if try_admit(
                    cid,
                    "source_diverse_fill",
                    "fill relaxed (source cap)",
                    quality=False,
                ):
                    fill_n += 1
                    break
            else:
                break
    print(f"Source-diverse fill: {fill_n} (total {len(picked)} / {target_n})", flush=True)

    # --- post-trim mega-hubs (non-protected only) ---
    cap = tracker.max_allowed_degree()
    trimmed = 0
    changed = True
    while changed:
        changed = False
        over = [b for b, cs in tracker.bridge_cases.items() if len(cs) > cap]
        if not over:
            break
        hub = max(over, key=lambda b: len(tracker.bridge_cases[b]))
        victims = [
            c
            for c in tracker.bridge_cases[hub]
            if not is_protected(c) and "source_diverse_fill" in picked[c]["buckets"]
        ]
        if not victims:
            victims = [
                c
                for c in tracker.bridge_cases[hub]
                if not is_protected(c) and "reinforce" in picked[c]["buckets"]
            ]
        if not victims:
            break
        drop = min(victims, key=lambda c: spine_richness_score(cases[c]))
        tracker.remove(drop)
        del picked[drop]
        trimmed += 1
        changed = True
    if trimmed:
        print(f"Mega-hub trim: removed {trimmed} non-protected cases")

    ids = sorted(picked.keys())
    platform_coverage: Dict[str, int] = {}
    for g in PLATFORM_GROUPS:
        platform_coverage[g] = sum(
            1 for cid in ids if g in groups_by_id[cid]
        )

    bucket_spine: Dict[str, List[int]] = defaultdict(list)
    for cid in ids:
        primary = picked[cid]["buckets"][0]
        bucket_spine[primary].append(sum(spine_by_id[cid][:2]))

    def median(vals: List[int]) -> float:
        if not vals:
            return 0.0
        s = sorted(vals)
        return float(s[len(s) // 2])

    median_spine_nodes = {k: median(v) for k, v in bucket_spine.items()}

    _write_selection_output(
        picked=picked,
        target_n=target_n,
        mode="default",
        cases=cases,
        substantive=substantive,
        ai_ids=ai_ids,
        n_seed=n_seed,
        n_seed_missing=n_seed_missing,
        extra={
            "ncmec_excluded": ncmec_excluded,
            "quality_gate_rejected": quality_gate_rejected,
            "quotas": opts,
            "bridge_degree_histogram": tracker.degree_histogram(),
            "top_bridges": tracker.top_bridges(20),
            "median_spine_nodes": median_spine_nodes,
            "corpus_median_spine_events_roles": corpus_median_spine,
            "max_bridge_degree_cap": cap,
            "platform_group_coverage_in_selection": platform_coverage,
        },
    )
    print("Bridge degree histogram (cases_touched → n_bridges):", tracker.degree_histogram())
    print("Top bridges:", tracker.top_bridges(5))
    print("Median spine (events+roles) by bucket:", median_spine_nodes)


if __name__ == "__main__":
    main()
