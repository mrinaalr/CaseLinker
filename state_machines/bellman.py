"""Value of a phase under the observed process (Bellman expectation equation).

    V_g(s) = R_g(s) + γ Σ_s' P̂(s' | s) V_g(s')

P̂ is the observed phase chain (state_machines.estimators.phase_chain), which
equals Σ_a π̂(a | s) T̂(s' | s, a). There is no max: V_g summarises the
recorded paths and makes no claim that offenders optimise trajectories.

γ < 1 is required. ExploitationPhase is both mid-path and final, so it cannot
be absorbing at the level of phase types, and the Exploitation <-> Maintenance
loop makes the chain recurrent. Phases with no outgoing steps (StingOperation)
take V = R.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Callable

from state_machines.estimators import phase_chain, step_counts, steps_from_case
from state_machines.iris import (
    COERCION_CYCLE,
    EXPLOITATION_PHASE,
    MAINTENANCE_PHASE,
)

DEFAULT_GAMMA = 0.9
PEAK_REWARD = 10.0


def goal_reward_profile(goal: str) -> dict[str, float]:
    """R_g: reward on the phase where the offense type's harm concentrates."""
    peaks = {
        "enticement": EXPLOITATION_PHASE,
        "production": EXPLOITATION_PHASE,
        "sextortion": COERCION_CYCLE,
        "enterprise": MAINTENANCE_PHASE,
        "trafficking": MAINTENANCE_PHASE,
    }
    return {peaks.get(goal, MAINTENANCE_PHASE): PEAK_REWARD}


def observed_value(
    chain: dict[tuple[str, str], float],
    rewards: dict[str, float],
    *,
    gamma: float = DEFAULT_GAMMA,
    tol: float = 1e-10,
    max_iter: int = 10_000,
) -> dict[str, float]:
    """Iterative policy evaluation of V = R + γ P̂ V (converges for γ < 1)."""
    if not 0.0 <= gamma < 1.0:
        raise ValueError("gamma must be in [0, 1): the observed chain is recurrent")
    out: dict[str, list[tuple[str, float]]] = defaultdict(list)
    states = set(rewards)
    for (src, dst), p in chain.items():
        out[src].append((dst, p))
        states.update((src, dst))
    v = {s: rewards.get(s, 0.0) for s in states}
    for _ in range(max_iter):
        new_v = {
            s: rewards.get(s, 0.0) + gamma * sum(p * v[d] for d, p in out.get(s, ()))
            for s in states
        }
        delta = max(abs(new_v[s] - v[s]) for s in states) if states else 0.0
        v = new_v
        if delta < tol:
            break
    return v


def value_for_goal(
    cases: dict[str, dict],
    goal: str,
    modality_of: Callable[[str], str],
    start: str,
    *,
    gamma: float = DEFAULT_GAMMA,
) -> dict:
    """V_g on the chain estimated from the cases of modality g only."""
    ids = sorted(cid for cid in cases if modality_of(cid) == goal)
    steps = [
        s
        for cid in ids
        for s in steps_from_case(cid, cases[cid]["types"], cases[cid]["tags"])
    ]
    chain = phase_chain(step_counts(steps))
    v = observed_value(chain, goal_reward_profile(goal), gamma=gamma)
    return {
        "goal": goal,
        "n_cases": len(ids),
        "case_ids": ids,
        "gamma": gamma,
        "reward_state": next(iter(goal_reward_profile(goal))),
        "v_start": v.get(start, 0.0),
        "v": v,
    }
