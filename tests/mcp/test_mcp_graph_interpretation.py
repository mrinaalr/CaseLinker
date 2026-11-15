"""Graph tool responses say they are CAC concept matches, not conduct similarity (#28)."""

from __future__ import annotations

import asyncio
import types

import pytest

from caselinker_mcp import server

R = "https://w3id.org/caselinker/resource"
CAC = "https://cacontology.projectvic.org"

# Two cases with different conduct (possession-only vs production) that share
# one platform node. That shared node is the only link between them.
FLAT_NODES = [
    {
        "@id": f"{R}/platform/discord",
        "@type": [f"{CAC}/platforms#AnonymousChatPlatform"],
        "_cases": ["case_possession", "case_production"],
        "_isShared": True,
    },
    {
        "@id": f"{R}/case/case_possession/event/csam",
        "@type": [f"{CAC}/legal-outcomes#CSAM_Possession"],
        "usesPlatform": {"@id": f"{R}/platform/discord"},
        "_cases": ["case_possession"],
    },
    {
        "@id": f"{R}/case/case_production/event/production",
        "@type": [f"{CAC}/core#CSAMProduction"],
        "usesPlatform": {"@id": f"{R}/platform/discord"},
        "_cases": ["case_production"],
    },
]


def _payload() -> dict:
    from graph_utils import flat_nodes_to_nodes_edges

    flat = [dict(n) for n in FLAT_NODES]
    nodes, edges = flat_nodes_to_nodes_edges(flat)
    return {
        "nodes": nodes,
        "edges": edges,
        "flat_nodes": flat,
        "metadata": {
            "requested_count": 2,
            "cases_mapped": ["case_possession", "case_production"],
            "skipped": [],
        },
    }


@pytest.fixture(autouse=True)
def _in_memory_graph_store(monkeypatch):
    monkeypatch.setattr(server, "_redis_available", False)
    monkeypatch.setattr(server, "_graph_store", {})
    fake = types.ModuleType("graph_generate")
    fake.generate_graph_for_ids = lambda ids: _payload()
    monkeypatch.setitem(__import__("sys").modules, "graph_generate", fake)


def _assert_cac_interpretation(resp: dict, kind: str) -> None:
    assert "error" not in resp, resp
    assert resp.get("interpretation_kind") == kind
    note = resp.get("interpretation_note") or ""
    assert "Not a conduct-similarity" in note
    assert "filter_cases_by_tags" in note


def _graph_id() -> str:
    resp = asyncio.run(server.case2cac(["case_possession", "case_production"]))
    _assert_cac_interpretation(resp, "cac_concept_graph")
    return resp["graph_id"]


def test_case2cac_self_describes():
    _graph_id()


def test_case2cac_empty_input_self_describes():
    resp = asyncio.run(server.case2cac([]))
    assert resp["graph_id"] is None
    assert resp["interpretation_kind"] == "cac_concept_graph"


def test_find_cases_by_concept_is_concept_match_not_conduct_cohort():
    gid = _graph_id()
    resp = asyncio.run(server.graph_find_cases_by_concept(gid, "discord"))
    _assert_cac_interpretation(resp, "cac_concept_match")
    # The trap: a platform concept returns both offense types.
    assert resp["matched_cases"] == ["case_possession", "case_production"]


def test_get_neighbors_self_describes():
    gid = _graph_id()
    resp = asyncio.run(server.graph_get_neighbors(gid, f"{R}/platform/discord"))
    _assert_cac_interpretation(resp, "cac_graph_adjacency")
    assert len(resp["neighbors"]) == 2


def test_summarize_self_describes():
    gid = _graph_id()
    resp = asyncio.run(server.graph_summarize(gid))
    _assert_cac_interpretation(resp, "cac_concept_cooccurrence")


def test_compare_cohorts_self_describes_and_keeps_prose():
    gid_a = _graph_id()
    gid_b = _graph_id()
    resp = asyncio.run(server.graph_compare_cohorts(gid_a, gid_b))
    _assert_cac_interpretation(resp, "cac_concept_overlap")
    assert isinstance(resp["interpretation"], str)
    assert "not a conduct-similarity measure" in resp["interpretation"]


def test_graph_tool_docstrings_disclaim_conduct_similarity():
    for name in (
        "case2cac",
        "graph_get_neighbors",
        "graph_find_cases_by_concept",
        "graph_summarize",
        "graph_compare_cohorts",
    ):
        doc = (getattr(server, name).__doc__ or "").lower()
        assert "interpretation_kind" in doc, name
        assert "conduct" in doc, name
