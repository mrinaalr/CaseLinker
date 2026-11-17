"""Integrity rules T01-T14. Each rule has a fixture that fails without it."""
from __future__ import annotations

import json

import pytest

from tests.pacer import fixtures as F
from state_machines.evidence import evidence as E
from state_machines.evidence.schema import SCHEMA_PATH, schema_json
from state_machines.evidence.validate import identifier_hits, validate


def run(bundle, root, **kw):
    return F.codes(validate(bundle, text_root=root, **kw))


def ev(bundle, eid):
    return next(e for e in bundle["events"] if e["event_id"] == eid)


def test_committed_schema_matches_generator():
    assert SCHEMA_PATH.read_text(encoding="utf-8") == schema_json()


def test_fictional_case_is_valid_and_every_passage_verifies(tmp_path):
    bundle = F.fresh(tmp_path)
    findings = validate(bundle, text_root=tmp_path, require_verified=True)
    assert [f for f in findings if f.severity == "error"] == []


def test_T01_schema_rejects_synthetic_status_and_unknown_codes(tmp_path):
    b = F.fresh(tmp_path)
    ev(b, "e03")["status"] = "SYNTHETIC"
    assert run(b, tmp_path) == ["T01"]
    b = F.fresh(tmp_path)
    ev(b, "e03")["action"] = "ConditioningPhase"
    assert run(b, tmp_path) == ["T01"]
    b = F.fresh(tmp_path)
    ev(b, "e01")["affordances"][0]["affordance"] = "coordination"   # old June class, not in O
    assert run(b, tmp_path) == ["T01"]


def test_T02_duplicate_ids(tmp_path):
    b = F.fresh(tmp_path)
    b["events"].append(dict(ev(b, "e01")))
    assert "T02" in run(b, tmp_path)


def test_T03_dangling_passage_in_platform_mention(tmp_path):
    b = F.fresh(tmp_path)
    ev(b, "e01")["platform_mentions"] = [{"platform_surface": "messaging application", "passage_ids": ["p99"]}]
    assert run(b, tmp_path) == ["T03"]


def test_T03_dangling_passage_and_unsupported_relation(tmp_path):
    b = F.fresh(tmp_path)
    ev(b, "e01")["support"][0]["passage_id"] = "p99"
    assert run(b, tmp_path) == ["T03"]
    b = F.fresh(tmp_path)
    b["relations"][0]["support"] = []
    assert run(b, tmp_path) == ["T03"]


def test_T04_provenance_hash_mismatch_and_missing_page_text(tmp_path):
    b = F.fresh(tmp_path)
    p = b["passages"][0]
    p["char_start"] += 3                    # offsets drift off the quoted text
    assert run(b, tmp_path) == ["T04"]
    b = F.fresh(tmp_path)
    E.write_page(F.CASE, "sof", 1, F.PAGES[("sof", 1)].replace("public group", "private group"), tmp_path)
    assert run(b, tmp_path) == ["T04"]       # page text no longer matches the bundle hash
    b = F.fresh(tmp_path / "elsewhere")
    assert run(b, tmp_path / "empty", require_verified=True) == ["T04"]
    assert run(b, tmp_path / "empty") == []  # without the local store it is a warning, not an error


def test_T05_ocr_page_needs_image_check(tmp_path):
    b = F.fresh(tmp_path)
    jdg = next(d for d in b["documents"] if d["doc_id"] == "jdg")
    jdg["pages"][0]["image_checked"] = False
    assert run(b, tmp_path) == ["T05"]


def test_T06_allegation_cannot_become_admitted(tmp_path):
    b = F.fresh(tmp_path)
    next(p for p in b["passages"] if p["passage_id"] == "p06")["source_status"] = "ADMITTED"
    assert run(b, tmp_path) == ["T06"]      # a conviction elsewhere does not upgrade an indictment passage
    b = F.fresh(tmp_path)
    next(p for p in b["passages"] if p["passage_id"] == "p07")["source_status"] = "VERDICT_ELEMENT"
    assert run(b, tmp_path) == ["T06"]      # allowed for a judgment, but only with a reason


