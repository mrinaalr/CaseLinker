#!/usr/bin/env python3
"""
Build + cache merged JSON-LD flat node lists for Patterns compare / Big Bang / Universe.

Layout:
  graph_output/            — full mapped corpus staging (~10k; Find/load pool=full)
  graph_output/universe/   — secret Universe mode + compare chips source (~1969)
  graph_output/big_bang/   — Big Bang button half-sample
  graph_output/analysis/   — custom MCP/research cohorts (Analysis mode; see analysis_ids.txt)

Patterns visualizer: Find/load/compare use staging (max 2000 merge). Secret double-click
modes still merge universe / big_bang / analysis via /api/ontology/merged.

Caches to:
  ontology/cache/merged_compare.json
  ontology/cache/merged_all.json.gz
  ontology/cache/merged_universe.json.gz
  ontology/cache/merged_analysis.json.gz

Redis keys (when available):
  caselinker:ontology:merged:compare:{manifest}
  caselinker:ontology:merged:all:{manifest}
  caselinker:ontology:merged:universe:{manifest}
  caselinker:ontology:merged:analysis:{manifest}
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

REPO_ROOT = Path(__file__).resolve().parent.parent
ONTOLOGY = REPO_ROOT / "ontology"
GRAPH_ROOT = ONTOLOGY / "graph_output"
UNIVERSE_DIR = GRAPH_ROOT / "universe"
BIG_BANG_DIR = GRAPH_ROOT / "big_bang"
ANALYSIS_DIR = GRAPH_ROOT / "analysis"
BIG_BANG_IDS_FILE = ONTOLOGY / "big_bang_ids.txt"
ANALYSIS_IDS_FILE = ONTOLOGY / "analysis_ids.txt"
CACHE_DIR = ONTOLOGY / "cache"
COMPARE_IDS_FILE = ONTOLOGY / "selected_200_ids.txt"
NLP_GRAPH_RE = re.compile(r"/graphs/nlp$")

_POOL_CACHE_FILES = {
    "compare": CACHE_DIR / "merged_compare.json",
    "all": CACHE_DIR / "merged_all.json.gz",
    "universe": CACHE_DIR / "merged_universe.json.gz",
    "analysis": CACHE_DIR / "merged_analysis.json.gz",
}


def _compare_pool_ids() -> List[str]:
    if not COMPARE_IDS_FILE.is_file():
        return []
    return [ln.strip() for ln in COMPARE_IDS_FILE.read_text().splitlines() if ln.strip()]


def _analysis_pool_ids() -> List[str]:
    if not ANALYSIS_IDS_FILE.is_file():
        return []
    return [ln.strip() for ln in ANALYSIS_IDS_FILE.read_text().splitlines() if ln.strip()]


def graph_dir_for_pool(pool: str) -> Path:
    """Return on-disk graph directory for a Patterns pool."""
    p = pool.strip().lower()
    if p == "compare":
        return UNIVERSE_DIR
    if p in ("all", "big_bang"):
        return BIG_BANG_DIR
    if p == "universe":
        return UNIVERSE_DIR
    if p == "analysis":
        return ANALYSIS_DIR
    raise ValueError(f"unknown pool: {pool}")


def graph_manifest(graph_dir: Optional[Path] = None) -> str:
    """Fingerprint graph dir contents for cache invalidation."""
    d = graph_dir or UNIVERSE_DIR
    if not d.is_dir():
        return "empty"
    parts: List[str] = []
    for p in sorted(d.glob("*.jsonld")):
        st = p.stat()
        parts.append(f"{p.stem}:{st.st_size}:{int(st.st_mtime)}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]


def flatten_named_graphs(json_ld: Any) -> List[Dict[str, Any]]:
    nodes: List[Dict[str, Any]] = []
    if isinstance(json_ld, dict):
        graphs = [json_ld]
    elif isinstance(json_ld, list):
        graphs = json_ld
    else:
        return nodes

    for named in graphs:
        is_nlp = bool(
            isinstance(named, dict)
            and NLP_GRAPH_RE.search(str(named.get("@id") or ""))
        )
        for node in named.get("@graph") or []:
            if not isinstance(node, dict) or not node.get("@id"):
                continue
            copy = dict(node)
            if is_nlp:
                copy["_isNlp"] = True
            nodes.append(copy)
    return nodes


def _serialize_term(v: Any) -> str:
    if isinstance(v, dict):
        if "@id" in v:
            return "id:" + str(v["@id"])
        if "@value" in v:
            return "v:" + str(v.get("@type") or "") + ":" + str(v["@value"])
    return "lit:" + str(v)


def merge_case_into_store(store: Dict[str, Dict[str, Any]], case_id: str, json_ld: Any) -> None:
    for node in flatten_named_graphs(json_ld):
        nid = node["@id"]
        if nid not in store:
            copy = dict(node)
            t = copy.get("@type")
            if isinstance(t, list):
                copy["@type"] = list(t)
            copy["_cases"] = [case_id]
            copy["_isNlp"] = bool(node.get("_isNlp"))
            store[nid] = copy
            continue
        ex = store[nid]
        if case_id not in ex["_cases"]:
            ex["_cases"].append(case_id)
        if node.get("_isNlp"):
            ex["_isNlp"] = True
        for k, v in node.items():
            if k in ("@id", "_cases", "_isNlp"):
                continue
            if k == "@type":
                ea = ex.get(k) or []
                ea = ea if isinstance(ea, list) else [ea]
                na = v if isinstance(v, list) else [v]
                ex[k] = list(dict.fromkeys([*ea, *na]))
                continue
            if k not in ex:
                ex[k] = v
                continue
            if isinstance(ex[k], list) and isinstance(v, list):
                seen = {_serialize_term(x) for x in ex[k]}
                for item in v:
                    key = _serialize_term(item)
                    if key not in seen:
                        ex[k].append(item)
                        seen.add(key)


def build_merged_flat(
    case_ids: List[str],
    graph_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    d = graph_dir or UNIVERSE_DIR
    store: Dict[str, Dict[str, Any]] = {}
    for cid in case_ids:
        path = d / f"{cid}.jsonld"
        if not path.is_file():
            continue
        try:
            doc = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        merge_case_into_store(store, cid, doc)
    flat = list(store.values())
    for n in flat:
        n["_isShared"] = len(n.get("_cases") or []) > 1
    return flat


def case_ids_for_pool(pool: str) -> List[str]:
    d = graph_dir_for_pool(pool)
    graphs = sorted(p.stem for p in d.glob("*.jsonld")) if d.is_dir() else []
    if pool == "compare":
        order = _compare_pool_ids()
        graph_set = set(graphs)
        return [cid for cid in order if cid in graph_set]
    if pool == "analysis":
        order = _analysis_pool_ids()
        if order:
            graph_set = set(graphs)
            return [cid for cid in order if cid in graph_set]
        return graphs
    return graphs


def load_merged_payload(pool: str) -> Optional[Dict[str, Any]]:
    d = graph_dir_for_pool(pool)
    manifest = graph_manifest(d)
    path = _POOL_CACHE_FILES.get(pool)
    if not path:
        return None
    if not path.is_file():
        return None
    try:
        if path.suffix == ".gz":
            raw = gzip.decompress(path.read_bytes()).decode()
        else:
            raw = path.read_text()
        payload = json.loads(raw)
        if payload.get("manifest") == manifest and payload.get("pool") == pool:
            return payload
    except (json.JSONDecodeError, OSError):
        pass
    return None


def save_merged_payload(pool: str, flat: List[Dict[str, Any]], case_ids: List[str]) -> Dict[str, Any]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    d = graph_dir_for_pool(pool)
    manifest = graph_manifest(d)
    payload = {
        "pool": pool,
        "manifest": manifest,
        "n_cases": len(case_ids),
        "n_nodes": len(flat),
        "case_ids": case_ids,
        "flat_nodes": flat,
    }
    path = _POOL_CACHE_FILES.get(pool)
    if not path:
        raise ValueError(f"unknown pool: {pool}")
    if path.suffix == ".gz":
        data = json.dumps(payload).encode()
        path.write_bytes(gzip.compress(data, compresslevel=6))
    else:
        path.write_text(json.dumps(payload))
    return payload


def get_or_build_merged(pool: str, redis_get=None, redis_set=None) -> Dict[str, Any]:
    """Return merged payload; use Redis hooks from run/redis_cache when provided."""
    pool = pool.strip().lower()
    if pool not in ("compare", "all", "universe", "analysis"):
        raise ValueError("pool must be compare, all, universe, or analysis")

    d = graph_dir_for_pool(pool)
    manifest = graph_manifest(d)
    redis_key = f"caselinker:ontology:merged:{pool}:{manifest}"

    if redis_get:
        hit = redis_get(redis_key)
        if hit and isinstance(hit, dict) and hit.get("manifest") == manifest:
            hit["cache"] = "redis"
            return hit

    disk = load_merged_payload(pool)
    if disk:
        disk["cache"] = "disk"
        if redis_set:
            redis_set(redis_key, disk, ttl=86400 * 7)
        return disk

    case_ids = case_ids_for_pool(pool)
    flat = build_merged_flat(case_ids, graph_dir=d)
    payload = save_merged_payload(pool, flat, case_ids)
    payload["cache"] = "built"
    if redis_set:
        redis_set(redis_key, payload, ttl=86400 * 7)
    return payload


def warm_all_caches(redis_get=None, redis_set=None) -> None:
    for pool in ("compare", "all", "universe", "analysis"):
        p = get_or_build_merged(pool, redis_get=redis_get, redis_set=redis_set)
        print(f"  merged {pool}: {p['n_cases']} cases, {p['n_nodes']} nodes ({p.get('cache')})")


if __name__ == "__main__":
    try:
        import sys

        sys.path.insert(0, str(REPO_ROOT / "run"))
        from redis_cache import get_cached, set_cached  # noqa: E402

        warm_all_caches(redis_get=get_cached, redis_set=lambda k, v, ttl=604800: set_cached(k, v, ttl=ttl))
    except ImportError:
        warm_all_caches()
