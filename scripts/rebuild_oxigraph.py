#!/usr/bin/env python3
"""Wholesale Oxigraph reload from canonical case2cac Turtle graphs.

Rebuilds the triplestore by writing one N-Quads file (named graph per case) and
PUT-replacing /store. Not incremental.

Usage (from repo root):
  python3 scripts/rebuild_oxigraph.py
  python3 scripts/rebuild_oxigraph.py --output /tmp/caselinker.nq --no-put
  OXIGRAPH_URL=http://oxigraph.railway.internal:7878 python3 scripts/rebuild_oxigraph.py
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
    canonical_ttl_paths,
    put_nquads,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build canonical per-case N-Quads and wholesale-replace Oxigraph /store."
    )
    parser.add_argument(
        "--graph-root",
        type=Path,
        default=GRAPH_ROOT,
        help="ontology/graph_output directory (default: repo ontology/graph_output)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_NQ,
        help=f"N-Quads output path (default: {DEFAULT_NQ})",
    )
    put_group = parser.add_mutually_exclusive_group()
    put_group.add_argument(
        "--put",
        action="store_true",
        help="PUT the N-Quads to OXIGRAPH_URL/store (also the default when OXIGRAPH_URL is set)",
    )
    put_group.add_argument(
        "--no-put",
        action="store_true",
        help="Build N-Quads only; do not contact Oxigraph",
    )
    parser.add_argument(
        "--oxigraph-url",
        default=os.environ.get("OXIGRAPH_URL", "").strip(),
        help="Oxigraph base URL (default: env OXIGRAPH_URL)",
    )
    args = parser.parse_args()

    ttl_by_id = canonical_ttl_paths(args.graph_root)
    if not ttl_by_id:
        print(f"No Turtle graphs under {args.graph_root}", file=sys.stderr)
        return 1

    print(
        f"Canonical TTL files: {len(ttl_by_id)} "
        f"(priority universe > staging > big_bang > analysis)",
        flush=True,
    )
    result = build_nquads(ttl_by_id, args.output)
    print(
        f"Wrote {result['quads']} quads from {result['cases_loaded']}/{result['cases_requested']} "
        f"cases → {result['destination']}",
        flush=True,
    )
    print(f"Source pools: {result['pool_counts']}", flush=True)
    failed = result.get("failed") or []
    if failed:
        print(f"Failed parses: {len(failed)}", file=sys.stderr)
        for row in failed[:10]:
            print(f"  {row['case_id']}: {row['reason']}", file=sys.stderr)

    if args.no_put:
        do_put = False
    elif args.put:
        do_put = True
    else:
        do_put = bool(args.oxigraph_url)

    if do_put:
        if not args.oxigraph_url:
            print("OXIGRAPH_URL / --oxigraph-url is required for --put", file=sys.stderr)
            return 1
        print(f"PUT {args.output} → {args.oxigraph_url.rstrip('/')}/store", flush=True)
        put_nquads(args.output, args.oxigraph_url)
        print("Oxigraph store replaced.", flush=True)
    else:
        print("Skipping PUT (pass --put with OXIGRAPH_URL, or omit --no-put when the env is set).")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
