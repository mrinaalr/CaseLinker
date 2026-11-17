#!/usr/bin/env python3
"""Rebuild the Oxigraph triplestore from the canonical case graphs.

Writes one N-Quads file (each case and its provenance sidecar as named graphs),
then bulk-loads it, plus any ``--extra-nq`` files such as the PACER graphs, into
an empty store with ``POST /store?no_transaction``. The bulk loader writes data
files directly and keeps no write-ahead log, so a full corpus fits the 5 GB
Railway volume. The store must be empty: wipe the volume first.

PACER court-record graphs come from a release built by state_machines/graphs/release.py.
``--pacer-release <id>`` writes that release's N-Quads (named graphs
urn:caselinker:pacer:<case_id>:evidence|trajectories) and loads them with the corpus.
``--verify`` checks the loaded store against the release manifest: every PACER graph
present and non-empty, nothing outside the release, no superseded urn:pacer:kg graphs,
and at least ``--min-case-graphs`` press-release case graphs.

Usage (from repo root):
  python3 scripts/oxigraph/rebuild_oxigraph.py --output /tmp/caselinker.nq.gz --no-load \\
      --pacer-release pacer-v1
  OXIGRAPH_URL=http://localhost:7878 python3 scripts/oxigraph/rebuild_oxigraph.py \\
      --output /tmp/caselinker.nq.gz --skip-build --pacer-release pacer-v1 --verify
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "ontology" / "pipeline"))
sys.path.insert(0, str(REPO_ROOT))

from oxigraph_rebuild import (  # noqa: E402
    DEFAULT_NQ,
    GRAPH_ROOT,
    build_nquads,
    bulk_load_nquads,
    canonical_ttl_paths,
)


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build canonical per-case N-Quads and bulk-load them into an empty Oxigraph store."
    )
    parser.add_argument("--graph-root", type=Path, default=GRAPH_ROOT,
                        help="ontology/graph_output directory (default: repo ontology/graph_output)")
    parser.add_argument("--output", type=Path, default=DEFAULT_NQ,
                        help=f"N-Quads path, gzip when it ends in .gz (default: {DEFAULT_NQ})")
    parser.add_argument("--skip-build", action="store_true",
                        help="load the existing --output file instead of rebuilding it")
    parser.add_argument("--extra-nq", type=Path, action="append", default=[],
                        help="another N-Quads file to load after the case graphs (repeatable), e.g. PACER")
    parser.add_argument("--pacer-release", default="",
                        help="PACER release id under state_machines/data/ to export and load (urn:caselinker:pacer:*)")
    parser.add_argument("--verify", action="store_true",
                        help="after loading, check the store against the PACER release manifest via SPARQL")
    parser.add_argument("--min-case-graphs", type=int, default=1,
                        help="with --verify: fewest press-release case graphs the store must hold")
    parser.add_argument("--no-load", action="store_true", help="build N-Quads only; do not contact Oxigraph")
    parser.add_argument("--oxigraph-url", default=os.environ.get("OXIGRAPH_URL", "").strip(),
                        help="Oxigraph base URL (default: env OXIGRAPH_URL)")
    parser.add_argument("--chunk-lines", type=int, default=500_000, help="quads per bulk POST")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if not args.no_load:
        if not args.oxigraph_url:
            print("OXIGRAPH_URL / --oxigraph-url is required to load (or pass --no-load)", file=sys.stderr)
            return 1
        missing = [p for p in args.extra_nq if not p.is_file()]
        if missing:
            print(f"--extra-nq not found: {', '.join(map(str, missing))}", file=sys.stderr)
            return 1
    failed = []
    if args.skip_build:
        if not args.output.is_file():
            print(f"--skip-build: {args.output} does not exist", file=sys.stderr)
            return 1
    else:
        ttl_by_id = canonical_ttl_paths(args.graph_root)
        if not ttl_by_id:
            print(f"No Turtle graphs under {args.graph_root}", file=sys.stderr)
            return 1
        print(f"Canonical TTL files: {len(ttl_by_id)} "
              f"(priority universe > staging > big_bang > analysis > pacer)", flush=True)
        result = build_nquads(ttl_by_id, args.output)
        print(f"Wrote {result['quads']} quads from {result['cases_loaded']}/{result['cases_requested']} "
              f"cases and {result['provenance_loaded']} provenance graphs → {result['destination']}", flush=True)
        print(f"Source pools: {result['pool_counts']}", flush=True)
        failed = list(result.get("failed") or []) + list(result.get("provenance_failed") or [])
        if failed:
            print(f"Failed parses: {len(failed)}", file=sys.stderr)
            for row in failed[:10]:
                print(f"  {row['case_id']}: {row['reason']}", file=sys.stderr)
            return 1

    pacer_nq, manifest = None, None
    if args.pacer_release:
        from state_machines.graphs.release import DATA, nquads
        manifest_path = DATA / args.pacer_release / "manifest.json"
        if not manifest_path.is_file():
            print(f"--pacer-release: no manifest at {manifest_path}; build the release first", file=sys.stderr)
            return 1
        import json
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not manifest.get("adjudicated"):
            print(f"WARNING: release {args.pacer_release} is not adjudicated (preview)", file=sys.stderr)
        pacer_nq = nquads(args.pacer_release)
        print(f"PACER release {args.pacer_release}: {len(manifest['cases'])} cases → {pacer_nq}", flush=True)
    if args.no_load:
        print("Built N-Quads only (--no-load).")
        return 0
    paths = [args.output, *args.extra_nq, *([pacer_nq] if pacer_nq else [])]
    print(f"Bulk-loading {', '.join(p.name for p in paths)} → {args.oxigraph_url.rstrip('/')}/store", flush=True)
    loaded = bulk_load_nquads(paths, args.oxigraph_url, chunk_lines=args.chunk_lines)
    print(f"Oxigraph store loaded: {loaded['store_quads']} quads.", flush=True)
    if args.verify:
        if manifest is None:
            print("--verify needs --pacer-release", file=sys.stderr)
            return 1
        from state_machines.graphs.release import verify_store
        problems = verify_store(manifest, lambda q: sparql_select(args.oxigraph_url, q), min_case_graphs=args.min_case_graphs)
        for p in problems:
            print(f"VERIFY: {p}", file=sys.stderr)
        if problems:
            return 1
        print("Verified: PACER graphs match the release manifest.", flush=True)
    return 0


def sparql_select(base_url: str, query: str) -> list:
    """SPARQL SELECT against Oxigraph; bindings as {var: plain string}."""
    import json
    import urllib.parse
    import urllib.request

    req = urllib.request.Request(base_url.rstrip("/") + "/query", data=urllib.parse.urlencode({"query": query}).encode(),
                                 headers={"Accept": "application/sparql-results+json",
                                          "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.load(resp)
    return [{k: v["value"] for k, v in row.items()} for row in data["results"]["bindings"]]


if __name__ == "__main__":
    raise SystemExit(main())
