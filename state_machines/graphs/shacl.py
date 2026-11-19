"""Pinned-ontology SHACL validation for emitted graphs.

Shape set (pinned; ontology/CAC_ONTOLOGY_VERSION): every vendored file. UCO 1.5.0 and
CASE 1.5.0 (with their class shapes), legalproc (SDK v1.34.0, byte-identical to the
v1.31.2 vendored copy), gUFO 1.0.0, W3C oa, ALL 97 files of CAC 3.1.0 (every module and
every *-shapes.ttl), and the experimental caselinker-trajectory 0.3.0 extension.

Vendored files are never edited. Two kinds of upstream content cannot run as published
and are reported, never silently dropped:
  - SHACL-SPARQL constraints whose query does not parse with the prefixes they declare
    (SHACL 5.2.1): skipped_upstream_constraints()
  - SHACL-AF sh:rule blocks (inference rules, malformed in CAC 3.1.0): pyshacl is run
    without SHACL-AF, and skipped_upstream_rules() lists them
validation_report() says which of those apply to the graph being checked. Conformance is
"full" only when none does.

A third kind runs but is wrong: shapes listed in shacl_upstream_defects.json reject valid
UCO data. Their violations are kept apart (upstream_defect_violations) so a defect in our
own output is never hidden behind them, and they still make conformance "fails".

The SDK's own validate_graph_file is not used: it looks for ontologies in the SDK monorepo
layout, which a pip install does not have (ontology/SDK_VERSION, known gaps).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List, Tuple

import pyshacl
import rdflib

REPO = Path(__file__).resolve().parents[2]
VENDOR = REPO / "ontology" / "vendor"
EXTENSION = REPO / "ontology" / "extensions" / "caselinker-trajectory" / "0.3.0"


def shape_files() -> List[Path]:
    files = sorted((VENDOR / "uco-1.5.0").rglob("*.ttl")) + sorted((VENDOR / "case-1.5.0").glob("*.ttl"))
    files += [VENDOR / "case-uco-sdk-1.31.2" / "legalproc.ttl", VENDOR / "gufo-1.0.0" / "gufo.ttl", VENDOR / "w3c" / "oa.ttl"]
    files += sorted((VENDOR / "cac-3.1.0").glob("*.ttl"))
    files += [EXTENSION / "caselinker-trajectory.ttl", EXTENSION / "caselinker-trajectory-shapes.ttl"]
    return files


def _parse_all() -> rdflib.Graph:
    g = rdflib.Graph()
    for path in shape_files():
        g.parse(path, format="turtle")
    return g


@lru_cache(maxsize=1)
def _parsed() -> rdflib.Graph:
    return _parse_all()


@lru_cache(maxsize=1)
def ontology_graph() -> rdflib.Graph:
    return _parse_all()


SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")


def _declared_prefixes(g: rdflib.Graph, constraint) -> dict:
    ns = {}
    for decl_owner in g.objects(constraint, SH.prefixes):
        for decl in g.objects(decl_owner, SH.declare):
            prefix, namespace = g.value(decl, SH.prefix), g.value(decl, SH.namespace)
            if prefix is not None and namespace is not None:
                ns[str(prefix)] = str(namespace)
    return ns


def _declared_prefix_list(g: rdflib.Graph, constraint) -> List[Tuple[str, str]]:
    out = []
    for decl_owner in g.objects(constraint, SH.prefixes):
        for decl in g.objects(decl_owner, SH.declare):
            prefix, namespace = g.value(decl, SH.prefix), g.value(decl, SH.namespace)
            if prefix is not None and namespace is not None:
                out.append((str(prefix), str(namespace)))
    return sorted(set(out))


def _unrunnable_sparql(g: rdflib.Graph) -> List[Tuple[str, str]]:
    """SPARQL constraints that do not parse with the prefixes they declare (SHACL 5.2.1)."""
    from rdflib.plugins.sparql import prepareQuery

    bad = []
    for shape, constraint in g.subject_objects(SH.sparql):
        query = g.value(constraint, SH.select) or g.value(constraint, SH.ask)
        if query is None:
            continue
        # Mirror the engine: pyshacl prepends one PREFIX line per declaration, so two prefixes
        # for the same namespace are fine (rdflib's initNs binding would silently drop one).
        header = "".join(f"PREFIX {p}: <{ns}>\n" for p, ns in _declared_prefix_list(g, constraint))
        try:
            prepareQuery(header + str(query).replace("$this", "?this"))
        except Exception as exc:  # noqa: BLE001 - any parse failure makes the constraint unrunnable
            bad.append((str(shape), str(exc).splitlines()[0][:120]))
    return sorted(bad)


@lru_cache(maxsize=1)
def skipped_upstream_constraints() -> Tuple[Tuple[str, str], ...]:
    """Upstream SPARQL constraints left out because no SHACL engine can run them as published."""
    return tuple(_unrunnable_sparql(_parsed()))


@lru_cache(maxsize=1)
def skipped_upstream_rules() -> Tuple[str, ...]:
    """Shapes carrying SHACL-AF sh:rule blocks, which are not evaluated (validation runs SHACL
    Core + SHACL-SPARQL only; the CAC 3.1.0 rules use INSERT inside sh:construct and are malformed)."""
    return tuple(sorted({str(s) for s in _parsed().subjects(SH.rule, None)}))


@lru_cache(maxsize=1)
def shapes_graph() -> rdflib.Graph:
    """The pinned shapes, minus SPARQL constraints that cannot run as published.

    Vendored files are never edited. A constraint whose query does not parse with its own
    declared prefixes (in CAC 3.1.0, most SPARQL constraints declare none) is dropped from
    this in-memory copy and listed by skipped_upstream_constraints(). Our own extension
    shapes must all run (tests/pacer/test_emit_shacl.py).
    """
    g = _parse_all()
    skipped = {shape for shape, _ in skipped_upstream_constraints()}
    for shape, constraint in list(g.subject_objects(SH.sparql)):
        if str(shape) in skipped and (g.value(constraint, SH.select) or g.value(constraint, SH.ask)) is not None:
            g.remove((shape, SH.sparql, constraint))
    return g


WAIVERS_PATH = Path(__file__).resolve().parent / "shacl_waivers.json"


def waivers() -> dict:
    """Recorded decisions to release despite an applicable, unrunnable upstream constraint."""
    import json

    return json.loads(WAIVERS_PATH.read_text()) if WAIVERS_PATH.is_file() else {"waivers": []}


DEFECTS_PATH = Path(__file__).resolve().parent / "shacl_upstream_defects.json"


def upstream_defects() -> dict:
    """Published upstream shapes known to reject valid data, with the upstream status."""
    import json

    return json.loads(DEFECTS_PATH.read_text()) if DEFECTS_PATH.is_file() else {"defects": []}


def _node_shape(shapes: rdflib.Graph, shape):
    """The named node shape a (possibly blank) source shape belongs to."""
    seen = set()
    while isinstance(shape, rdflib.BNode) and shape not in seen:
        seen.add(shape)
        parent = next(shapes.subjects(SH.property, shape), None) or next(shapes.subjects(SH.sparql, shape), None)
        if parent is None:
            break
        shape = parent
    return shape


def _targets_present(data: rdflib.Graph, ont: rdflib.Graph, shapes: rdflib.Graph, shape) -> bool:
    """Whether a shape's declared targets select at least one node of ``data``."""
    for cls in shapes.objects(shape, SH.targetClass):
        subclasses = set(ont.transitive_subjects(rdflib.RDFS.subClassOf, cls)) | {cls}
        if any(True for c in subclasses for _ in data.subjects(rdflib.RDF.type, c)):
            return True
    if (shape, rdflib.RDF.type, rdflib.OWL.Class) in shapes or (shape, rdflib.RDF.type, rdflib.RDFS.Class) in shapes:
        subclasses = set(ont.transitive_subjects(rdflib.RDFS.subClassOf, shape)) | {shape}
        if any(True for c in subclasses for _ in data.subjects(rdflib.RDF.type, c)):
            return True   # implicit class target (SHACL 2.1.3.3)
    if any((n, None, None) in data or (None, None, n) in data for n in shapes.objects(shape, SH.targetNode)):
        return True
    if any((None, p, None) in data for p in shapes.objects(shape, SH.targetSubjectsOf)):
        return True
    return any((None, p, None) in data for p in shapes.objects(shape, SH.targetObjectsOf))


