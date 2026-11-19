"""Ontology emission with the pinned SDK, and SHACL against the pinned shape set."""
from __future__ import annotations

import json
import re

import pytest
import rdflib

from tests.pacer import fixtures as F
from state_machines.evidence import vocab as V
from state_machines.trajectories.derive import derive

pytest.importorskip("case_uco")

from state_machines.graphs.emit import evidence_graph, serialize, trajectory_graph  # noqa: E402
from state_machines.graphs.shacl import EXTENSION, validate_jsonld  # noqa: E402


@pytest.fixture(scope="module")
def outputs():
    bundle, quotes = F.build()
    ev = serialize(evidence_graph(bundle))
    tr = serialize(trajectory_graph(bundle, derive(bundle, "INFERRED")))
    return bundle, quotes, ev, tr


def test_emitted_graphs_conform_to_pinned_shapes(outputs):
    _, _, ev, tr = outputs
    conforms, messages = validate_jsonld(ev, tr)
    assert conforms, messages[:10]


def test_published_cac_fails_our_graphs_only_on_the_synthesis_defect(outputs):
    from state_machines.graphs.shacl import validation_report
    _, _, ev, tr = outputs
    r = validation_report(ev, tr)
    # CAC 3.1.0 as published: ActionSemanticsShape rejects every lifecycle and object-less action
    assert r["violations"] == [] and r["upstream_defect_shapes"] == [F.SYNTHESIS_DEFECT]
    assert r["upstream_defect_violations"] and r["conformance"] == "fails" and not r["release_ok"]


def test_listed_upstream_defect_shapes_exist_in_vendored_cac():
    from state_machines.graphs.shacl import _parsed, upstream_defects
    g = _parsed()
    for d in upstream_defects()["defects"]:
        assert (rdflib.URIRef(d["shape"]), rdflib.RDF.type, rdflib.URIRef("http://www.w3.org/ns/shacl#NodeShape")) in g


def test_emission_is_deterministic(outputs):
    bundle, _, ev, tr = outputs
    assert serialize(evidence_graph(bundle)) == ev
    assert serialize(trajectory_graph(bundle, derive(bundle, "INFERRED"))) == tr


def test_graphs_hold_no_quote_text_and_no_phase_instances(outputs):
    _, quotes, ev, tr = outputs
    for q in quotes.values():
        if len(q.split()) > 4:
            assert q not in ev and q not in tr
    g = rdflib.Graph().parse(data=ev, format="json-ld").parse(data=tr, format="json-ld")
    phase_ns = "https://cacontology.projectvic.org/"
    assert not [o for o in g.objects(None, rdflib.RDF.type) if str(o).startswith(phase_ns) and "Phase" in str(o)]


def test_O_i_is_emitted_as_cac_affordance_classes_on_trajectory_steps(outputs):
    _, _, _, tr = outputs
    g = rdflib.Graph().parse(data=tr, format="json-ld")
    clt = rdflib.Namespace("https://w3id.org/caselinker/trajectory#")
    used = {str(o) for o in g.objects(None, clt.stepAffordance)}
    assert used <= set(V.AFFORDANCE_CLASSES.values()) and used


def test_shacl_rejects_instrumental_claim_without_basis_or_evidence(outputs):
    _, _, ev, _ = outputs
    doc = json.loads(ev)
    rel = next(n for n in doc["@graph"] if n["@id"].startswith("kb:supports-"))
    del rel["clt:affordanceBasis"]          # serialization alone must not make a bare claim valid
    conforms, messages = validate_jsonld(json.dumps(doc))
    assert not conforms and any("not an instrumental claim" in m for m in messages)
    doc = json.loads(ev)
    sup = next(n for n in doc["@graph"] if n["@id"].startswith("kb:supports-"))["@id"]
    doc["@graph"] = [n for n in doc["@graph"] if not ("oa:Annotation" in str(n.get("@type"))
                                                      and n.get("oa:hasBody", {}).get("@id") == sup)]
    conforms, messages = validate_jsonld(json.dumps(doc))
    assert not conforms and any("rest on at least one evidence annotation" in m for m in messages)


def test_shacl_rejects_phase_instances_and_synthetic_status(outputs):
    _, _, ev, _ = outputs
    doc = json.loads(ev)
    doc["@graph"].append({"@id": "kb:fake-phase", "@type": "https://cacontology.projectvic.org/grooming#ExploitationPhase"})
    conforms, messages = validate_jsonld(json.dumps(doc))
    assert not conforms and any("Phase instances" in m for m in messages)
    doc = json.loads(ev)
    action = next(n for n in doc["@graph"] if n["@id"].startswith("kb:action-"))
    action["clt:assertionStatus"] = {"@type": "xsd:string", "@value": "SYNTHETIC"}
    conforms, messages = validate_jsonld(json.dumps(doc))
    assert not conforms and any("assertionStatus" in m for m in messages)


def test_shacl_rejects_action_without_evidence(outputs):
    _, _, ev, _ = outputs
    doc = json.loads(ev)
    doc["@graph"] = [n for n in doc["@graph"] if "oa:Annotation" not in str(n.get("@type"))]
    conforms, messages = validate_jsonld(json.dumps(doc))
    assert not conforms and any("evidence annotation" in m for m in messages)


