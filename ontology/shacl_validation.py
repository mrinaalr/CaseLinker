"""Full SHACL validation of a case graph against every pinned shape (#57 §6).

``CaseToCAC.validate`` checks the CAC core shapes on every export. This module
is the complete check: all CAC v3.1.0 module shapes, UCO 1.5.0 and CASE 1.5.0,
with RDFS inference over the vendored ontologies. It is slow (seconds per
graph), so the test runs it on fixtures and ``scripts/ontology_audit`` on a
sample.

Every violation is sorted into one of three buckets:

* ``caselinker`` — the graph is wrong. Must be empty.
* ``unstated`` — a shape requires a value press releases do not state
  (a role's begin time, a registry offender's name). CaseLinker leaves the
  value out rather than invent it (#57 §4 rule).
* ``upstream`` — the shape itself is defective (targets every Event, or an
  anti-rigid ``sh:not`` that fails every instance); listed for CAC.

The bucket is decided by the violation message, which is fixed text in the
pinned shapes. A message not in either table is ``caselinker`` and fails.
SPARQL constraints that cannot be prepared (no ``sh:prefixes``, syntax
errors) are removed before validating and counted, so they surface in the
report instead of silently passing or crashing pyshacl.
"""

from __future__ import annotations

import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Tuple

from rdflib import Graph, Namespace, RDF
from rdflib.plugins.sparql import prepareQuery

_THIS_DIR = Path(__file__).resolve().parent
VENDOR = _THIS_DIR / "vendor"
SH = Namespace("http://www.w3.org/ns/shacl#")

# Shapes that require a value no press release states. Keyed by message prefix.
_BEGIN = "a release reports a date, not when a role, phase or age began"
_ENUM = "a release does not state this classification"
UNSTATED: Dict[str, str] = {
    "Offender role must have begin point": _BEGIN,
    "Victim role must have begin point": _BEGIN,
    "Initial phase must have begin point": _BEGIN,
    "AgeAtTimeSituation must have a begin timestamp": _BEGIN,
    "Criminal event must involve victim and offender roles": "no victim stated, or several events and no pairing stated",
    "CSAM incident must have digital artifact facets": "no file or hash details in a release",
    "Less than 1 values on ->cacontology-us-ncmec:hasNCMECIncidentType": "releases do not give the CyberTipline incident code",
    "Less than 1 values on ->cac-core:assesses": "sentence with several defendants: the release does not say whose",
    "A hotline report must have at least one reporter": "reporter not stated (cybertip_reporter kind=unstated)",
    "A hotline report must have at least one evidence item": "no tip contents in a release",
    "A hotline report must specify its intake channel": _ENUM,
    "Reporter roles must have assignment timestamps": _BEGIN,
    "A hotline report must have a status": _ENUM,
    "A hotline report must have a current operational phase": _ENUM,
    "Multi-jurisdictional operation must specify operation type": _ENUM,
    "Multi-jurisdictional operation must involve between 2 and 50 jurisdictions": "jurisdiction count not stated",
    "Multi-jurisdictional operation must specify lead agency type": _ENUM,
    "Multi-jurisdictional operation must specify coordination level": _ENUM,
    "Task force operation must specify operation type": _ENUM,
    "Task force operation must specify operation scope": _ENUM,
    "Task force operation must have between 1 and 25 participating agencies": "participating-agency count not stated",
    "Undercover operation must specify operation type": _ENUM,
    "Undercover operation must specify operation status": _ENUM,
    "Undercover operation must specify risk level": _ENUM,
    "Production offense must specify exactly one production method": _ENUM,
    "Production offense must specify victim count": "victim count not stated",
    "Sextortion incident must specify incident type": _ENUM,
    "Sextortion incident must specify severity level": _ENUM,
    "Sextortion incident must specify victim count": "victim count not stated",
    "Grooming behavior must specify grooming stage": _ENUM,
    "Grooming behavior must specify behavior type": _ENUM,
    "Content hashing action must specify start time": _BEGIN,
    "Content hashing action must specify the hashing tool used": "tool not stated",
    "Custodial relationship must specify trust level": _ENUM,
    "Custodial relationship must specify access level": _ENUM,
    "Custodial relationship must be in exactly one phase": _ENUM,
    "Trust violation must specify violation type": _ENUM,
    "Trust violation must specify severity": _ENUM,
    "Probation sentence must have between 1 and 50 conditions": "conditions not stated",
    "Probation sentence must specify supervision level": _ENUM,
    "Probation sentence must specify reporting frequency": _ENUM,
    "Offender must have a full name": "names are never stored (no-direct-identifiers rule)",
    "Offender must have a date of birth": "never stored (no-direct-identifiers rule)",
    "Sex must be Male, Female, or Unknown": "not stated",
    "Offender must be registered in at least one registry": "registry not named",
    "Action must have exactly one performer IRI": "the actor of a legal or investigative step is rarely named; CAC synthesis ActionSemanticsShape targets every UCO Action (#57 §6 B2)",
    "Action must reference at least one object IRI": "as above",
}
# Shapes that are wrong upstream: they fire on every instance whatever the data says.
UPSTREAM: Dict[str, str] = {
    "Every federal criminal event must have at least one participant": "usa-federal participation shape targets every cac-core:Event (CAC#58, PR #61)",
    "Every forensic event must have at least one participant": "forensics participation shape targets every cac-core:Event (CAC#58, PR #61)",
    "Every grooming event must have at least one participant": "grooming participation shape targets every cac-core:Event (not yet filed in CAC)",
    "Production event must have exactly one begin point": "production shape targets every cac-core:Event (not yet filed in CAC)",
    "gUFO Events must have at least one temporal beginning point": "gUFO bridge shape requires a begin point on every Event (not yet filed in CAC)",
    "Roles are anti-rigid and cannot be subclasses of rigid Kinds": "anti-rigid sh:not role shapes (CAC#63)",
    "Role instances must be anti-rigid": "anti-rigid sh:not role shapes (CAC#63)",
    "Forensic roles are anti-rigid": "anti-rigid sh:not role shapes (CAC#63)",
    "Grooming roles are anti-rigid": "anti-rigid sh:not role shapes (CAC#63)",
    "Liaison roles are anti-rigid": "anti-rigid sh:not role shapes (CAC#63)",
    "Institutional roles are anti-rigid": "anti-rigid sh:not role shapes (CAC#63)",
    "International coordination roles are anti-rigid": "anti-rigid sh:not role shapes (CAC#63)",
    "gUFO Roles must be OWL classes": "anti-rigid sh:not role shapes (CAC#63)",
    "Phase instances must be anti-rigid": "anti-rigid sh:not phase shapes, same pattern as CAC#63 (not yet filed)",
    "Phases are anti-rigid and cannot be subclasses of rigid Kinds": "as above",
    "Vulnerable child phases are anti-rigid temporal stages": "as above",
    "Situations should involve multiple entities or persist over time": "gUFO situation heuristic fires on every Situation (not yet filed in CAC)",
    "gUFO Qualities must inhere in at least one Object": "temporal:concernsAgeQuality's required value temporal:Age is a class, which its range then types as a Quality instance (not yet filed in CAC)",
    "Custodial relationship must be typed as gUFO Kind": "custodial shape expects instances typed gufo:Kind, a class-level type (not yet filed in CAC)",
}


