#!/usr/bin/env python3
"""
Generate + SHACL-eval + merge-metrics for ontology/pools/big_bang_ids.txt.

1. Wipe ontology/graph_output/*.jsonld + *.ttl (staging root only — not universe/ or big_bang/)
2. Build JSON-LD + TTL per selected ID (features_to_cac)
3. SHACL gate (target 100%)
4. Merged Big Bang payload + structural / bridge / connectivity metrics
5. Payload size reality check (browser ~42k node ceiling, localStorage ~5MB)

Writes: ontology/big_bang_graph_eval.json

Usage:
  python ontology/pools/eval_big_bang_graphs.py
  python ontology/pools/eval_big_bang_graphs.py --limit 50
  python ontology/pools/eval_big_bang_graphs.py --no-wipe
"""

from __future__ import annotations

import gzip
import json
import re
import sys
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY = REPO_ROOT / "ontology"
GRAPH_ROOT = ONTOLOGY / "graph_output"
GRAPH_DIR = GRAPH_ROOT
CACHE_DIR = ONTOLOGY / "cache"
IDS_FILE = ONTOLOGY / "pools" / "big_bang_ids.txt"
SEED_FILE = ONTOLOGY / "pools" / "selected_200_ids.txt"
OUT_FILE = ONTOLOGY / "big_bang_graph_eval.json"

BROWSER_NODE_CEILING = 42_000
LOCALSTORAGE_QUOTA_MB = 5.0
MAX_BRIDGE_SHARE_PCT = 25.0

sys.path.insert(0, str(ONTOLOGY / "pipeline"))

CASE_IRI_RE = re.compile(r"/case/[^/]+$")
NLP_RE = re.compile(r"/nlp/")


def load_ids(limit: int | None) -> List[str]:
    ids = [ln.strip() for ln in IDS_FILE.read_text().splitlines() if ln.strip()]
    if limit:
        ids = ids[:limit]
    return ids


def load_seed_ids() -> Set[str]:
    if not SEED_FILE.is_file():
        return set()
    return {ln.strip() for ln in SEED_FILE.read_text().splitlines() if ln.strip()}


def bridge_uri(u: str) -> bool:
    if not u:
        return False
    if CASE_IRI_RE.search(u):
        return False
    if NLP_RE.search(u):
        return False
    return True


def wipe_graph_output() -> int:
    """Remove staging graphs at graph_output/ root (viz subdirs untouched)."""
    n = 0
    for pat in ("*.jsonld", "*.ttl"):
        for p in GRAPH_ROOT.glob(pat):
            p.unlink()
            n += 1
    return n


def flatten_graph_nodes(json_ld: Any) -> List[Dict[str, Any]]:
    from merge_graph_cache import flatten_named_graphs  # noqa: E402

    return flatten_named_graphs(json_ld)


def spine_events_roles_from_doc(json_ld: Any) -> Tuple[int, int]:
    events = roles = 0
    for node in flatten_graph_nodes(json_ld):
        types = node.get("@type") or []
        if not isinstance(types, list):
            types = [types]
        names = " ".join(
            t.rsplit("/", 1)[-1].split("#")[-1] for t in types if isinstance(t, str)
        )
        if re.search(
            r"Event|Action|Operation|Offense|Incident|Abuse|Violation|Grooming|"
            r"Sextortion|Production|Conspiracy|Investigation",
            names,
        ):
            events += 1
        if re.search(r"Role|Victim|Offender|Predator|Investigator", names):
            roles += 1
    return events, roles


def extract_edges(flat_nodes: List[Dict[str, Any]]) -> List[Tuple[str, str, str]]:
    """(source_id, target_id, predicate_local_name)"""
    id_set = {n["@id"] for n in flat_nodes if n.get("@id")}
    reserved = {"@id", "@type", "@context", "_cases", "_isNlp", "_isShared"}
    edges: List[Tuple[str, str, str]] = []
    for src in flat_nodes:
        sid = src.get("@id")
        if not sid:
            continue
        for key, val in src.items():
            if key in reserved:
                continue
            pred = key.rsplit("/", 1)[-1].split("#")[-1]

            def add_ref(ref: Dict[str, Any]) -> None:
                tid = ref.get("@id")
                if tid and tid in id_set:
                    edges.append((sid, tid, pred))

            if isinstance(val, dict) and "@id" in val:
                add_ref(val)
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, dict) and "@id" in item:
                        add_ref(item)
    return edges


