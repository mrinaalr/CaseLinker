"""MCP-local facet tree operations — reads caselinker.db directly, no REST API."""

from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_REPO_ROOT = Path(__file__).resolve().parent.parent
_STORAGE_LAYER = _REPO_ROOT / "src" / "Storage Layer"
if str(_STORAGE_LAYER) not in sys.path:
    sys.path.insert(0, str(_STORAGE_LAYER))

from facet_tree import (  # noqa: E402
    DEFAULT_FACET_ORDER,
    FacetTreeNode,
    build_facet_tree,
    cohort_members_for_path,
    count_nodes,
    distinct_field_values,
    enrich_cases_with_era_period,
    facet_order_subset,
    filter_cases_by_constraints,
    max_tree_depth,
)
from storage import CaseStorage  # noqa: E402

PACER_CASES_JSON = _REPO_ROOT / "ontology" / "PACER" / "pacer_cases.json"

# Ten-level partition order matching the search UI (excludes perp_admission).
SEARCH_UI_FACET_ORDER: Sequence[Tuple[str, str]] = tuple(
    step for step in DEFAULT_FACET_ORDER if step[0] != "perpetrator_admission_themes"
)


def _db_path() -> Path:
    env = os.environ.get("CASELINKER_DB", "").strip()
    if env:
        return Path(env)
    return _REPO_ROOT / "caselinker.db"


def _parse_constraints(raw: str | Dict[str, List[str]] | None) -> Dict[str, List[str]]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return {k: list(v) for k, v in raw.items() if v}
    s = str(raw).strip()
    if not s:
        return {}
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        return {}
    if not isinstance(obj, dict):
        return {}
    valid = {k for k, _ in DEFAULT_FACET_ORDER}
    out: Dict[str, List[str]] = {}
    for k, v in obj.items():
        if k not in valid:
            continue
        if isinstance(v, list):
            out[k] = [str(x) for x in v if x is not None and str(x).strip()]
        elif v is not None and str(v).strip():
            out[k] = [str(v).strip()]
    return out


def _parse_include_facets(raw: str | List[str] | None) -> Optional[List[str]]:
    if raw is None:
        return None
    if isinstance(raw, list):
        parts = [str(p).strip() for p in raw if str(p).strip()]
    else:
        s = str(raw).strip()
        if not s:
            return None  # MCP default: full facet order (unlike API ?include_facets=)
        parts = [p.strip() for p in s.split(",") if p.strip()]
    valid = {k for k, _ in DEFAULT_FACET_ORDER}
    filtered = [p for p in parts if p in valid]
    return filtered or None


def _path_tuples(raw_path: List[Dict[str, str]]) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for step in raw_path:
        if not isinstance(step, dict):
            continue
        fk = step.get("facet") or step.get("field")
        val = step.get("value")
        if fk is not None and val is not None:
            out.append((str(fk), str(val)))
    return out


def load_cases_by_ids(case_ids: Sequence[str]) -> List[Dict[str, Any]]:
    db = _db_path()
    if not db.exists():
        raise FileNotFoundError(f"Database not found: {db}")
    storage = CaseStorage(str(db))
    all_cases = storage.get_all_cases(include_raw_data=False) or []
    enrich_cases_with_era_period(all_cases)
    want = {cid.strip() for cid in case_ids if cid and cid.strip()}
    return [c for c in all_cases if str(c.get("id") or "") in want]


def load_pacer_case_ids(min_confidence: str = "low") -> List[str]:
    if not PACER_CASES_JSON.exists():
        raise FileNotFoundError(
            f"PACER pool not found: {PACER_CASES_JSON}. Run: python collector/pacer/corpus2pacer.py"
        )
    data = json.loads(PACER_CASES_JSON.read_text(encoding="utf-8"))
    rank = {"high": 3, "medium": 2, "low": 1}
    min_rank = rank.get(min_confidence, 1)
    ids: List[str] = []
    for rec in data.get("cases") or []:
        if rank.get(rec.get("confidence", "low"), 1) >= min_rank and rec.get("id"):
            ids.append(str(rec["id"]))
    if not ids and data.get("case_ids"):
        ids = [str(x) for x in data["case_ids"]]
    return ids


