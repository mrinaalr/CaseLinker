"""Step-count estimators and the observed-process value (state_machines/README.md)."""

from collections import defaultdict

import pytest

from state_machines.bellman import observed_value
from state_machines.estimators import (
    NO_TAG,
    backbone,
    observed_policy,
    path_coverage_intervention,
    phase_chain,
    step_counts,
    steps_from_case,
    transition_estimate,
)
from state_machines.iris import STING_OPERATION

# Exploitation repeats inside case c1, so case counts and step counts differ.
CASES = {
    "c1": (["I", "C", "E", "M", "E"], [None, "anon", "unmon", "dist", "dist"]),
    "c2": (["I", "C", "E", "M"], [None, "anon", None, "dist"]),
    "c3": (["I", "C", "E", STING_OPERATION], [None, "disc", "unmon", "coord"]),
}


def _steps():
    return [s for cid, (t, a) in CASES.items() for s in steps_from_case(cid, t, a)]


def test_rows_sum_to_one():
    n = step_counts(_steps())
    for row in transition_estimate(n).values():
        assert sum(row.values()) == pytest.approx(1.0)
    for row in observed_policy(n).values():
        assert sum(row.values()) == pytest.approx(1.0)
    out = defaultdict(float)
    for (src, _dst), p in phase_chain(n).items():
        out[src] += p
    assert all(v == pytest.approx(1.0) for v in out.values())


def test_chain_counts_steps_not_cases():
    chain = phase_chain(step_counts(_steps()))
    # E is left 4 times: M (c1, c2, c1's second E has no successor), Sting (c3).
    assert chain[("E", "M")] == pytest.approx(2 / 3)
    assert chain[("E", STING_OPERATION)] == pytest.approx(1 / 3)


def test_untagged_steps_stay_in_policy_not_in_t_hat():
    n = step_counts(_steps())
    assert NO_TAG in observed_policy(n)["C"]
    assert all(aff != NO_TAG for (_s, aff) in transition_estimate(n))


def test_backbone_uses_completed_trajectories_only():
    seqs = {cid: t for cid, (t, _a) in CASES.items()}
    assert backbone(seqs) == ["C", "E", "I", "M"]
    kappa = path_coverage_intervention(seqs, "M", lambda _cid: "g")
    assert kappa["g"] == {"kappa": 0.0, "avoiding": 0, "completed": 2}


def test_value_is_an_expectation_not_a_max():
    chain = {("A", "B"): 0.5, ("A", "C"): 0.5}
    v = observed_value(chain, {"B": 10.0}, gamma=0.5)
    assert v["A"] == pytest.approx(0.5 * 0.5 * 10.0)  # a max would give 5.0


def test_gamma_one_is_rejected_for_a_recurrent_chain():
    with pytest.raises(ValueError):
        observed_value({("E", "M"): 1.0, ("M", "E"): 1.0}, {"M": 1.0}, gamma=1.0)
