"""L*_{g,A} computation over PACER CAC-native state machine graphs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
REPO_ROOT = WORKSPACE.parent
sys.path.insert(0, str(REPO_ROOT))

from state_machines.bellman import (  # noqa: E402
    BACKBONE_FOR_INTERVENTION,
    bellman_for_goal,
    bellman_lstar,
    goal_reward_profile,
    intervention_delta,
    matrix_from_sequences,
)
from state_machines.iris import (  # noqa: E402
    get_case_meta,
    EXPLOITATION_PHASE,
    INITIAL_CONTACT_PHASE,
    LSTAR_JSON,
    MAINTENANCE_PHASE,
    display_type,
    infer_modality,
    local_name,
)
from state_machines.sparql_queries import (  # noqa: E402
    affordance_on_arrival,
    case_graphs,
    load_state_machine_graphs,
    ordered_phase_sequence,
    ordered_type_sequence,
    phase_metadata,
    query_affordance_annotations,
    query_phases_per_case,
    query_transition_matrix,
    weighted_transition_matrix,
)
from state_machines.trajectory import (  # noqa: E402
    cross_case_comparison,
    max_weight_empirical_path,
    path_weight_for_sequence,
)

OUTPUT_PATH = LSTAR_JSON

BELLMAN_GOALS = ("enticement", "sextortion", "production", "enterprise", "trafficking")


def _case_id_from_graph(graph_uri: str) -> str:
    return graph_uri.rsplit(":", 1)[-1]


def _format_phase_line(
    index: int,
    meta: dict,
    aff_class: str | None,
    is_terminal: bool,
) -> list[str]:
    lines = []
    type_display = display_type(meta["type"] or "")
    terminal = " [TERMINAL]" if is_terminal else ""
    lines.append(f"  {index}. {type_display}{terminal}")
    if meta["label"]:
        detail = meta["label"]
        if meta["comment"]:
            detail += f" — {meta['comment'].split('.')[0]}"
        lines.append(f'     "{detail}"')
    if aff_class:
        lines.append(f"     Affordance on arrival: {local_name(aff_class)}")
    return lines


def _serialize_bellman(result: dict) -> dict:
    return {
        "goal": result.get("goal"),
        "n_cases": result.get("n_cases"),
        "case_ids": result.get("case_ids", []),
        "trajectory": result["trajectory"],
        "trajectory_display": [display_type(t) for t in result["trajectory"]],
        "v_star_start": result["v_star_start"],
    }


def main() -> None:
    cg = load_state_machine_graphs()
    matrix, n_cases = weighted_transition_matrix(cg)
    raw_transitions = query_transition_matrix(cg)
    affordances = query_affordance_annotations(cg)
    phases_per_case = query_phases_per_case(cg)

    sequences: dict[str, list[str]] = {}
    case_results: dict[str, dict] = {}

    global_lstar = max_weight_empirical_path(
        matrix, INITIAL_CONTACT_PHASE, EXPLOITATION_PHASE, n_cases
    )
    global_lstar_maintenance = max_weight_empirical_path(
        matrix, INITIAL_CONTACT_PHASE, MAINTENANCE_PHASE, n_cases
    )

    for graph in case_graphs(cg):
        case_id = _case_id_from_graph(str(graph))
        phase_uris = ordered_phase_sequence(cg, graph)
        type_seq = ordered_type_sequence(cg, graph)
        sequences[case_id] = type_seq
        path_weight, step_weights = path_weight_for_sequence(type_seq, matrix)

        phase_details = []
        for i, uri in enumerate(phase_uris, start=1):
            meta = phase_metadata(cg, graph, uri)
            aff, _ = affordance_on_arrival(cg, graph, uri)
            phase_details.append(
                {
                    **meta,
                    "affordance_on_arrival": aff,
                    "index": i,
                    "is_terminal": i == len(phase_uris),
                }
            )

        case_lstar = max_weight_empirical_path(
            matrix, INITIAL_CONTACT_PHASE, EXPLOITATION_PHASE, n_cases
        )
        case_lstar["case_sequence"] = type_seq
        case_lstar["case_path_weight"] = path_weight
        case_lstar["case_step_weights"] = {
            f"{a}|{b}": w for (a, b), w in step_weights.items()
        }
        case_lstar["weights"] = {
            f"{a}|{b}": w for (a, b), w in case_lstar["weights"].items()
        }

        meta = get_case_meta(case_id)
        modality = infer_modality(case_id, meta)
        case_matrix = matrix_from_sequences({case_id: type_seq})
        case_bellman = bellman_lstar(
            case_matrix,
            INITIAL_CONTACT_PHASE,
            goal_reward_profile(modality),
            row_normalize_matrix=False,
        )

        case_results[case_id] = {
            "title": meta.get("title", case_id.upper()),
            "citation": meta.get("citation", case_id),
            "modality": modality,
            "phase_sequence": type_seq,
            "phase_details": phase_details,
            "empirical_lstar": case_lstar,
            "bellman_lstar": _serialize_bellman(
                {**case_bellman, "goal": modality, "n_cases": 1, "case_ids": [case_id]}
            ),
            "path_weight": path_weight,
        }

        print("═" * 55)
        print(f"{meta.get('title', case_id)} — {meta.get('citation', case_id)}")
        print("═" * 55)
        print("Phases (CAC-native):")
        for i, uri in enumerate(phase_uris, start=1):
            meta_p = phase_metadata(cg, graph, uri)
            aff, _ = affordance_on_arrival(cg, graph, uri)
            for line in _format_phase_line(
                i, meta_p, aff, is_terminal=(i == len(phase_uris))
            ):
                print(line)

        traj = " → ".join(display_type(t) for t in type_seq)
        all_one = path_weight == 1.0 or abs(path_weight - 1.0) < 1e-9
        weight_note = (
            f"All weights 1.0 (N={n_cases} — degenerate but correct)"
            if all_one
            else f"weighted by cross-case frequencies (N={n_cases})"
        )
        print(f"\nL*_{{g,A}} (N={n_cases}): {traj}")
        print(f"Path weight: {path_weight:.4f} | {weight_note}")
        print("─" * 55)
        print()

    comparison = cross_case_comparison(sequences)

    bellman_by_goal = {
        goal: _serialize_bellman(bellman_for_goal(sequences, goal, infer_modality))
        for goal in BELLMAN_GOALS
    }

    anchor_sequences = {
        cid: seq for cid, seq in sequences.items() if cid in BELLMAN_GOALS
    }
    anchor_matrix = matrix_from_sequences(anchor_sequences)
    intervention_at_backbone: list[dict] = []
    for phase in BACKBONE_FOR_INTERVENTION:
        row: dict = {"phase": display_type(phase), "by_goal": {}}
        for goal in BELLMAN_GOALS:
            delta = intervention_delta(
                anchor_matrix,
                INITIAL_CONTACT_PHASE,
                goal_reward_profile(goal),
                phase,
            )
            row["by_goal"][goal] = {
                "delta": delta["delta"],
                "v_star_before": delta["v_star_before"],
                "v_star_after": delta["v_star_after"],
            }
        intervention_at_backbone.append(row)

    print("═" * 55)
    print(f"CROSS-CASE COMPARISON (all {n_cases} offense types)")
    print("═" * 55)
    print("Fundamental (appears in all 5):")
    print(
        "  "
        + ", ".join(display_type(t) for t in comparison["fundamental"])
        or "  (none)"
    )
    print("\nVariant stages:")
    for t, count in comparison["variant"]:
        cases = comparison["type_cases"][t]
        print(f"  {local_name(t):24} {count}/{n_cases}  ({', '.join(cases)})")
    if comparison["unique"]:
        print("\nUnique (one case only):")
        for t in comparison["unique"]:
            cases = comparison["type_cases"][t]
            print(f"  {local_name(t):24} ({cases[0]})")

    print("═" * 55)
    print("BELLMAN L*_{g,A} (goal-conditioned, modality-filtered)")
    print("═" * 55)
    for goal, result in bellman_by_goal.items():
        traj = " → ".join(result["trajectory_display"])
        print(f"  {goal:12} (n={result['n_cases']}): {traj}")
        print(f"               V*(s0)={result['v_star_start']:.4f}")

    payload = {
        "n_cases": n_cases,
        "transition_matrix": {
            f"{display_type(a)} → {display_type(b)}": w
            for (a, b), w in sorted(matrix.items())
        },
        "raw_transitions": [
            {
                "from": display_type(str(r["from_type"])),
                "to": display_type(str(r["to_type"])),
                "case_count": int(r["case_count"]),
                "weight": matrix.get(
                    (str(r["from_type"]), str(r["to_type"])), 0.0
                ),
            }
            for r in raw_transitions
        ],
        "affordance_annotations": [
            {
                "from": display_type(str(r["from_type"])),
                "to": display_type(str(r["to_type"])),
                "affordance": local_name(str(r["affordance_class"])),
                "case_count": int(r["case_count"]),
            }
            for r in affordances
        ],
        "phases_sparql": [
            {
                "case": _case_id_from_graph(str(r["case_graph"])),
                "phase": str(r["phase"]),
                "type": display_type(str(r["phase_type"])),
            }
            for r in phases_per_case
        ],
        "global_lstar": {
            **{
                **global_lstar,
                "weights": {
                    f"{a}|{b}": w
                    for (a, b), w in global_lstar["weights"].items()
                },
            },
            "trajectory_display": [display_type(t) for t in global_lstar["trajectory"]],
            "method": "max_weight_empirical_path",
        },
        "global_lstar_maintenance": {
            **{
                k: v
                for k, v in global_lstar_maintenance.items()
                if k != "weights"
            },
            "weights": {
                f"{a}|{b}": w
                for (a, b), w in global_lstar_maintenance["weights"].items()
            },
            "trajectory_display": [
                display_type(t) for t in global_lstar_maintenance["trajectory"]
            ],
            "method": "max_weight_empirical_path",
        },
        "bellman_by_goal": bellman_by_goal,
        "intervention_at_backbone": intervention_at_backbone,
        "cases": case_results,
        "cross_case_comparison": {
            **comparison,
            "fundamental_display": [display_type(t) for t in comparison["fundamental"]],
            "variant_display": [
                (display_type(t), count) for t, count in comparison["variant"]
            ],
        },
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
