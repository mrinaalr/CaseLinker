"""A case graph says only what the case's extracted fields say (#57 §4, #20)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from rdflib import Namespace, RDF, URIRef
from rdflib.namespace import DCTERMS, XSD

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "ontology"))
sys.path.insert(0, str(REPO / "tests"))

import ontology_fixtures as FX  # noqa: E402
from features_to_cac import (  # noqa: E402
    BASE, CAC, CAC_CORE, CAC_HOTLINES, CAC_LEGAL, CAC_NCMEC, CAC_PLATFORMS, CAC_REGISTRY,
    CAC_TEMPORAL, GRAPH_NLP, UCO_CORE, CaseToCAC, flatten_dataset,
)

OBS = Namespace("https://ontology.unifiedcyberontology.org/uco/observable/")
USA_FED = Namespace("https://cacontology.projectvic.org/usa-federal-law#")


def _graph(case_id):
    graph, _ = CaseToCAC().map_case(FX.case(case_id))
    return graph, flatten_dataset(graph)


def _typed(g, cls):
    return set(g.subjects(RDF.type, cls))


def test_victims_only_when_stated():
    _, full = _graph("fixture_full_001")
    _, arrest = _graph("fixture_arrest_002")
    assert len(_typed(full, CAC.VictimRole)) == 2          # victim_count = 2
    assert _typed(arrest, CAC.VictimRole) == set()          # no count, no age, no relationship


def test_offenders_from_ages_or_prosecution_and_role_follows_status():
    _, full = _graph("fixture_full_001")
    _, arrest = _graph("fixture_arrest_002")
    _, empty = _graph("fixture_empty_003")
    assert len(_typed(full, CAC.OffenderRole)) == 1 and not _typed(full, CAC_LEGAL.DefendantRole)
    assert len(_typed(arrest, CAC_LEGAL.DefendantRole)) == 1 and not _typed(arrest, CAC.OffenderRole)
    assert not (_typed(empty, CAC.OffenderRole) | _typed(empty, CAC_LEGAL.DefendantRole))


def test_people_play_roles_through_has_role_and_ages_are_situations():
    _, g = _graph("fixture_full_001")
    rels = _typed(g, UCO_CORE.Relationship)
    has_role = {r for r in rels if str(g.value(r, UCO_CORE.kindOfRelationship)) == "Has_Role"}
    roles = _typed(g, CAC.VictimRole) | _typed(g, CAC.OffenderRole) | _typed(g, CAC_REGISTRY.RegisteredSexOffender)
    assert {g.value(r, UCO_CORE.target) for r in has_role} >= roles
    ages = _typed(g, CAC_TEMPORAL.AgeAtTimeSituation)
    assert [str(g.value(a, CAC_TEMPORAL.hasAgeInYears)) for a in ages] == ["37"]
    offender = BASE["case/fixture_full_001/person/offender/1"]
    assert {g.value(a, CAC_TEMPORAL.ageSubject) for a in ages} == {offender}


def test_registered_offender_is_a_cac_role_of_the_sole_offender():
    _, g = _graph("fixture_full_001")
    rso = _typed(g, CAC_REGISTRY.RegisteredSexOffender)
    assert len(rso) == 1
    bearer = [g.value(r, UCO_CORE.source) for r in _typed(g, UCO_CORE.Relationship)
              if g.value(r, UCO_CORE.target) in rso]
    assert bearer == [BASE["case/fixture_full_001/person/offender/1"]]


def test_links_to_an_event_only_when_there_is_one_event():
    _, full = _graph("fixture_full_001")      # csam, sextortion, grooming, production → several events
    _, arrest = _graph("fixture_arrest_002")  # online_only → one event
    for p in (CAC.participatesInEvent, CAC.usesChannel, CAC.severityLevel):
        assert not list(full.triples((None, p, None))), p
    assert (None, CAC.usesChannel, BASE["platform/snapchat"]) in arrest
    assert list(arrest.triples((None, CAC.participatesInEvent, None)))


def test_no_invented_dates_facets_conspiracy_or_charge_events():
    _, g = _graph("fixture_full_001")
    for p in (CAC.hasRoleBeginPoint, CAC.hasPhaseBeginPoint, CAC_LEGAL.hasProceedingBeginPoint):
        assert not list(g.triples((None, p, None))), p
    assert not _typed(g, OBS.ContentDataFacet)
    assert not _typed(g, CAC.ConspiracyToCommitCSA)
    assert not any("/offense-event/" in str(s) for s in g.subjects())
    proceeding = BASE["case/fixture_full_001/legal-proceeding"]
    assert int(g.value(proceeding, CAC_LEGAL.chargeCount)) == 5   # 3 + 1 + 1 stated counts


def test_release_date_keeps_its_precision():
    _, full = _graph("fixture_full_001")
    _, arrest = _graph("fixture_arrest_002")
    assert full.value(BASE["case/fixture_full_001"], DCTERMS.date).datatype == XSD.date
    month = arrest.value(BASE["case/fixture_arrest_002"], DCTERMS.date)
    assert (str(month), month.datatype) == ("2017-03", XSD.gYearMonth)   # stored 2017-03-01 = month only
    created = full.value(BASE["case/fixture_full_001"], DCTERMS.created)
    assert created.datatype == XSD.dateTime


def test_cybertip_only_from_a_case_scoped_tip_and_ncmec_receives_it():
    _, full = _graph("fixture_full_001")
    _, arrest = _graph("fixture_arrest_002")   # names NCMEC as a partner, no tip
    tip = BASE["case/fixture_full_001/cybertip"]
    assert _typed(arrest, CAC_NCMEC.NCMECCybertipReport) == set()
    assert (BASE["case/fixture_full_001"], UCO_CORE.object, tip) in full
    assert (tip, CAC_HOTLINES.receivedBy, BASE["agency/ncmec"]) in full
    assert not list(full.triples((None, CAC_NCMEC.supportedBy, None)))


def test_named_reporter_is_an_esp_playing_reporter_role():
    _, g = _graph("fixture_full_001")
    tip = BASE["case/fixture_full_001/cybertip"]
    esp = BASE["esp/kik"]
    assert (tip, RDF.type, CAC_HOTLINES.ESPReport) in g
    role = g.value(tip, CAC_HOTLINES.reportedBy)
    assert (role, RDF.type, CAC_HOTLINES.ReporterRole) in g
    assert [g.value(r, UCO_CORE.source) for r in _typed(g, UCO_CORE.Relationship)
            if g.value(r, UCO_CORE.target) == role] == [esp]
    assert (esp, RDF.type, CAC_PLATFORMS.ElectronicServiceProvider) in g
    assert (BASE["platform/kik"], CAC_PLATFORMS.operatedBy, esp) in g   # FULL_CASE uses Kik


def test_a_reporter_is_not_a_platform_the_case_used():
    case = FX.case("fixture_full_001")
    case["cybertip_reporter"] = {"kind": "esp", "esps": ["Google"], "category": None}
    g = flatten_dataset(CaseToCAC().map_case(case)[0])
    assert (BASE["esp/google"], RDF.type, CAC_PLATFORMS.ElectronicServiceProvider) in g
    assert BASE["platform/google"] not in set(g.all_nodes())


@pytest.mark.parametrize("reporter, expect_type, expect_role", [
    ({"kind": "unstated", "esps": [], "category": None}, None, False),
    ({"kind": "esp", "esps": [], "category": "social_media"}, CAC_HOTLINES.ESPReport, False),
    ({"kind": "public", "esps": [], "category": None}, CAC_HOTLINES.PublicReport, False),
])
def test_unnamed_or_unstated_reporter(reporter, expect_type, expect_role):
    case = FX.case("fixture_full_001")
    case["cybertip_reporter"] = reporter
    g = flatten_dataset(CaseToCAC().map_case(case)[0])
    tip = BASE["case/fixture_full_001/cybertip"]
    assert ((tip, CAC_HOTLINES.reportedBy, None) in g) is expect_role
    if expect_type is not None:
        assert (tip, RDF.type, expect_type) in g
    assert (tip, RDF.type, CAC_HOTLINES.ESPReport) in g if reporter["kind"] == "esp" else True


def test_ungrounded_places_stay_in_their_case():
    _, g = _graph("fixture_full_001")
    assert (BASE["case/fixture_full_001"], DCTERMS.spatial, BASE["location/campton-hills-village"]) in g
    assert (BASE["case/fixture_full_001"], DCTERMS.spatial,
            BASE["case/fixture_full_001/location/springfield"]) in g
    assert BASE["location/springfield"] not in set(g.all_nodes())


def test_contact_charge_names_the_offense_it_concerns_without_an_event():
    case = FX.case("fixture_full_001")
    case["prosecution_outcome"]["charges"].append({"count": 1, "charge": "child molestation"})
    g = flatten_dataset(CaseToCAC().map_case(case)[0])
    subjects = {o for c in _typed(g, CAC_LEGAL.CriminalCharge) for o in g.objects(c, DCTERMS.subject)}
    assert USA_FED.SexualAbuseOfMinor in subjects
    assert not _typed(g, USA_FED.SexualAbuseOfMinor)


def test_similarity_scores_are_assessments_not_events():
    graph, _ = CaseToCAC().map_case(FX.case("fixture_full_001"))
    nlp = graph.get_context(GRAPH_NLP)
    results = _typed(nlp, CAC_CORE.AssessmentResult)
    assert results, "ml_features under extracted_features must be read"
    narrative = BASE["case/fixture_full_001/narrative"]
    assert {nlp.value(r, CAC_CORE.assesses) for r in results} == {narrative}
    assert CAC_REGISTRY.RegisteredSexOffender in {nlp.value(r, DCTERMS.subject) for r in results}
    assert not _typed(nlp, CAC_CORE.Event)
    assert not list(nlp.triples((None, CAC.hasStep, None)))


def test_no_caselinker_shacl_violations_under_full_validation():
    pytest.importorskip("pyshacl")
    from shacl_validation import full_validate

    for case in FX.CASES:
        buckets = full_validate(flatten_dataset(CaseToCAC().map_case(FX.case(case["id"]))[0]))
        assert dict(buckets["caselinker"]) == {}, case["id"]


def _reachable_from_case(g, case_id):
    """Nodes joined to the case IRI by any chain of edges, in either direction."""
    start = BASE[f"case/{case_id}"]
    adjacent = {}
    for s, p, o in g:
        if p != RDF.type and isinstance(o, URIRef):
            adjacent.setdefault(s, set()).add(o)
            adjacent.setdefault(o, set()).add(s)
    seen, stack = {start}, [start]
    while stack:
        for nxt in adjacent.get(stack.pop(), ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


@pytest.mark.parametrize("case_id", ["fixture_full_001", "fixture_arrest_002"])
def test_people_and_platforms_are_objects_of_the_investigation(case_id):
    # fixture_full_001 has several CSA events, so nothing is paired with an event;
    # its people and platforms must still hang off the case, not float beside it.
    graph, g = _graph(case_id)
    inv = BASE[f"case/{case_id}"]
    objects = set(g.objects(inv, UCO_CORE.object))
    people = _typed(g, URIRef("https://ontology.unifiedcyberontology.org/uco/identity/Person"))
    platforms = _typed(g, CAC_CORE.DigitalSystemEntity)
    assert people and platforms
    assert people <= objects
    assert platforms <= objects
    reached = _reachable_from_case(g, case_id)
    nlp_nodes = set(graph.get_context(GRAPH_NLP).subjects())
    floating = {s for s in set(g.subjects()) if isinstance(s, URIRef)} - reached - nlp_nodes
    assert floating == set(), sorted(floating)
