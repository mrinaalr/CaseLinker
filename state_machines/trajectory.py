"""Descriptive path summaries over the observed phase chain P̂."""

from __future__ import annotations

from collections import defaultdict


def max_weight_empirical_path(
    transition_matrix: dict[tuple[str, str], float],
    start_type: str,
    terminal_type: str,
    n_cases: int = 1,
) -> dict:
    """
    Most probable simple path from start to terminal under the observed chain
    P̂ (max-product / Viterbi). Descriptive: the commonest recorded route, not
    a route anyone optimised. Cycles are not unrolled.
    """
    nodes: set[str] = {start_type, terminal_type}
    for f, t in transition_matrix:
        nodes.add(f)
        nodes.add(t)

    adjacency: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for (f, t), w in transition_matrix.items():
        if w > 0:
            adjacency[f].append((t, w))

    best: dict[str, tuple[float, list[str]]] = {start_type: (1.0, [start_type])}
    frontier = [start_type]

    for _ in range(len(nodes) + 2):
        nxt: list[str] = []
        for node in frontier:
            base_weight, path = best[node]
            for neighbor, w in adjacency.get(node, []):
                candidate = base_weight * w
                prev = best.get(neighbor)
                if prev is None or candidate > prev[0]:
                    best[neighbor] = (candidate, path + [neighbor])
                    nxt.append(neighbor)
        if not nxt:
            break
        frontier = nxt

    if terminal_type in best:
        path_weight, trajectory = best[terminal_type]
    else:
        trajectory = [start_type]
        path_weight = 1.0

    step_weights: dict[tuple[str, str], float] = {}
    for i in range(len(trajectory) - 1):
        edge = (trajectory[i], trajectory[i + 1])
        step_weights[edge] = transition_matrix.get(edge, 0.0)

    fundamental = [
        trajectory[i]
        for i in range(len(trajectory) - 1)
        if transition_matrix.get((trajectory[i], trajectory[i + 1]), 0.0) == 1.0
    ]
    if trajectory and (
        not trajectory[:-1]
        or transition_matrix.get((trajectory[-2], trajectory[-1]), 0.0) == 1.0
    ):
        if trajectory[-1] not in fundamental:
            fundamental.append(trajectory[-1])

    variant = [
        (trajectory[i], transition_matrix.get((trajectory[i], trajectory[i + 1]), 0.0))
        for i in range(len(trajectory) - 1)
        if transition_matrix.get((trajectory[i], trajectory[i + 1]), 0.0) < 1.0
    ]

    return {
        "trajectory": trajectory,
        "weights": step_weights,
        "path_weight": path_weight,
        "N": n_cases,
        "fundamental": fundamental,
        "variant": variant,
    }


def path_weight_for_sequence(
    type_sequence: list[str],
    transition_matrix: dict[tuple[str, str], float],
) -> tuple[float, dict[tuple[str, str], float]]:
    """Probability of a case's type sequence under P̂ (product of step probabilities)."""
    weights: dict[tuple[str, str], float] = {}
    product = 1.0
    for i in range(len(type_sequence) - 1):
        edge = (type_sequence[i], type_sequence[i + 1])
        w = transition_matrix.get(edge, 0.0)
        weights[edge] = w
        product *= w if w > 0 else 0.0
    if not weights:
        product = 1.0
    return product, weights


def cross_case_comparison(
    sequences: dict[str, list[str]],
) -> dict:
    """Coverage over all given trajectories: fundamental (all), variant (some), unique (one).

    For the backbone over completed trajectories use estimators.backbone.
    """
    type_cases: dict[str, set[str]] = defaultdict(set)
    for case_id, seq in sequences.items():
        for t in set(seq):
            type_cases[t].add(case_id)

    n_cases = len(sequences)
    fundamental = sorted(t for t, cases in type_cases.items() if len(cases) == n_cases)
    variant = sorted(
        (t, len(type_cases[t]))
        for t in type_cases
        if 1 < len(type_cases[t]) < n_cases
    )
    unique = sorted(t for t, cases in type_cases.items() if len(cases) == 1)

    return {
        "fundamental": fundamental,
        "variant": variant,
        "unique": unique,
        "type_cases": {k: sorted(v) for k, v in type_cases.items()},
        "n_cases": n_cases,
    }
