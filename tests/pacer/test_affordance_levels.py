"""Three affordance levels: available (A), action-relevant (B), instrumental (C = O_i).

Uses a fictional platform, "Chirpline", so no test datum is a factual claim about a real
product. The three scenarios mirror the codebook example (a court record that names
a messaging app; one that says messages went through it; one that says an anonymous
account was used to hide identity).
"""
from __future__ import annotations

import copy
import json

import pytest

from tests.pacer import fixtures as F
from state_machines.trajectories.affordances import Registry, validate_registry
from state_machines.trajectories.derive import derive
from state_machines.evidence.validate import validate

SRC = [{"citation": "Fictional help centre, 'Accounts'", "url": "https://chirpline.invalid/help/accounts", "accessed": "2026-11-16"}]


def registry_doc(review="reviewed") -> dict:
    cap = lambda cid, aff, feature, frm=None, to=None: {  # noqa: E731
        "capability_id": cid, "platform_id": "chirpline", "feature": feature, "affordance": aff,
        "valid_from": frm, "valid_to": to, "sources": SRC, "review_status": review,
        "reviewed_by": "reviewer_X" if review == "reviewed" else None}
    return {"registry_version": "0.1.0", "platforms": [{"platform_id": "chirpline", "names": ["Chirpline", "Chirpline app"], "kind": "messaging"}],
            "capabilities": [cap("chirpline.pseudonymous_accounts", "anonymity", "accounts without identity verification"),
                             cap("chirpline.private_messages", "unmonitored_communication", "one-to-one private messages"),
                             cap("chirpline.vanishing_messages", "ephemerality", "messages that expire", "2015", "2020-06"),
                             cap("chirpline.public_groups", "contact_discovery", "searchable public groups")]}


def scenario(kind: str) -> dict:
    """The fictional case with event e02 recoded for one scenario."""
    b, _ = F.build()
    e02 = next(e for e in b["events"] if e["event_id"] == "e02")
    e02["affordances"] = []
    e02["time"] = {"earliest": "2024-03", "latest": "2024-03", "precision": "month", "basis": "explicit_date", "passage_ids": ["p09"]}
    if kind == "named_only":
        e02["platform_mentions"] = [{"platform_surface": "Chirpline", "passage_ids": ["p02"]}]
    if kind in ("messaging", "concealment"):
        e02["action"] = "COMMUNICATE"
        e02["platform_interactions"] = [{"platform_surface": "Chirpline", "status": "DIRECT", "support": [F.S("p02", "platform")]}]
    if kind == "concealment":
        e02["affordances"] = [F._aff("anonymity", "p02", basis="mechanism_stated", term="account under another name")]
    return b


def step(bundle, reg, eid="e02", threshold="INFERRED"):
    d = derive(bundle, threshold, Registry(reg))
    return next(s for t in d["tracks"] for L in t["trajectories"] for s in L["steps"] if s["event_id"] == eid)


def test_named_only_platform_gives_no_step_level_affordance():
    s = step(scenario("named_only"), registry_doc())
    assert s["affordances"] == [] and s["action_relevant_affordances"] == [] and s["available_affordances"] == []


def test_documented_messaging_makes_communication_relevant_but_not_anonymity():
    s = step(scenario("messaging"), registry_doc())
    assert s["affordances"] == []                                               # O_i: nothing instrumental
    assert s["action_relevant_affordances"] == ["unmonitored_communication"]    # B
    assert "anonymity" in s["available_affordances"]                            # A only
    assert "anonymity" not in s["action_relevant_affordances"]
    assert ("chirpline.private_messages", "in_period") in [tuple(c) for c in s["capability_evidence"]]


def test_documented_identity_concealment_enters_O_i():
    s = step(scenario("concealment"), registry_doc())
    assert s["affordances"] == ["anonymity"]                                    # C, from the court record
    assert s["action_relevant_affordances"] == ["unmonitored_communication"]    # B is unchanged by C


