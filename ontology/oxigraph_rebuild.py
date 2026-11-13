"""Build a wholesale N-Quads dataset from canonical per-case Turtle graphs.

Canonical source priority (first match wins):
  universe > staging (graph_output/*.ttl) > big_bang > analysis > pacer

Each case is loaded into named graph
  https://w3id.org/caselinker/resource/case/{case_id}

A sibling ``{case_id}.provenance.ttl`` beside that chosen case file is loaded
into named graph
  https://w3id.org/caselinker/resource/case/{case_id}/provenance
It is not a case. A sidecar in a lower-priority pool is not substituted.

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
from typing import Any, Dict, List, Mapping, Optional, Tuple

from rdflib import Graph, URIRef

REPO_ROOT = Path(__file__).resolve().parent.parent
ONTOLOGY = REPO_ROOT / "ontology"
GRAPH_ROOT = ONTOLOGY / "graph_output"
DEFAULT_NQ = ONTOLOGY / "cache" / "caselinker.nq"

CASE_GRAPH_BASE = "https://w3id.org/caselinker/resource/case/"
PROVENANCE_FILENAME_SUFFIX = ".provenance.ttl"

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


def provenance_graph_iri(case_id: str) -> URIRef:
    return URIRef(CASE_GRAPH_BASE + case_id.strip() + "/provenance")


def provenance_sidecar(case_path: Path) -> Path:
    """``{case_id}.provenance.ttl`` in the same directory as the case file."""
    return case_path.with_name(case_path.stem + PROVENANCE_FILENAME_SUFFIX)


def canonical_ttl_paths(graph_root: Optional[Path] = None) -> Dict[str, Path]:
    """Return case_id -> TTL path using universe > staging > big_bang > analysis > pacer.

    ``*.provenance.ttl`` is excluded. Those files are sidecars, not cases.
    """
    root = graph_root or GRAPH_ROOT
    chosen: Dict[str, Path] = {}
    for pool in POOL_PRIORITY:
        directory = root if pool is None else root / pool
        if not directory.is_dir():
            continue
        for path in directory.glob("*.ttl"):
            if path.parent != directory:
                continue
            if path.name.endswith(PROVENANCE_FILENAME_SUFFIX):
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


def _parse_turtle(path: Path) -> Graph:
    parsed = Graph()
    parsed.parse(path, format="turtle")
    return parsed


def _prefix_bnodes(body: str, prefix: str) -> str:
    """Rename `_:label` outside quoted N-Triples strings so graphs can be concatenated."""
    if "_:" not in body:
        return body
    out: List[str] = []
    i = 0
    n = len(body)
    in_str = False
    while i < n:
        ch = body[i]
        if in_str:
            out.append(ch)
            if ch == "\\":
                if i + 1 < n:
                    out.append(body[i + 1])
                    i += 2
                    continue
            elif ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue
        if body.startswith("_:", i):
            j = i + 2
            while j < n and (body[j].isalnum() or body[j] in "_-"):
                j += 1
            out.append("_:")
            out.append(prefix)
            out.append(body[i + 2 : j])
            i = j
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _write_named_graph(graph: Graph, graph_iri: URIRef, handle, prefix: str) -> int:
    """Append one named graph as N-Quads. Returns the number of quads written.

    N-Triples escaping is required. `term.n3()` can emit raw line breaks inside
    literals, which Oxigraph rejects.
    """
    text = graph.serialize(format="nt")
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    graph_tok = graph_iri.n3()
    written = 0
    for line in text.splitlines():
        if not line.endswith(" ."):
            continue
        body = _prefix_bnodes(line[:-2], prefix)
        handle.write(f"{body} {graph_tok} .\n")
        written += 1
    return written


def build_nquads(
    ttl_by_id: Mapping[str, Path],
    destination: Path,
) -> Dict[str, object]:
    """Parse each case TTL into its named graph and write N-Quads.

    When ``{case_id}.provenance.ttl`` sits beside the chosen case file, those
    triples go into ``…/case/{case_id}/provenance``. A missing sidecar is
    normal. A sidecar that does not parse is recorded and does not remove the
    case. Overwrites *destination*, gzip-compressed when its name ends in ``.gz``.

    Graphs are written as they are parsed. The previous single in-memory
    Dataset made each added triple slower as the store grew.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    failed: List[Dict[str, str]] = []
    provenance_failed: List[Dict[str, str]] = []
    loaded = 0
    provenance_loaded = 0
    quads = 0
    total = len(ttl_by_id)
    with _open_nquads(destination, "wt") as handle:
        for case_id, path in ttl_by_id.items():
            try:
                parsed = _parse_turtle(path)
            except Exception as exc:
                failed.append({"case_id": case_id, "path": str(path), "reason": str(exc)})
                continue
            quads += _write_named_graph(
                parsed, case_graph_iri(case_id), handle, f"c{loaded}b"
            )
            loaded += 1
            sidecar = provenance_sidecar(path)
            if sidecar.is_file():
                try:
                    prov = _parse_turtle(sidecar)
                except Exception as exc:
                    provenance_failed.append(
                        {"case_id": case_id, "path": str(sidecar), "reason": str(exc)}
                    )
                else:
                    quads += _write_named_graph(
                        prov,
                        provenance_graph_iri(case_id),
                        handle,
                        f"p{provenance_loaded}b",
                    )
                    provenance_loaded += 1
            if loaded % 2000 == 0:
                print(f"  nquads {loaded}/{total} cases, {quads} quads", flush=True)
    return {
        "destination": str(destination),
        "cases_requested": total,
        "cases_loaded": loaded,
        "provenance_loaded": provenance_loaded,
        "quads": quads,
        "failed": failed,
        "provenance_failed": provenance_failed,
        "pool_counts": summarize_sources(ttl_by_id),
    }


