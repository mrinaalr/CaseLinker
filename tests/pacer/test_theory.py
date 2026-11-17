"""Theory layer: AfH Appendix X, reproduced on the paper's own worked example."""
from __future__ import annotations

import ast
import itertools
import random
from pathlib import Path

import pytest

from state_machines.theory.transition_systems import (
    TransitionSystem, aff, admits_partial_order, admits_prefix, appendix_x_example, attribution_holds, delta_path, delta_supp,
    epsilon, monotone_and_local, pi,
)

ROOT = Path(__file__).resolve().parents[2]


def test_worked_example_ephemerality_adds_support_not_a_new_path():
    ex = appendix_x_example()
    P, Pe = ex["P"], ex["P+ephemerality"]
    assert delta_path("ephemerality", P, Pe, 4) == set()                     # Δ_path(e; P) = ∅
    L_e = (("contact", frozenset({"contact_discovery"})),
           ("request", frozenset({"unmonitored_communication", "ephemerality"})))
    assert L_e in delta_supp("ephemerality", P, Pe, 4)                         # L_e ∈ Δ_supp(e; P)


def test_worked_example_synthesis_opens_a_path_without_contact():
    ex = appendix_x_example()
    new = delta_path("generative_synthesis", ex["P"], ex["P+generative_synthesis"], 4)
    assert ("synthesize",) in new                                              # (synthesize) ∈ Δ_path(g; P)
    assert all("contact" not in seq for seq in new)


def test_trajectories_include_prefixes_and_failed_attempts():
    P = appendix_x_example()["P"]
    L = P.trajectories(4)
    assert () in L and (("contact", frozenset({"contact_discovery"})),) in L
    refused = [r for r in P.runs(4) if r and r[-1][3] == "s3"]
    assert refused and pi(epsilon(refused[0])) == ("contact", "request")      # same sequence, different outcome


def test_no_probabilities_rewards_or_policies_anywhere():
    src = (ROOT / "state_machines" / "theory" / "transition_systems.py").read_text()
    tree = ast.parse(src)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | \
            {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | \
            {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    assert not {x for x in names if any(w in x.lower() for w in ("prob", "reward", "utility", "policy", "optimal", "gamma"))}


def test_locality_is_enforced_and_its_violation_breaks_attribution():
    P = appendix_x_example()["P"]
    with pytest.raises(ValueError, match="locality"):
        P.add("ephemerality", [("s0", "synthesize", {"unmonitored_communication"}, "s2")])
    bad = P.add("ephemerality", [("s0", "synthesize", {"unmonitored_communication"}, "s2")], check=False)
    assert not monotone_and_local(P, bad, "ephemerality")["locality"]
    assert not attribution_holds("ephemerality", P, bad, 4)                    # the counterexample


def _random_system(rng: random.Random, n_states=4, actions=("a", "b", "c"), affs=("x", "y", "z")):
    trans = set()
    for s, a, t in itertools.product(range(n_states), actions, range(n_states)):
        if rng.random() < 0.18:
            trans.add((f"s{s}", a, frozenset(rng.sample(affs, rng.randint(0, 2))), f"s{t}"))
    return TransitionSystem.build("s0", trans, extra_affordances=affs)


def test_attribution_proposition_on_generated_systems():
    rng = random.Random(7)
    checked = 0
    for _ in range(60):
        P = _random_system(rng)
        new = [(f"s{rng.randrange(4)}", rng.choice("abcd"), {"o"} | set(rng.sample(["x", "y"], rng.randint(0, 1))),
                f"s{rng.randrange(4)}") for _ in range(rng.randint(1, 3))]
        Po = P.add("o", new)
        assert monotone_and_local(P, Po, "o") == {"monotonicity": True, "locality": True}
        assert attribution_holds("o", P, Po, 4)
        checked += bool(delta_path("o", P, Po, 4))
    assert checked > 5                                                         # non-vacuous: real new paths occurred


def test_documented_sequence_can_be_tested_against_a_model_not_fitted_to_it():
    P = appendix_x_example()["P"]
    assert admits_prefix(P, ["INITIATE_CONTACT", "SOLICIT_IMAGERY"],
                         {"INITIATE_CONTACT": "contact", "SOLICIT_IMAGERY": "request"})
    assert not admits_prefix(P, ["SOLICIT_IMAGERY"], {"SOLICIT_IMAGERY": "request"})


def test_unknown_affordance_in_a_transition_is_rejected():
    with pytest.raises(ValueError):
        TransitionSystem(frozenset({"s0"}), frozenset({"a"}), frozenset(), frozenset({("s0", "a", frozenset({"x"}), "s0")}), "s0")


def test_theory_never_reads_pacer_data():
    for p in (ROOT / "state_machines" / "theory").rglob("*.py"):
        tree = ast.parse(p.read_text())
        mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module} | \
               {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        assert not {m for m in mods if m.startswith("state_machines.") and not m.startswith("state_machines.theory")}, p
        assert "PACER" not in p.read_text().replace("PACER records", "")


def test_partial_order_is_searched_over_every_source_consistent_ordering():
    P = appendix_x_example()["P"]
    amap = {"INITIATE_CONTACT": "contact", "SOLICIT_IMAGERY": "request"}
    acts = {"e1": "SOLICIT_IMAGERY", "e2": "INITIATE_CONTACT"}
    # unordered: the arbitrary listed order (request, contact) fails, but contact-then-request runs
    assert not admits_prefix(P, [acts["e1"], acts["e2"]], amap)
    assert admits_partial_order(P, acts, [], amap) == ("e2", "e1")
    # documented order request-before-contact: no admitted ordering
    assert admits_partial_order(P, acts, [("e1", "e2")], amap) is None


def test_attribution_needs_only_locality():
    # a non-monotone introduction (an old transition removed) still attributes new paths to o
    P = appendix_x_example()["P"]
    kept = frozenset(t for t in P.transitions if t[3] != "s3")
    shrunk = TransitionSystem(P.states, P.actions, P.affordances, kept, P.s0)
    after = shrunk.add("generative_synthesis", [("s0", "synthesize", {"generative_synthesis"}, "s2")])
    assert not monotone_and_local(P, after, "generative_synthesis")["monotonicity"]
    assert attribution_holds("generative_synthesis", P, after, 4)