def test_extension_value_lists_match_vocab():
    shapes = (EXTENSION / "caselinker-trajectory-shapes.ttl").read_text()
    lists = {m.group(1): set(re.findall(r'"([^"]+)"', m.group(2)))
             for m in re.finditer(r"sh:path clt:(\w+) ;[^(\]]*sh:in \(([^)]*)\)", shapes)}
    assert lists["outcome"] == set(V.OUTCOMES)
    assert lists["assertionStatus"] == set(V.ASSERTION_STATUS)
    assert lists["sourceStatus"] == set(V.SOURCE_STATUS)
    assert lists["affordanceBasis"] == set(V.AFFORDANCE_BASIS)
    assert lists["capabilityConfidence"] == {"documented", "approximate", "uncertain"}
    assert lists["legalStatus"] == set(V.LEGAL_STATUS)
    assert lists["timeBasis"] == set(V.TIME_BASIS)
    assert lists["interactionMode"] == set(V.INTERACTION_MODES)
    assert lists["audience"] == set(V.AUDIENCES)
    assert lists["countStated"] == set(V.COUNT_STATED)
    assert lists["victimKind"] == set(V.VICTIM_KIND)
    assert lists["h0Category"] == set(V.H0)


def test_no_canonical_namespace_is_redefined_by_the_extension():
    g = rdflib.Graph().parse(EXTENSION / "caselinker-trajectory.ttl")
    subjects = {str(s) for s in g.subjects() if isinstance(s, rdflib.URIRef)}
    assert all(s.startswith("https://w3id.org/caselinker/trajectory") for s in subjects)
    # exactly the two documented classes, both under uco-core:UcoObject
    classes = set(g.subjects(rdflib.RDF.type, rdflib.OWL.Class))
    assert {str(c) for c in classes} == {"https://w3id.org/caselinker/trajectory#Collective",
                                         "https://w3id.org/caselinker/trajectory#TimeAssertion"}
    uco_object = rdflib.URIRef("https://ontology.unifiedcyberontology.org/uco/core/UcoObject")
    assert all((c, rdflib.RDFS.subClassOf, uco_object) in g for c in classes)


def test_full_cac_shape_set_is_loaded():
    from state_machines.graphs.shacl import shape_files, VENDOR
    loaded = {p.name for p in shape_files() if p.parent.name == "cac-3.1.0"}
    assert loaded == {p.name for p in (VENDOR / "cac-3.1.0").glob("*.ttl")} and len(loaded) == 97


def test_only_unrunnable_upstream_constraints_are_skipped_and_none_of_ours():
    from state_machines.graphs.shacl import skipped_upstream_constraints, skipped_upstream_rules
    assert all(not s.startswith("https://w3id.org/caselinker/") for s in skipped_upstream_rules())
    skipped = [shape for shape, _ in skipped_upstream_constraints()]
    assert all(not s.startswith("https://w3id.org/caselinker/") for s in skipped)
    assert "https://cacontology.projectvic.org/platforms#PlatformOperatorCrossReferenceShape" in skipped


def test_report_separates_full_from_partial_conformance(outputs, monkeypatch):
    from state_machines.graphs.shacl import validation_report
    F.with_synthesis_fix(monkeypatch)
    _, _, ev, tr = outputs
    r = validation_report(ev, tr)
    # participants are uco-identity nodes, which two unrunnable upstream CAC 3.1.0 constraints
    # target (custodial, detection: undeclared prefixes, upstream U1); the report must say
    # partial, list them, and block the release check until they run or are waived
    assert r["violations"] == []
    assert set(r["applicable_skipped"]) == {"https://cacontology.projectvic.org/custodial#AuthorityRoleExclusivityShape",
                                            "https://cacontology.projectvic.org/detection#DetectionRoleParticipationShape"}
    assert r["conformance"] == "partial" and not r["release_ok"]
    assert len(r["skipped_constraints"]) > 6    # the complete CAC 3.1.0 shape set is loaded


def test_applicable_skipped_constraint_makes_conformance_partial_and_blocks_release(outputs, monkeypatch):
    from state_machines.graphs.shacl import validation_report
    F.with_synthesis_fix(monkeypatch)
    _, _, ev, _ = outputs
    doc = json.loads(ev)
    doc["@graph"].append({"@id": "kb:platform-x", "@type": "https://cacontology.projectvic.org/platforms#MessagingService",
                          "uco-core:name": {"@type": "xsd:string", "@value": "fictional messenger"}})
    r = validation_report(json.dumps(doc))
    assert r["violations"] == [] and r["conformance"] == "partial"
    assert "https://cacontology.projectvic.org/platforms#PlatformOperatorCrossReferenceShape" in r["applicable_skipped"]
    assert not r["release_ok"] and r["unwaived_applicable_skipped"]


def test_emitted_terms_are_declared_upstream_or_in_the_extension(tmp_path):
    """Every class, predicate and datatype the PACER graphs use is declared by pinned UCO/CASE/CAC
    or by the clt extension; no placeholder IRIs (#57)."""
    import sys
    from pathlib import Path
    from rdflib import RDF, URIRef
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ontology" / "pipeline"))
    from term_resolution import graph_terms, declared_terms, parse_jsonld
    ext = rdflib.Graph().parse(EXTENSION / "caselinker-trajectory.ttl", format="turtle")
    known = declared_terms() | {str(s) for s in ext.subjects(RDF.type, None) if isinstance(s, URIRef)}
    bundle, _ = F.build()
    for name, g in (("evidence", evidence_graph(bundle)), ("trajectories", trajectory_graph(bundle, derive(bundle, "INFERRED")))):
        path = tmp_path / f"{name}.jsonld"
        doc = serialize(g)
        path.write_text(doc if isinstance(doc, str) else json.dumps(doc), encoding="utf-8")
        parsed = parse_jsonld(path)
        missing = {k: sorted(t for t in terms if t not in known) for k, terms in graph_terms(parsed).items()}
        assert {k: v for k, v in missing.items() if v} == {}, name
        assert not any("example.org" in str(n) for n in parsed.all_nodes()), name
