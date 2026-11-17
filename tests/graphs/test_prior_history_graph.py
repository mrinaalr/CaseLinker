"""Prior history reaches the case graph per masked defendant, in declared terms only (#64).

Every person is made up. Records are what resolution.resolve_prior_history returns.
"""

from __future__ import annotations

import sys
from pathlib import Path

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF

REPO = Path(__file__).resolve().parents[2]
for sub in ("tests", "tests/graphs", "ontology/pipeline", "src", "src/Processing Layer", "src/Storage Layer", "src/Ingestion Layer"):
    if str(REPO / sub) not in sys.path:
        sys.path.insert(0, str(REPO / sub))

import ontology_fixtures as FX  # noqa: E402
from features_to_cac import CAC_REGISTRY, UCO_CORE, CaseToCAC  # noqa: E402
from shacl_validation import full_validate  # noqa: E402
from term_resolution import undeclared_terms  # noqa: E402

BASE = "https://w3id.org/caselinker/resource/case/"


def _map(case_id: str, prior: dict, ages: list, status: str = "sentenced"):
    case = FX.case("fixture_full_001")
    case.update({"id": case_id, "perpetrator_age": sorted(ages), "perpetrator_count": len(ages),
                 "perpetrator_registered_sex_offender": False, "prior_history": prior})
    case["prosecution_outcome"] = {**case["prosecution_outcome"], "booking_status": status}
    mapper = CaseToCAC()
    dataset, warnings = mapper.map_case(case)
    mapper.last_warnings = warnings
    graph = Graph()  # the mapper writes named graphs; one flat graph to read and validate
    for s_, p_, o_, _c in dataset.quads((None, None, None, None)):
        graph.add((s_, p_, o_))
    return mapper, graph


def _annotations(g: Graph):
    out = {}
    for ann in g.subjects(RDF.type, UCO_CORE.Annotation):
        if str(ann).endswith("prior-history") or "/prior-history/" in str(ann):
            out[str(ann)] = {
                "object": str(g.value(ann, UCO_CORE.object)),
                "tags": sorted(str(t) for t in g.objects(ann, UCO_CORE.tag)),
                "statement": str(g.value(ann, UCO_CORE.statement)),
            }
    return out


TWO = {
    "records": [
        {"person": "p1", "age": 34, "kinds": ["on_supervision", "prior_conviction"], "count": 2, "years": [],
         "sex_offense": True, "spans": [[1, 2]]},
        {"person": "p2", "age": 52, "kinds": ["prior_conviction", "registered_offender"], "count": 2,
         "years": [2008], "sex_offense": True, "spans": [[3, 4]]},
    ],
    "has_prior_conviction": True, "registered": True, "on_supervision": True,
}


def test_each_record_lands_on_its_own_offender_by_age():
    _, g = _map("ph_2024_001", TWO, [52, 34])
    ann = _annotations(g)
    by_tags = {tuple(v["tags"]): v for v in ann.values()}
    # perpetrator_age is sorted as stored ([34, 52]); offender 1 is 34, offender 2 is 52 in either input order
    ages = {str(s).rsplit("/age", 1)[0]: int(float(o)) for s, o in
            g.subject_objects(URIRef("https://cacontology.projectvic.org/temporal#hasAgeInYears"))}
    person_for_age = {v: k for k, v in ages.items()}
    assert by_tags[("on_supervision", "prior_conviction")]["object"] == person_for_age[34]
    assert by_tags[("prior_conviction", "registered_offender")]["object"] == person_for_age[52]
    assert "count=2" in by_tags[("on_supervision", "prior_conviction")]["statement"]
    assert "years=2008" in by_tags[("prior_conviction", "registered_offender")]["statement"]