def connected_components(
    node_ids: Set[str], edges: List[Tuple[str, str, str]]
) -> List[int]:
    parent: Dict[str, str] = {n: n for n in node_ids}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for s, t, _ in edges:
        if s in parent and t in parent:
            union(s, t)
    roots: Counter = Counter(find(n) for n in node_ids)
    return sorted(roots.values(), reverse=True)


def bridge_metrics_from_flat(
    flat: List[Dict[str, Any]], n_cases: int
) -> Dict[str, Any]:
    bridge_case_counts: Counter = Counter()
    for node in flat:
        nid = node.get("@id")
        if not nid or not bridge_uri(nid):
            continue
        cases = node.get("_cases") or []
        bridge_case_counts[nid] = len(cases)

    hist: Counter = Counter()
    for deg in bridge_case_counts.values():
        hist[deg] += 1

    top = sorted(
        [{"uri": u, "degree": d} for u, d in bridge_case_counts.items()],
        key=lambda x: (-x["degree"], x["uri"]),
    )[:20]

    max_deg = top[0]["degree"] if top else 0
    max_share_pct = round(100.0 * max_deg / max(n_cases, 1), 2)
    shared_2plus = sum(1 for d in bridge_case_counts.values() if d >= 2)

    return {
        "n_unique_bridge_uris": len(bridge_case_counts),
        "n_bridges_shared_by_2plus_cases": shared_2plus,
        "bridge_degree_histogram": dict(sorted(hist.items())),
        "top_bridges": top,
        "max_single_bridge_degree": max_deg,
        "max_single_bridge_share_pct": max_share_pct,
        "max_bridge_share_ok": max_share_pct <= MAX_BRIDGE_SHARE_PCT,
    }