def test_capability_outside_its_period_is_not_available():
    b = scenario("messaging")
    e02 = next(e for e in b["events"] if e["event_id"] == "e02")
    assert "ephemerality" not in step(b, registry_doc())["available_affordances"]   # expired 2020-06
    next(e for e in b["events"] if e["event_id"] == "e01")["time"] = {"precision": "none", "basis": "none", "passage_ids": []}
    e02["time"] = {"earliest": "2018-01", "latest": "2018-02", "precision": "month", "basis": "explicit_date", "passage_ids": ["p09"]}
    s = step(b, registry_doc())
    assert "ephemerality" in s["available_affordances"] and "ephemerality" in s["action_relevant_affordances"]
    e02["time"] = {"precision": "none", "basis": "none", "passage_ids": []}
    s = step(b, registry_doc())
    assert ("chirpline.vanishing_messages", "period_unchecked") in [tuple(c) for c in s["capability_evidence"]]


def test_proposed_capabilities_are_left_out_unless_asked_for():
    s = step(scenario("messaging"), registry_doc(review="proposed"))
    assert s["available_affordances"] == []
    d = derive(scenario("messaging"), "INFERRED", Registry(registry_doc(review="proposed"), review=("proposed", "reviewed")))
    assert d["derivation"]["capability_review_included"] == ["proposed", "reviewed"]


def test_levels_never_change_O_i_or_the_trajectory_shape():
    plain = derive(scenario("messaging"), "INFERRED", Registry({"registry_version": "0", "platforms": [], "capabilities": []}))
    rich = derive(scenario("messaging"), "INFERRED", Registry(registry_doc()))
    strip = lambda d: [[(s["event_id"], s["affordances"]) for s in L["steps"]] for t in d["tracks"] for L in t["trajectories"]]  # noqa: E731
    assert strip(plain) == strip(rich)


def test_interaction_bundles_validate(tmp_path):
    F.write_pages(tmp_path)
    for kind in ("named_only", "messaging", "concealment"):
        assert [f for f in validate(scenario(kind), text_root=tmp_path) if f.severity == "error"] == []


@pytest.mark.parametrize("mutate,code", [
    (lambda r: r["capabilities"][0].update(sources=[]), "C04"),
    (lambda r: r["capabilities"][0].update(reviewed_by=None), "C04"),
    (lambda r: r["capabilities"][2].update(valid_from="2021"), "C05"),
    (lambda r: r["platforms"].append({"platform_id": "other", "names": ["chirpline"], "kind": "messaging"}), "C02"),
    (lambda r: r["capabilities"][0].update(affordance="coordination"), "C01"),
])
def test_registry_validation_negative_cases(mutate, code):
    reg = registry_doc()
    assert validate_registry(reg) == []
    mutate(reg)
    assert code in {f.code for f in validate_registry(reg)}


def test_capability_and_interaction_graphs_conform_and_reject_bad_claims(monkeypatch):
    pytest.importorskip("case_uco")
    from state_machines.graphs.emit import capability_graph, evidence_graph, serialize, trajectory_graph
    from state_machines.graphs.shacl import validate_jsonld

    reg = registry_doc()
    b = scenario("concealment")
    ev = serialize(evidence_graph(b, Registry(reg)))
    tr = serialize(trajectory_graph(b, derive(b, "INFERRED", Registry(reg))))
    cap = serialize(capability_graph(reg))
    from state_machines.graphs.shacl import validation_report
    r = validation_report(ev, tr, cap)
    assert r["violations"] == [], r["violations"][:5]
    assert r["conformance"] == "fails" and r["upstream_defect_shapes"] == [F.SYNTHESIS_DEFECT]
    F.with_synthesis_fix(monkeypatch)
    r = validation_report(ev, tr, cap)
    # platform nodes carry CAC platform classes, which unrunnable upstream constraints target:
    # the result must say partial, never full, and the release check must not pass unwaived
    assert r["conformance"] == "partial" and r["applicable_skipped"] and not r["release_ok"]
    assert "uco-action:instrument" in ev and "Carried_Out_Through" in ev and "Provides_Affordance" in cap
    doc = json.loads(cap)
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
