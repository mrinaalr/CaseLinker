"""Every class, predicate and datatype CaseLinker writes is declared somewhere pinned (#57)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from rdflib import Graph, Literal, Namespace, RDF, URIRef

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "ontology"))
sys.path.insert(0, str(REPO / "tests"))

import ontology_fixtures as FX  # noqa: E402
from features_to_cac import CaseToCAC  # noqa: E402
from provenance_export import build_provenance_graph  # noqa: E402
from term_resolution import (  # noqa: E402
    declared_terms,
    parse_jsonld,
    undeclared_terms,
    upstream_dangling,
)

EX = Namespace("https://example.org/not-an-ontology#")


def _clean(found):
    return {kind: sorted(terms) for kind, terms in found.items() if terms}


def test_canary_undeclared_terms_are_reported():
    g = Graph()
    s = URIRef("https://w3id.org/caselinker/resource/case/canary")
    g.add((s, RDF.type, EX.MadeUpClass))
    g.add((s, EX.madeUpProperty, Literal("x", datatype=EX.madeUpType)))
    found = undeclared_terms(g)
    assert found["classes"] == {str(EX.MadeUpClass)}
    assert found["predicates"] == {str(EX.madeUpProperty)}
    assert found["datatypes"] == {str(EX.madeUpType)}


def test_pinned_ontologies_declare_what_the_mapper_relies_on():
    known = declared_terms()
    for iri in (
        "https://cacontology.projectvic.org#participatesInEvent",
        "https://cacontology.projectvic.org/hotlines#reportedBy",
        "https://cacontology.projectvic.org/legal-outcomes#DefendantRole",
        "https://cacontology.projectvic.org/temporal#AgeAtTimeSituation",
        "https://ontology.unifiedcyberontology.org/uco/core/Relationship",
        "http://www.w3.org/ns/oa#hasTarget",
        "https://w3id.org/caselinker/ns/provenance#groundStatus",
    ):
        assert iri in known, iri
    assert "https://ontology.unifiedcyberontology.org/uco/role/VictimRole" not in known


@pytest.mark.parametrize("case_id", [c["id"] for c in FX.CASES])
def test_case_graph_uses_only_declared_terms(case_id):
    graph, _ = CaseToCAC().map_case(FX.case(case_id))
    assert _clean(undeclared_terms(graph)) == {}


def test_provenance_graph_uses_only_declared_terms():
    graph = build_provenance_graph(
        FX.FULL_CASE["id"], FX.FULL_CASE_ASSERTIONS, FX.FULL_CASE_RESOLUTIONS,
        run_id="run_fixture", issued_at="2026-11-09T00:00:00Z",
        location_grounds=FX.FULL_CASE["location_grounds"],
        agency_grounds=FX.FULL_CASE["agency_grounds"],
    )
    assert _clean(undeclared_terms(graph)) == {}


def test_committed_pacer_graphs_use_only_declared_terms_and_real_iris():
    paths = sorted((REPO / "ontology" / "PACER").rglob("*.jsonld"))
    assert len(paths) >= 297
    bad, placeholder = {}, []
    for path in paths:
        g = parse_jsonld(path)
        found = _clean(undeclared_terms(g))
        if found:
            bad[path.name] = found
        if any("example.org" in str(n) for n in g.all_nodes()):
            placeholder.append(path.name)
    assert bad == {}
    assert placeholder == []


def test_upstream_dangling_references_are_reported_not_failed():
    """CAC superclasses with no UCO declaration are CAC's to fix (CAC#67), not ours."""
    dangling = upstream_dangling()
    assert any(o.endswith("/uco/role/VictimRole") for _, _, o in dangling)
