"""Compute the state machine estimates over the PACER case graphs.

Writes state_machines/data/lstar_all_cases.json. Every estimate is built from
observed steps (state_machines/estimators.py); see state_machines/README.md
for the notation. Nothing here assumes offenders optimise trajectories.

    python3 -m state_machines.compute_lstar
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
REPO_ROOT = WORKSPACE.parent
sys.path.insert(0, str(REPO_ROOT))

from state_machines.bellman import DEFAULT_GAMMA, value_for_goal  # noqa: E402
from state_machines.estimators import (  # noqa: E402
    NO_TAG,
    backbone,
    coverage,
    is_completed,
    observed_policy,
    path_coverage_intervention,
    phase_chain,
    step_counts,
    steps_from_case,
    transition_estimate,
)
from state_machines.iris import (  # noqa: E402
    EXPLOITATION_PHASE,
    INITIAL_CONTACT_PHASE,
    LSTAR_JSON,
    MAINTENANCE_PHASE,
    display_type,
    get_case_meta,
    infer_modality,
    local_name,
)
from state_machines.sparql_queries import (  # noqa: E402
    affordance_on_arrival,
    case_graphs,
    load_state_machine_graphs,
    ordered_phase_sequence,
    phase_metadata,
    phase_type_for_instance,
)
from state_machines.trajectory import (  # noqa: E402
    cross_case_comparison,
    max_weight_empirical_path,
    path_weight_for_sequence,
)

OUTPUT_PATH = LSTAR_JSON
GOALS = ("enticement", "sextortion", "production", "enterprise", "trafficking")


def _case_id(graph_uri: str) -> str:
    return graph_uri.rsplit(":", 1)[-1]


def _tag_name(tag: str) -> str | None:
    return None if tag == NO_TAG else local_name(tag)


def load_cases() -> dict[str, dict]:
    """Per case: ordered phase types, arrival tags, and phase details."""
    cg = load_state_machine_graphs()
    cases: dict[str, dict] = {}
    for graph in case_graphs(cg):
        cid = _case_id(str(graph))
        types: list[str] = []
        tags: list[str | None] = []
        details: list[dict] = []
        for uri in ordered_phase_sequence(cg, graph):
            ptype = phase_type_for_instance(cg, graph, uri)
            if ptype is None:
                continue
            aff, _desc = affordance_on_arrival(cg, graph, uri)
            types.append(ptype)
            tags.append(aff)
            details.append({**phase_metadata(cg, graph, uri), "affordance_on_arrival": aff})
        for i, d in enumerate(details, start=1):
            d["index"] = i
            d["is_terminal"] = i == len(details)
        cases[cid] = {"types": types, "tags": tags, "details": details}
    return cases


def main() -> None:
    cases = load_cases()
    modality = {cid: infer_modality(cid, get_case_meta(cid)) for cid in cases}
    modality_of = modality.__getitem__
    sequences = {cid: c["types"] for cid, c in cases.items()}

    steps = [s for cid, c in cases.items() for s in steps_from_case(cid, c["types"], c["tags"])]
    n = step_counts(steps)
    chain = phase_chain(n)
    t_hat = transition_estimate(n)
    pi_hat = observed_policy(n)

    step_cases: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for s in steps:
        step_cases[(s.src, s.affordance, s.dst)].add(s.case_id)
    pair_steps: dict[tuple[str, str], int] = defaultdict(int)
    pair_cases: dict[tuple[str, str], set[str]] = defaultdict(set)
    for (src, aff, dst), k in n.items():
        pair_steps[(src, dst)] += k
        pair_cases[(src, dst)] |= step_cases[(src, aff, dst)]
    leave_steps: dict[tuple[str, str], int] = defaultdict(int)
    for (src, aff, _dst), k in n.items():
        leave_steps[(src, aff)] += k

    b = backbone(sequences)
    cov_all = coverage(sequences)
    completed = {cid: seq for cid, seq in sequences.items() if is_completed(seq)}
    cov_completed = coverage(completed)
    phases_seen = sorted(cov_all, key=lambda t: (-len(cov_all[t]), t))

    case_results: dict[str, dict] = {}
    for cid, c in cases.items():
        meta = get_case_meta(cid)
        p_path, step_p = path_weight_for_sequence(c["types"], chain)
        case_results[cid] = {
            "title": meta.get("title", cid.upper()),
            "citation": meta.get("citation", cid),
            "modality": modality[cid],
            "completed": is_completed(c["types"]),
            "phase_sequence": c["types"],
            "phase_details": c["details"],
            "path_probability": p_path,
            "step_probabilities": {f"{a}|{b_}": p for (a, b_), p in step_p.items()},
        }

    def _most_likely(terminal: str) -> dict:
        r = max_weight_empirical_path(chain, INITIAL_CONTACT_PHASE, terminal, len(cases))
        return {
            "trajectory": r["trajectory"],
            "trajectory_display": [display_type(t) for t in r["trajectory"]],
            "probability": r["path_weight"],
            "method": "most probable simple path under P̂ (Viterbi)",
        }

    payload = {
        "method": {
            "unit": "step",
            "estimators": "T̂ = n(s,a,s')/n(s,a,·); π̂ = n(s,a,·)/n(s,·,·); P̂ = n(s,·,s')/n(s,·,·)",
            "value": f"V_g = R_g + γ P̂ V_g, expectation under the observed process, γ = {DEFAULT_GAMMA}, no max",
            "backbone": "phases in every completed (non-sting) trajectory",
            "intervention": "κ_g(b) = share of completed trajectories of goal g that avoid b",
            "readme": "state_machines/README.md",
        },
        "n_cases": len(cases),
        "n_completed": len(completed),
        "n_steps": len(steps),
        "n_tagged_steps": sum(1 for s in steps if s.affordance != NO_TAG),
        "phase_chain": [
            {
                "from": display_type(src),
                "to": display_type(dst),
                "p": p,
                "steps": pair_steps[(src, dst)],
                "cases": len(pair_cases[(src, dst)]),
            }
            for (src, dst), p in sorted(chain.items())
        ],
        "transition_estimate": [
            {
                "from": display_type(src),
                "affordance": local_name(aff),
                "to": display_type(dst),
                "p": p,
                "steps": n[(src, aff, dst)],
                "steps_leaving_via_a": leave_steps[(src, aff)],
                "cases": len(step_cases[(src, aff, dst)]),
            }
            for (src, aff), row in sorted(t_hat.items())
            for dst, p in sorted(row.items())
        ],
        "observed_policy": [
            {"from": display_type(src), "affordance": _tag_name(aff), "p": p}
            for src, row in sorted(pi_hat.items())
            for aff, p in sorted(row.items())
        ],
        # Shapes kept for lifecycle_api and MCP consumers.
        "raw_transitions": [
            {
                "from": display_type(src),
                "to": display_type(dst),
                "case_count": len(pair_cases[(src, dst)]),
                "weight": p,
            }
            for (src, dst), p in sorted(chain.items())
        ],
        "affordance_annotations": [
            {
                "from": display_type(src),
                "to": display_type(dst),
                "affordance": local_name(aff),
                "case_count": len(ids),
            }
            for (src, aff, dst), ids in sorted(step_cases.items())
            if aff != NO_TAG
        ],
        "backbone": {
            "phases": b,
            "phases_display": [display_type(t) for t in b],
            "coverage": [
                {
                    "phase": display_type(t),
                    "all": len(cov_all[t]),
                    "completed": len(cov_completed.get(t, [])),
                    "in_backbone": t in b,
                }
                for t in phases_seen
            ],
            "disrupted_cases": sorted(cid for cid in sequences if cid not in completed),
        },
        "intervention": [
            {
                "phase": display_type(t),
                "in_backbone": t in b,
                "by_goal": path_coverage_intervention(sequences, t, modality_of),
            }
            for t in phases_seen
        ],
        "value_by_goal": {
            g: {
                k: v
                for k, v in value_for_goal(cases, g, modality_of, INITIAL_CONTACT_PHASE).items()
                if k != "v"
            }
            for g in GOALS
        },
        "most_likely_path": {
            "to_exploitation": _most_likely(EXPLOITATION_PHASE),
            "to_maintenance": _most_likely(MAINTENANCE_PHASE),
        },
        "cases": case_results,
        "cross_case_comparison": {
            **(cc := cross_case_comparison(sequences)),
            "fundamental_display": [display_type(t) for t in cc["fundamental"]],
            "variant_display": [(display_type(t), k) for t, k in cc["variant"]],
        },
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"{len(cases)} cases · {len(completed)} completed · {len(steps)} steps · {payload['n_tagged_steps']} tagged")
    print("Backbone (completed trajectories): " + ", ".join(local_name(t) for t in b))
    for row in payload["backbone"]["coverage"]:
        print(f"  {row['phase']:46} {row['all']:>2}/{len(cases)}  completed {row['completed']:>2}/{len(completed)}")
    for g, r in payload["value_by_goal"].items():
        print(f"  V_{g}(s0) = {r['v_start']:.4f}  (n={r['n_cases']}, reward at {local_name(r['reward_state'])})")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
