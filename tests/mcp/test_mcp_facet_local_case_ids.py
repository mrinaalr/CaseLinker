"""Sub-corpus facet tools (case_ids) import facet_local as a package module."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from caselinker_mcp import server
from storage import CaseStorage

CASES = (("t_tn_1", "Tennessee"), ("t_tn_2", "Tennessee"), ("t_wy_1", "Wyoming"))


@pytest.fixture
def fixture_db(tmp_path: Path, monkeypatch) -> Path:
    path = tmp_path / "facet.db"
    storage = CaseStorage(str(path))
    for case_id, location in CASES:
        storage.store_case({
            "id": case_id,
            "source": "TEST",
            "raw_data": {"source_file": "t.pdf", "case_text": "x", "case_id": case_id},
            "locations": [location],
        })
    monkeypatch.setenv("CASELINKER_DB", str(path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return path


def _call(tool, **kwargs):
    fn = getattr(tool, "fn", tool)
    return asyncio.run(fn(**kwargs))


def test_get_facet_tree_with_case_ids(fixture_db):
    out = _call(server.get_facet_tree, case_ids=[c for c, _ in CASES], include_facets="locations", max_depth=1)
    assert "error" not in out, out
    assert "Tennessee" in str(out) and "Wyoming" in str(out)


def test_get_cohort_members_with_case_ids(fixture_db):
    out = _call(
        server.get_cohort_members,
        path=[{"facet": "locations", "value": "Tennessee"}],
        case_ids=[c for c, _ in CASES],
    )
    assert "error" not in out, out
    assert out["case_ids"] == ["t_tn_1", "t_tn_2"]