def build_facet_tree_payload(
    cases: List[Dict[str, Any]],
    *,
    max_depth: Optional[int] = None,
    facet_constraints: Optional[Dict[str, List[str]]] = None,
    include_facets: Optional[List[str]] = None,
    use_search_ui_order: bool = False,
    root_label: Optional[str] = None,
) -> Dict[str, Any]:
    source_count = len(cases)
    constraints = facet_constraints or {}
    filtered = filter_cases_by_constraints(cases, constraints)
    base_order = SEARCH_UI_FACET_ORDER if use_search_ui_order else DEFAULT_FACET_ORDER
    order = facet_order_subset(base_order, include_facets)
    active = {k: v for k, v in constraints.items() if v}
    label = root_label or ("Matching cases" if active else "All cases")
    root = build_facet_tree(
        filtered,
        facet_order=order,
        max_depth=max_depth,
        root_label=label,
    )
    return {
        "total_cases": len(filtered),
        "source_case_count": source_count,
        "node_count": count_nodes(root),
        "tree_max_depth": max_tree_depth(root),
        "max_depth_param": max_depth,
        "facet_levels": len(order),
        "facet_levels_full": len(base_order),
        "facet_order": [{"field": k, "label": lab} for k, lab in order],
        "prune_constraints": constraints,
        "include_facets": include_facets,
        "root": root.to_dict(),
        "_root_node": root,
        "_cases": filtered,
    }


