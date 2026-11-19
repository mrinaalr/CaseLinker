"""The analysis digest keeps registry capabilities out of documented use, and use notes beside the step."""
from __future__ import annotations

import json

import pytest
import yaml

from state_machines.trajectories.affordances import Registry, load
from state_machines.trajectories.digest import case_digest, render, render_html, step_view
from state_machines.trajectories.use_notes import NoteError, validate


def registry(tmp_path) -> Registry:
    cap = {"native": "yes", "default_on": "yes", "first_available": "2011-07", "ended": None,
           "confidence": "approximate", "evidence": []}
    path = tmp_path / "messaging.yaml"
    path.write_text(yaml.safe_dump({"platforms": {"Snapchat": {"launched": 2011, "capabilities": {
        "ephemerality": cap, "unmonitored_communication": dict(cap, confidence="documented"),
        "contact_discovery": cap, "distribution_infrastructure": dict(cap, confidence="documented")}}}}))
    return Registry(load([path]))


def step(action="INITIATE_CONTACT"):
    return {"event_id": "e169", "action": action, "platforms": ["Snapchat"], "affordances": []}


def life(action="INITIATE_CONTACT"):
    return {"action": action, "platforms": [{"key": "Snapchat", "mode": "through", "status": "DIRECT"}],
            "time": [{"basis": "explicit_date", "earliest": "2020-04-01", "latest": "2020-04-01",
                      "precision": "day", "status": "DIRECT"}]}


def test_contact_through_snapchat_offers_ephemerality_and_does_not_record_use(tmp_path):
    view = step_view(step(), life(), registry(tmp_path), [])
    assert view["stated_platform_means"] == ["Snapchat"]
    assert view["documented_feature_use"] == []
    assert view["how_used"] == []
    assert "ephemerality" not in {e["affordance"] for e in view["candidate_capabilities"]}
    assert "ephemerality" in {e["affordance"] for e in view["available_on_platform"]}
    assert view["date"] == {"earliest": "2020-04-01", "latest": "2020-04-01"}


def test_a_communications_act_may_carry_ephemerality_as_a_candidate(tmp_path):
    view = step_view(step("SOLICIT_IMAGERY"), life("SOLICIT_IMAGERY"), registry(tmp_path), [])
    found = next(e for e in view["candidate_capabilities"] if e["affordance"] == "ephemerality")
    assert found["availability"] == "uncertain"          # approximate introduction date
    assert view["documented_feature_use"] == []


def test_a_researcher_note_stays_out_of_documented_use(tmp_path):
    case = {"case_id": "anchorage_pd_2022_007", "events": {"e169": life()}}
    derived = {"tracks": [{"track_id": "t", "kind": "offender", "unordered_pairs": [],
                           "trajectories": [{"trajectory_id": "t.L1", "steps": [step()]}]}]}
    observations = {"observations": [{"kind": "feature", "observation_id": "o0033", "feature_class": "ephemerality",
                                      "feature_term": "self-destructing", "doc_id": "indictment", "pdf_page": 7}]}
    bare = case_digest(case, derived, observations, registry(tmp_path), {})
    offered = {("anchorage_pd_2022_007", "e169"): {"ephemerality", "contact_discovery", "unmonitored_communication"}}
    notes = validate([{
        "case_id": "anchorage_pd_2022_007", "event_id": "e169", "affordance": "ephemerality",
        "judgment": "unclear", "basis": "researcher_inference", "author": "Author",
        "note": "the filing names the feature and does not say it was the means",
    }], offered)
    filled = case_digest(case, derived, observations, registry(tmp_path),
                         {("anchorage_pd_2022_007", "e169"): [{
                             "affordance": "ephemerality", "judgment": "unclear", "author": "Author", "note": notes[0]["note"]}]})
    got = filled["tracks"][0]["chains"][0]["steps"][0]
    assert got["documented_feature_use"] == []
    assert got["how_used"][0]["affordance"] == "ephemerality"
    assert bare["stated_feature_phrases"][0]["feature_term"] == "self-destructing"
    text = render({"release": "fixture", "use_notes": 1, "cases": [filled], "claims": {}})
    assert "documented use" not in text.split("e169")[1].split("\n")[0]
    assert "how used" in text


def test_the_coding_bench_contains_the_digest_and_no_filing_text():
    page = render_html({"release": "fixture", "use_notes": 0, "claims": {}, "cases": [
        {"case_id": "anchorage_pd_2022_007", "tracks": [], "stated_feature_phrases": []}]})
    assert "anchorage_pd_2022_007" in page and "__DIGEST__" not in page
    assert "quote" not in page and "span_text" not in page


def test_a_model_cannot_author_a_use_note():
    with pytest.raises(NoteError):
        validate([{
            "case_id": "c", "event_id": "e169", "affordance": "ephemerality", "judgment": "used",
            "basis": "model_inference", "author": "Author", "note": "disappearing messages were the means",
        }], {("c", "e169"): {"ephemerality"}})


def test_a_note_cannot_introduce_a_capability_the_frame_does_not_contain():
    with pytest.raises(NoteError):
        validate([{
            "case_id": "c", "event_id": "e169", "affordance": "generative_synthesis", "judgment": "used",
            "basis": "researcher_inference", "author": "Author", "note": "images were generated",
        }], {("c", "e169"): {"ephemerality"}})
