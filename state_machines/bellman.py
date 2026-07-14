"""Goal-conditioned Bellman L*_{g,A} over CAC phase transition graphs."""

from __future__ import annotations

from collections import defaultdict
from typing import Callable

from state_machines.iris import (
    COERCION_CYCLE,
    CONDITIONING_PHASE,
    EXPLOITATION_PHASE,
    INITIAL_CONTACT_PHASE,
    MAINTENANCE_PHASE,
    TRUST_BUILDING_PHASE,
)

GoalRewardFn = Callable[[str], dict[str, float]]


def matrix_from_sequences(
    sequences: dict[str, list[str]],
) -> dict[tuple[str, str], float]:
    """Edge weight = fraction of sequences that contain that consecutive type pair."""
    if not sequences:
        return {}
    n = len(sequences)
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for seq in sequences.values():
        for i in range(len(seq) - 1):
            counts[(seq[i], seq[i + 1])] += 1
    return {edge: count / n for edge, count in counts.items()}


def row_normalize(
    matrix: dict[tuple[str, str], float],
) -> dict[tuple[str, str], float]:
    """Convert corpus edge frequencies to conditional P(s' | s)."""
    out_sum: dict[str, float] = defaultdict(float)
    for (frm, _to), w in matrix.items():
        out_sum[frm] += w
    return {
        (frm, to): w / out_sum[frm]
        for (frm, to), w in matrix.items()
        if out_sum[frm] > 0
    }


def _outgoing(
    matrix: dict[tuple[str, str], float],
) -> dict[str, list[tuple[str, float]]]:
    adj: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for (frm, to), w in matrix.items():
        if w > 0:
            adj[frm].append((to, w))
    return adj


def _states_in_matrix(matrix: dict[tuple[str, str], float]) -> set[str]:
    nodes: set[str] = set()
    for frm, to in matrix:
        nodes.add(frm)
        nodes.add(to)
    return nodes


def goal_reward_profile(goal: str) -> dict[str, float]:
    """
    Peak-state rewards R_g(s) from paper Appendix X (goal-dependent divergence).
    """
    peaks: dict[str, dict[str, float]] = {
        "enticement": {EXPLOITATION_PHASE: 10.0},
        "sextortion": {COERCION_CYCLE: 10.0},
        "enterprise": {MAINTENANCE_PHASE: 10.0},
        "production": {EXPLOITATION_PHASE: 10.0},
        "trafficking": {MAINTENANCE_PHASE: 10.0},
    }
    return dict(peaks.get(goal, {MAINTENANCE_PHASE: 10.0}))


def bellman_value_iteration(
    matrix: dict[tuple[str, str], float],
    rewards: dict[str, float],
    *,
    gamma: float = 1.0,
    max_iter: int = 64,
    row_normalize_matrix: bool = True,
) -> tuple[dict[str, float], dict[str, str | None]]:
    """
    V*(s) = R(s) + gamma * max_{s'} P(s'|s) V*(s') on a finite phase graph.
    """
    transitions = row_normalize(matrix) if row_normalize_matrix else matrix
    adj = _outgoing(transitions)
    nodes = _states_in_matrix(transitions)
    for state in rewards:
        nodes.add(state)

    v: dict[str, float] = {s: rewards.get(s, 0.0) for s in nodes}
    for _ in range(max_iter):
        changed = False
        new_v: dict[str, float] = {}
        for state in nodes:
            edges = adj.get(state, [])
            if not edges:
                new_v[state] = rewards.get(state, 0.0)
                continue
            best = rewards.get(state, 0.0)
            for nxt, prob in edges:
                candidate = rewards.get(state, 0.0) + gamma * prob * v.get(
                    nxt, rewards.get(nxt, 0.0)
                )
                if candidate > best:
                    best = candidate
            new_v[state] = best
            if abs(new_v[state] - v.get(state, 0.0)) > 1e-9:
                changed = True
        v = new_v
        if not changed:
            break

    policy: dict[str, str | None] = {}
    for state in nodes:
        edges = adj.get(state, [])
        if not edges:
            policy[state] = None
            continue
        best_next: str | None = None
        best_val = float("-inf")
        for nxt, prob in edges:
            val = rewards.get(state, 0.0) + gamma * prob * v.get(
                nxt, rewards.get(nxt, 0.0)
            )
            if val > best_val:
                best_val = val
                best_next = nxt
        policy[state] = best_next

    return v, policy


def rollout_policy(
    policy: dict[str, str | None],
    start: str,
    *,
    max_steps: int = 24,
) -> list[str]:
    path = [start]
    seen = {start}
    cur = start
    for _ in range(max_steps):
        nxt = policy.get(cur)
        if not nxt or nxt in seen:
            break
        path.append(nxt)
        seen.add(nxt)
        cur = nxt
    return path


def bellman_lstar(
    matrix: dict[tuple[str, str], float],
    start: str,
    rewards: dict[str, float],
    *,
    gamma: float = 1.0,
    max_iter: int = 64,
    max_steps: int = 24,
    row_normalize_matrix: bool = True,
) -> dict:
    """Bellman-optimal trajectory and value from start."""
    v_star, policy = bellman_value_iteration(
        matrix,
        rewards,
        gamma=gamma,
        max_iter=max_iter,
        row_normalize_matrix=row_normalize_matrix,
    )
    trajectory = rollout_policy(policy, start, max_steps=max_steps)
    return {
        "trajectory": trajectory,
        "v_star_start": v_star.get(start, 0.0),
        "v_star": v_star,
        "policy": policy,
        "rewards": rewards,
    }


def matrix_without_state(
    matrix: dict[tuple[str, str], float],
    blocked: str,
) -> dict[tuple[str, str], float]:
    """Remove a phase type from the reachable graph (intervention corollary)."""
    return {
        (frm, to): w
        for (frm, to), w in matrix.items()
        if frm != blocked and to != blocked
    }


def intervention_delta(
    matrix: dict[tuple[str, str], float],
    start: str,
    rewards: dict[str, float],
    blocked: str,
    **kwargs,
) -> dict:
    """Measure V*(start) before and after removing blocked state."""
    baseline = bellman_lstar(matrix, start, rewards, **kwargs)
    perturbed = bellman_lstar(
        matrix_without_state(matrix, blocked),
        start,
        rewards,
        **kwargs,
    )
    before = baseline["v_star_start"]
    after = perturbed["v_star_start"]
    return {
        "blocked": blocked,
        "v_star_before": before,
        "v_star_after": after,
        "delta": before - after,
        "baseline_trajectory": baseline["trajectory"],
        "perturbed_trajectory": perturbed["trajectory"],
    }


def bellman_for_goal(
    sequences: dict[str, list[str]],
    goal: str,
    modality_of: Callable[[str], str],
    *,
    start: str = INITIAL_CONTACT_PHASE,
    **kwargs,
) -> dict:
    """Pooled Bellman L* using only cases whose modality matches goal."""
    filtered = {
        cid: seq for cid, seq in sequences.items() if modality_of(cid) == goal
    }
    matrix = matrix_from_sequences(filtered)
    rewards = goal_reward_profile(goal)
    result = bellman_lstar(
        matrix,
        start,
        rewards,
        **kwargs,
    )
    result["goal"] = goal
    result["n_cases"] = len(filtered)
    result["case_ids"] = sorted(filtered)
    return result


BACKBONE_FOR_INTERVENTION = (
    INITIAL_CONTACT_PHASE,
    CONDITIONING_PHASE,
    EXPLOITATION_PHASE,
    MAINTENANCE_PHASE,
)
