"""Check that every class, predicate and datatype in a graph is declared.

Declared means: a typed subject in a vendored ontology (UCO 1.5.0, CASE 1.5.0,
CAC 3.1.0, gUFO 1.0.0, W3C Web Annotation, and the CASE-UCO SDK ``legalproc``
extension the PACER graphs use, pending casework/CASE#192), the CaseLinker
provenance vocabulary, or a closed W3C namespace rdflib ships (RDF, RDFS, OWL,
XSD, PROV, DCTERMS, SKOS). SHACL only checks shapes, so an undeclared IRI passes it; this
check catches the IRI itself.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, Set, Tuple

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, PROV, RDF, RDFS, SKOS, XSD

_THIS_DIR = Path(__file__).resolve().parent
VENDOR_DIR = _THIS_DIR / "vendor"
PROVENANCE_VOCAB = _THIS_DIR / "caselinker-provenance.ttl"

_W3C_CLOSED = (RDF, RDFS, OWL, XSD, PROV, DCTERMS, SKOS)
# rdf:langString / rdf:PlainLiteral are datatypes RDF itself defines.
_EXTRA = {str(RDF.langString), str(RDF.PlainLiteral), str(RDF.HTML), str(RDF.XMLLiteral)}


def vendored_ontology_files() -> Iterable[Path]:
    for sub in ("uco-1.5.0", "case-1.5.0", "cac-3.1.0", "gufo-1.0.0", "w3c", "case-uco-sdk-1.31.2"):
        yield from sorted((VENDOR_DIR / sub).rglob("*.ttl"))


@lru_cache(maxsize=1)
def declared_terms() -> frozenset:
    """Every IRI declared (typed) in the vendored ontologies and the provenance vocabulary."""
    declared: Set[str] = set(_EXTRA)
    for path in list(vendored_ontology_files()) + [PROVENANCE_VOCAB]:
        g = Graph()
        g.parse(str(path), format="turtle")
        for s in g.subjects(RDF.type, None):
            if isinstance(s, URIRef):
                declared.add(str(s))
    for ns in _W3C_CLOSED:
        for name in getattr(ns, "__annotations__", {}):
            declared.add(str(ns[name]))
    return frozenset(declared)


def graph_terms(graph: Graph) -> Dict[str, Set[str]]:
    """Classes (``rdf:type`` objects), predicates and literal datatypes used in ``graph``.

    ``graph`` may be a Graph, ConjunctiveGraph or Dataset; every named graph counts.
    """
    classes: Set[str] = set()
    predicates: Set[str] = set()
    datatypes: Set[str] = set()
    quads = graph.quads((None, None, None, None)) if hasattr(graph, "quads") else (
        (s, p, o, None) for s, p, o in graph
    )
    for s, p, o, _ctx in quads:
        predicates.add(str(p))
        if p == RDF.type and isinstance(o, URIRef):
            classes.add(str(o))
        if isinstance(o, Literal) and o.datatype is not None:
            datatypes.add(str(o.datatype))
    return {"classes": classes, "predicates": predicates, "datatypes": datatypes}


def undeclared_terms(graph: Graph) -> Dict[str, Set[str]]:
    """Terms in ``graph`` that no pinned ontology declares, by kind. Empty sets mean clean."""
    known = declared_terms()
    return {kind: {t for t in terms if t not in known} for kind, terms in graph_terms(graph).items()}


def upstream_dangling() -> Set[Tuple[str, str, str]]:
    """(file, term, referenced IRI) where a vendored CAC module references a UCO/CASE IRI nobody declares.

    These come in through CAC (e.g. ``cacontology:VictimRole rdfs:subClassOf
    uco-role:VictimRole``, CAC#67). They are upstream findings, reported apart
    from CaseLinker's own terms.
    """
    known = declared_terms()
    out: Set[Tuple[str, str, str]] = set()
    refs = (RDFS.subClassOf, RDFS.subPropertyOf, RDFS.domain, RDFS.range)
    for path in sorted((VENDOR_DIR / "cac-3.1.0").glob("*.ttl")):
        if path.name.endswith("-shapes.ttl"):
            continue
        g = Graph()
        g.parse(str(path), format="turtle")
        for s, p, o in g:
            if p in refs and isinstance(o, URIRef) and str(o).startswith(
                ("https://ontology.unifiedcyberontology.org/", "https://ontology.caseontology.org/")
            ) and str(o) not in known:
                out.add((path.name, str(s), str(o)))
    return out


_ANNO_CONTEXT = "http://www.w3.org/ns/anno.jsonld"


def parse_jsonld(path: Path) -> Graph:
    """Parse a JSON-LD file offline: the W3C annotation context comes from ``vendor/w3c``."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    ctx = data.get("@context") if isinstance(data, dict) else None
    if ctx == _ANNO_CONTEXT or (isinstance(ctx, list) and _ANNO_CONTEXT in ctx):
        local = json.loads((VENDOR_DIR / "w3c" / "anno.jsonld").read_text(encoding="utf-8"))["@context"]
        items = ctx if isinstance(ctx, list) else [ctx]
        data["@context"] = [local if c == _ANNO_CONTEXT else c for c in items]
    g = Graph()
    g.parse(data=json.dumps(data), format="json-ld", base=Path(path).resolve().as_uri())
    return g
