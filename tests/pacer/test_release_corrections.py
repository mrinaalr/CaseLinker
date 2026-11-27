"""Pre-publication corrections to the AfH 2.0 PACER release (instrument only; the evidence is unchanged).

1. Coder provenance: a published act's platform interaction is coder A's, never compared with coder B.
2. Historical availability: an uncertain registry entry is never stated as access, in claims, graphs or /lifecycle.
4. /lifecycle shows SAME_ACT links and cross-track order without changing a chain.
5. The Level-3 query stays inside one case's graphs.
"""
from __future__ import annotations

import copy
import json

import rdflib

from state_machines.coding.resolve import FIELD_STANDING, resolve
from state_machines.graphs.emit import evidence_graph, serialize, trajectory_graph
from state_machines.observations.queries import QUERIES
from state_machines.trajectories.derive import derive
from state_machines.trajectories.payload import case_payload
from tests.pacer import fixtures as F
from tests.pacer.test_affordance_levels import cap, registry, scenario, step
from tests.pacer.test_resolve import _coders

CLT = rdflib.Namespace("https://w3id.org/caselinker/trajectory#")


# -- 1. coder provenance ----------------------------------------------------------------------------

def _with_platforms(a_platform: str, b_platform: str):
    a, b = _coders()
    for bundle, key in ((a, a_platform), (b, b_platform)):
        e = next(e for e in bundle["events"] if e["event_id"] == "e02")
        e["platform_interactions"] = [{"platform_surface": key, "platform_key": key, "mode": "through",
                                       "audience": "one_to_one", "status": "DIRECT", "support": [F.S("p02", "platform")]}]
    return a, b


def test_published_platform_is_coder_a_s_even_when_coder_b_names_another():
    a, b = _with_platforms("Chirpline", "Otherline")
    out, _ = resolve(a, b)
    e02 = next(e for e in out["events"] if e["event_id"] == "e02")
    assert [i["platform_key"] for i in e02["platform_interactions"]] == ["Chirpline"]
    assert "platform_interactions" in FIELD_STANDING["coder_a"]
    assert "platform_interactions" not in FIELD_STANDING["intersected"]


def test_report_does_not_say_both_coders_coded_the_platform(tmp_path, monkeypatch):
    from state_machines.coding import report as R
    rel = tmp_path / "rel" / "cases"
    rel.mkdir(parents=True)
    a, b = _with_platforms("Chirpline", "Otherline")
    out, _ = resolve(a, b)
    (rel / "synth.json").write_text(json.dumps(out))
    monkeypatch.setattr(R, "DATA", tmp_path)
    counts = R.published_content("rel")
    assert not any("both coders coded a platform" in k for k in counts)
    assert any("coder A" in k and "platform interaction" in k for k in counts)


def test_evidence_graph_marks_coder_a_relationships_single_coder():
    a, b = _with_platforms("Chirpline", "Otherline")
    out, _ = resolve(a, b)
    g = rdflib.Graph().parse(data=serialize(evidence_graph(out)), format="json-ld")
    UCO = rdflib.Namespace("https://ontology.unifiedcyberontology.org/uco/core/")
    through = [r for r in g.subjects(UCO.kindOfRelationship, rdflib.Literal("Carried_Out_Through"))]
    assert through and all(g.value(r, CLT.reviewStatus) == rdflib.Literal("single_coder") for r in through)
    plain = copy.deepcopy(out)     # the same acts, not from a machine resolution: relationships are not marked
    plain["coding"] = dict(plain["coding"], coder_id="adjudicator")
    g2 = rdflib.Graph().parse(data=serialize(evidence_graph(plain)), format="json-ld")
    through2 = list(g2.subjects(UCO.kindOfRelationship, rdflib.Literal("Carried_Out_Through")))
    assert through2 and not any(g2.value(r, CLT.reviewStatus) for r in through2)


# -- 2. historical availability ---------------------------------------------------------------------

def _undated_messaging():
    b = scenario("messaging")
    next(e for e in b["events"] if e["event_id"] == "e02")["time"] = {"assertions": []}
    return b


def test_undated_act_has_no_supported_candidate(tmp_path):
    s = step(_undated_messaging(), registry(tmp_path))
    assert s["claims"]["candidate_capabilities"]                    # the union is still reported, as before
    assert s["claims"]["candidate_capabilities_supported"] == []
    assert set(s["claims"]["candidate_capabilities_uncertain"]) == set(s["claims"]["candidate_capabilities"])
    assert {c["availability"] for c in s["capability_status"]} == {"uncertain"}


def test_dated_act_inside_documented_period_is_supported_and_keeps_default_on(tmp_path):
    s = step(scenario("messaging"), registry(tmp_path, unmonitored_communication=cap(default_on="no")))
    um = next(c for c in s["capability_status"] if c["affordance"] == "unmonitored_communication")
    assert um["availability"] == "supported" and um["default_on"] is False and um["action_relevant"] is True
    assert "unmonitored_communication" in s["claims"]["candidate_capabilities_supported"]


def test_trajectory_graph_states_access_only_for_supported_entries(tmp_path):
    reg = registry(tmp_path)
    for bundle, expect in ((_undated_messaging(), False), (scenario("messaging"), True)):
        g = rdflib.Graph().parse(data=serialize(trajectory_graph(bundle, derive(bundle, "INFERRED", reg))), format="json-ld")
        relevant = list(g.objects(None, CLT.stepRelevantAffordance))
        entries = [str(o) for o in g.objects(None, CLT.capabilityEntry)]
        assert bool(relevant) is expect
        assert entries and all(e.count("|") == 3 and "|default_on=" in e for e in entries)
        assert any("|uncertain|" in e for e in entries) or expect