def validation_report(*documents: str) -> dict:
    """SHACL result that keeps full and partial conformance apart.

    conformance  "full": every applicable constraint ran and passed
                 "partial": every constraint that ran passed, but applicable upstream
                            constraints could not run (listed in applicable_skipped)
                 "fails": a constraint that ran was violated, ours or a listed upstream
                          defect (upstream_defect_violations keeps the latter apart)
    release_ok   no violations, and every applicable skipped constraint has a recorded waiver
                 in trajectories/shacl_waivers.json (shape IRI, reason, upstream defect)
    """
    data = rdflib.Graph()
    for doc in documents:
        data.parse(data=doc, format="json-ld")
    ont, shapes = ontology_graph(), shapes_graph()
    conforms, report, _ = pyshacl.validate(data, shacl_graph=shapes, ont_graph=ont, inference="none",
                                           allow_infos=True, allow_warnings=True, advanced=False)
    defect_shapes = {d["shape"] for d in upstream_defects()["defects"]}
    violations, upstream = [], []
    for r in report.subjects(rdflib.RDF.type, SH.ValidationResult):
        if report.value(r, SH.resultSeverity) == SH.Violation:
            focus = str(report.value(r, SH.focusNode)).rsplit("/", 1)[-1]
            path = report.value(r, SH.resultPath)
            msg = f"{focus} {str(path).rsplit('/', 1)[-1] if path else ''}: {report.value(r, SH.resultMessage)}"
            source = str(_node_shape(shapes, report.value(r, SH.sourceShape)))
            (upstream if source in defect_shapes else violations).append((source, msg))
    full = _parsed()
    skipped = [{"shape": shape, "reason": reason} for shape, reason in skipped_upstream_constraints()]
    skipped += [{"shape": shape, "reason": "SHACL-AF sh:rule not evaluated"} for shape in skipped_upstream_rules()]
    applicable = [s for s in skipped if _targets_present(data, ont, full, rdflib.URIRef(s["shape"]))]
    waived = {w["shape"] for w in waivers()["waivers"]}
    unwaived = [s["shape"] for s in applicable if s["shape"] not in waived]
    ran_ok = bool(conforms) or not (violations or upstream)
    return {
        "conformance": "fails" if not ran_ok else ("partial" if applicable else "full"),
        "violations": sorted(m for _, m in violations),
        "upstream_defect_violations": sorted(m for _, m in upstream),
        "upstream_defect_shapes": sorted({s for s, _ in upstream}),
        "violating_shapes": sorted({s for s, _ in violations}),
        "skipped_constraints": skipped,
        "applicable_skipped": [s["shape"] for s in applicable],
        "unwaived_applicable_skipped": unwaived,
        "release_ok": ran_ok and not unwaived,
        "shape_files": [str(p.relative_to(REPO)) for p in shape_files()],
    }


def validate_jsonld(*documents: str) -> Tuple[bool, List[str]]:
    """(no violations outside the known upstream defects, those violation messages).

    For tests that check our own shapes and data: a violation caused only by a listed
    upstream defect does not make this False, so a negative test cannot pass vacuously on
    it. This boolean is never a conformance claim; validation_report is."""
    r = validation_report(*documents)
    return not r["violations"], r["violations"]