def _open_nquads(path: Path, mode: str = "rb"):
    """Open an N-Quads file, gzip-compressed when the name ends in ``.gz``."""
    encoding = None if "b" in mode else "utf-8"
    if str(path).endswith(".gz"):
        import gzip

        return gzip.open(str(path), mode, encoding=encoding, compresslevel=1) if "w" in mode \
            else gzip.open(str(path), mode, encoding=encoding)
    return path.open(mode.replace("t", ""), encoding=encoding)


def bulk_load_nquads(
    nq_paths: List[Path],
    oxigraph_url: str,
    *,
    chunk_lines: int = 500_000,
    retries: int = 4,
    retry_wait_s: float = 20.0,
    timeout_s: float = 1800.0,
    client: Any = None,
) -> Dict[str, int]:
    """Load N-Quads into an empty Oxigraph store through its bulk loader.

    ``POST /store?no_transaction`` makes ``oxigraph serve`` use the bulk loader,
    which writes sorted data files directly and keeps no write-ahead log. The
    transactional path (plain ``PUT``/``POST /store``) logs every quad first, and
    on the 5 GB volume that log overflowed the disk before a full load finished.

    The bulk path is not atomic, so it only loads into an empty store: wipe the
    volume (or start a fresh location) first. ``CLEAR ALL`` is not a substitute,
    because the delete goes through the log and the old data stays on disk until
    compaction. Each file is sent in ``chunk_lines`` slices so a dropped
    connection costs one slice, not the whole load. A slice is posted again after
    a failure; reposting quads already stored is harmless, a store is a set.

    Holds the rebuild lock so ``/sparql`` answers 503 while the store is partial.
    Returns lines sent and the store's quad count, and raises when the store
    does not end with exactly the lines sent (the files hold no duplicate quads:
    every case is its own named graph).
    """
    import time

    import httpx

    _run = Path(__file__).resolve().parent.parent / "run"
    if str(_run) not in sys.path:
        sys.path.insert(0, str(_run))
    from sparql_rebuild_lock import acquire_rebuild_lock, release_rebuild_lock

    base = oxigraph_url.rstrip("/")
    http = client or httpx.Client(timeout=timeout_s)

    def count() -> int:
        response = http.post(
            f"{base}/query",
            data={"query": "SELECT (COUNT(*) AS ?n) WHERE { GRAPH ?g { ?s ?p ?o } }"},
            headers={"Accept": "application/sparql-results+json"},
        )
        response.raise_for_status()
        return int(response.json()["results"]["bindings"][0]["n"]["value"])

    def post(body: bytes, label: str) -> None:
        for attempt in range(1, retries + 1):
            try:
                response = http.post(
                    f"{base}/store?no_transaction",
                    content=body,
                    headers={"Content-Type": "application/n-quads"},
                )
                if response.status_code < 400:
                    return
                error = f"HTTP {response.status_code} {response.text[:300]}"
            except httpx.HTTPError as exc:
                error = repr(exc)
            print(f"  {label}: attempt {attempt} failed: {error}", flush=True)
            if attempt < retries:
                time.sleep(retry_wait_s)
        raise RuntimeError(f"Oxigraph bulk load failed at {label} after {retries} attempts")

    before = count()
    if before:
        raise RuntimeError(
            f"Oxigraph store at {base} already holds {before} quads. The bulk loader "
            "only loads an empty store; wipe the volume first."
        )
    acquire_rebuild_lock()
    sent = 0
    try:
        for path in nq_paths:
            buf: List[bytes] = []
            with _open_nquads(path) as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    buf.append(line)
                    if len(buf) >= chunk_lines:
                        post(b"".join(buf), f"{path.name} line {sent + len(buf)}")
                        sent += len(buf)
                        buf = []
                        print(f"  {sent} quads loaded", flush=True)
            if buf:
                post(b"".join(buf), f"{path.name} line {sent + len(buf)}")
                sent += len(buf)
            print(f"  {path.name} done, {sent} quads loaded", flush=True)
        after = count()
    finally:
        release_rebuild_lock()
    if after != sent:
        raise RuntimeError(f"Oxigraph holds {after} quads after loading {sent} lines")
    return {"quads_sent": sent, "store_quads": after}


def summarize_sources(ttl_by_id: Mapping[str, Path]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for path in ttl_by_id.values():
        label = pool_label_for_path(path)
        counts[label] = counts.get(label, 0) + 1
    return counts
