"""Step-count estimators for the exploitation state machine.

Notation follows state_machines/README.md:

    n(s_i, a, s_j)      observed steps s_i --a--> s_j, summed over case graphs
    T̂(s_j | s_i, a)     = n(s_i, a, s_j) / n(s_i, a, ·)
    π̂(a | s_i)          = n(s_i, a, ·)  / n(s_i, ·, ·)
    P̂(s_j | s_i)        = n(s_i, ·, s_j) / n(s_i, ·, ·)

The unit of count is the step, not the case: phase types repeat inside a
case (the Exploitation <-> Maintenance loop), and only step counts make each
row of T̂, π̂ and P̂ sum to 1. Affordance tags record the capability used on a
step; nothing here conditions on what was available.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Callable, Iterable

from state_machines.iris import STING_OPERATION

NO_TAG = "∅"


@dataclass(frozen=True)
class Step:
    case_id: str
    src: str
    affordance: str  # affordance class IRI, or NO_TAG
    dst: str


def steps_from_case(case_id: str, types: list[str], arrival_tags: list[str | None]) -> list[Step]:
    """Steps of one case. arrival_tags[i] is the affordance on the step into types[i]."""
    out: list[Step] = []
    for i in range(len(types) - 1):
        tag = arrival_tags[i + 1] if i + 1 < len(arrival_tags) else None
        out.append(Step(case_id, types[i], tag or NO_TAG, types[i + 1]))
    return out


def step_counts(steps: Iterable[Step]) -> Counter:
    """n(s_i, a, s_j)."""
    return Counter((s.src, s.affordance, s.dst) for s in steps)


def transition_estimate(n: Counter) -> dict[tuple[str, str], dict[str, float]]:
    """T̂(· | s_i, a) for every observed (s_i, a), untagged steps excluded."""
    row: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for (src, aff, dst), k in n.items():
        if aff != NO_TAG:
            row[(src, aff)][dst] += k
    return {key: _normalise(c) for key, c in row.items()}


def observed_policy(n: Counter) -> dict[str, dict[str, float]]:
    """π̂(a | s_i), including NO_TAG for untagged steps."""
    row: dict[str, Counter] = defaultdict(Counter)
    for (src, aff, _dst), k in n.items():
        row[src][aff] += k
    return {src: _normalise(c) for src, c in row.items()}


def phase_chain(n: Counter) -> dict[tuple[str, str], float]:
    """P̂(s_j | s_i): row-normalised step counts, affordance marginalised."""
    row: dict[str, Counter] = defaultdict(Counter)
    for (src, _aff, dst), k in n.items():
        row[src][dst] += k
    out: dict[tuple[str, str], float] = {}
    for src, c in row.items():
        for dst, p in _normalise(c).items():
            out[(src, dst)] = p
    return out


def _normalise(c: Counter) -> dict[str, float]:
    total = sum(c.values())
    return {k: v / total for k, v in c.items()} if total else {}


# ---------- Trajectories, backbone, intervention ----------

def is_completed(types: list[str]) -> bool:
    """Completed = not disrupted by a sting before the chain finished."""
    return STING_OPERATION not in types


def coverage(sequences: dict[str, list[str]]) -> dict[str, list[str]]:
    """Phase type -> sorted case ids whose trajectory contains it."""
    cases: dict[str, set[str]] = defaultdict(set)
    for cid, seq in sequences.items():
        for t in set(seq):
            cases[t].add(cid)
    return {t: sorted(c) for t, c in cases.items()}


def backbone(sequences: dict[str, list[str]]) -> list[str]:
    """B = phases in every completed trajectory."""
    completed = [set(seq) for seq in sequences.values() if is_completed(seq)]
    if not completed:
        return []
    return sorted(set.intersection(*completed))


def path_coverage_intervention(
    sequences: dict[str, list[str]],
    blocked: str,
    modality_of: Callable[[str], str],
) -> dict[str, dict[str, float | int]]:
    """κ_g(b): share of completed trajectories of goal g that avoid `blocked`."""
    by_goal: dict[str, list[list[str]]] = defaultdict(list)
    for cid, seq in sequences.items():
        if is_completed(seq):
            by_goal[modality_of(cid)].append(seq)
    out: dict[str, dict[str, float | int]] = {}
    for goal, seqs in sorted(by_goal.items()):
        avoid = sum(1 for s in seqs if blocked not in s)
        out[goal] = {"kappa": avoid / len(seqs), "avoiding": avoid, "completed": len(seqs)}
    return out