def test_T07_event_status_needs_matching_support(tmp_path):
    b = F.fresh(tmp_path)
    ev(b, "e03")["support"][0]["status"] = "INFERRED"
    assert run(b, tmp_path) == ["T07"]
    b = F.fresh(tmp_path)
    ev(b, "e03")["support"][0]["facet"] = "time"
    assert run(b, tmp_path) == ["T07"]


def test_T08_law_enforcement_and_victims_cannot_perform_offender_actions(tmp_path):
    b = F.fresh(tmp_path)
    ev(b, "e07")["action"] = "TRAVEL_TO_MEET"
    assert run(b, tmp_path) == ["T08"]
    b = F.fresh(tmp_path)
    ev(b, "e04")["action"] = "SOLICIT_IMAGERY"
    assert run(b, tmp_path) == ["T08"]


def test_T09_instrumental_affordance_needs_feature_evidence(tmp_path):
    b = F.fresh(tmp_path)
    ev(b, "e01")["affordances"][0]["basis"] = "platform_name_only"   # no longer a level-C basis
    assert run(b, tmp_path) == ["T01"]
    b = F.fresh(tmp_path)
    ev(b, "e01")["affordances"][0]["support"][0]["facet"] = "action"
    assert run(b, tmp_path) == ["T09"]   # DIRECT affordance needs a DIRECT passage about the feature


def test_T15_documented_interaction_needs_a_platform_passage(tmp_path):
    b = F.fresh(tmp_path)
    ev(b, "e02")["platform_interactions"] = [{"platform_surface": "messaging application",
                                              "platform_key": "unnamed:messaging application", "mode": "through",
                                              "audience": "one_to_one", "status": "DIRECT",
                                              "support": [F.S("p02", "action")]}]
    assert run(b, tmp_path) == ["T15"]
    ev(b, "e02")["platform_interactions"][0]["support"] = [F.S("p02", "platform")]
    assert run(b, tmp_path) == []


def test_T10_harm_on_undercover_persona_is_rejected(tmp_path):
    b = F.fresh(tmp_path)
    ev(b, "e03")["harms"][0]["victim_kind"] = "undercover_persona"
    assert run(b, tmp_path) == ["T10"]
    b = F.fresh(tmp_path)
    b["participants"][1]["kind"] = "persona"
    assert "T10" in run(b, tmp_path)


def test_T10_harm_needs_the_victim_as_a_victim_target_of_the_event(tmp_path):
    b = F.fresh(tmp_path)
    ev(b, "e03")["targets"] = [{"participant_ref": "P2", "role": "recipient"}]
    assert run(b, tmp_path) == ["T10"]


def test_T11_false_chronology_cycle(tmp_path):
    b = F.fresh(tmp_path)
    b["relations"].append(F._rel("r99", "BEFORE", "e03", "e01", [F.S("p01", "time")]))
    assert "T11" in run(b, tmp_path)


def test_T12_order_contradicted_by_dates(tmp_path):
    b = F.fresh(tmp_path)
    b["relations"].append(F._rel("r99", "BEFORE", "e07", "e06", [F.S("p07", "time")]))
    assert run(b, tmp_path) == ["T12", "T16"]   # arrest on Apr 3 cannot precede a threat on Apr 2


def test_T16_transitive_conflict_between_order_and_dates(tmp_path):
    b = F.fresh(tmp_path)
    # arrest e07 (Apr 3) BEFORE the undated e05, and e05 BEFORE the threat e06 (Apr 2, relation r06).
    # No single relation contradicts a date (T12 is silent), but the chain does.
    b["relations"].append(F._rel("r99", "BEFORE", "e07", "e05", [F.S("p07", "time")]))
    assert run(b, tmp_path) == ["T16"]


