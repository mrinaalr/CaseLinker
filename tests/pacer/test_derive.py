"""Trajectory derivation: partial order, tracks, interruptions, O_i, determinism."""
from __future__ import annotations

import copy

import pytest

from tests.pacer import fixtures as F
from state_machines.trajectories import afh
from state_machines.trajectories.derive import DerivationError, derive, derived_json


def steps(L):
    return [s["event_id"] for s in L["steps"]]


@pytest.fixture
def bundle():
    b, _ = F.build()
    return b


def test_unordered_events_split_into_separate_chains_not_a_forced_sequence(bundle):
    track = derive(bundle, "INFERRED")["tracks"][0]
    chains = [steps(L) for L in track["trajectories"]]
    assert chains == [["e01", "e02", "e03", "e05", "e06"], ["e01", "e02", "e03", "e05", "e08"]]
    assert ["e06", "e08"] in track["unordered_pairs"]


def test_direct_threshold_drops_inferred_order_and_annotations(bundle):
    track = derive(bundle, "DIRECT")["tracks"][0]
    chains = [steps(L) for L in track["trajectories"]]
    # e02 -> e03 and e05 -> e06 rest on INFERRED order only: under DIRECT they are not ordered.
    assert ["e01", "e02"] in chains and ["e03", "e05", "e08"] in chains
    assert all(not ({"e02", "e03"} <= set(c)) for c in chains)
    e08 = next(s for L in track["trajectories"] for s in L["steps"] if s["event_id"] == "e08")
    assert e08["affordances"] == []        # its affordance is INFERRED; O_i may be empty


def test_non_offender_events_never_become_steps(bundle):
    track = derive(bundle, "INFERRED")["tracks"][0]
    assert {"e04", "e07"} == {x["event_id"] for x in track["excluded_events"]}
    assert all(s["action"] not in ("RESP_BLOCK", "LE_ARREST") for L in track["trajectories"] for s in L["steps"])


def test_consecutive_steps_are_not_immediate_unless_meets_is_stated(bundle):
    L = derive(bundle, "INFERRED")["tracks"][0]["trajectories"][0]
    assert [s["immediate_after_previous"] for s in L["steps"]] == [False] * 5
    b = copy.deepcopy(bundle)
    b["relations"].append(F._rel("r20", "MEETS", "e01", "e02", [F.S("p11", "time")]))
    L = derive(b, "INFERRED")["tracks"][0]["trajectories"][0]
    assert L["steps"][1]["immediate_after_previous"] is True


def test_interruptions_attach_to_the_interrupted_step(bundle):
    L = derive(bundle, "INFERRED")["tracks"][0]["trajectories"][0]
    assert L["steps"][-1]["event_id"] == "e06" and L["steps"][-1]["interrupted_by"] == ["e07"]


def test_O_i_holds_instrumental_annotations_only(bundle):
    L = derive(bundle, "INFERRED")["tracks"][0]["trajectories"][0]
    e02 = L["steps"][1]
    assert e02["affordances"] == ["unmonitored_communication"]
    assert e02["action_relevant_affordances"] == [] and e02["available_affordances"] == []   # no registry, no A/B


def test_order_cycle_is_an_error(bundle):
    bundle["relations"].append(F._rel("r99", "BEFORE", "e03", "e01", [F.S("p01", "time")]))
    with pytest.raises(DerivationError):
        derive(bundle)


def test_no_phases_terminal_states_or_probabilities_in_output(bundle):
    text = derived_json(bundle, "INFERRED")
    for banned in ("Phase", "terminal", "probab", "reward", "utility", "lstar", "bellman"):
        assert banned.lower() not in text.lower()


def test_derivation_is_deterministic(bundle):
    shuffled = copy.deepcopy(bundle)
    shuffled["events"].reverse()
    shuffled["relations"].reverse()
    shuffled["tracks"][0]["event_ids"].reverse()
    a, b = derive(bundle, "INFERRED"), derive(shuffled, "INFERRED")
    assert a["tracks"] == b["tracks"]
    assert derived_json(bundle) == derived_json(bundle)


def test_aff_psi_and_coverage_identity(bundle):
    derived = derive(bundle, "INFERRED")
    affs = afh.case_affordances(derived)
    assert affs == {"anonymity", "contact_discovery", "distribution_infrastructure", "unmonitored_communication"}
    harms = afh.case_harms(bundle)
    assert harms == {"h2", "h3", "h4"}
    cases = [(F.CASE, affs, harms), ("fictional_case_002", set(), {"h5"})]
    psi = afh.psi(cases)
    assert psi["anonymity"] == [("h2", [F.CASE]), ("h3", [F.CASE]), ("h4", [F.CASE])]
    assert psi["generative_synthesis"] == []
    assert afh.coverage_identity_holds(cases)


def test_cited_dates_order_events_and_overlapping_dates_do_not(bundle):
    from state_machines.trajectories.derive import date_order
    b = copy.deepcopy(bundle)
    b["relations"] = []                       # no coded order at all
    pairs = date_order(b, ("DIRECT", "INFERRED"))
    assert ("e01", "e06") in pairs            # March 2024 is before 2024-04-02
    assert ("e06", "e07") in pairs            # 2024-04-02 before 2024-04-03
    assert not any("e02" in p for p in pairs) # undated events get no order from dates
    ev = next(e for e in b["events"] if e["event_id"] == "e06")
    ev["time"].update({"earliest": "2024-03", "latest": "2024-04-02"})
    assert ("e01", "e06") not in date_order(b, ("DIRECT", "INFERRED"))   # overlapping intervals stay unordered


def test_derivation_refuses_when_relations_and_dates_conflict(bundle):
    b = copy.deepcopy(bundle)
    b["relations"].append(F._rel("r99", "BEFORE", "e07", "e06", [F.S("p07", "time")]))   # Apr 3 before Apr 2
    with pytest.raises(DerivationError, match="dates conflict"):
        derive(b, "INFERRED")
