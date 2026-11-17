"""In-memory CAC graph helpers for MCP traversal (no REST exposure)."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from itertools import combinations
from typing import Any, Dict, List, Set, Tuple

RESERVED_KEYS = frozenset({"@id", "@type", "@context", "_isNlp", "_cases", "_isShared"})
_FLAT_NODE_META_KEYS = frozenset({"_cases", "_isShared", "_isNlp"})

# Graph tools answer "which CAC concepts / affordances do cases share in this
# session graph", not "which cases involve similar criminal conduct" (#28).
# In current mapper output only platform, agency and location nodes carry an
# IRI shared across cases; events, roles and charges are per-case nodes. So the
# only edges between two cases run through a shared platform, agency or location.
INTERPRETATION_GRAPH = "cac_concept_graph"
INTERPRETATION_NEIGHBORS = "cac_graph_adjacency"
INTERPRETATION_CONCEPT_MATCH = "cac_concept_match"
INTERPRETATION_SUMMARY = "cac_concept_cooccurrence"
INTERPRETATION_COMPARE = "cac_concept_overlap"

NOT_CONDUCT_SIMILARITY_NOTE = (
    "Shared CAC ontology concepts / affordances within the case2cac session graph only. "
    "Not a conduct-similarity score and not a same-offense cohort: cases are linked only "
    "through shared platform, agency or location nodes, or by carrying the same mapped CAC "
    "class. For a conduct cohort, filter with filter_cases_by_tags (topics, platforms, "
    "severity, investigation type), get_case_ids_by_filter (perpetrator age_range, year) "
    "and get_cohort_members (locations / agencies with case_ids)."
)


def interpretation_fields(kind: str) -> Dict[str, str]:
    """Self-describing fields added to every graph tool response (#28)."""
    return {"interpretation_kind": kind, "interpretation_note": NOT_CONDUCT_SIMILARITY_NOTE}


SPINE_BASES = re.compile(
    r"^(EnduringEntity|Occurrent|Event|Role|Phase|Situation|"
    r"OrganizationLikeEntity|DigitalSystemEntity|PersonLikeEntity|CustodialRelationship)$"
)


def local_name(uri: str) -> str:
    if not uri:
        return uri
    h = uri.rfind("#")
    s = uri.rfind("/")
    return uri[max(h, s) + 1 :] or uri


def short_prop_key(uri: str) -> str:
    if not uri or uri.startswith("@"):
        return uri
    return local_name(uri)


def short_type(type_val: Any) -> str:
    if not type_val:
        return "Entity"
    arr = type_val if isinstance(type_val, list) else [type_val]
    domain = next((t for t in arr if not SPINE_BASES.match(local_name(str(t)))), None)
    return local_name(str(domain or arr[0]))


def _first_literal(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, list):
        if not val:
            return None
        val = val[0]
    if isinstance(val, dict) and "@value" in val:
        return val["@value"]
    if isinstance(val, dict) and "@id" in val:
        return None
    return val


def node_label(node: Dict[str, Any]) -> str:
    for key, val in node.items():
        if local_name(str(key)) == "label" and _first_literal(val) is not None:
            return str(_first_literal(val))

    node_id = str(node.get("@id") or "")
    path = node_id.split("/resource/")[-1] if "/resource/" in node_id else local_name(node_id)
    st = short_type(node.get("@type"))

    for key, val in node.items():
        ln = local_name(str(key))
        if re.search(r"ageEstimate|victimAge", ln):
            age = _first_literal(val)
            if age is not None:
                if "victim" in path:
                    return f"Victim (age {age})"
                n = re.search(r"offender/(\d+)", path)
                return f"Offender {n.group(1) if n else ''} (age {age})".strip()

    if "/nlp/" in path and "confidence" not in path:
        return f"NLP · {st}"
    if re.fullmatch(r"case/[^/]+", path):
        return f"Investigation: {path.replace('case/', '')}"

    path_labels = {
        "role/victim/1": "Victim (role)",
        "role/offender/1": "Offender 1 (role)",
        "event/production": "CSAM Production",
        "event/csam": "CSAM Incident",
        "event/hands-on": "Contact Offense",
        "operation": "Proactive Op.",
    }
    for fragment, name in path_labels.items():
        if path.endswith(fragment):
            return name
    return st or path


def flat_nodes_to_nodes_edges(flat_nodes: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    id_set = {n["@id"] for n in flat_nodes if n.get("@id")}
    nodes: List[Dict[str, Any]] = []
    for n in flat_nodes:
        nid = n.get("@id")
        if not nid:
            continue
        types = n.get("@type")
        types_list = types if isinstance(types, list) else ([types] if types else [])
        nodes.append(
            {
                "node_id": nid,
                "node_type": short_type(types_list),
                "label": node_label(n),
                "types": [str(t) for t in types_list],
                "is_shared": bool(n.get("_isShared")),
                "cases": list(n.get("_cases") or []),
                "is_nlp": bool(n.get("_isNlp")),
            }
        )

    edges: List[Dict[str, Any]] = []
    for src in flat_nodes:
        sid = src.get("@id")
        if not sid:
            continue
        for key, val in src.items():
            if key in RESERVED_KEYS:
                continue
            refs: List[Dict[str, Any]] = []
            if isinstance(val, dict) and val.get("@id"):
                refs.append(val)
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, dict) and item.get("@id"):
                        refs.append(item)
            for ref in refs:
                tid = ref["@id"]
                if tid in id_set:
                    edges.append(
                        {
                            "source": sid,
                            "target": tid,
                            "relationship": short_prop_key(str(key)),
                            "property": str(key),
                        }
                    )
    return nodes, edges


def cac_classes_from_node(node: Dict[str, Any]) -> List[str]:
    types = node.get("@type")
    arr = types if isinstance(types, list) else ([types] if types else [])
    out: List[str] = []
    for t in arr:
        name = local_name(str(t))
        if name and not SPINE_BASES.match(name):
            out.append(name)
    return out


def build_adjacency(edges: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    adj: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    node_lookup: Dict[str, Dict[str, Any]] = {}
    for e in edges:
        adj[e["source"]].append(
            {
                "node_id": e["target"],
                "relationship": e["relationship"],
                "direction": "out",
            }
        )
        adj[e["target"]].append(
            {
                "node_id": e["source"],
                "relationship": e["relationship"],
                "direction": "in",
            }
        )
    _ = node_lookup
    return adj


def enrich_neighbors(
    graph: Dict[str, Any],
    node_id: str,
) -> List[Dict[str, Any]]:
    if node_id not in graph.get("node_index", {}):
        return []
    adj = graph.get("adjacency") or {}
    node_index = graph["node_index"]
    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for item in adj.get(node_id, []):
        nid = item["node_id"]
        if nid in seen:
            continue
        seen.add(nid)
        n = node_index.get(nid, {})
        out.append(
            {
                "node_id": nid,
                "node_type": n.get("node_type", "Entity"),
                "label": n.get("label", nid),
                "relationship": item["relationship"],
                "direction": item["direction"],
            }
        )
    return out


def summarize_graph(graph: Dict[str, Any]) -> Dict[str, Any]:
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    flat_nodes = graph.get("flat_nodes") or []

    type_counts: Counter[str] = Counter()
    edge_type_counts: Counter[str] = Counter()
    concept_counts: Counter[str] = Counter()
    degrees: Counter[str] = Counter()

    for n in nodes:
        type_counts[n.get("node_type") or "Entity"] += 1
    for e in edges:
        edge_type_counts[e.get("relationship") or "related"] += 1
        degrees[e["source"]] += 1
        degrees[e["target"]] += 1

    for fn in flat_nodes:
        for cls in cac_classes_from_node(fn):
            concept_counts[cls] += 1

    top_bridges = sorted(
        (
            {
                "node_id": n["node_id"],
                "label": n.get("label"),
                "node_type": n.get("node_type"),
                "degree": degrees.get(n["node_id"], 0),
            }
            for n in nodes
        ),
        key=lambda x: x["degree"],
        reverse=True,
    )[:10]

    case_concepts: Dict[str, Set[str]] = defaultdict(set)
    for fn in flat_nodes:
        for case_id in fn.get("_cases") or []:
            for cls in cac_classes_from_node(fn):
                case_concepts[case_id].add(cls)

    pair_counts: Counter[tuple[str, str]] = Counter()
    for concepts in case_concepts.values():
        for a, b in combinations(sorted(concepts), 2):
            pair_counts[(a, b)] += 1

    concept_cooccurrence = [
        {"concepts": [a, b], "case_count": c}
        for (a, b), c in pair_counts.most_common(10)
    ]

    mapped_cases = graph.get("metadata", {}).get("cases_mapped") or []
    return {
        "node_count_by_type": dict(type_counts.most_common()),
        "top_bridge_nodes": top_bridges,
        "concept_cooccurrence": concept_cooccurrence,
        "edge_type_distribution": dict(edge_type_counts.most_common()),
        "case_coverage": {
            "cases_requested": graph.get("metadata", {}).get("requested_count", 0),
            "cases_mapped": len(mapped_cases),
            "cases_with_nodes": len(case_concepts),
        },
        "totals": {
            "nodes": len(nodes),
            "edges": len(edges),
        },
        **interpretation_fields(INTERPRETATION_SUMMARY),
    }


def find_cases_by_concept(graph: Dict[str, Any], concept: str) -> Dict[str, Any]:
    needle = concept.strip().lower()
    if not needle:
        return {"error": "concept is required"}

    flat_nodes = graph.get("flat_nodes") or []
    matched_nodes: List[Dict[str, Any]] = []
    matched_cases: Set[str] = set()

    for fn in flat_nodes:
        nid = str(fn.get("@id") or "")
        label = node_label(fn)
        types = " ".join(cac_classes_from_node(fn)).lower()
        hay = f"{nid} {label} {types}".lower()
        if needle in hay:
            matched_nodes.append(
                {
                    "node_id": nid,
                    "label": label,
                    "type": short_type(fn.get("@type")),
                }
            )
            for case_id in fn.get("_cases") or []:
                matched_cases.add(str(case_id))

    return {
        "concept": concept,
        "matched_cases": sorted(matched_cases),
        "match_count": len(matched_cases),
        "matched_nodes": matched_nodes[:50],
        **interpretation_fields(INTERPRETATION_CONCEPT_MATCH),
    }


def compare_graphs(graph_a: Dict[str, Any], graph_b: Dict[str, Any]) -> Dict[str, Any]:
    flat_a = graph_a.get("flat_nodes") or []
    flat_b = graph_b.get("flat_nodes") or []

    concepts_a: Set[str] = set()
    concepts_b: Set[str] = set()
    cases_a: Set[str] = set()
    cases_b: Set[str] = set()
    ids_a: Set[str] = set()
    ids_b: Set[str] = set()

    for fn in flat_a:
        ids_a.add(str(fn.get("@id") or ""))
        for cls in cac_classes_from_node(fn):
            concepts_a.add(cls)
        for cid in fn.get("_cases") or []:
            cases_a.add(str(cid))

    for fn in flat_b:
        ids_b.add(str(fn.get("@id") or ""))
        for cls in cac_classes_from_node(fn):
            concepts_b.add(cls)
        for cid in fn.get("_cases") or []:
            cases_b.add(str(cid))

    ids_a.discard("")
    ids_b.discard("")
    shared_ids = ids_a & ids_b
    union_ids = ids_a | ids_b
    jaccard = len(shared_ids) / len(union_ids) if union_ids else 0.0

    shared_concepts = sorted(concepts_a & concepts_b)
    unique_a = sorted(concepts_a - concepts_b)
    unique_b = sorted(concepts_b - concepts_a)
    shared_case_count = len(cases_a & cases_b)
    union_concepts = concepts_a | concepts_b
    jaccard_pct = f"{jaccard:.1%}"

    interpretation = (
        f"Compared {len(cases_a)}-case and {len(cases_b)}-case cohorts: "
        f"{len(shared_concepts)} shared CAC concept types out of {len(union_concepts)} total "
        f"(node Jaccard {jaccard_pct}). "
        f"Cohort A has {len(unique_a)} unique concepts"
        f"{(' (e.g. ' + ', '.join(unique_a[:3]) + ')') if unique_a else ''}; "
        f"cohort B has {len(unique_b)} unique concepts"
        f"{(' (e.g. ' + ', '.join(unique_b[:3]) + ')') if unique_b else ''}. "
        f"{shared_case_count} case(s) overlap between cohorts. "
        "Node Jaccard counts shared node IRIs; only platform, agency and location nodes "
        "are shared across cases, so it is not a conduct-similarity measure."
    )

    return {
        "shared_concepts": shared_concepts,
        "unique_to_a": unique_a,
        "unique_to_b": unique_b,
        "node_jaccard_similarity": round(jaccard, 4),
        "shared_case_count": shared_case_count,
        "interpretation": interpretation,
        **interpretation_fields(INTERPRETATION_COMPARE),
    }


def strip_flat_node_metadata(node: Dict[str, Any]) -> Dict[str, Any]:
    """Remove CaseLinker merge annotations before RDF export."""
    return {k: v for k, v in node.items() if k not in _FLAT_NODE_META_KEYS}


_GRAPH_BASE = "https://w3id.org/caselinker/resource"
GRAPH_DETERMINISTIC_ID = f"{_GRAPH_BASE}/graphs/deterministic"
GRAPH_NLP_ID = f"{_GRAPH_BASE}/graphs/nlp"


def flat_nodes_to_named_jsonld(flat_nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Rebuild a Dataset JSON-LD document from merged flat nodes.

    graph_generate writes the flat node list. Patterns reads that list and
    this { @id, @graph } wrapper. Splits deterministic vs NLP using _isNlp.
    """
    det: List[Dict[str, Any]] = []
    nlp: List[Dict[str, Any]] = []
    for node in flat_nodes:
        if not node.get("@id"):
            continue
        cleaned = strip_flat_node_metadata(node)
        if node.get("_isNlp"):
            nlp.append(cleaned)
        else:
            det.append(cleaned)

    out: List[Dict[str, Any]] = []
    if det:
        out.append({"@id": GRAPH_DETERMINISTIC_ID, "@graph": det})
    if nlp:
        out.append({"@id": GRAPH_NLP_ID, "@graph": nlp})
    return out


def flat_nodes_to_exports(
    flat_nodes: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], str, int, int]:
    """Return (named_jsonld, turtle, triple_count, node_count)."""
    jsonld = flat_nodes_to_named_jsonld(flat_nodes)
    turtle, triple_count, node_count = flat_nodes_to_turtle(flat_nodes)
    return jsonld, turtle, triple_count, node_count


def flat_nodes_to_turtle(flat_nodes: List[Dict[str, Any]]) -> Tuple[str, int, int]:
    """
    Reconstruct Turtle from merged flat JSON-LD nodes (expanded absolute IRIs).

    Returns (turtle_string, triple_count, node_count).
    """
    from rdflib import Graph, URIRef

    from features_to_cac import CaseToCAC  # noqa: E402

    cleaned = [strip_flat_node_metadata(n) for n in flat_nodes if n.get("@id")]
    if not cleaned:
        return "", 0, 0

    g = Graph()
    g.parse(data=json.dumps({"@graph": cleaned}), format="json-ld")
    CaseToCAC._bind_namespaces(g)

    turtle = g.serialize(format="turtle")
    triple_count = len(g)
    node_ids: Set[Any] = set()
    for s, _p, o in g:
        node_ids.add(s)
        if isinstance(o, URIRef):
            node_ids.add(o)
    return turtle, triple_count, len(node_ids)


def build_graph_summary(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    flat_nodes: List[Dict[str, Any]],
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    concept_counts: Counter[str] = Counter()
    degrees: Counter[str] = Counter()
    for fn in flat_nodes:
        for cls in cac_classes_from_node(fn):
            concept_counts[cls] += 1
    for e in edges:
        degrees[e["source"]] += 1
        degrees[e["target"]] += 1

    bridge_nodes = sorted(
        (
            {
                "node_id": n["node_id"],
                "label": n.get("label"),
                "degree": degrees.get(n["node_id"], 0),
            }
            for n in nodes
        ),
        key=lambda x: x["degree"],
        reverse=True,
    )[:5]

    cac_classes = sorted(concept_counts.keys())
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "cases_mapped": metadata.get("cases_mapped") or [],
        "concept_distribution": [
            {"concept": k, "count": v} for k, v in concept_counts.most_common(10)
        ],
        "bridge_nodes": bridge_nodes,
        "cac_classes_covered": cac_classes,
    }