def test_T13_dates_need_a_passage(tmp_path):
    b = F.fresh(tmp_path)
    ev(b, "e06")["time"]["assertions"][0]["passage_ids"] = []
    assert run(b, tmp_path) == ["T01"]


def test_T13_real_calendar_dates(tmp_path):
    b = F.fresh(tmp_path)
    ev(b, "e06")["time"]["assertions"][0].update(earliest="2024-02-30", latest="2024-02-30")
    assert "T13" in run(b, tmp_path)


def test_T13_enclosing_window_is_an_inferred_constraint(tmp_path):
    b = F.fresh(tmp_path)
    a = ev(b, "e02")["time"] = F._when("2024-03", "p09", "month", "the count window", basis="enclosing_window")
    assert run(b, tmp_path) == ["T13"]                      # DIRECT window: rejected
    a["assertions"][0]["status"] = "INFERRED"
    assert run(b, tmp_path) == []


def test_T13_contradictory_dates_must_be_flagged_and_kept(tmp_path):
    b = F.fresh(tmp_path)
    t = ev(b, "e06")["time"]
    t["assertions"].append({"expression": "May 2024", "precision": "month", "earliest": "2024-05-01",
                            "latest": "2024-05-31", "basis": "explicit_date", "status": "DIRECT", "passage_ids": ["p10"]})
    assert "T13" in run(b, tmp_path)
    t["conflict_flagged"] = True
    assert "T13" not in run(b, tmp_path)


def test_contradicted_event_gives_no_date_order(tmp_path):
    from state_machines.trajectories.derive import date_order
    b = F.fresh(tmp_path)
    b["relations"] = []
    assert ("e06", "e07") in date_order(b, ("DIRECT", "INFERRED"))
    t = ev(b, "e06")["time"]
    t["assertions"].append({"precision": "day", "earliest": "2024-05-09", "latest": "2024-05-09",
                            "basis": "explicit_date", "status": "DIRECT", "passage_ids": ["p10"]})
    t["conflict_flagged"] = True
    assert not any("e06" in p for p in date_order(b, ("DIRECT", "INFERRED")))


def test_enclosing_window_orders_only_at_the_inferred_threshold(tmp_path):
    from state_machines.trajectories.derive import date_order
    b = F.fresh(tmp_path)
    b["relations"] = []
    ev(b, "e02")["time"] = F._when("2024-02", "p09", "month", "the count window", basis="enclosing_window", status="INFERRED")
    assert ("e02", "e06") in date_order(b, ("DIRECT", "INFERRED"))
    assert ("e02", "e06") not in date_order(b, ("DIRECT",))


def test_T17_one_person_can_hold_different_roles_in_different_events(tmp_path):
    b = F.fresh(tmp_path)
    # P3 is a co-offender in e05 and the target of the defendant's threat in e06 (R04)
    ev(b, "e05")["co_actors"] = [{"participant_ref": "P3", "role": "co_offender", "mode": "assisting"}]
    ev(b, "e06")["targets"].append({"participant_ref": "P3", "role": "victim"})
    ev(b, "e06")["harms"].append({"harm": "HARM_EXPOSURE_THREAT", "victim_ref": "P3", "victim_kind": "adult",
                                  "status": "DIRECT", "support": [F.S("p06")]})
    assert run(b, tmp_path) == []


def test_adult_directed_harm_is_not_counted_in_H0(tmp_path):
    from state_machines.trajectories.afh import case_harms
    b = F.fresh(tmp_path)
    for h in ev(b, "e06")["harms"]:
        h["victim_kind"] = "adult"
    assert "h4" not in case_harms(b, "INFERRED")
    assert "h4" in case_harms(b, "INFERRED", victim_kinds=("minor", "adult"))


