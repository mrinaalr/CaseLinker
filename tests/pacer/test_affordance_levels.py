"""Three affordance levels: available (A), action-relevant (B), instrumental (C = O_i).

Uses a fictional platform, "Chirpline", in a registry file shaped like the shared AfH
capability sources, so no test datum is a factual claim about a real product. The three
scenarios mirror the codebook example (a court record that names a messaging app; one that
says messages went through it; one that says an account under another name hid identity).
"""
from __future__ import annotations

import copy
import json

import pytest
import yaml

from tests.pacer import fixtures as F
from state_machines.trajectories.affordances import Registry, load
from state_machines.trajectories.derive import derive
from state_machines.evidence.validate import validate

URL = "https://chirpline.invalid/help/accounts"


def cap(native="yes", confidence="documented", first="2015-01", ended=None, default_on="yes"):
    return {"native": native, "default_on": default_on, "first_available": first, "ended": ended,
            "confidence": confidence, "evidence": [{"url": URL, "publisher": "Chirpline", "published_date": "2015-01-05",
                                                    "supports": "fictional"}]}


def registry(tmp_path, **over) -> Registry:
    caps = {"anonymity": cap(), "unmonitored_communication": cap(), "contact_discovery": cap(),
            "ephemerality": cap(first="2015-03", ended="2020-06"), "generative_synthesis": cap(native="no")}
    caps.update(over)
    path = tmp_path / "messaging.yaml"
    path.write_text(yaml.safe_dump({"platforms": {"Chirpline": {"launched": 2015, "capabilities": caps}}}))
    return Registry(load([path]))


def scenario(kind: str, mode: str = "through") -> dict:
    """The fictional case with event e02 recoded for one scenario."""
    b, _ = F.build()
    e02 = next(e for e in b["events"] if e["event_id"] == "e02")
    e02["affordances"] = []
    e02["time"] = F._when("2024-03", "p09", "month", "March 2024")
    if kind == "named_only":
        e02["platform_mentions"] = [{"platform_surface": "Chirpline", "passage_ids": ["p02"]}]
    if kind in ("messaging", "concealment"):
        e02["action"] = "COMMUNICATE"
        e02["platform_interactions"] = [{"platform_surface": "Chirpline", "platform_key": "Chirpline", "mode": mode,
                                         "audience": "one_to_one", "status": "DIRECT", "support": [F.S("p02", "platform")]}]
    if kind == "concealment":
        e02["affordances"] = [F._aff("anonymity", "p02", basis="mechanism_stated", term="account under another name")]
    return b


def step(bundle, reg, eid="e02", threshold="INFERRED"):
    d = derive(bundle, threshold, reg)
    return next(s for t in d["tracks"] for L in t["trajectories"] for s in L["steps"] if s["event_id"] == eid)


def test_named_only_platform_gives_no_step_level_affordance(tmp_path):
    s = step(scenario("named_only"), registry(tmp_path))
    assert s["affordances"] == [] and s["action_relevant_affordances"] == [] and s["available_affordances"] == []


def test_documented_messaging_makes_communication_relevant_but_not_anonymity(tmp_path):
    s = step(scenario("messaging"), registry(tmp_path))
    assert s["affordances"] == []                                               # O_i: nothing instrumental
    assert s["action_relevant_affordances"] == ["unmonitored_communication"]   # B (ephemerality ended 2020-06)
    assert "anonymity" in s["available_affordances"]                            # A only
    assert "anonymity" not in s["action_relevant_affordances"]
    assert ("Chirpline", "unmonitored_communication", "supported") in s["capability_evidence"]
    assert s["level_unit"] == "event"


def test_contact_through_a_platform_does_not_establish_that_ephemerality_was_used(tmp_path):
    """The platform was the stated means. Ephemerality stays a capability the platform offered.
    It is not action-relevant for contact, and it does not enter O_i. A person may later say how."""
    from state_machines.trajectories.claims import claims

    reg = registry(tmp_path, ephemerality=cap())
    bundle = scenario("messaging")
    event = next(e for e in bundle["events"] if e["event_id"] == "e02")
    event["action"] = "INITIATE_CONTACT"
    got = claims(step(bundle, reg))
    assert got["stated_platform_means"] == ["Chirpline"]
    assert got["documented_feature_use"] == []
    assert "ephemerality" in got["available_on_platform"]
    assert "ephemerality" not in got["candidate_capabilities"]
    assert set(got["candidate_capabilities"]) <= {"contact_discovery", "unmonitored_communication"}
    assert got["how_used"] is None


def test_a_communications_act_may_carry_ephemerality_as_a_candidate_only(tmp_path):
    from state_machines.trajectories.claims import claims

    reg = registry(tmp_path, ephemerality=cap())
    got = claims(step(scenario("messaging"), reg))
    assert "ephemerality" in got["candidate_capabilities"]
    assert got["documented_feature_use"] == []
    assert got["how_used"] is None


def test_documented_identity_concealment_enters_O_i(tmp_path):
    s = step(scenario("concealment"), registry(tmp_path))
    assert s["affordances"] == ["anonymity"]                                    # C, from the court record
    assert "anonymity" not in s["action_relevant_affordances"]                  # B is unchanged by C


