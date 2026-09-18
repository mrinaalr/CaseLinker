"""Build /api/lifecycle/cases payload from L* computation output."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

from state_machines.iris import (
    ANCHOR_CASE_IDS,
    CASE_META,
    EXPANSION_CASE_IDS,
    LSTAR_JSON,
    REPO_ROOT,
    STATE_MACHINES_WORKSPACE,
    display_type,
    infer_modality,
    local_name,
    modality_label,
)
from state_machines.trajectory import cross_case_comparison


def _ensure_lstar_json() -> dict[str, Any]:
    if LSTAR_JSON.is_file():
        return json.loads(LSTAR_JSON.read_text(encoding="utf-8"))
    script = STATE_MACHINES_WORKSPACE / "compute_lstar.py"
    subprocess.run([sys.executable, str(script)], check=True, cwd=REPO_ROOT)
    return json.loads(LSTAR_JSON.read_text(encoding="utf-8"))


def load_lstar_raw() -> dict[str, Any]:
    """Return full state_machines/data/lstar_all_cases.json (compute if missing)."""
    return _ensure_lstar_json()


def _transitions_for_case(
    phase_details: list[dict[str, Any]],
    affordance_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    transitions: list[dict[str, Any]] = []
    for i in range(len(phase_details) - 1):
        src = phase_details[i]
        dst = phase_details[i + 1]
        aff_iri = dst.get("affordance_on_arrival")
        aff_name = local_name(aff_iri) if aff_iri else None
        if aff_name:
            for row in affordance_rows:
                if (
                    row.get("from") == display_type(src["type"])
                    and row.get("to") == display_type(dst["type"])
                    and row.get("affordance") == aff_name
                ):
                    break
        transitions.append(
            {
                "from_uri": src["uri"],
                "to_uri": dst["uri"],
                "from_type": src["type"],
                "to_type": dst["type"],
                "from_label": src.get("label"),
                "to_label": dst.get("label"),
                "affordance": aff_iri,
                "affordance_name": aff_name,
                "disrupts_chain": bool(dst.get("disrupts_chain")),
                "disrupted_target": dst.get("disrupted_target"),
            }
        )
    return transitions


def _anchor_fundamental(data: dict[str, Any]) -> list[str]:
    sequences = {
        case_id: data["cases"][case_id]["phase_sequence"]
        for case_id in ANCHOR_CASE_IDS
        if case_id in data.get("cases", {})
    }
    return cross_case_comparison(sequences)["fundamental"]


def _anchor_type_cases(data: dict[str, Any]) -> dict[str, list[str]]:
    sequences = {
        case_id: data["cases"][case_id]["phase_sequence"]
        for case_id in ANCHOR_CASE_IDS
        if case_id in data.get("cases", {})
    }
    return cross_case_comparison(sequences)["type_cases"]


def _expansion_ids_in_file_order(all_cases: dict[str, Any]) -> list[str]:
    """Expansion swimlane order follows EXPANSION_CASE_IDS in iris.py."""
    ordered = [cid for cid in EXPANSION_CASE_IDS if cid in all_cases]
    for case_id in sorted(all_cases):
        if case_id not in ANCHOR_CASE_IDS and case_id not in ordered:
            ordered.append(case_id)
    return ordered


def _lifecycle_case_ids(data: dict[str, Any]) -> list[str]:
    all_cases = data.get("cases", {})
    anchors = [cid for cid in ANCHOR_CASE_IDS if cid in all_cases]
    expansion = _expansion_ids_in_file_order(all_cases)
    return anchors + expansion


def _all_cases_type_cases(data: dict[str, Any]) -> dict[str, list[str]]:
    """Phase-type → case ids (one per case) across anchor + expansion rows."""
    case_ids = _lifecycle_case_ids(data)
    sequences = {
        case_id: data["cases"][case_id]["phase_sequence"]
        for case_id in case_ids
    }
    return cross_case_comparison(sequences)["type_cases"]


def _offense_type_for_case(case_id: str, data: dict[str, Any]) -> str:
    """Map a lifecycle case id to its exploitation modality / offense type label."""
    if case_id in ANCHOR_CASE_IDS:
        return case_id
    meta = CASE_META.get(case_id, {})
    block = data.get("cases", {}).get(case_id, {})
    return str(block.get("modality") or infer_modality(case_id, meta))


def _unique_offense_types(case_ids: list[str], data: dict[str, Any]) -> list[str]:
    """Deduplicated offense types for cases that contain a phase, anchor order first."""
    lifecycle_order = {
        cid: idx for idx, cid in enumerate(_lifecycle_case_ids(data))
    }
    seen: set[str] = set()
    for case_id in sorted(case_ids, key=lambda cid: lifecycle_order.get(cid, 999)):
        offense_type = _offense_type_for_case(case_id, data)
        seen.add(offense_type)
    anchor_part = [ot for ot in ANCHOR_CASE_IDS if ot in seen]
    other_part = sorted(ot for ot in seen if ot not in ANCHOR_CASE_IDS)
    return anchor_part + other_part


def _build_case_record(
    case_id: str,
    block: dict[str, Any],
    meta: dict[str, Any],
    *,
    tier: str,
    type_cases: dict[str, list[str]],
    fundamental: list[str],
    affordance_rows: list[dict[str, Any]],
    n_anchor: int,
) -> dict[str, Any]:
    # Prefer explicit CASE_META modality/citation; fall back to lstar block for older rows.
    explicit_modality = meta.get("modality")
    if explicit_modality and not meta.get("infer_modality_from_conduct"):
        modality = str(explicit_modality)
    else:
        modality = block.get("modality") or infer_modality(case_id, meta)
    phase_details = block.get("phase_details", [])
    phases = []
    for phase in phase_details:
        ptype = phase.get("type", "")
        coverage = len(type_cases.get(ptype, []))
        phases.append(
            {
                **phase,
                "type_display": display_type(ptype),
                "short_type": local_name(ptype),
                "coverage": coverage,
                "is_fundamental": ptype in fundamental,
            }
        )

    title = meta.get("title", case_id.upper())
    block_citation = block.get("citation", "")
    meta_citation = meta.get("citation", "")
    if meta_citation and (
        not block_citation
        or block_citation == case_id
        or not str(block_citation).startswith("United States")
    ):
        citation = meta_citation
    else:
        citation = block_citation or meta_citation
    if tier == "expansion":
        offense_type = modality_label(modality)
        case_name = citation or title
    else:
        offense_type = title
        case_name = title

    return {
        "id": case_id,
        "tier": tier,
        "case_name": case_name,
        "citation": citation,
        "offense_type": offense_type,
        "modality": modality,
        "modality_label": modality_label(modality),
        "corpus_id": meta.get("corpus_id"),
        "defendant": meta.get("defendant"),
        "sting_operation": meta.get("sting_operation") or any(
            p.get("disrupts_chain") for p in phases
        ),
        "sting_only": meta.get("sting_only"),
        "victim_harmed": meta.get("victim_harmed"),
        "chain_disrupted": any(p.get("disrupts_chain") for p in phases),
        "trajectory": block.get("phase_sequence", []),
        "trajectory_display": [
            display_type(t) for t in block.get("phase_sequence", [])
        ],
        "phases": phases,
        "transitions": _transitions_for_case(phase_details, affordance_rows),
        "path_weight": block.get("path_weight"),
        "n_anchor": n_anchor,
    }


def build_lifecycle_payload(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    data = raw if raw is not None else _ensure_lstar_json()
    fundamental = _anchor_fundamental(data)
    type_cases = _anchor_type_cases(data)
    all_type_cases = _all_cases_type_cases(data)
    lifecycle_case_ids = _lifecycle_case_ids(data)
    n_lifecycle = len(lifecycle_case_ids)
    n_anchor = len(ANCHOR_CASE_IDS)
    affordance_rows = data.get("affordance_annotations", [])
    all_cases = data.get("cases", {})

    anchor_cases: list[dict[str, Any]] = []
    for case_id in ANCHOR_CASE_IDS:
        block = all_cases.get(case_id, {})
        meta = CASE_META.get(case_id, {})
        anchor_cases.append(
            _build_case_record(
                case_id,
                block,
                meta,
                tier="anchor",
                type_cases=type_cases,
                fundamental=fundamental,
                affordance_rows=affordance_rows,
                n_anchor=n_anchor,
            )
        )

    expansion_cases: list[dict[str, Any]] = []
    for case_id in _expansion_ids_in_file_order(all_cases):
        block = all_cases[case_id]
        meta = CASE_META.get(case_id, {})
        expansion_cases.append(
            _build_case_record(
                case_id,
                block,
                meta,
                tier="expansion",
                type_cases=type_cases,
                fundamental=fundamental,
                affordance_rows=affordance_rows,
                n_anchor=n_anchor,
            )
        )

    cross_case: dict[str, dict[str, Any]] = {}
    for iri, cases in type_cases.items():
        cross_case[iri] = {
            "count": len(cases),
            "cases": cases,
            "display": display_type(iri),
            "short_name": local_name(iri),
        }

    cross_case_all: dict[str, dict[str, Any]] = {}
    for iri, cases in all_type_cases.items():
        cross_case_all[iri] = {
            "count": len(cases),
            "cases": cases,
            "offense_types": _unique_offense_types(cases, data),
            "display": display_type(iri),
            "short_name": local_name(iri),
        }

    shared_transitions = len(data.get("raw_transitions", []))
    anchor_types = set()
    for case in anchor_cases:
        for phase in case["phases"]:
            anchor_types.add(phase.get("type"))

    return {
        "n_cases": data.get("n_cases", n_anchor),
        "n_anchor": n_anchor,
        "n_expansion": len(expansion_cases),
        "anchor_stage_count": len(anchor_types),
        "shared_transition_count": shared_transitions,
        "fundamental": fundamental,
        "fundamental_display": [display_type(t) for t in fundamental],
        "cross_case": cross_case,
        "cross_case_all": cross_case_all,
        "n_lifecycle": n_lifecycle,
        "affordance_annotations": affordance_rows,
        "anchor_cases": anchor_cases,
        "expansion_cases": expansion_cases,
        "cases": anchor_cases,
    }