def test_T17_collectives(tmp_path):
    b = F.fresh(tmp_path)
    b["participants"].append({"participant_ref": "P4", "kind": "collective",
                              "count": {"min": 3, "max": None, "stated": "at_least", "support": [F.S("p08", "count")]},
                              "members": [{"participant_ref": "P1", "status": "INFERRED", "support": [F.S("p08", "membership", "INFERRED")]}]})
    ev(b, "e08")["targets"].append({"participant_ref": "P4", "role": "recipient"})
    assert run(b, tmp_path) == []
    b["participants"][-1]["count"]["support"] = []
    assert run(b, tmp_path) == ["T17"]
    b["participants"][-1]["count"]["support"] = [F.S("p08", "count")]
    b["participants"][0]["members"] = [{"participant_ref": "P2", "status": "DIRECT", "support": [F.S("p01", "membership")]}]
    assert run(b, tmp_path) == ["T17"]               # only a collective has members


def test_T17_persona_only_acts_as_undercover(tmp_path):
    b = F.fresh(tmp_path)
    b["participants"].append({"participant_ref": "P5", "kind": "persona"})
    ev(b, "e07")["actor"] = {"participant_ref": "P5", "role": "law_enforcement"}
    assert "T17" in run(b, tmp_path)


def test_T08_directing_co_actor_is_not_held_to_the_action_family(tmp_path):
    b = F.fresh(tmp_path)
    ev(b, "e08")["co_actors"] = [{"participant_ref": "P3", "role": "law_enforcement", "mode": "assisting"}]
    assert "T08" in run(b, tmp_path)
    ev(b, "e08")["co_actors"][0]["mode"] = "directing"
    assert "T08" not in run(b, tmp_path)


def test_T18_possible_identity_never_direct_and_never_merges(tmp_path):
    from state_machines.trajectories.derive import derive
    b = F.fresh(tmp_path)
    base = derive(b, "INFERRED")
    b["relations"].append(F._rel("r20", "SAME_ACT", "e06", "e08", [F.S("p08", "action", "INFERRED")],
                                 basis="coder_inference", status="INFERRED"))
    assert run(b, tmp_path) == []
    d = derive(b, "INFERRED")
    strip = lambda d: [[s["event_id"] for s in L["steps"]] for t in d["tracks"] for L in t["trajectories"]]  # noqa: E731
    assert strip(d) == strip(base)                       # no merge, no new order, same chains
    assert d["tracks"][0]["possible_same_act"] == [["e06", "e08"]]
    b["relations"][-1]["status"] = "DIRECT"
    assert "T18" in run(b, tmp_path)


def test_T18_possible_identity_between_ordered_events_warns(tmp_path):
    b = F.fresh(tmp_path)
    b["relations"].append(F._rel("r21", "SAME_ACT", "e01", "e03", [F.S("p03", "action", "INFERRED")],
                                 basis="coder_inference", status="INFERRED"))
    findings = validate(b, text_root=tmp_path)
    assert not [f for f in findings if f.severity == "error"]
    assert any(f.code == "T18" and f.severity == "warning" for f in findings)


@pytest.mark.parametrize("text", [
    "Defendant used the handle dark_fox99 to reach the minor.",
    "Contacted the minor at 904-555-0100.",
    "Emailed coach.fictional@example.com about the images.",
    "Messaged @fictionalhandle after the block.",
    "Victim J.Q. was 14.",
])
def test_T14_direct_identifiers_in_coded_text(tmp_path, text):
    b = F.fresh(tmp_path)
    ev(b, "e01")["description"] = text
    assert run(b, tmp_path) == ["T14"]


def test_T14_deny_list_catches_names_from_the_caption(tmp_path):
    b = F.fresh(tmp_path)
    ev(b, "e01")["notes"] = "Per Quillfeather's proffer the contact came first."
    assert run(b, tmp_path, deny_list=["Quillfeather"]) == ["T14"]
    assert identifier_hits("Court records: U.S. District Court, E.D. Va., D.C.") == []


def test_bundle_holds_no_quote_text(tmp_path):
    bundle, quotes = F.build()
    text = json.dumps(bundle)
    assert not any(q in text for q in quotes.values() if len(q.split()) > 4)
