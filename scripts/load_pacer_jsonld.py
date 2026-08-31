#!/usr/bin/env python3
"""Convert CASE-UCO SDK modeled PACER JSON-LD to named-graph N-Quads; optionally POST to Oxigraph.

Each file becomes named graph ``urn:pacer:kg:<percent-encoded-relative-path>``.
This is incremental Graph Store POST — it does not replace the store.
``scripts/rebuild_oxigraph.py`` PUT does not restore these graphs.

Usage (from repo root):
  python3 scripts/load_pacer_jsonld.py
  python3 scripts/load_pacer_jsonld.py --root ontology/PACER \\
      --output ontology/cache/pacer_kg.nq
  OXIGRAPH_URL=http://oxigraph.railway.internal:7878 \\
      python3 scripts/load_pacer_jsonld.py --post
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import traceback
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote

from rdflib import Graph

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = REPO_ROOT / "ontology" / "PACER"
DEFAULT_OUTPUT = REPO_ROOT / "ontology" / "cache" / "pacer_kg.nq"

# URN NSS / pchar-safe set; encode space and anything else invalid.
IRI_SAFE = "/-._~()+,;=$&!*:@"
HEXBIN_RE = re.compile(
    r'"([0-9a-fA-F]+)"(\^\^<http://www\.w3\.org/2001/XMLSchema#hexBinary>)'
)
GRAPH_IRI_PREFIX = "urn:pacer:kg:"


def graph_iri(relpath: str) -> str:
    return GRAPH_IRI_PREFIX + quote(relpath, safe=IRI_SAFE)


def collect_hexbinary(obj, found: List[str]) -> None:
    if isinstance(obj, dict):
        typ = obj.get("@type")
        if isinstance(typ, str) and typ.endswith("hexBinary"):
            val = obj.get("@value")
            if isinstance(val, str):
                found.append(val)
        for val in obj.values():
            collect_hexbinary(val, found)
    elif isinstance(obj, list):
        for val in obj:
            collect_hexbinary(val, found)


def restore_hex(nq: str, originals: Iterable[str]) -> str:
    mapping = {orig.lower(): orig for orig in originals}

    def repl(match: re.Match[str]) -> str:
        val, dt = match.group(1), match.group(2)
        return f'"{mapping.get(val.lower(), val)}"{dt}'

    return HEXBIN_RE.sub(repl, nq)


def classify(path: Path) -> Optional[str]:
    name = path.name
    if name == "annotations.jsonld":
        return None
    if name.endswith(".extracted-content.json") or name == "extracted-content.json":
        return None
    if name.endswith("-investigation.jsonld"):
        return "investigation"
    if name.endswith(".annotations.jsonld"):
        return "annotation"
    if name.endswith(".jsonld"):
        return "document"
    return None


def to_nquads(path: Path, relpath: str) -> Tuple[str, int, int]:
    raw = path.read_text(encoding="utf-8")
    doc = json.loads(raw)
    originals: List[str] = []
    collect_hexbinary(doc, originals)

    parsed = Graph()
    parsed.parse(data=raw, format="json-ld", publicID=str(path))
    nt = parsed.serialize(format="nt")
    iri = graph_iri(relpath)
    lines = []
    for line in nt.splitlines():
        line = line.rstrip()
        if not line:
            continue
        if line.endswith(" ."):
            lines.append(f"{line[:-2]} <{iri}> .")
        elif line.endswith("."):
            lines.append(f"{line[:-1].rstrip()} <{iri}> .")
        else:
            raise ValueError(f"unexpected NT line: {line[:120]}")
    nq = "\n".join(lines)
    if lines:
        nq += "\n"
    nq = restore_hex(nq, originals)
    remaining_lower = 0
    for match in HEXBIN_RE.finditer(nq):
        val = match.group(1)
        if val != val.upper() and any(c.isalpha() for c in val):
            remaining_lower += 1
    return nq, len(parsed), remaining_lower


def collect_sources(root: Path) -> Tuple[Dict[str, List[Tuple[Path, str]]], List[str]]:
    buckets: Dict[str, List[Tuple[Path, str]]] = {
        "document": [],
        "investigation": [],
        "annotation": [],
    }
    skipped: List[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if "processed" in path.parts:
            continue
        rel = path.relative_to(root).as_posix()
        kind = classify(path)
        if kind is None:
            if path.suffix in {".jsonld", ".json"}:
                skipped.append(rel)
            continue
        buckets[kind].append((path, rel))
    return buckets, skipped


def convert_tree(root: Path, destination: Path) -> Dict[str, object]:
    """Write one N-Quads file for every classified JSON-LD under *root*."""
    buckets, skipped = collect_sources(root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest: Dict[str, object] = {
        "counts": {k: len(v) for k, v in buckets.items()},
        "skipped": skipped,
        "failures": [],
        "graphs": [],
        "lowercase_remaining": 0,
        "quads": 0,
        "destination": str(destination),
    }
    failures: List[Dict[str, str]] = []
    graphs: List[Dict[str, object]] = []
    quads = 0
    lowercase_remaining = 0
    with destination.open("w", encoding="utf-8") as handle:
        for kind, rows in buckets.items():
            for path, rel in rows:
                try:
                    nq, triples, lower_left = to_nquads(path, rel)
                except Exception as exc:
                    err = f"{type(exc).__name__}: {exc}"
                    failures.append({"file": rel, "error": err})
                    print(f"FAIL {kind} {rel}: {err}", flush=True)
                    traceback.print_exc()
                    continue
                handle.write(nq)
                quads += triples
                lowercase_remaining += lower_left
                graphs.append(
                    {
                        "kind": kind,
                        "file": rel,
                        "iri": graph_iri(rel),
                        "triples": triples,
                    }
                )
    manifest["failures"] = failures
    manifest["graphs"] = graphs
    manifest["quads"] = quads
    manifest["lowercase_remaining"] = lowercase_remaining
    return manifest


def post_nquads(nq_path: Path, oxigraph_url: str, *, timeout_s: float = 300.0) -> None:
    """Incrementally add quads via Graph Store POST /store. Does not replace."""
    import httpx

    base = oxigraph_url.rstrip("/")
    url = f"{base}/store"
    with nq_path.open("rb") as handle:
        response = httpx.post(
            url,
            content=handle,
            headers={"Content-Type": "application/n-quads"},
            timeout=timeout_s,
        )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Oxigraph POST {url} failed: HTTP {response.status_code} {response.text[:2000]}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert PACER JSON-LD to N-Quads; optionally POST to Oxigraph."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help=f"JSON-LD tree (default: {DEFAULT_ROOT})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"N-Quads destination (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--post",
        action="store_true",
        help="POST the N-Quads to OXIGRAPH_URL/store (incremental; not a wholesale PUT)",
    )
    parser.add_argument(
        "--oxigraph-url",
        default=os.environ.get("OXIGRAPH_URL", "").strip(),
        help="Oxigraph base URL (default: env OXIGRAPH_URL)",
    )
    args = parser.parse_args()

    if not args.root.is_dir():
        print(f"JSON-LD root not found: {args.root}", file=sys.stderr)
        return 1

    print(f"Converting {args.root} → {args.output}", flush=True)
    manifest = convert_tree(args.root, args.output)
    print(
        f"classified {manifest['counts']} skipped {len(manifest['skipped'])} "
        f"quads={manifest['quads']} failed={len(manifest['failures'])} "
        f"lowercase_remaining={manifest['lowercase_remaining']}",
        flush=True,
    )
    if manifest["failures"]:
        return 1

    if args.post:
        if not args.oxigraph_url:
            print("OXIGRAPH_URL / --oxigraph-url is required for --post", file=sys.stderr)
            return 1
        print(f"POST {args.output} → {args.oxigraph_url.rstrip('/')}/store", flush=True)
        post_nquads(args.output, args.oxigraph_url)
        print("Oxigraph store updated (incremental POST).", flush=True)
    else:
        print("Skipping POST (pass --post with OXIGRAPH_URL to upload).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
