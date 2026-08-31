"""PACER JSON-LD → Turtle conversion preserves instance triples."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCTERMS

ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY = ROOT / "ontology"
if str(ONTOLOGY) not in sys.path:
    sys.path.insert(0, str(ONTOLOGY))

from pacer_jsonld_to_ttl import (  # noqa: E402
    convert_jsonld_file,
    pacer_graph_iri,
    pacer_sources,
)


def test_pacer_source_catalog_old_shape_removed():
    """Old one-file-per-case JSON-LD is gone; CASE-UCO SDK graphs live under ontology/PACER/ family folders."""
    rows = pacer_sources()
    assert rows == []


def test_convert_adds_only_metadata_triples(tmp_path: Path):
    fixture = {
        "@context": {
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
            "kb": "http://example.org/kb/",
        },
        "@graph": [
            {"@id": "kb:example-investigation", "rdfs:label": "Example"},
        ],
    }
    source = tmp_path / "doj_ceos_2025_014.jsonld"
    source.write_text(json.dumps(fixture), encoding="utf-8")
    dest = tmp_path / "pacer_doj_ceos_2025_014.ttl"
    result = convert_jsonld_file(
        source, slug="doj_ceos_2025_014", kind="paired", destination=dest
    )
    assert result["source_triples"] == 1
    assert result["added_triples"] == 2
    assert result["ttl_triples"] == 3

    out = Graph()
    out.parse(dest, format="turtle")
    graph_iri = pacer_graph_iri("doj_ceos_2025_014")
    assert (
        graph_iri,
        DCTERMS.identifier,
        Literal("pacer_doj_ceos_2025_014"),
    ) in out
    assert (
        graph_iri,
        URIRef("http://www.w3.org/ns/prov#wasDerivedFrom"),
        URIRef("https://caselinker.up.railway.app/resource/case/doj_ceos_2025_014"),
    ) in out
    assert (
        URIRef("http://example.org/kb/example-investigation"),
        URIRef("http://www.w3.org/2000/01/rdf-schema#label"),
        Literal("Example"),
    ) in out