def test_availability_is_supported_uncertain_or_unsupported(tmp_path):
    reg = registry(tmp_path, unmonitored_communication=cap(confidence="approximate"),
                   contact_discovery=cap(first=None))
    s = step(scenario("messaging"), reg)
    ev = {(c[1], c[2]) for c in s["capability_evidence"]}
    assert ("unmonitored_communication", "uncertain") in ev        # approximate date never becomes supported
    assert ("contact_discovery", "uncertain") in ev                # unknown introduction date
    assert ("anonymity", "supported") in ev
    assert not any(c == "generative_synthesis" for c, _ in ev)     # not native: unsupported, left out
    assert not any(c == "ephemerality" for c, _ in ev)             # ended 2020-06, event 2024-03: unsupported


def test_event_before_introduction_is_unsupported_and_undated_is_uncertain(tmp_path):
    b = scenario("messaging")
    e02 = next(e for e in b["events"] if e["event_id"] == "e02")
    e02["time"] = F._when("2014-06", "p09", "month", "June 2014")
    next(e for e in b["events"] if e["event_id"] == "e01")["time"] = {"assertions": []}
    assert step(b, registry(tmp_path))["available_affordances"] == []
    e02["time"] = {"assertions": []}
    s = step(b, registry(tmp_path))
    assert {c[2] for c in s["capability_evidence"]} == {"uncertain"}


def test_only_through_and_to_interactions_reach_level_b(tmp_path):
    for mode, expect in (("through", True), ("to", True), ("from", False), ("acted_on", False)):
        s = step(scenario("messaging", mode), registry(tmp_path))
        assert bool(s["action_relevant_affordances"]) is expect, mode


def test_unnamed_platforms_never_match_the_registry(tmp_path):
    b = scenario("messaging")
    inter = next(e for e in b["events"] if e["event_id"] == "e02")["platform_interactions"][0]
    inter["platform_key"] = "unnamed:messaging app"
    s = step(b, registry(tmp_path))
    assert s["available_affordances"] == [] and s["unmatched_platforms"] == ["unnamed:messaging app"]


def test_coded_configuration_is_carried_beside_registry_default(tmp_path):
    from state_machines.trajectories.affordances import event_levels
    b = scenario("messaging")
    e02 = next(e for e in b["events"] if e["event_id"] == "e02")
    e02["platform_interactions"][0]["configuration"] = [{"feature_term": "vanishing messages", "setting": "on",
                                                         "support": [F.S("p02", "configuration")]}]
    lv = event_levels(e02, registry(tmp_path, ephemerality=cap(first="2015-03", default_on="no")), ("DIRECT", "INFERRED"))
    eph = next(c for c in lv["available"] if c["affordance"] == "ephemerality")
    assert eph["default_on"] == "no" and eph["coded_configuration"] == {"vanishing messages": "on"}


def test_levels_never_change_O_i_or_the_trajectory_shape(tmp_path):
    plain = derive(scenario("messaging"), "INFERRED", Registry({"platforms": {}}))
    rich = derive(scenario("messaging"), "INFERRED", registry(tmp_path))
    strip = lambda d: [[(s["event_id"], s["affordances"]) for s in L["steps"]] for t in d["tracks"] for L in t["trajectories"]]  # noqa: E731
    assert strip(plain) == strip(rich)


def test_missing_registry_gives_empty_levels(tmp_path):
    assert load([tmp_path / "absent.yaml"]) == {"platforms": {}}


def test_interaction_bundles_validate(tmp_path):
    F.write_pages(tmp_path)
    for kind in ("named_only", "messaging", "concealment"):
        assert [f for f in validate(scenario(kind), text_root=tmp_path) if f.severity == "error"] == []


def test_channels_are_not_platforms(tmp_path):
    F.write_pages(tmp_path)
    b = scenario("messaging")
    inter = next(e for e in b["events"] if e["event_id"] == "e02")["platform_interactions"][0]
    inter["platform_surface"] = inter["platform_key"] = "text messaging"
    assert "T19" in F.codes(validate(b, text_root=tmp_path))


def test_capability_and_interaction_graphs_conform_and_reject_bad_claims(tmp_path, monkeypatch):
    pytest.importorskip("case_uco")
    from state_machines.graphs.emit import capability_graph, evidence_graph, serialize, trajectory_graph
    from state_machines.graphs.shacl import validate_jsonld, validation_report

    reg = registry(tmp_path)
    b = scenario("concealment")
    ev = serialize(evidence_graph(b))
    tr = serialize(trajectory_graph(b, derive(b, "INFERRED", reg)))
    cap_g = serialize(capability_graph(reg.data))
    r = validation_report(ev, tr, cap_g)
    assert r["violations"] == [], r["violations"][:5]
    assert r["conformance"] == "fails" and r["upstream_defect_shapes"] == [F.SYNTHESIS_DEFECT]
    F.with_synthesis_fix(monkeypatch)
    r = validation_report(ev, tr, cap_g)
    assert r["violations"] == [] and r["conformance"] in ("full", "partial")
    assert "uco-action:instrument" in ev and "Carried_Out_Through" in ev and "Provides_Affordance" in cap_g
    doc = json.loads(cap_g)
    for n in doc["@graph"]:
        n.pop("dcterms:source", None)       # a capability with no cited source
    conforms, messages = validate_jsonld(json.dumps(doc))
    assert not conforms and messages
    doc = json.loads(ev)
    through = next(n for n in doc["@graph"] if n["@id"].startswith("kb:through-"))["@id"]
    doc["@graph"] = [n for n in doc["@graph"] if not ("oa:Annotation" in str(n.get("@type"))
                                                      and n.get("oa:hasBody", {}).get("@id") == through)]
    conforms, messages = validate_jsonld(json.dumps(doc))
    assert not conforms and any("Carried_Out_Through" in m for m in messages)
