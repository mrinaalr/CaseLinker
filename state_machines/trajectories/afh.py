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


def release_analysis(root=None, threshold: str = "INFERRED", case_id: str = "") -> dict:
    """AfH quantities over a PACER release: Aff(c), H(c), psi_C and the coverage identity.

    ``root`` is a release folder (default: the release the /lifecycle page shows). H(c) counts
    minor-directed harms (H0). psi_C records co-occurrence within a case, not causation."""
    import json
    from state_machines.trajectories.derive import derive
    from state_machines.trajectories.payload import release_dir

    root = root or release_dir()
    if root is None:
        return {"release": None, "cases": []}
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    rows, per_case = [], []
    for c in manifest["cases"]:
        if case_id and c["case_id"] != case_id:
            continue
        bundle = json.loads((root / "cases" / f"{c['case_id']}.json").read_text(encoding="utf-8"))
        d = derive(bundle, threshold)
        affs, harms = case_affordances(d), case_harms(bundle, threshold)
        rows.append((c["case_id"], affs, harms))
        per_case.append({
            "case_id": c["case_id"], "aff": sorted(affs), "h0": sorted(harms),
            "tracks": [{"track": t["track_id"], "kind": t["kind"], "chains": len(t["trajectories"]),
                        "unordered_pairs": len(t["unordered_pairs"]), "possible_same_act": t["possible_same_act"],
                        "aff_by_chain": [sorted(aff(L)) for L in t["trajectories"]]} for t in d["tracks"]],
        })
    return {"release": manifest["release_id"], "adjudicated": manifest["adjudicated"], "threshold": threshold,
            "cases": per_case,
            "psi": {o: [{"harm": h, "cases": ids} for h, ids in pairs] for o, pairs in psi(rows).items()},
            "coverage_identity_holds": coverage_identity_holds(rows),
            "note": "Aff and psi use level-C (instrumental) affordances only; psi is co-occurrence, not causation."}