def median(vals: List[float]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    return float(s[len(s) // 2])


def generate_graphs(ids: List[str]) -> Dict[str, Any]:
    from features_to_cac import CaseToCAC, _load_case_with_fallback  # noqa: E402
    from rdflib import Graph

    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    mapper = CaseToCAC()

    generated: List[str] = []
    skipped: List[Dict[str, str]] = []
    failed: List[Dict[str, str]] = []
    shacl_ok: List[str] = []
    shacl_fail: List[Dict[str, Any]] = []
    per_case: List[Dict[str, Any]] = []

    for i, cid in enumerate(ids, 1):
        try:
            case, src = _load_case_with_fallback(cid)
            if case is None:
                skipped.append({"case_id": cid, "reason": "not in DB"})
                continue

            graph, warnings = mapper.map_case(case)
            conforms, shacl_report = mapper.validate(graph)

            jsonld_path = GRAPH_DIR / f"{cid}.jsonld"
            ttl_path = GRAPH_DIR / f"{cid}.ttl"
            graph.serialize(destination=str(jsonld_path), format="json-ld", indent=2)
            flat_g = Graph()
            for ctx in graph.graphs():
                for triple in ctx:
                    flat_g.add(triple)
            for prefix, ns in graph.namespaces():
                flat_g.bind(prefix, ns, replace=True)
            flat_g.serialize(destination=str(ttl_path), format="turtle")

            doc = json.loads(jsonld_path.read_text())
            ev, ro = spine_events_roles_from_doc(doc)

            entry: Dict[str, Any] = {
                "case_id": cid,
                "status": "ok",
                "load_source": src,
                "shacl_conforms": conforms,
                "warnings_n": len(warnings),
                "spine_events": ev,
                "spine_roles": ro,
                "node_count": len(flatten_graph_nodes(doc)),
            }
            if not conforms:
                entry["shacl_report"] = (shacl_report or "")[:4000]
                shacl_fail.append(entry)
            else:
                shacl_ok.append(cid)
            generated.append(cid)
            per_case.append(entry)

        except Exception as exc:
            failed.append(
                {
                    "case_id": cid,
                    "reason": str(exc),
                    "traceback": traceback.format_exc()[-1500:],
                }
            )
            print(f"  FAIL {cid}: {exc}", file=sys.stderr)

        if i % 50 == 0:
            print(f"  [{i}/{len(ids)}] generated={len(generated)} shacl_ok={len(shacl_ok)} fail={len(failed)}")

    return {
        "generated": generated,
        "skipped": skipped,
        "failed": failed,
        "shacl_ok": shacl_ok,
        "shacl_fail": shacl_fail,
        "per_case": per_case,
    }


def build_and_analyze_merge(
    case_ids: List[str],
    seed_ids: Set[str],
    graph_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    from merge_graph_cache import build_merged_flat, graph_manifest, save_merged_payload  # noqa: E402

    gdir = graph_dir or GRAPH_DIR
    flat = build_merged_flat(case_ids, graph_dir=gdir)
    payload = save_merged_payload("all", flat, case_ids)
    manifest = graph_manifest(gdir)

    raw_json = json.dumps({"flat_nodes": flat, "pool": "all", "manifest": manifest, "n_cases": len(case_ids)})
    raw_bytes = len(raw_json.encode("utf-8"))
    gz_bytes = len(gzip.compress(raw_json.encode("utf-8"), compresslevel=6))

    edges = extract_edges(flat)
    node_ids = {n["@id"] for n in flat if n.get("@id")}
    comp_sizes = connected_components(node_ids, edges)
    n_components = len(comp_sizes)

    seed_spine: List[int] = []
    other_spine: List[int] = []
    for cid in case_ids:
        path = (graph_dir or GRAPH_DIR) / f"{cid}.jsonld"
        if not path.is_file():
            continue
        ev, ro = spine_events_roles_from_doc(json.loads(path.read_text()))
        s = ev + ro
        if cid in seed_ids:
            seed_spine.append(s)
        else:
            other_spine.append(s)

    bm = bridge_metrics_from_flat(flat, len(case_ids))

    return {
        "manifest": manifest,
        "n_cases_merged": len(case_ids),
        "n_merged_nodes": len(flat),
        "n_merged_edges": len(edges),
        "payload_raw_bytes": raw_bytes,
        "payload_raw_mb": round(raw_bytes / 1024 / 1024, 3),
        "payload_gzip_bytes": gz_bytes,
        "payload_gzip_mb": round(gz_bytes / 1024 / 1024, 3),
        "payload_gzip_fits_localstorage_5mb": gz_bytes < int(LOCALSTORAGE_QUOTA_MB * 1024 * 1024),
        "gzip_on_wire_recommended": raw_bytes > int(LOCALSTORAGE_QUOTA_MB * 1024 * 1024),
        "browser_node_ceiling": BROWSER_NODE_CEILING,
        "under_browser_node_ceiling": len(flat) < BROWSER_NODE_CEILING,
        "nodes_vs_ceiling_pct": round(100.0 * len(flat) / BROWSER_NODE_CEILING, 1),
        **bm,
        "connectivity": {
            "n_connected_components": n_components,
            "component_sizes_top10": comp_sizes[:10],
            "largest_component_size": comp_sizes[0] if comp_sizes else 0,
            "largest_component_share_pct": round(
                100.0 * (comp_sizes[0] if comp_sizes else 0) / max(len(node_ids), 1), 2
            ),
        },
        "spine_sanity": {
            "median_events_plus_roles_seed_200": median([float(x) for x in seed_spine]),
            "median_events_plus_roles_non_seed": median([float(x) for x in other_spine]),
            "n_seed_with_graph": len(seed_spine),
            "n_non_seed_with_graph": len(other_spine),
        },
        "cache_file": "ontology/cache/merged_all.json.gz",
    }


def main() -> None:
    limit = None
    no_wipe = "--no-wipe" in sys.argv
    if "--limit" in sys.argv:
        i = sys.argv.index("--limit")
        if i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])

    ids = load_ids(limit)
    n_selected = len(ids)
    seed_ids = load_seed_ids()

    print(f"Big Bang graph eval: {n_selected} IDs")
    if not no_wipe:
        GRAPH_DIR.mkdir(parents=True, exist_ok=True)
        removed = wipe_graph_output()
        print(f"Wiped {removed} stale files from {GRAPH_DIR}")
    else:
        print("(skipping wipe — --no-wipe)")

    gen = generate_graphs(ids)
    n_generated = len(gen["generated"])
    gen_gap = [cid for cid in ids if cid not in set(gen["generated"])]

    print("\n--- SHACL ---")
    print(f"  n_selected:        {n_selected}")
    print(f"  n_graphs_generated: {n_generated}")
    if gen_gap:
        print(f"  generation gap ({len(gen_gap)}):")
        for cid in gen_gap:
            reason = next(
                (x.get("reason") for x in gen["skipped"] if x["case_id"] == cid),
                next((x.get("reason") for x in gen["failed"] if x["case_id"] == cid), "?"),
            )
            print(f"    {cid}: {reason}")

    n_shacl_pass = len(gen["shacl_ok"])
    print(f"  SHACL pass: {n_shacl_pass}/{n_generated}")
    if gen["shacl_fail"]:
        print(f"  SHACL failures ({len(gen['shacl_fail'])}):")
        for row in gen["shacl_fail"]:
            print(f"    {row['case_id']}")
            head = (row.get("shacl_report") or "")[:200].replace("\n", " ")
            print(f"      {head}")

    merge = {}
    if n_generated:
        print("\n--- Merge + metrics ---")
        merge = build_and_analyze_merge(gen["generated"], seed_ids)

    report: Dict[str, Any] = {
        "n_selected": n_selected,
        "n_graphs_generated": n_generated,
        "generation_gap_ids": gen_gap,
        "skipped": gen["skipped"],
        "failed": gen["failed"],
        "shacl_pass": n_shacl_pass,
        "shacl_total": n_generated,
        "shacl_rate": round(n_shacl_pass / n_generated, 4) if n_generated else 0.0,
        "shacl_failures": gen["shacl_fail"],
        "demo_ready": (
            n_generated == n_selected
            and n_shacl_pass == n_generated
            and merge.get("under_browser_node_ceiling", False)
            and merge.get("max_bridge_share_ok", False)
        ),
        "merge": merge,
        "per_case": gen["per_case"],
    }
    OUT_FILE.write_text(json.dumps(report, indent=2))

    print("\n======== SUMMARY ========")
    print(f"  n_graphs:           {n_generated} / {n_selected}")
    print(f"  SHACL pass rate:    {n_shacl_pass}/{n_generated} ({report['shacl_rate']:.1%})")
    if merge:
        print(f"  merged nodes:       {merge['n_merged_nodes']}")
        print(f"  merged edges:       {merge['n_merged_edges']}")
        print(f"  bridges shared 2+:  {merge['n_bridges_shared_by_2plus_cases']}")
        print(f"  max bridge share:   {merge['max_single_bridge_share_pct']}%")
        print(
            f"  components / largest: {merge['connectivity']['n_connected_components']} / "
            f"{merge['connectivity']['largest_component_size']}"
        )
        print(f"  gzipped payload:    {merge['payload_gzip_mb']} MB")
        print(f"  under 42k nodes:    {merge['under_browser_node_ceiling']}")
        print(f"  fits 5MB localStorage (gzip): {merge['payload_gzip_fits_localstorage_5mb']}")
    print(f"  demo_ready:         {report['demo_ready']}")
    print(f"  → {OUT_FILE}")


if __name__ == "__main__":
    main()