def _files(*globs: str) -> List[Path]:
    out: List[Path] = []
    for pattern in globs:
        out.extend(sorted(VENDOR.glob(pattern)))
    return out


@lru_cache(maxsize=1)
def load_shapes() -> Tuple[Graph, int]:
    """Every vendored shape, minus SPARQL constraints that cannot be prepared.

    Returns (shapes_graph, removed_constraint_count).
    """
    shapes = Graph()
    for path in _files("cac-3.1.0/*-shapes.ttl", "uco-1.5.0/**/*.ttl", "case-1.5.0/*.ttl"):
        shapes.parse(str(path), format="turtle")
    removed = 0
    for shape, constraint in list(shapes.subject_objects(SH.sparql)):
        query = shapes.value(constraint, SH.select) or shapes.value(constraint, SH.ask)
        if query is None:
            continue
        prefixes = {
            str(shapes.value(d, SH.prefix)): str(shapes.value(d, SH.namespace))
            for pd in shapes.objects(constraint, SH.prefixes)
            for d in shapes.objects(pd, SH.declare)
        }
        head = "".join(f"PREFIX {k}: <{v}>\n" for k, v in prefixes.items())
        try:
            prepareQuery(head + str(query).replace("$this", "?this"))
        except Exception:
            shapes.remove((shape, SH.sparql, constraint))
            removed += 1
    return shapes, removed


@lru_cache(maxsize=1)
def load_ontologies() -> Graph:
    """The vendored ontologies, for RDFS inference during validation."""
    ont = Graph()
    for path in _files("cac-3.1.0/*.ttl", "gufo-1.0.0/*.ttl", "uco-1.5.0/**/*.ttl", "case-1.5.0/*.ttl"):
        if not path.name.endswith("-shapes.ttl"):
            ont.parse(str(path), format="turtle")
    return ont


def _bucket(message: str) -> str:
    for table, name in ((UNSTATED, "unstated"), (UPSTREAM, "upstream")):
        if any(message.startswith(prefix) for prefix in table):
            return name
    return "caselinker"


def _normalize(message: str) -> str:
    """'Less than 1 values on <iri>->rdfs:label' → 'Less than 1 values on ->rdfs:label'."""
    return re.sub(r"<[^>]*>", "", message)


def classify_report(report: Graph) -> Dict[str, Counter]:
    """Violations in a pyshacl results graph, by bucket and normalized message."""
    out: Dict[str, Counter] = {"caselinker": Counter(), "unstated": Counter(), "upstream": Counter()}
    for result in report.subjects(RDF.type, SH.ValidationResult):
        if report.value(result, SH.resultSeverity) != SH.Violation:
            continue
        message = _normalize(str(report.value(result, SH.resultMessage) or ""))
        out[_bucket(message)][message] += 1
    return out


def full_validate(graph: Graph) -> Dict[str, Counter]:
    """Validate ``graph`` against every pinned shape; violations by bucket and message."""
    import pyshacl

    from rdflib import term

    shapes, _removed = load_shapes()
    # RDFS inference runs owlrl, which replaces rdflib's process-wide lexical
    # conversions (owlrl.DatatypeHandling.use_Alt_lexical_conversions) and never
    # restores them; later xsd:dateTime literals would then serialize differently.
    saved = dict(term._toPythonMapping)
    try:
        _conforms, report, _text = pyshacl.validate(
            graph,
            shacl_graph=shapes,
            ont_graph=load_ontologies(),
            inference="rdfs",
            allow_warnings=True,
        )
    finally:
        term._toPythonMapping.clear()
        term._toPythonMapping.update(saved)
    return classify_report(report)
