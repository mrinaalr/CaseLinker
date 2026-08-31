#!/usr/bin/env python3
"""Convert PACER court-record JSON-LD graphs to Turtle for Oxigraph rebuild.

Each graph is written to ontology/graph_output/pacer/pacer_{slug}.ttl. The
rebuild assigns named graph
  https://caselinker.up.railway.app/resource/case/pacer_{slug}
from the filename stem (same contract as press-release TTLs).

Added triples (only):
  <graph> dcterms:identifier "pacer_{slug}"
  paired bulk: <graph> prov:wasDerivedFrom <resource/case/{slug}>
  canonical exemplars: <graph> dcterms:type "offense-family-exemplar"

Instance triples from the JSON-LD are preserved.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from rdflib import Dataset, Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, RDF

REPO_ROOT = Path(__file__).resolve().parent.parent
ONTOLOGY = Path(__file__).resolve().parent
PACER_DIR = ONTOLOGY / "PACER"
OUTPUT_DIR = ONTOLOGY / "graph_output" / "pacer"

if str(ONTOLOGY) not in sys.path:
    sys.path.insert(0, str(ONTOLOGY))

from oxigraph_rebuild import CASE_GRAPH_BASE, case_graph_iri  # noqa: E402

PROV = Namespace("http://www.w3.org/ns/prov#")

TTL_PREFIXES = {
    "dcterms": DCTERMS,
    "prov": PROV,
    "rdf": RDF,
    "rdfs": Namespace("http://www.w3.org/2000/01/rdf-schema#"),
    "xsd": Namespace("http://www.w3.org/2001/XMLSchema#"),
    "kb": Namespace("http://example.org/kb/"),
    "case-investigation": Namespace("https://ontology.caseontology.org/case/investigation/"),
    "uco-action": Namespace("https://ontology.unifiedcyberontology.org/uco/action/"),
    "uco-core": Namespace("https://ontology.unifiedcyberontology.org/uco/core/"),
    "uco-identity": Namespace("https://ontology.unifiedcyberontology.org/uco/identity/"),
    "uco-location": Namespace("https://ontology.unifiedcyberontology.org/uco/location/"),
    "uco-observable": Namespace("https://ontology.unifiedcyberontology.org/uco/observable/"),
    "uco-role": Namespace("https://ontology.unifiedcyberontology.org/uco/role/"),
    "uco-victim": Namespace("https://ontology.unifiedcyberontology.org/uco/victim/"),
    "cacontology": Namespace("https://cacontology.projectvic.org#"),
    "cac-core": Namespace("https://cacontology.projectvic.org/core#"),
    "cacontology-platforms": Namespace("https://cacontology.projectvic.org/platforms#"),
    "cacontology-sextortion": Namespace("https://cacontology.projectvic.org/sextortion#"),
    "cacontology-extremist-enterprises": Namespace("https://cacontology.projectvic.org/extremist-enterprises#"),
    "cacontology-legal-outcomes": Namespace("https://cacontology.projectvic.org/legal-outcomes#"),
    "cacontology-usa-federal-law": Namespace("https://cacontology.projectvic.org/usa-federal-law#"),
    "cacontology-multi": Namespace("https://cacontology.projectvic.org/multi-jurisdiction#"),
    "cacontology-asset-forfeiture": Namespace("https://cacontology.projectvic.org/asset-forfeiture#"),
    "cacontology-victim-impact": Namespace("https://cacontology.projectvic.org/victim-impact#"),
    "cacontology-grooming": Namespace("https://cacontology.projectvic.org/grooming#"),
    "cacontology-us-ncmec": Namespace("https://cacontology.projectvic.org/us/ncmec#"),
    "cacontology-production": Namespace("https://cacontology.projectvic.org/production#"),
    "cacontology-gufo": Namespace("https://cacontology.projectvic.org/gufo#"),
    "gufo": Namespace("http://purl.org/nemo/gufo#"),
}

CANONICAL_SLUGS = (
    "sextortion",
    "enticement",
    "enterprise",
    "trafficking",
    "production",
)

CANONICAL_JSONLD: Dict[str, Path] = {
    "sextortion": PACER_DIR / "SEXTORTION" / "sextortion.jsonld",
    "enticement": PACER_DIR / "ENTICEMENT" / "enticement.jsonld",
    "enterprise": PACER_DIR / "ENTERPRISE" / "enterprise.jsonld",
    "trafficking": PACER_DIR / "TRAFFICKING" / "trafficking.jsonld",
    "production": PACER_DIR / "PRODUCTION" / "ai" / "production.jsonld",
}

UNPAIRED_BULK_SLUGS = frozenset({"external_extortion"})


def pacer_slug(case_id: str) -> str:
    return f"pacer_{case_id.strip()}"


def pacer_graph_iri(case_id: str) -> URIRef:
    return case_graph_iri(pacer_slug(case_id))


def press_release_graph_iri(case_id: str) -> URIRef:
    return case_graph_iri(case_id)


def bulk_jsonld_paths() -> List[Tuple[str, Path]]:
    bulk = PACER_DIR / "BULK_FOLDER"
    rows: List[Tuple[str, Path]] = []
    if not bulk.is_dir():
        return rows
    for directory in sorted(p for p in bulk.iterdir() if p.is_dir()):
        path = directory / f"{directory.name}.jsonld"
        if path.is_file():
            rows.append((directory.name, path))
    return rows


def pacer_sources() -> List[Tuple[str, Path, str]]:
    """Return (slug, jsonld_path, kind) with kind in {paired, unpaired, exemplar}."""
    rows: List[Tuple[str, Path, str]] = []
    for slug, path in bulk_jsonld_paths():
        kind = "unpaired" if slug in UNPAIRED_BULK_SLUGS else "paired"
        rows.append((slug, path, kind))
    for slug in CANONICAL_SLUGS:
        path = CANONICAL_JSONLD[slug]
        if path.is_file():
            rows.append((slug, path, "exemplar"))
    return rows


def extra_triples_for(slug: str, kind: str) -> List[Tuple[URIRef, URIRef, object]]:
    graph_iri = pacer_graph_iri(slug)
    extras: List[Tuple[URIRef, URIRef, object]] = [
        (graph_iri, DCTERMS.identifier, Literal(pacer_slug(slug))),
    ]
    if kind == "paired":
        extras.append((graph_iri, PROV.wasDerivedFrom, press_release_graph_iri(slug)))
    elif kind == "exemplar":
        extras.append((graph_iri, DCTERMS.type, Literal("offense-family-exemplar")))
    return extras


def convert_jsonld_file(
    jsonld_path: Path,
    *,
    slug: Optional[str] = None,
    kind: Optional[str] = None,
    destination: Optional[Path] = None,
) -> Dict[str, object]:
    """Parse one PACER JSON-LD file and write Turtle plus graph-IRI metadata."""
    if slug is None:
        slug = jsonld_path.stem
    if kind is None:
        if slug in CANONICAL_SLUGS:
            kind = "exemplar"
        elif slug in UNPAIRED_BULK_SLUGS:
            kind = "unpaired"
        else:
            kind = "paired"
    if destination is None:
        destination = OUTPUT_DIR / f"{pacer_slug(slug)}.ttl"

    dataset = Dataset()
    dataset.parse(jsonld_path, format="json-ld")
    parsed = Graph()
    for context in dataset.graphs():
        for triple in context:
            parsed.add(triple)
    source_triples = len(parsed)

    extras = extra_triples_for(slug, kind)
    for triple in extras:
        parsed.add(triple)

    parsed.bind("dcterms", DCTERMS)
    parsed.bind("prov", PROV)
    parsed.bind("rdf", RDF)
    for prefix, ns in TTL_PREFIXES.items():
        parsed.bind(prefix, ns)

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        source_label = str(jsonld_path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        source_label = str(jsonld_path)
    header = (
        f"# Named graph: <{pacer_graph_iri(slug)}>\n"
        f"# Source JSON-LD: {source_label}\n"
        f"# kind: {kind}\n"
    )
    body = parsed.serialize(format="turtle")
    destination.write_text(header + body, encoding="utf-8")

    return {
        "slug": slug,
        "kind": kind,
        "source": str(jsonld_path),
        "destination": str(destination),
        "source_triples": source_triples,
        "ttl_triples": len(parsed),
        "added_triples": len(extras),
        "graph_iri": str(pacer_graph_iri(slug)),
    }


def convert_all(
    sources: Optional[Iterable[Tuple[str, Path, str]]] = None,
    *,
    output_dir: Optional[Path] = None,
) -> List[Dict[str, object]]:
    output_dir = output_dir or OUTPUT_DIR
    results: List[Dict[str, object]] = []
    for slug, path, kind in sources or pacer_sources():
        dest = output_dir / f"{pacer_slug(slug)}.ttl"
        results.append(convert_jsonld_file(path, slug=slug, kind=kind, destination=dest))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert PACER JSON-LD court-record graphs to Turtle for Oxigraph."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help=f"TTL destination (default: {OUTPUT_DIR})",
    )
    args = parser.parse_args()

    results = convert_all(output_dir=args.output_dir)
    if not results:
        print("No PACER JSON-LD sources found.", file=sys.stderr)
        return 1
    for row in results:
        delta = int(row["ttl_triples"]) - int(row["source_triples"])
        print(
            f"{row['slug']:28} {row['kind']:9} "
            f"jsonld={row['source_triples']:4} ttl={row['ttl_triples']:4} "
            f"+{delta} → {row['destination']}"
        )
    print(f"Wrote {len(results)} Turtle graphs → {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