def test_registered_and_convicted_here_is_a_recidivist_with_the_stated_count():
    _, g = _map("ph_2024_002", TWO, [34, 52])
    roles = list(g.subjects(RDF.type, CAC_REGISTRY.RecidivistSexOffender))
    assert len(roles) == 1
    assert g.value(roles[0], CAC_REGISTRY.priorConvictionCount) == Literal(2, datatype=URIRef(
        "http://www.w3.org/2001/XMLSchema#nonNegativeInteger"))


def test_registered_but_only_charged_here_is_registered_not_recidivist():
    _, g = _map("ph_2024_003", TWO, [34, 52], status="arrested")
    assert not list(g.subjects(RDF.type, CAC_REGISTRY.RecidivistSexOffender))
    assert len(list(g.subjects(RDF.type, CAC_REGISTRY.RegisteredSexOffender))) == 1


def test_a_record_naming_no_one_goes_on_the_sole_offender_or_else_on_the_case():
    one = {"records": [{"person": None, "age": None, "kinds": ["prior_conviction"], "count": None, "years": [],
                        "sex_offense": False, "spans": [[1, 2]]}]}
    _, g = _map("ph_2024_004", one, [40])
    [(ann, v)] = _annotations(g).items()
    assert v["object"].startswith(f"{BASE}ph_2024_004/person/offender/1")
    mapper, g = _map("ph_2024_005", one, [40, 41])
    [(ann, v)] = _annotations(g).items()
    assert v["object"] == f"{BASE}ph_2024_005"
    assert any("not attributed to one offender" in w for w in mapper.last_warnings)


def test_two_people_of_the_same_age_are_not_guessed():
    same = {"records": [{"person": "p2", "age": 40, "kinds": ["prior_conviction"], "count": None, "years": [],
                         "sex_offense": False, "spans": [[1, 2]]}]}
    _, g = _map("ph_2024_006", same, [40, 40])
    [(ann, v)] = _annotations(g).items()
    assert v["object"] == f"{BASE}ph_2024_006"


def test_prior_history_graphs_use_only_declared_terms_and_pass_full_shacl():
    for case_id, prior, ages, status in (("ph_2024_007", TWO, [34, 52], "sentenced"),
                                         ("ph_2024_008", TWO, [34, 52], "arrested")):
        mapper, g = _map(case_id, prior, ages, status)
        found = undeclared_terms(g)
        assert not any(found.values()), found
        buckets = full_validate(g)
        prior = {m: n for m, n in buckets.get("caselinker", {}).items()}
        assert not prior, prior


def test_evidence_nodes_name_the_annotation_and_the_role():
    mapper, g = _map("ph_2024_009", TWO, [34, 52])
    ev = [(f, r, n) for f, r, _v, n in mapper.evidence_nodes if f == "prior_history"]
    roles = {r for _f, r, _n in ev}
    assert roles == {"prior_conviction", "on_supervision", "registered_offender"}
    assert all((URIRef(n), RDF.type, None) in g for _f, _r, n in ev)


def test_release_text_to_graph_links_each_prior_history_quote_to_its_node(tmp_path):
    import test_provenance_node_links as L

    text = L.P + ("Hollis Wexley, 41, a registered sex offender, was sentenced to 120 months in federal prison "
                  "for receipt of child pornography. Wexley has two prior convictions for child sexual abuse.")
    result, out = L._generate(tmp_path, {"ph_2024_010": text})
    links = L._links(out, "ph_2024_010")
    case = Graph().parse(out / "ph_2024_010.ttl", format="turtle")
    ann = [str(s).removeprefix(f"{BASE}ph_2024_010/") for s in case.subjects(RDF.type, UCO_CORE.Annotation)
           if str(s).endswith("prior-history")]
    assert ann, "no prior-history annotation in the case graph"
    assert links[("prior_conviction", "prior_conviction")] == ann
    assert set(links[("registered_offender", "registered_offender")]) >= set(ann)
    assert list(case.subjects(RDF.type, CAC_REGISTRY.RecidivistSexOffender))
    assert result["coverage_gaps"] == []
