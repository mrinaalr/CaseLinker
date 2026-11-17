"""Shared platform/agency/location nodes must not depend on batch order (#10).

One ``CaseToCAC`` instance is reused for a whole batch (``graph_generate``).
Every case graph that references a shared IRI must carry the same full node,
so a case's per-case graph is identical whether it is mapped first or later.
"""

from __future__ import annotations

import sys
from pathlib import Path

from rdflib import Graph, Literal
from rdflib.compare import isomorphic
from rdflib.namespace import RDF, RDFS

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ontology" / "pipeline"))

from features_to_cac import (  # noqa: E402
    AZICAC_2011_006_FIXTURE,
    BASE,
    CAC_CORE,
    CAC_PLATFORMS,
    GRAPH_DETERMINISTIC,
    GRAPH_NLP,
    CaseToCAC,
)

SHARED = {
    "platforms_used": ["Mega.nz", "Signal"],
    "p2p_clients": ["LimeWire"],
    "agencies_involved": ["FBI", "NCMEC"],
    "locations": ["Mesa, Arizona"],
}


def _case(case_id: str) -> dict:
    return {**AZICAC_2011_006_FIXTURE, **SHARED, "id": case_id}


def _node(graph, uri) -> Graph:
    """All triples with ``uri`` as subject in the deterministic graph."""
    out = Graph()
    for p, o in graph.get_context(GRAPH_DETERMINISTIC).predicate_objects(uri):
        out.add((uri, p, o))
    return out


def _contexts(graph) -> dict:
    return {
        name: graph.get_context(name)
        for name in (GRAPH_DETERMINISTIC, GRAPH_NLP)
    }


def test_second_case_gets_full_platform_node():
    mapper = CaseToCAC()
    g1, _ = mapper.map_case(_case("order_a"))
    g2, _ = mapper.map_case(_case("order_b"))

    mega = BASE["platform/meganz"]
    det2 = g2.get_context(GRAPH_DETERMINISTIC)
    assert (mega, CAC_PLATFORMS.encryptionLevel, Literal("end-to-end")) in det2
    assert (mega, RDF.type, CAC_CORE.DigitalSystemEntity) in det2
    assert (mega, RDFS.label, Literal("Mega.nz")) in det2

    for uri in (
        mega,
        BASE["platform/signal"],
        BASE["platform/limewire"],
        BASE["agency/fbi"],
        BASE["agency/ncmec"],
    ):
        n1, n2 = _node(g1, uri), _node(g2, uri)
        assert len(n1) > 0, uri
        assert set(n1) == set(n2), uri


def test_per_case_graphs_identical_in_either_order():
    fwd = CaseToCAC()
    a_first, _ = fwd.map_case(_case("order_a"))
    b_second, _ = fwd.map_case(_case("order_b"))

    rev = CaseToCAC()
    b_first, _ = rev.map_case(_case("order_b"))
    a_second, _ = rev.map_case(_case("order_a"))

    for one, two in ((a_first, a_second), (b_first, b_second)):
        c1, c2 = _contexts(one), _contexts(two)
        for name in c1:
            assert len(c1[name]) == len(c2[name]), name
            assert isomorphic(c1[name], c2[name]), name
