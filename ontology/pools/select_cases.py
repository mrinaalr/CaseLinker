#!/usr/bin/env python3
"""
Stratified selection of 200 cases for the CAC corpus.

Tiers (deduplicated to 200 unique case ids):
  T0  20  linked_case_id from data/case_studies.json (published)
  T1  40  highest richness + feature density
  T2  40  highest severity score
  T3  50  platform/technology coverage (technology-revolver label universe;
          prefer non-noise / signal mentions)
  T4  50  underrepresented sources (not yet in selection; severe + dense)

Outputs:
  ontology/selected_200_cases.json
  ontology/pools/selected_200_ids.txt
  ontology/excluded_cases.json  (noisy-case registry via NoiseFilter)

Graphs (default on run):
  ontology/graph_output/{case_id}.jsonld + .ttl  (staging — not loaded by Patterns viz)

Usage:
  python ontology/select_200.py
  python ontology/select_200.py --no-graphs
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY = REPO_ROOT / "ontology"
sys.path.insert(0, str(ONTOLOGY / "pipeline"))

from noise_filter import NoiseFilter  # noqa: E402

TARGET = 200
N_CASE_STUDIES = 20
N_RICH = 40
N_SEVERE = 40
N_PLATFORM = 50
N_UNDERREP = 50

TECH_BUCKETS = (
    "platforms_used",
    "investigation_technology",
    "anonymization_network",
    "p2p_clients",
)

CASE_STUDIES_PATH = REPO_ROOT / "data" / "case_studies.json"
GRAPH_DIR = ONTOLOGY / "graph_output"


def parse_list(s: Any) -> List[str]:
    if s is None:
        return []
    if isinstance(s, list):
        return [str(x).strip() for x in s if str(x).strip()]
    if isinstance(s, str):
        s = s.strip()
        if not s:
            return []
        try:
            v = json.loads(s)
            return [str(x) for x in v] if isinstance(v, list) else []
        except json.JSONDecodeError:
            return [s]
    return []


def parse_ef(blob: Any) -> Dict[str, Any]:
    if isinstance(blob, dict):
        return blob
    if isinstance(blob, str):
        try:
            return json.loads(blob)
        except json.JSONDecodeError:
            return {}
    return {}


def tech_labels_for_case(case: Dict[str, Any]) -> Dict[str, Set[str]]:
    """Labels per revolver bucket (same fields as /api/technology-revolver)."""
    out: Dict[str, Set[str]] = defaultdict(set)
    ef = parse_ef(case.get("extracted_features"))
    for bucket in TECH_BUCKETS:
        labs = parse_list(case.get(bucket))
        if not labs and isinstance(ef, dict):
            labs = parse_list(ef.get(bucket))
        for lab in labs:
            if lab:
                out[bucket].add(lab)
    return out


def all_tech_labels(case: Dict[str, Any]) -> Set[str]:
    labs: Set[str] = set()
    for s in tech_labels_for_case(case).values():
        labs |= s
    return labs


def score_richness(case: Dict[str, Any]) -> int:
    ef = parse_ef(case.get("extracted_features"))
    platforms = parse_list(case.get("platforms_used"))
    topics = parse_list(case.get("case_topics"))
    severity = parse_list(case.get("severity_indicators"))
    agencies = ef.get("agencies_involved") or []
    if not isinstance(agencies, list):
        agencies = []
    inv_tech = ef.get("investigation_technology") or []
    if not isinstance(inv_tech, list):
        inv_tech = []
    p2p = ef.get("p2p_clients") or []
    if not isinstance(p2p, list):
        p2p = []
    anon = ef.get("anonymization_network") or []
    if not isinstance(anon, list):
        anon = []
    inv_type = ef.get("investigation_type")
    pros = ef.get("prosecution_outcome") or {}
    evidence = ef.get("evidence_volume") or {}

    rs = 0
    rs += min(len(platforms), 5)
    rs += min(len(topics), 4)
    rs += min(len(severity), 4)
    rs += min(len(agencies), 6)
    if inv_type and inv_type != "unknown":
        rs += 2
    if isinstance(pros, dict):
        if pros.get("booking_status"):
            rs += 1
        if pros.get("charges"):
            rs += 2
    try:
        if case.get("victim_count") and int(case["victim_count"]) > 0:
            rs += 1
    except (TypeError, ValueError):
        pass
    try:
        if case.get("perpetrator_count") and int(case["perpetrator_count"]) > 0:
            rs += 1
    except (TypeError, ValueError):
        pass
    if case.get("relationship_to_victim") and str(case["relationship_to_victim"]).strip():
        rs += 1
    if isinstance(evidence, dict) and any(v is not None for v in evidence.values()):
        rs += 1
    if inv_tech:
        rs += 2
    if p2p:
        rs += 3
    if anon:
        rs += 3
    return rs


def score_density(case: Dict[str, Any]) -> int:
    """Populated extracted_features + top-level list fields."""
    ef = parse_ef(case.get("extracted_features"))
    n = sum(
        1
        for v in ef.values()
        if v is not None and v != "" and v != {} and v != []
    )
    n += min(len(parse_list(case.get("platforms_used"))), 5)
    n += min(len(parse_list(case.get("case_topics"))), 4)
    n += min(len(parse_list(case.get("severity_indicators"))), 4)
    return n


def score_severity(case: Dict[str, Any]) -> int:
    severity = parse_list(case.get("severity_indicators"))
    topics = parse_list(case.get("case_topics"))
    sev_set = {s.lower() for s in severity}
    topic_set = {t.lower() for t in topics}
    ss = 0
    if "infant" in sev_set or "very_young" in sev_set:
        ss += 3
    if "under_12" in sev_set:
        ss += 2
    if "sexual_abuse" in sev_set:
        ss += 2
    if "multiple_perpetrators" in sev_set:
        ss += 2
    if "hands_on" in topic_set:
        ss += 3
    if "production" in topic_set:
        ss += 2
    try:
        vc = case.get("victim_count")
        if vc and int(vc) > 5 and int(vc) <= 200:
            ss += 2
        if vc and int(vc) > 10 and int(vc) <= 200:
            ss += 3
    except (TypeError, ValueError):
        pass
    return ss


def case_study_ids() -> List[str]:
    data = json.loads(CASE_STUDIES_PATH.read_text())
    ids: List[str] = []
    for study in data.get("case_studies") or []:
        if study.get("status") != "published":
            continue
        cid = study.get("linked_case_id") or study.get("id")
        if cid:
            ids.append(str(cid))
    return ids[:N_CASE_STUDIES]


def build_revolver_index(
    cases: Dict[str, Dict[str, Any]], nf: NoiseFilter
) -> Tuple[Dict[str, Set[str]], Dict[str, List[Tuple[str, int, bool]]]]:
    """
    label -> set(case_ids)
    label -> [(case_id, score, signal_ok), ...] sorted by score desc
    """
    label_to_cases: Dict[str, Set[str]] = defaultdict(set)
    for cid, case in cases.items():
        for lab in all_tech_labels(case):
            label_to_cases[lab].add(cid)

    label_ranked: Dict[str, List[Tuple[str, int, bool]]] = {}
    text_cache: Dict[str, str] = {}

    def case_text(cid: str) -> str:
        if cid not in text_cache:
            text_cache[cid] = nf.case_text(cases[cid])
        return text_cache[cid]

    for lab, cids in label_to_cases.items():
        ranked: List[Tuple[str, int, bool]] = []
        for cid in cids:
            case = cases[cid]
            buckets = tech_labels_for_case(case)
            in_platforms = lab in buckets.get("platforms_used", set())
            sig = (
                nf.is_platform_signal(case_text(cid), lab)
                if in_platforms
                else True
            )
            sc = score_richness(case) + score_severity(case) + (20 if sig else 0)
            ranked.append((cid, sc, sig))
        ranked.sort(key=lambda t: (-t[1], -int(t[2]), t[0]))
        label_ranked[lab] = ranked
    return dict(label_to_cases), label_ranked


def pick_platform_tier(
    cases: Dict[str, Dict[str, Any]],
    selected: Dict[str, Dict[str, Any]],
    label_ranked: Dict[str, List[Tuple[str, int, bool]]],
    all_labels: List[str],
    nf: NoiseFilter,
) -> Tuple[List[str], Set[str]]:
    """Greedy set cover: up to N_PLATFORM cases, prefer signal + rare labels."""
    uncovered = set(all_labels)
    picked: List[str] = []
    # Rare labels first (hardest to cover)
    labels_by_rarity = sorted(all_labels, key=lambda l: len(label_ranked.get(l, [])))

    while len(picked) < N_PLATFORM and uncovered:
        best_cid: Optional[str] = None
        best_key = (-1, -1, -1)
        best_covers: Set[str] = set()

        for cid, case in cases.items():
            if cid in selected or cid in picked:
                continue
            case_labels = all_tech_labels(case) & uncovered
            if not case_labels:
                continue
            text = nf.case_text(case)
            plat_set = tech_labels_for_case(case).get("platforms_used", set())
            signal_hits = sum(
                1
                for lab in case_labels
                if lab not in plat_set or nf.is_platform_signal(text, lab)
            )
            key = (
                len(case_labels),
                signal_hits,
                score_richness(case) + score_severity(case),
            )
            if key > best_key:
                best_key = key
                best_cid = cid
                best_covers = case_labels

        if best_cid is None:
            break
        picked.append(best_cid)
        uncovered -= best_covers

    # Fill remaining slots with high-signal platform-dense cases
    if len(picked) < N_PLATFORM:
        extras = sorted(
            [
                (cid, score_richness(cases[cid]) + score_severity(cases[cid]))
                for cid in cases
                if cid not in selected and cid not in picked and all_tech_labels(cases[cid])
            ],
            key=lambda t: -t[1],
        )
        for cid, _ in extras:
            if len(picked) >= N_PLATFORM:
                break
            picked.append(cid)

    return picked, uncovered


def pick_underrep_tier(
    cases: Dict[str, Dict[str, Any]],
    selected: Dict[str, Dict[str, Any]],
) -> List[str]:
    corpus_src = Counter(c.get("source") or "?" for c in cases.values())
    sel_src = Counter(selected[cid]["source"] for cid in selected)

    def underrep_priority(src: str) -> float:
        total = corpus_src.get(src, 0)
        if total == 0:
            return 0.0
        picked = sel_src.get(src, 0)
        return (1.0 / (1 + picked)) * (1.0 / max(1, total))

    candidates = [
        cid
        for cid in cases
        if cid not in selected and not NoiseFilter().is_noisy_case(cases[cid])[0]
    ]
    candidates.sort(
        key=lambda cid: (
            -underrep_priority(cases[cid].get("source") or "?"),
            -(score_richness(cases[cid]) + score_severity(cases[cid])),
        )
    )

    picked: List[str] = []
    seen_src: Set[str] = set()
    for cid in candidates:
        if len(picked) >= N_UNDERREP:
            break
        src = cases[cid].get("source") or "?"
        if src in seen_src and len(picked) >= N_UNDERREP // 2:
            continue
        picked.append(cid)
        seen_src.add(src)

    if len(picked) < N_UNDERREP:
        for cid in candidates:
            if cid not in picked:
                picked.append(cid)
            if len(picked) >= N_UNDERREP:
                break
    return picked[:N_UNDERREP]


def write_excluded(cases: Dict[str, Dict[str, Any]], nf: NoiseFilter) -> int:
    excluded = []
    for cid, case in cases.items():
        noisy, reason = nf.is_noisy_case(case)
        if noisy:
            excluded.append({"case_id": cid, "source": case.get("source"), "reason": reason})
    path = ONTOLOGY / "excluded_cases.json"
    path.write_text(
        json.dumps(
            {"n_total": len(cases), "n_excluded": len(excluded), "excluded": excluded},
            indent=2,
        )
    )
    return len(excluded)


def trim_to_target(
    selected: Dict[str, Dict[str, Any]],
    cases: Dict[str, Dict[str, Any]],
    protected: Set[str],
) -> Dict[str, Dict[str, Any]]:
    if len(selected) <= TARGET:
        return selected
    keep = set(protected)
    rest = sorted(
        [cid for cid in selected if cid not in keep],
        key=lambda c: (
            0 if selected[c]["tier"].startswith("T0") else 1,
            0 if selected[c]["tier"].startswith("T3") else 1,
            -(selected[c].get("rs", 0) + selected[c].get("ss", 0)),
        ),
    )
    for cid in rest:
        if len(keep) >= TARGET:
            break
        keep.add(cid)
    return {cid: selected[cid] for cid in keep if cid in selected}


def topup(
    selected: Dict[str, Dict[str, Any]],
    cases: Dict[str, Dict[str, Any]],
    nf: NoiseFilter,
) -> None:
    if len(selected) >= TARGET:
        return
    ranked = sorted(
        [
            (cid, score_richness(cases[cid]) + score_severity(cases[cid]))
            for cid in cases
            if cid not in selected and not nf.is_noisy_case(cases[cid])[0]
        ],
        key=lambda t: -t[1],
    )
    for cid, sc in ranked:
        if len(selected) >= TARGET:
            break
        selected[cid] = {
            "case_id": cid,
            "tier": "topup",
            "rationale": f"backfill combined score={sc}",
            "source": cases[cid].get("source"),
            "rs": score_richness(cases[cid]),
            "ss": score_severity(cases[cid]),
        }


def generate_graphs(case_ids: List[str]) -> None:
    from features_to_cac import CaseToCAC, _load_case_with_fallback  # noqa: E402
    from rdflib import Graph

    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    mapper = CaseToCAC()
    ok = fail = 0
    for i, cid in enumerate(case_ids, 1):
        case, _src = _load_case_with_fallback(cid)
        if case is None:
            print(f"  [{i}/{len(case_ids)}] skip {cid} (not in DB)")
            fail += 1
            continue
        graph, _warnings = mapper.map_case(case)
        jsonld_path = GRAPH_DIR / f"{cid}.jsonld"
        ttl_path = GRAPH_DIR / f"{cid}.ttl"
        graph.serialize(destination=str(jsonld_path), format="json-ld", indent=2)
        flat = Graph()
        for ctx in graph.graphs():
            for triple in ctx:
                flat.add(triple)
        for prefix, ns in graph.namespaces():
            flat.bind(prefix, ns, replace=True)
        flat.serialize(destination=str(ttl_path), format="turtle")
        ok += 1
        if i % 25 == 0:
            print(f"  graphs {i}/{len(case_ids)}")
    print(f"Graphs written: {ok} ok, {fail} failed → {GRAPH_DIR}")


def main() -> None:
    do_graphs = "--no-graphs" not in sys.argv
    nf = NoiseFilter()
    db = REPO_ROOT / "caselinker.db"
    conn = sqlite3.connect(str(db))
    cols = [c[1] for c in conn.execute("PRAGMA table_info(cases)").fetchall()]
    cases = {dict(zip(cols, row))["id"]: dict(zip(cols, row)) for row in conn.execute("SELECT * FROM cases")}
    print(f"Loaded {len(cases)} cases from DB")

    n_excl = write_excluded(cases, nf)
    print(f"Wrote excluded_cases.json ({n_excl} noisy cases)")

    eligible = {
        cid: c
        for cid, c in cases.items()
        if not nf.is_noisy_case(c)[0] or cid in set(case_study_ids())
    }

    selected: Dict[str, Dict[str, Any]] = {}

    def add(cid: str, tier: str, rationale: str, extra: Optional[Dict[str, Any]] = None) -> bool:
        if cid in selected or cid not in cases:
            return False
        row = {
            "case_id": cid,
            "tier": tier,
            "rationale": rationale,
            "source": cases[cid].get("source"),
            "rs": score_richness(cases[cid]),
            "ss": score_severity(cases[cid]),
            "density": score_density(cases[cid]),
        }
        if extra:
            row.update(extra)
        selected[cid] = row
        return True

    # T0: case studies
    cs_ids = case_study_ids()
    for cid in cs_ids:
        add(cid, "T0_case_study", "published case study linked_case_id")
    print(f"T0 case studies     : {sum(1 for c in selected if selected[c]['tier']=='T0_case_study')}")

    # T1: rich + dense
    rich_rank = sorted(
        eligible.keys(),
        key=lambda c: (-(score_richness(cases[c]) + score_density(cases[c])), c),
    )
    n = 0
    for cid in rich_rank:
        if n >= N_RICH:
            break
        if add(cid, "T1_richness", f"richness={score_richness(cases[cid])} density={score_density(cases[cid])}"):
            n += 1
    print(f"T1 richness         : {n}")

    # T2: severe
    sev_rank = sorted(
        eligible.keys(),
        key=lambda c: (-score_severity(cases[c]), -score_richness(cases[c])),
    )
    n = 0
    for cid in sev_rank:
        if n >= N_SEVERE:
            break
        if add(cid, "T2_severity", f"severity={score_severity(cases[cid])}"):
            n += 1
    print(f"T2 severity         : {n}")

    # T3: platform / tech (revolver label universe)
    _, label_ranked = build_revolver_index(cases, nf)
    all_labels = sorted(label_ranked.keys(), key=str.lower)
    print(f"Technology revolver labels in corpus: {len(all_labels)}")
    plat_ids, uncovered = pick_platform_tier(cases, selected, label_ranked, all_labels, nf)
    for cid in plat_ids:
        labs = sorted(all_tech_labels(cases[cid]))
        sig_labs = [
            lab
            for lab in labs
            if lab in tech_labels_for_case(cases[cid]).get("platforms_used", set())
            and nf.is_platform_signal(nf.case_text(cases[cid]), lab)
        ]
        add(
            cid,
            "T3_platform_tech",
            f"platform/tech coverage labels={labs[:8]}{'...' if len(labs)>8 else ''}",
            extra={"tech_labels": labs, "signal_platform_labels": sig_labs},
        )
    print(f"T3 platform/tech    : {len(plat_ids)} (uncovered labels: {len(uncovered)})")

    # T4: underrepresented sources
    under_ids = pick_underrep_tier(cases, selected)
    for cid in under_ids:
        src = cases[cid].get("source") or "?"
        add(
            cid,
            "T4_underrepresented_source",
            f"underrepresented source={src} rs={score_richness(cases[cid])} ss={score_severity(cases[cid])}",
        )
    print(f"T4 underrep sources : {len(under_ids)}")

    topup(selected, cases, nf)
    protected = set(cs_ids)
    selected = trim_to_target(selected, cases, protected)
    if len(selected) < TARGET:
        topup(selected, cases, nf)

    print(f"\nFinal selection: {len(selected)} cases")
    tier_dist = Counter(r["tier"] for r in selected.values())
    for tier, cnt in sorted(tier_dist.items()):
        print(f"  {tier:30s} {cnt}")

    out = {
        "n_selected": len(selected),
        "n_target": TARGET,
        "n_excluded_noisy": n_excl,
        "n_revolver_labels": len(all_labels),
        "n_uncovered_tech_labels": len(uncovered),
        "uncovered_tech_labels": sorted(uncovered)[:100],
        "selection": list(selected.values()),
    }
    (ONTOLOGY / "selected_200_cases.json").write_text(json.dumps(out, indent=2))
    ids = sorted(selected.keys())
    (ONTOLOGY / "pools" / "selected_200_ids.txt").write_text("\n".join(ids) + "\n")
    print(f"Wrote ontology/selected_200_cases.json")
    print(f"Wrote ontology/pools/selected_200_ids.txt")

    if do_graphs:
        print("\nGenerating graphs...")
        generate_graphs(ids)
    else:
        print("\nSkipped graphs (--no-graphs)")


if __name__ == "__main__":
    main()
