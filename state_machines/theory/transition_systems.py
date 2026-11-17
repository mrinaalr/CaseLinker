"""Affordance-aware state-space construction (AfH, Appendix X). THEORETICAL.

    M_P = (S, A, O(P), T_P, s0),   T_P ⊆ S × A × 2^O(P) × S

A tuple (s, a, O, s') means action a, supported by affordances O, permits a transition from
s to s'. No probabilities are assigned. A finite run starts at s0 and follows T_P; ε(run)
erases the states and keeps the ordered (action, affordance-set) pairs, so the feasible
trajectories are L(P) = {ε(r) : r a finite run of M_P from s0}, prefixes included.

Comparing P with P ⊕ o (an isolated additive introduction of affordance o):
    monotonicity  T_P ⊆ T_{P⊕o}
    locality      every transition in T_{P⊕o} \\ T_P has o in its annotation
    Δ_path(o; P) = π(L(P⊕o)) \\ π(L(P))                     newly feasible action sequences
    Δ_supp(o; P) = {L ∈ L(P⊕o) : π(L) ∈ π(L(P)), o ∈ Aff(L)} new support for old sequences
Proposition (attribution): under monotonicity and locality, every trajectory realising a
sequence in Δ_path(o; P) contains o in Aff(L).

Models are specified by hand with declared assumptions. A documented trajectory can be
tested against a model (is its action sequence a run prefix?); it is not used to fit one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

Step = Tuple[str, FrozenSet[str]]            # (action, affordance set)
Trajectory = Tuple[Step, ...]
Transition = Tuple[str, str, FrozenSet[str], str]   # (s, a, O, s')

VALIDATION_STATUS = "theoretical"


@dataclass(frozen=True)
class TransitionSystem:
    """M_P = (S, A, O(P), T_P, s0) with its declared assumptions."""
    states: FrozenSet[str]
    actions: FrozenSet[str]
    affordances: FrozenSet[str]
    transitions: FrozenSet[Transition]
    s0: str
    assumptions: Tuple[str, ...] = ()
    validation_status: str = VALIDATION_STATUS

    def __post_init__(self):
        if self.s0 not in self.states:
            raise ValueError("s0 must be a state")
        for s, a, o, t in self.transitions:
            if s not in self.states or t not in self.states:
                raise ValueError(f"transition ({s}, {a}, {sorted(o)}, {t}) uses an unknown state")
            if a not in self.actions:
                raise ValueError(f"unknown action {a}")
            if not o <= self.affordances:
                raise ValueError(f"affordances {sorted(o - self.affordances)} are not in O(P)")

    @classmethod
    def build(cls, s0: str, transitions: Iterable[Tuple[str, str, Iterable[str], str]],
              assumptions: Iterable[str] = (), extra_affordances: Iterable[str] = ()) -> "TransitionSystem":
        T = frozenset((s, a, frozenset(o), t) for s, a, o, t in transitions)
        states = frozenset({s0} | {s for s, _, _, _ in T} | {t for _, _, _, t in T})
        return cls(states, frozenset(a for _, a, _, _ in T),
                   frozenset(x for _, _, o, _ in T for x in o) | frozenset(extra_affordances),
                   T, s0, tuple(assumptions))

    def runs(self, max_len: int) -> List[Tuple[Transition, ...]]:
        """Every finite run from s0 of length 0..max_len (bounded: runs may loop)."""
        out: List[Tuple[Transition, ...]] = [()]
        frontier: List[Tuple[str, Tuple[Transition, ...]]] = [(self.s0, ())]
        for _ in range(max_len):
            nxt = []
            for state, run in frontier:
                for tr in sorted(self.transitions, key=lambda x: (x[0], x[1], sorted(x[2]), x[3])):
                    if tr[0] == state:
                        r = run + (tr,)
                        out.append(r)
                        nxt.append((tr[3], r))
            frontier = nxt
        return out

    def trajectories(self, max_len: int) -> Set[Trajectory]:
        """L(P): ε of every finite run, prefixes included."""
        return {epsilon(r) for r in self.runs(max_len)}

    def add(self, o: str, new_transitions: Iterable[Tuple[str, str, Iterable[str], str]],
            check: bool = True) -> "TransitionSystem":
        """P ⊕ o. With ``check``, refuse additions that break monotonicity or locality."""
        new = frozenset((s, a, frozenset(x), t) for s, a, x, t in new_transitions)
        if check:
            bad = [tr for tr in new if o not in tr[2]]
            if bad:
                raise ValueError(f"locality violated: {len(bad)} new transition(s) do not use {o}")
        T = self.transitions | new
        return TransitionSystem(frozenset(self.states | {s for s, *_ in new} | {t for *_, t in new}),
                                frozenset(self.actions | {a for _, a, _, _ in new}),
                                frozenset(self.affordances | {o}), T, self.s0,
                                self.assumptions + (f"isolated additive introduction of {o}",))


def epsilon(run: Iterable[Transition]) -> Trajectory:
    """ε: erase the states, keep the ordered (action, affordances) pairs."""
    return tuple((a, o) for _, a, o, _ in run)


def pi(trajectory: Trajectory) -> Tuple[str, ...]:
    """π(L): the action sequence."""
    return tuple(a for a, _ in trajectory)


def aff(trajectory: Trajectory) -> FrozenSet[str]:
    """Aff(L) = ∪ O_i."""
    return frozenset(x for _, o in trajectory for x in o)


def monotone_and_local(before: TransitionSystem, after: TransitionSystem, o: str) -> Dict[str, bool]:
    new = after.transitions - before.transitions
    return {"monotonicity": before.transitions <= after.transitions,
            "locality": all(o in tr[2] for tr in new)}


def delta_path(o: str, before: TransitionSystem, after: TransitionSystem, max_len: int) -> Set[Tuple[str, ...]]:
    """Δ_path(o; P): action sequences feasible after the introduction and not before."""
    return {pi(L) for L in after.trajectories(max_len)} - {pi(L) for L in before.trajectories(max_len)}


def delta_supp(o: str, before: TransitionSystem, after: TransitionSystem, max_len: int) -> Set[Trajectory]:
    """Δ_supp(o; P): trajectories of P⊕o whose action sequence was already feasible and that use o."""
    old = {pi(L) for L in before.trajectories(max_len)}
    return {L for L in after.trajectories(max_len) if pi(L) in old and o in aff(L)}


def attribution_holds(o: str, before: TransitionSystem, after: TransitionSystem, max_len: int) -> bool:
    """The Appendix X proposition, checked by enumeration up to ``max_len``."""
    seqs = delta_path(o, before, after, max_len)
    return all(o in aff(L) for L in after.trajectories(max_len) if pi(L) in seqs)


def admits_prefix(system: TransitionSystem, actions: Iterable[str], action_map: Optional[Dict[str, str]] = None) -> bool:
    """Is a documented action sequence (mapped onto the model's actions) the action sequence of
    some run prefix? A test of a model against evidence, never an estimate from it."""
    seq = tuple((action_map or {}).get(a, a) for a in actions)
    states = {system.s0}
    for a in seq:
        states = {t for s, act, _, t in system.transitions if s in states and act == a}
        if not states:
            return False
    return True


def admits_partial_order(system: TransitionSystem, actions: Dict[str, str], order: Iterable[Tuple[str, str]],
                         action_map: Optional[Dict[str, str]] = None) -> Optional[Tuple[str, ...]]:
    """Does some ordering of documented events that respects their documented order run in the model?

    ``actions`` maps event ids to action codes, ``order`` holds (earlier, later) pairs of the
    documented partial order. Returns one admitted ordering of event ids, or None when no
    source-consistent ordering is admitted. Unordered events are not forced into one arbitrary
    sequence: every linear extension is searched, pruned by the model's reachable states."""
    amap = action_map or {}
    preds = {e: set() for e in actions}
    for a, b in order:
        if a in preds and b in preds:
            preds[b].add(a)
    seen = set()

    def search(done: Tuple[str, ...], states: FrozenSet[str]):
        if len(done) == len(actions):
            return done
        key = (frozenset(done), states)
        if key in seen:
            return None
        seen.add(key)
        for e in sorted(actions):
            if e in done or not preds[e] <= set(done):
                continue
            act = amap.get(actions[e], actions[e])
            nxt = frozenset(t for s, x, _, t in system.transitions if s in states and x == act)
            if nxt:
                found = search(done + (e,), nxt)
                if found:
                    return found
        return None

    return search((), frozenset({system.s0}))


def appendix_x_example() -> Dict[str, TransitionSystem]:
    """The worked comparison of AfH Appendix X, verbatim in structure.

    s0  an image of an identifiable person is accessible, no channel yet (representation access)
    s1  a channel exists        s2  material has been obtained        s3  refused or blocked
    """
    base = TransitionSystem.build("s0", [
        ("s0", "contact", {"contact_discovery"}, "s1"),
        ("s1", "request", {"unmonitored_communication"}, "s2"),
        ("s1", "request", {"unmonitored_communication"}, "s3"),
    ], assumptions=("stylized toy system from AfH Appendix X; not estimated from any record",))
    with_e = base.add("ephemerality", [("s1", "request", {"unmonitored_communication", "ephemerality"}, "s2")])
    with_g = base.add("generative_synthesis", [("s0", "synthesize", {"generative_synthesis"}, "s2")])
    return {"P": base, "P+ephemerality": with_e, "P+generative_synthesis": with_g}


__all__ = ["TransitionSystem", "epsilon", "pi", "aff", "monotone_and_local", "delta_path", "delta_supp",
           "attribution_holds", "admits_prefix", "admits_partial_order", "appendix_x_example", "VALIDATION_STATUS"]