def test_lifecycle_payload_carries_status_and_default(tmp_path):
    b = _undated_messaging()
    reg = registry(tmp_path)
    p = case_payload(b, {"DIRECT": derive(b, "DIRECT", reg), "INFERRED": derive(b, "INFERRED", reg)})
    caps = p["events"]["e02"]["capabilities"]
    assert caps and {c["availability"] for c in caps} == {"uncertain"} and all("default_on" in c for c in caps)


# -- 4. /lifecycle: SAME_ACT and cross-track order, chains unchanged ---------------------------------

def test_payload_lists_same_act_and_cross_track_order_without_changing_chains():
    b, _ = F.build()
    offender = [e["event_id"] for e in b["events"] if e["action"] not in ("PROC_CHARGE", "PROC_PLEA", "PROC_SENTENCE")][:2]
    x, y = offender
    b2 = copy.deepcopy(b)
    b2["relations"] = b2["relations"] + [
        {"relation_id": "same-x-y", "type": "SAME_ACT", "from_event": x, "to_event": y, "basis": "coder_inference",
         "status": "INFERRED", "support": [], "review": {"status": "rule_derived", "coders": [], "adjudicator": None}}]
    before = derive(b, "DIRECT")
    after = derive(b2, "DIRECT")
    assert [[s["event_id"] for s in L["steps"]] for t in before["tracks"] for L in t["trajectories"]] == \
           [[s["event_id"] for s in L["steps"]] for t in after["tracks"] for L in t["trajectories"]]
    p = case_payload(b2, {"DIRECT": after, "INFERRED": derive(b2, "INFERRED")})
    assert {s["event"] for s in p["events"][x]["same_act"]} == {y}


def test_cross_track_order_is_listed_on_both_acts():
    b, _ = F.build()
    track = next(t for t in b["tracks"] if len(t["event_ids"]) >= 2)
    x, y = track["event_ids"][0], track["event_ids"][-1]
    for t in b["tracks"]:                      # y moves to a track of its own, so x and y share none
        t["event_ids"] = [e for e in t["event_ids"] if e != y]
    b["tracks"].append({"track_id": "split", "kind": track["kind"], "event_ids": [y],
                        **({"anchor_ref": track["anchor_ref"]} if track.get("anchor_ref") else {})})
    assert not ({t["track_id"] for t in b["tracks"] if x in t["event_ids"]} & {t["track_id"] for t in b["tracks"] if y in t["event_ids"]})
    b["relations"].append({"relation_id": "so-x-y", "type": "BEFORE", "from_event": x, "to_event": y,
                           "basis": "explicit_sequence_language", "status": "DIRECT", "support": [],
                           "review": {"status": "rule_derived", "coders": [], "adjudicator": None}})
    p = case_payload(b, {"DIRECT": derive(b, "DIRECT"), "INFERRED": derive(b, "INFERRED")})
    assert p["events"][x]["cross_track_order"][0]["this_act_is"] == "before"
    assert p["events"][y]["cross_track_order"][0]["this_act_is"] == "after"


def test_release_lifecycle_shows_the_known_cases():
    from state_machines.trajectories.payload import DATA
    path = DATA / "pacer-v2" / "lifecycle.json"
    if not path.is_file():
        return
    cases = {c["case_id"]: c for c in json.loads(path.read_text())["cases"]}
    ky = cases["ky_sp_2025_038"]["events"]
    assert {o["event"] for o in ky["e048"].get("cross_track_order", [])} == {"e049"}
    nc = cases["ncmec_2022_575"]["events"]
    assert {s["event"] for s in nc["e014"]["same_act"]} == {"e015", "e016"}
    assert json.loads(path.read_text())["release"]["field_standing"]["coder_a"]["fields"][0] == "platform_interactions"


# -- 5. Level-3 query --------------------------------------------------------------------------------

def test_level3_query_binds_relationship_and_act_graphs_from_the_case():
    q = QUERIES["supported"]["sparql"]
    assert "BIND(IRI(CONCAT(?base, \":evidence\")) AS ?eg)" in q and "VALUES ?part" in q
    from rdflib.plugins.sparql import prepareQuery
    prepareQuery(q)


# -- missing availability status (a release derived before the correction) is unknown, never uncertain --------

def test_candidate_status_reads_missing_status_as_unknown():
    from state_machines.trajectories.claims import candidate_status
    assert candidate_status({"candidate_capabilities": []}) == "none"
    assert candidate_status({"candidate_capabilities": ["distribution_infrastructure"]}) == "unknown"
    assert candidate_status({"candidate_capabilities": ["x"], "candidate_capabilities_supported": [], "candidate_capabilities_uncertain": ["x"]}) == "uncertain"
    assert candidate_status({"candidate_capabilities": ["x"], "candidate_capabilities_supported": ["x"], "candidate_capabilities_uncertain": []}) == "supported"


def test_report_counts_superseded_derived_steps_as_status_unknown(tmp_path, monkeypatch):
    from state_machines.coding import report as R
    (tmp_path / "old" / "cases").mkdir(parents=True)
    (tmp_path / "old" / "derived").mkdir()
    old_step = {"event_id": "e1", "claims": {"stated_platform_means": ["Chirpline"], "candidate_capabilities": ["distribution_infrastructure"],
                                             "available_on_platform": [], "documented_feature_use": [], "how_used": None}}
    (tmp_path / "old" / "derived" / "synth.direct.json").write_text(json.dumps(
        {"case_id": "synth", "tracks": [{"trajectories": [{"steps": [old_step]}]}]}))
    monkeypatch.setattr(R, "DATA", tmp_path)
    counts = R.published_content("old")
    assert counts.get("derived steps with a registry candidate: status unknown") == 1
    assert not any(k.endswith(": uncertain only") or k.endswith(": supported") for k in counts)