def facet_distinct_payload(cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    enrich_cases_with_era_period(cases)
    options: Dict[str, Any] = {}
    for field_key, label in DEFAULT_FACET_ORDER:
        options[field_key] = {
            "label": label,
            "values": distinct_field_values(cases, field_key),
        }
    return {"total_cases": len(cases), "facets": options}


def cohort_members_payload(
    cases: List[Dict[str, Any]],
    path: List[Dict[str, str]],
    facet_constraints: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    enrich_cases_with_era_period(cases)
    filtered = filter_cases_by_constraints(cases, facet_constraints or {})
    path_tuples = _path_tuples(path)
    members = cohort_members_for_path(filtered, path_tuples)
    ids = sorted(
        str(c["id"]) for c in members if c.get("id") is not None and str(c.get("id")).strip()
    )
    return {
        "count": len(ids),
        "case_ids": ids,
        "facet_path": [{"facet": k, "value": v} for k, v in path_tuples],
        "prune_constraints": facet_constraints or {},
        "requires_access_key": False,
    }


def _collect_leaves(node: FacetTreeNode) -> List[FacetTreeNode]:
    if node.is_leaf or not node.children:
        return [node]
    out: List[FacetTreeNode] = []
    for child in node.children:
        out.extend(_collect_leaves(child))
    return out


def _random_walk_case(
    root: FacetTreeNode,
    cases: List[Dict[str, Any]],
    rng: random.Random,
) -> Optional[str]:
    node = root
    path: List[Tuple[str, str]] = []
    while node.children and not node.is_leaf:
        weights = [max(c.case_count, 1) for c in node.children]
        child = rng.choices(node.children, weights=weights, k=1)[0]
        if child.facet_key and child.facet_value:
            path.append((child.facet_key, child.facet_value))
        node = child
    members = cohort_members_for_path(cases, path)
    if not members:
        return None
    pick = rng.choice(members)
    cid = pick.get("id")
    return str(cid) if cid else None


def _signature_key(node: FacetTreeNode, dims: int = 3) -> Tuple[str, ...]:
    sig = node.facet_signature or []
    return tuple(v for _, v in sig[:dims])


def _targeted_sample(
    root: FacetTreeNode,
    cases: List[Dict[str, Any]],
    n: int,
    rng: random.Random,
    explicit_path: Optional[List[Tuple[str, str]]] = None,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    paths_used: List[Dict[str, Any]] = []
    if explicit_path:
        members = cohort_members_for_path(cases, explicit_path)
        ids = [str(c["id"]) for c in members if c.get("id")]
        rng.shuffle(ids)
        picked = ids[:n]
        paths_used.append(
            {
                "mode": "explicit",
                "path": [{"facet": k, "value": v} for k, v in explicit_path],
                "cohort_size": len(ids),
            }
        )
        return picked, paths_used

    leaves = [leaf for leaf in _collect_leaves(root) if leaf.case_count > 0]
    leaves.sort(key=lambda x: (-len(x.facet_signature), -x.case_count, x.label))
    picked_ids: List[str] = []
    seen_sig: set[Tuple[str, ...]] = set()

    for leaf in leaves:
        if len(picked_ids) >= n:
            break
        sig_key = _signature_key(leaf)
        if sig_key in seen_sig and len(leaves) > n:
            continue
        path = list(leaf.facet_signature)
        members = cohort_members_for_path(cases, path)
        if not members:
            continue
        choice = rng.choice(members)
        cid = choice.get("id")
        if not cid or str(cid) in picked_ids:
            continue
        picked_ids.append(str(cid))
        seen_sig.add(sig_key)
        paths_used.append(
            {
                "mode": "diverse_leaf",
                "path": [{"facet": k, "value": v} for k, v in path],
                "cohort_size": len(members),
                "leaf_label": leaf.label,
            }
        )

    while len(picked_ids) < n and leaves:
        leaf = rng.choice(leaves)
        path = list(leaf.facet_signature)
        members = cohort_members_for_path(cases, path)
        if not members:
            continue
        choice = rng.choice(members)
        cid = choice.get("id")
        if cid and str(cid) not in picked_ids:
            picked_ids.append(str(cid))

    return picked_ids[:n], paths_used


def tree_traversal_payload(
    *,
    case_ids: Optional[List[str]] = None,
    use_pacer_pool: bool = False,
    pacer_min_confidence: str = "low",
    random_count: int = 25,
    targeted_count: int = 25,
    max_depth: Optional[int] = None,
    facet_constraints_json: str = "",
    include_facets: str = "",
    targeted_path: Optional[List[Dict[str, str]]] = None,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    if use_pacer_pool:
        ids = load_pacer_case_ids(pacer_min_confidence)
    elif case_ids:
        ids = [c.strip() for c in case_ids if c and c.strip()]
    else:
        return {"error": "Provide case_ids or set use_pacer_pool=true"}

    if not ids:
        return {"error": "No case IDs to traverse", "case_ids": []}

    cases = load_cases_by_ids(ids)
    if not cases:
        return {
            "error": "None of the requested case IDs exist in the database",
            "requested": len(ids),
            "found": 0,
        }

    constraints = _parse_constraints(facet_constraints_json)
    include_list = _parse_include_facets(include_facets)
    tree_payload = build_facet_tree_payload(
        cases,
        max_depth=max_depth,
        facet_constraints=constraints,
        include_facets=include_list,
        use_search_ui_order=True,
        root_label=f"PACER pool ({len(cases)} cases)",
    )
    root: FacetTreeNode = tree_payload.pop("_root_node")
    filtered_cases: List[Dict[str, Any]] = tree_payload.pop("_cases")

    rng = random.Random(seed)
    random_ids: List[str] = []
    random_paths: List[Dict[str, Any]] = []
    attempts = 0
    while len(random_ids) < random_count and attempts < random_count * 100:
        attempts += 1
        cid = _random_walk_case(root, filtered_cases, rng)
        if cid and cid not in random_ids:
            random_ids.append(cid)
            random_paths.append({"case_id": cid, "mode": "random_walk"})

    explicit = _path_tuples(targeted_path) if targeted_path else None
    targeted_ids, targeted_paths = _targeted_sample(
        root, filtered_cases, targeted_count, rng, explicit_path=explicit or None
    )

    all_picked = list(dict.fromkeys(random_ids + targeted_ids))

    return {
        "input_case_count": len(ids),
        "loaded_case_count": len(cases),
        "tree": {
            "node_count": tree_payload["node_count"],
            "tree_max_depth": tree_payload["tree_max_depth"],
            "facet_levels": tree_payload["facet_levels"],
            "facet_order": tree_payload["facet_order"],
            "total_cases": tree_payload["total_cases"],
        },
        "random_sample": {
            "requested": random_count,
            "selected": random_ids,
            "count": len(random_ids),
        },
        "targeted_sample": {
            "requested": targeted_count,
            "selected": targeted_ids,
            "count": len(targeted_ids),
            "paths": targeted_paths,
        },
        "combined_case_ids": all_picked,
        "combined_count": len(all_picked),
        "seed": seed,
        "prune_constraints": constraints,
    }


__all__ = [
    "build_facet_tree_payload",
    "cohort_members_payload",
    "facet_distinct_payload",
    "load_cases_by_ids",
    "load_pacer_case_ids",
    "tree_traversal_payload",
    "_parse_constraints",
    "_parse_include_facets",
]
