"""Build a wholesale N-Quads dataset from canonical per-case Turtle graphs.

Canonical source priority (first match wins):
  universe > staging (graph_output/*.ttl) > big_bang > analysis > pacer

Each case is loaded into named graph
  https://caselinker.up.railway.app/resource/case/{case_id}

PACER court-record graphs live in graph_output/pacer/pacer_{slug}.ttl and
therefore become named graph …/resource/case/pacer_{slug}. The glob is
per-directory `*.ttl` (not recursive); pacer is an explicit pool so those
files are included without swallowing universe/big_bang/analysis.

The public Oxigraph service is expected to run with --union-default-graph so
default-graph SPARQL still sees the union of those named graphs.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple

from rdflib import Dataset, Graph, URIRef

REPO_ROOT = Path(__file__).resolve().parent.parent
ONTOLOGY = REPO_ROOT / "ontology"
GRAPH_ROOT = ONTOLOGY / "graph_output"
DEFAULT_NQ = ONTOLOGY / "cache" / "caselinker.nq"

CASE_GRAPH_BASE = "https://caselinker.up.railway.app/resource/case/"

# Directory name under graph_output/; None means the staging root.
POOL_PRIORITY: Tuple[Optional[str], ...] = (
    "universe",
    None,
    "big_bang",
    "analysis",
    "pacer",
)


def case_graph_iri(case_id: str) -> URIRef:
    return URIRef(CASE_GRAPH_BASE + case_id.strip())


def canonical_ttl_paths(graph_root: Optional[Path] = None) -> Dict[str, Path]:
    """Return case_id -> TTL path using universe > staging > big_bang > analysis > pacer."""
    root = graph_root or GRAPH_ROOT
    chosen: Dict[str, Path] = {}
    for pool in POOL_PRIORITY:
        directory = root if pool is None else root / pool
        if not directory.is_dir():
            continue
        for path in directory.glob("*.ttl"):
            if path.parent != directory:
                continue
            stem = path.stem
            if stem not in chosen:
                chosen[stem] = path
    return dict(sorted(chosen.items()))


def pool_label_for_path(path: Path, graph_root: Optional[Path] = None) -> str:
    parent = path.resolve().parent
    if graph_root is not None and parent == graph_root.resolve():
        return "staging"
    if parent.name in ("universe", "big_bang", "analysis", "pacer"):
        return parent.name
    return "staging"


def build_nquads(
    ttl_by_id: Mapping[str, Path],
    destination: Path,
) -> Dict[str, object]:
    """Parse each TTL into its per-case named graph and write N-Quads.

    Overwrites *destination*. Returns counts for the job log.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    dataset = Dataset()
    failed: List[Dict[str, str]] = []
    loaded = 0
    for case_id, path in ttl_by_id.items():
        parsed = Graph()
        try:
            parsed.parse(path, format="turtle")
        except Exception as exc:
            failed.append({"case_id": case_id, "path": str(path), "reason": str(exc)})
            continue
        ctx = dataset.graph(identifier=case_graph_iri(case_id))
        for triple in parsed:
            ctx.add(triple)
        loaded += 1
    dataset.serialize(destination=str(destination), format="nquads")
    return {
        "destination": str(destination),
        "cases_requested": len(ttl_by_id),
        "cases_loaded": loaded,
        "quads": len(dataset),
        "failed": failed,
        "pool_counts": summarize_sources(ttl_by_id),
    }


def put_nquads(
    nq_path: Path,
    oxigraph_url: str,
    *,
    timeout_s: float = 300.0,
) -> None:
    """Wholesale-replace the Oxigraph dataset via Graph Store PUT /store.

    Holds the rebuild lock for the duration of the PUT so /sparql can 503.
    """
    import httpx

    _run = Path(__file__).resolve().parent.parent / "run"
    if str(_run) not in sys.path:
        sys.path.insert(0, str(_run))
    from sparql_rebuild_lock import acquire_rebuild_lock, release_rebuild_lock

    acquire_rebuild_lock()
    try:
        base = oxigraph_url.rstrip("/")
        url = f"{base}/store"
        with nq_path.open("rb") as handle:
            response = httpx.put(
                url,
                content=handle,
                headers={"Content-Type": "application/n-quads"},
                timeout=timeout_s,
            )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Oxigraph PUT {url} failed: HTTP {response.status_code} {response.text[:2000]}"
            )
    finally:
        release_rebuild_lock()


def summarize_sources(ttl_by_id: Mapping[str, Path]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for path in ttl_by_id.values():
        label = pool_label_for_path(path)
        counts[label] = counts.get(label, 0) + 1
    return counts
