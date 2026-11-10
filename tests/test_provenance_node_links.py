"""Provenance annotations name the case-graph node they support (#73).

Each case runs the real path: extraction, storage in a scratch SQLite, graph
generation. Wording copies live release shapes; the people are made up.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from rdflib import Graph, URIRef

REPO = Path(__file__).resolve().parents[1]
for sub in ("ontology", "src", "src/Processing Layer", "src/Storage Layer", "src/Ingestion Layer"):
    if str(REPO / sub) not in sys.path:
        sys.path.insert(0, str(REPO / sub))

import graph_generate  # noqa: E402
import processing  # noqa: E402
from provenance_export import UCO_CORE, build_provenance_graph, evidence_coverage  # noqa: E402
from storage import CaseStorage  # noqa: E402

BASE = "https://w3id.org/caselinker/resource/case/"
P = "Publication date: 2024-05-02\nSource:\n"

TWO_OFFENDERS = P + (
    "Corin Ashcombe, 34, and Reese Thistlewood, 52, were arrested and charged with possession of child "
    "pornography."
)
SENTENCE_AND_RELEASE = P + (
    "Hollis Wexley, 41, pleaded guilty to receipt of child pornography. He was sentenced to 120 months in "
    "federal prison followed by 10 years of supervised release."
)
DECOY = P + (
    "Corin Ashcombe, 55, was arrested after chatting with an undercover officer posing as a 14-year-old "
    "girl. He was charged with attempted enticement of a minor."
)
CYBERTIP = P + (
    "The investigation began after Kik submitted a CyberTip to the National Center for Missing and "
    "Exploited Children. Reese Thistlewood, 29, was arrested and charged with distribution of child "
    "pornography."
)


def _store(tmp_path: Path, cases: dict) -> CaseStorage:
    storage = CaseStorage(str(tmp_path / "links.db"))
    for case_id, text in cases.items():
        raw = {"case_text": text, "case_id": case_id, "source": "TEST", "source_file": f"{case_id}.pdf"}
        features = processing.extract_features(raw)
        merged = processing.assign_comparison_values(processing.MergeProcessing().merge_features(features, None))
        merged["id"] = case_id
        merged.setdefault("raw_data", raw)
        assert storage.store_case(merged)
    return storage


def _generate(tmp_path: Path, cases: dict):
    storage = _store(tmp_path, cases)
    out = tmp_path / "graphs"
    result = graph_generate.generate_graphs(list(cases), out, storage=storage, resume=False)
    assert not result["failed"], result["failed"]
    return result, out


def _links(out: Path, case_id: str) -> dict:
    """{annotation value: sorted node paths} from the written provenance graph."""
    g = Graph().parse(out / f"{case_id}.provenance.ttl", format="turtle")
    links: dict = {}
    for ann, node in g.subject_objects(UCO_CORE.object):
        value = str(g.value(ann, URIRef("http://www.w3.org/ns/prov#value")))
        role = str(g.value(ann, URIRef("https://w3id.org/caselinker/ns/provenance#assertionRole")) or "")
        links.setdefault((value, role), set()).add(str(node).removeprefix(f"{BASE}{case_id}/"))
    return {k: sorted(v) for k, v in links.items()}


def test_each_offender_age_annotation_names_its_own_age_node(tmp_path):
    result, out = _generate(tmp_path, {"links_2024_001": TWO_OFFENDERS})
    links = _links(out, "links_2024_001")
    case = Graph().parse(out / "links_2024_001.ttl", format="turtle")
    ages = {
        str(s).removeprefix(f"{BASE}links_2024_001/"): int(float(o))
        for s, o in case.subject_objects(URIRef("https://cacontology.projectvic.org/temporal#hasAgeInYears"))
    }
    assert sorted(ages.values()) == [34, 52]
    by_age = {v: k for k, v in ages.items()}
    assert links[("34", "perpetrator")] == [by_age[34]]
    assert links[("52", "perpetrator")] == [by_age[52]]
    assert result["coverage_gaps"] == []


def test_imposed_term_and_supervised_release_link_to_their_own_sentence_nodes(tmp_path):
    result, out = _generate(tmp_path, {"links_2024_002": SENTENCE_AND_RELEASE})
    case = Graph().parse(out / "links_2024_002.ttl", format="turtle")
    labels = {
        str(s).removeprefix(f"{BASE}links_2024_002/"): str(o)
        for s, o in case.subject_objects(URIRef("http://www.w3.org/2000/01/rdf-schema#label"))
        if "/sentence/" in str(s)
    }
    node_for = {label: node for node, label in labels.items()}
    links = _links(out, "links_2024_002")
    imposed = [nodes for (value, role), nodes in links.items() if role == "imposed"]
    release = [nodes for (value, role), nodes in links.items() if role == "supervised_release"]
    assert imposed and all(nodes == [node_for["120 months"]] for nodes in imposed)
    assert release and all(nodes == [node_for["10 years supervised release"]] for nodes in release)
    assert result["coverage_gaps"] == []


def test_a_set_aside_age_names_no_node(tmp_path):
    _result, out = _generate(tmp_path, {"links_2024_003": DECOY})
    links = _links(out, "links_2024_003")
    assert not any(value == "14" for value, _role in links)
    assert links[("55", "perpetrator")] == ["person/offender/1/age"]


def test_the_cybertip_and_its_reporter_link_to_their_nodes(tmp_path):
    result, out = _generate(tmp_path, {"links_2024_004": CYBERTIP})
    links = _links(out, "links_2024_004")
    assert links[("cybertip", "case_action")] == ["cybertip"]
    assert links[("Kik", "named_esp")] == ["cybertip/reporter/kik"]
    assert result["coverage_gaps"] == []


def test_a_press_digest_mints_no_age_node_and_links_no_age(tmp_path):
    storage = _store(tmp_path, {"links_2024_005": TWO_OFFENDERS})
    case = storage.get_case("links_2024_005")
    case["press_digest_pollution"] = True
    import features_to_cac

    mapper = features_to_cac.CaseToCAC()
    mapper.map_case(case)
    assert not [n for n in mapper.evidence_nodes if n[0] == "age"]


def test_a_resolution_without_recorded_winners_links_nothing_and_coverage_says_so(tmp_path):
    storage = _store(tmp_path, {"links_2024_006": TWO_OFFENDERS})
    import features_to_cac

    mapper = features_to_cac.CaseToCAC()
    case_graph = features_to_cac.flatten_dataset(mapper.map_case(storage.get_case("links_2024_006"))[0])
    payload = storage.get_case_assertions("links_2024_006")
    resolutions = {f: {k: v for k, v in r.items() if k != "winning_assertion_ids"} for f, r in payload["resolutions"].items()}
    prov = build_provenance_graph(
        "links_2024_006", payload["assertions"], resolutions,
        issued_at="2026-11-10T00:00:00Z", evidence_nodes=mapper.evidence_nodes,
    )
    assert not list(prov.subject_objects(UCO_CORE.object))
    covered, report = evidence_coverage(case_graph, prov)
    assert not covered and "Age node has no annotation" in report


@pytest.mark.parametrize("case_id, text", [("links_2024_001", TWO_OFFENDERS), ("links_2024_002", SENTENCE_AND_RELEASE)])
def test_linked_provenance_still_passes_its_own_shapes(tmp_path, case_id, text):
    from provenance_export import validate_provenance

    _result, out = _generate(tmp_path, {case_id: text})
    conforms, report = validate_provenance(Graph().parse(out / f"{case_id}.provenance.ttl", format="turtle"))
    assert conforms, report
