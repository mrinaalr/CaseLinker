#!/usr/bin/env python3
"""Rebuild the Oxigraph triplestore from the canonical case graphs.

Writes one N-Quads file (each case and its provenance sidecar as named graphs),
then bulk-loads it, plus any ``--extra-nq`` files such as the PACER graphs, into
an empty store with ``POST /store?no_transaction``. The bulk loader writes data
files directly and keeps no write-ahead log, so a full corpus fits the 5 GB
Railway volume. The store must be empty: wipe the volume first.

Usage (from repo root):
  python3 scripts/rebuild_oxigraph.py --output /tmp/caselinker.nq.gz --no-load
  OXIGRAPH_URL=http://oxigraph.railway.internal:7878 python3 scripts/rebuild_oxigraph.py \\
      --output /tmp/caselinker.nq.gz --skip-build --extra-nq /tmp/pacer.nq.gz
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "ontology"))

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

    if args.no_load:
        print("Built N-Quads only (--no-load).")
        return 0
    paths = [args.output, *args.extra_nq]
    print(f"Bulk-loading {', '.join(p.name for p in paths)} → {args.oxigraph_url.rstrip('/')}/store", flush=True)
    loaded = bulk_load_nquads(paths, args.oxigraph_url, chunk_lines=args.chunk_lines)
    print(f"Oxigraph store loaded: {loaded['store_quads']} quads.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
