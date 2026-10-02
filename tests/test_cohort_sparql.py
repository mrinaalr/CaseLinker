"""Search cohort → SPARQL named-graph filter."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "run"
ONTOLOGY = ROOT / "ontology"
for p in (str(RUN), str(ONTOLOGY)):
    if p not in sys.path:
        sys.path.insert(0, p)

from cohort_sparql import (  # noqa: E402
    CASE_GRAPH_BASE,
    MAX_COHORT_GRAPHS,
    build_cohort_case_query,
    normalize_case_ids,
)
from sparql_proxy import prepare_sparql_query  # noqa: E402


def test_normalize_sorts_and_drops_unsafe_ids():
    ids = normalize_case_ids(
        [
            " wy_dci_2026_002 ",
            "nj_ag_2017_001",
            "nj_ag_2017_001",
            "nj_ag_2017_001> <http://evil.example/x>",
            "",
            "has space",
            "pacer_ok-1",
        ]
    )
    assert ids == ["nj_ag_2017_001", "pacer_ok-1", "wy_dci_2026_002"]


def test_query_embeds_named_graphs_and_survives_proxy_policy():
    built = build_cohort_case_query(
        ["wy_dci_2026_002", "nj_ag_2017_001"],
        label="Discord\n# ignore\n<script>",
    )
    assert built["included"] == 2
    assert built["truncated"] is False
    assert built["label"] == "Discord ignore script"
    text = built["sparql"]
    assert f"<{CASE_GRAPH_BASE}nj_ag_2017_001>" in text
    assert f"<{CASE_GRAPH_BASE}wy_dci_2026_002>" in text
    assert "GRAPH ?g" in text
    assert "dcterms:identifier ?id" in text
    assert "GROUP_CONCAT(DISTINCT ?platform" in text
    assert "cac-legal:hasCharge" in text
    assert "COUNT(DISTINCT ?g)" not in text
    assert text.rstrip().endswith("LIMIT 2")
    assert "# Search cohort: Discord ignore script (2 cases)" in text

    prepared = prepare_sparql_query(text)
    assert prepared.kind == "SelectQuery"
    assert prepared.limit_injected is False
    assert prepared.outer_limit == 2
    assert prepared.query == text.strip()


def test_cap_is_sorted_and_reported():
    ids = [f"src_{i:04d}" for i in range(MAX_COHORT_GRAPHS + 3)]
    built = build_cohort_case_query(ids, max_graphs=5)
    assert built["case_count"] == MAX_COHORT_GRAPHS + 3
    assert built["included"] == 5
    assert built["truncated"] is True
    assert "<" + CASE_GRAPH_BASE + "src_0000>" in built["sparql"]
    assert "src_0005" not in built["sparql"]
    assert "Capped at 5 of" in built["sparql"]
    prepared = prepare_sparql_query(built["sparql"])
    assert prepared.outer_limit == 5
    assert prepared.limit_injected is False
    assert built["sparql"].rstrip().endswith("LIMIT 5")


def test_empty_input_builds_no_graphs():
    built = build_cohort_case_query(["   ", "not an id!"])
    assert built["included"] == 0
    assert built["case_count"] == 0
    assert built["sparql"] == ""
