"""AfH Section 7 quantities over derived trajectories.

Aff(L)  = union of O_i over the steps of L                         (eq. trajectory-affordances)
psi_C(o) = {h : some case in C has o in Aff(c) and h in H(c)}      (eq. affordance-harm)

psi_C records co-occurrence within a case, not causation. Nothing here estimates
Delta_path or Delta_supp from observed cases, and no counts here are prevalence.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Set, Tuple

from state_machines.evidence import vocab as V


def aff(trajectory: dict) -> Set[str]:
    return {o for step in trajectory["steps"] for o in step["affordances"]}


def case_affordances(derived: dict) -> Set[str]:
    return {o for t in derived["tracks"] for L in t["trajectories"] for o in aff(L)}


def case_harms(bundle: dict, threshold: str = "DIRECT", victim_kinds: Tuple[str, ...] = ("minor",)) -> Set[str]:
    """H(c) in H0 terms: harm annotations with an admissible status and an H0 category.

    H0 is a set of child-directed harms, so by default only harms recorded against a minor
    count (R04). Adult-directed harms stay in the data under their own victim kind and can
    be read by passing ``victim_kinds``."""
    ok = V.ADMISSIBLE[threshold]
    return {V.HARM_H0[h["harm"]] for e in bundle["events"] for h in e.get("harms", [])
            if h["status"] in ok and V.HARM_H0[h["harm"]] and h["victim_kind"] in victim_kinds}


def psi(cases: Iterable[Tuple[str, Set[str], Set[str]]]) -> Dict[str, List[Tuple[str, List[str]]]]:
    """cases: (case_id, Aff(c), H(c)). Returns o -> [(h, supporting case_ids)], sorted."""
    out: Dict[str, Dict[str, Set[str]]] = {o: {} for o in V.AFFORDANCES}
    for case_id, affs, harms in cases:
        for o in affs:
            for h in harms:
                out[o].setdefault(h, set()).add(case_id)
    return {o: sorted((h, sorted(ids)) for h, ids in hs.items()) for o, hs in out.items()}


def coverage_identity_holds(cases: List[Tuple[str, Set[str], Set[str]]]) -> bool:
    """Manuscript eq. harm-coverage-invariant: union of psi = harms of cases with Aff != empty."""
    left = {h for pairs in psi(cases).values() for h, _ in pairs}
    middle = {h for _, affs, harms in cases if affs for h in harms}
    observed = {h for _, _, harms in cases for h in harms}
    return left == middle and middle <= observed
