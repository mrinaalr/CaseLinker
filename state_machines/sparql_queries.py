"""SPARQL transition-function queries over CAC-native PACER state machine graphs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rdflib import ConjunctiveGraph, Graph, URIRef
from rdflib.namespace import RDF, RDFS

from state_machines.iris import (
    AFFORDANCE_CLASS,
    AFFORDANCE_MISUSE,
    CAC_INVESTIGATION,
    CASE_FILES,
    DISRUPTED_TARGET,
    DISRUPTS_CHAIN,
    ENABLES_TRANSITION_FROM,
    ENABLES_TRANSITION_TO,
    HAS_STEP,
    MISUSE_DESCRIPTION,
    PHASE,
    PRECEDES,
    GRAPHS_DIR,
    local_name,
)

QUERY_PHASES = """
PREFIX cac-core: <https://cacontology.projectvic.org/core#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?case_graph ?phase ?phase_type
WHERE {
  GRAPH ?case_graph {
    ?phase rdf:type ?phase_type .
    ?phase_type rdfs:subClassOf* cac-core:Phase .
  }
}
ORDER BY ?case_graph ?phase
"""

QUERY_TRANSITION_MATRIX = """
PREFIX cac-core: <https://cacontology.projectvic.org/core#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?from_type ?to_type (COUNT(DISTINCT ?case_graph) AS ?case_count)
WHERE {
  GRAPH ?case_graph {
    ?from_phase rdf:type ?from_type .
    ?to_phase rdf:type ?to_type .
    ?from_phase cac-core:precedes ?to_phase .
  }
  FILTER(?from_type != cac-core:Phase && ?to_type != cac-core:Phase)
}
GROUP BY ?from_type ?to_type
ORDER BY DESC(?case_count)
"""

QUERY_AFFORDANCE_ANNOTATIONS = """
PREFIX cac-platforms: <https://cacontology.projectvic.org/platforms#>
PREFIX cac-core: <https://cacontology.projectvic.org/core#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?from_type ?to_type ?affordance_class (COUNT(DISTINCT ?case_graph) AS ?case_count)
WHERE {
  GRAPH ?case_graph {
    ?misuse rdf:type cac-platforms:AffordanceMisuse .
    ?misuse cac-platforms:enablesTransitionFrom ?from_phase .
    ?misuse cac-platforms:enablesTransitionTo ?to_phase .
    ?from_phase rdf:type ?from_type .
    ?to_phase rdf:type ?to_type .
    ?misuse cac-platforms:affordanceClass ?affordance_class .
  }
  FILTER(?from_type != cac-core:Phase && ?to_type != cac-core:Phase)
}
GROUP BY ?from_type ?to_type ?affordance_class
ORDER BY DESC(?case_count)
"""


def load_state_machine_graphs(
    directory: Path | None = None,
    filenames: tuple[str, ...] = CASE_FILES,
) -> ConjunctiveGraph:
    """Load JSON-LD case graphs into a ConjunctiveGraph (one named graph per file)."""
    directory = directory or GRAPHS_DIR
    cg = ConjunctiveGraph(identifier=URIRef("urn:caselinker:state-machines"))
    for filename in filenames:
        path = directory / filename
        graph_uri = URIRef(f"urn:caselinker:case:{path.stem}")
        g = Graph()
        g.parse(data=path.read_text(encoding="utf-8"), format="json-ld")
        ctx = cg.get_context(graph_uri)
        for triple in g:
            ctx.add(triple)
    return cg


def known_case_graph_uris(
    filenames: tuple[str, ...] = CASE_FILES,
) -> list[URIRef]:
    return [URIRef(f"urn:caselinker:case:{Path(f).stem}") for f in filenames]


def _rows(graph: ConjunctiveGraph, query: str) -> list[dict[str, Any]]:
    return [
        {str(k): v for k, v in row.asdict().items()}
        for row in graph.query(query)
    ]


def query_phases_per_case(graph: ConjunctiveGraph) -> list[dict[str, Any]]:
    return _rows(graph, QUERY_PHASES)


def query_transition_matrix(graph: ConjunctiveGraph) -> list[dict[str, Any]]:
    return _rows(graph, QUERY_TRANSITION_MATRIX)


def query_affordance_annotations(graph: ConjunctiveGraph) -> list[dict[str, Any]]:
    return _rows(graph, QUERY_AFFORDANCE_ANNOTATIONS)


def weighted_transition_matrix(
    graph: ConjunctiveGraph,
    filenames: tuple[str, ...] = CASE_FILES,
) -> tuple[dict[tuple[str, str], float], int]:
    """Observed phase chain P̂(s_j | s_i) from step counts, and N case graphs.

    Row-normalised over the steps that leave s_i (state_machines/README.md).
    """
    from state_machines.estimators import phase_chain, step_counts, steps_from_case

    steps = []
    graphs = known_case_graph_uris(filenames)
    for cgu in graphs:
        uris = ordered_phase_sequence(graph, cgu)
        types = [phase_type_for_instance(graph, cgu, u) for u in uris]
        tags = [affordance_on_arrival(graph, cgu, u)[0] for u in uris]
        keep = [i for i, t in enumerate(types) if t is not None]
        steps.extend(steps_from_case(str(cgu), [types[i] for i in keep], [tags[i] for i in keep]))
    return phase_chain(step_counts(steps)), len(graphs)


def _ctx(cg: ConjunctiveGraph, case_graph: URIRef) -> Graph:
    return cg.get_context(case_graph)


def _phase_nodes_in_graph(cg: ConjunctiveGraph, case_graph: URIRef) -> set[str]:
    ctx = _ctx(cg, case_graph)
    nodes: set[str] = set()
    for inv in ctx.subjects(RDF.type, URIRef(CAC_INVESTIGATION)):
        for step in ctx.objects(inv, URIRef(HAS_STEP)):
            nodes.add(str(step))
    for s, _, o in ctx.triples((None, URIRef(PRECEDES), None)):
        nodes.add(str(s))
        nodes.add(str(o))
    return nodes


def ordered_phase_sequence(cg: ConjunctiveGraph, case_graph: URIRef) -> list[str]:
    """
    Follow cac-core:precedes from the node with no incoming edge to the terminal node.
    Includes all hasStep nodes in traversal order.
    """
    nodes = _phase_nodes_in_graph(cg, case_graph)
    if not nodes:
        return []

    incoming: dict[str, set[str]] = {n: set() for n in nodes}
    outgoing: dict[str, str | None] = {n: None for n in nodes}

    ctx = _ctx(cg, case_graph)
    for s, _, o in ctx.triples((None, URIRef(PRECEDES), None)):
        s_id, o_id = str(s), str(o)
        if s_id in nodes and o_id in nodes:
            incoming[o_id].add(s_id)
            outgoing[s_id] = o_id

    starts = [n for n in nodes if not incoming[n]]
    if not starts:
        return sorted(nodes)
    if len(starts) > 1:
        step_order = []
        for inv in ctx.subjects(RDF.type, URIRef(CAC_INVESTIGATION)):
            step_order.extend(str(s) for s in ctx.objects(inv, URIRef(HAS_STEP)))
        starts.sort(key=lambda n: step_order.index(n) if n in step_order else 999)
    start = starts[0]

    sequence: list[str] = []
    current: str | None = start
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        sequence.append(current)
        current = outgoing.get(current)

    return sequence


def phase_type_for_instance(cg: ConjunctiveGraph, case_graph: URIRef, phase_uri: str) -> str | None:
    ctx = _ctx(cg, case_graph)
    skip = {
        str(RDF.Property),
        str(RDFS.Resource),
        "http://www.w3.org/2002/07/owl#NamedIndividual",
    }
    types = [
        str(t)
        for _, _, t in ctx.triples((URIRef(phase_uri), RDF.type, None))
        if str(t) not in skip and not str(t).endswith("AffordanceMisuse")
    ]
    if not types:
        return None
    specific = [t for t in types if t != PHASE]
    return specific[0] if specific else types[0]


def ordered_type_sequence(cg: ConjunctiveGraph, case_graph: URIRef) -> list[str]:
    return [
        t
        for uri in ordered_phase_sequence(cg, case_graph)
        if (t := phase_type_for_instance(cg, case_graph, uri)) is not None
    ]


def affordance_on_arrival(
    cg: ConjunctiveGraph,
    case_graph: URIRef,
    phase_uri: str,
) -> tuple[str | None, str | None]:
    """Return (affordance_class_iri, misuse_description) for transition into phase_uri."""
    ctx = _ctx(cg, case_graph)
    for misuse in ctx.subjects(RDF.type, URIRef(AFFORDANCE_MISUSE)):
        target = ctx.value(misuse, URIRef(ENABLES_TRANSITION_TO))
        if target and str(target) == phase_uri:
            aff = ctx.value(misuse, URIRef(AFFORDANCE_CLASS))
            desc = ctx.value(misuse, URIRef(MISUSE_DESCRIPTION))
            return (str(aff) if aff else None, str(desc) if desc else None)
    return None, None


def phase_metadata(
    cg: ConjunctiveGraph,
    case_graph: URIRef,
    phase_uri: str,
) -> dict[str, str | None]:
    ctx = _ctx(cg, case_graph)
    node = URIRef(phase_uri)
    label = ctx.value(node, RDFS.label)
    comment = ctx.value(node, RDFS.comment)
    ptype = phase_type_for_instance(cg, case_graph, phase_uri)
    disrupts = ctx.value(node, URIRef(DISRUPTS_CHAIN))
    disrupted = ctx.value(node, URIRef(DISRUPTED_TARGET))
    disrupts_chain = disrupts is not None and str(disrupts).lower() in ("true", "1")
    return {
        "uri": phase_uri,
        "type": ptype,
        "label": str(label) if label else None,
        "comment": str(comment) if comment else None,
        "disrupts_chain": disrupts_chain,
        "disrupted_target": str(disrupted) if disrupted else None,
    }


def case_graphs(
    cg: ConjunctiveGraph,
    filenames: tuple[str, ...] = CASE_FILES,
) -> list[URIRef]:
    return known_case_graph_uris(filenames)
