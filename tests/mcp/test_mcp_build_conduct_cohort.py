"""build_conduct_cohort intersects the existing filters and reports each step (#28)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from caselinker_mcp import server
from storage import CaseStorage

LOCATIONS = {"c1": "Tennessee", "c2": "Tennessee", "c3": "Wyoming", "c4": "TENNESSEE"}
TAGGED = ["c1", "c2", "c3", "c4"]
AGE_25_29 = ["c1", "c3", "c4", "c9"]
PLATFORM_KIK = ["c1", "c3"]


@pytest.fixture
def api(tmp_path: Path, monkeypatch):
    path = tmp_path / "cohort.db"
    storage = CaseStorage(str(path))
    for case_id, location in LOCATIONS.items():
        storage.store_case({
            "id": case_id,
            "source": "TEST",
            "raw_data": {"source_file": "t.pdf", "case_text": "x", "case_id": case_id},
            "locations": [location],
        })
    monkeypatch.setenv("CASELINKER_DB", str(path))
    monkeypatch.delenv("DATABASE_URL", raising=False)

    calls: list[tuple] = []

    async def fake_post(route, payload, **_):
        calls.append(("POST", route, payload))
        assert route == "/api/return-tagged-cases"
        return {"cases": [{"id": c} for c in TAGGED]}

    async def fake_get(route, params=None, **_):
        calls.append(("GET", route, params))
        if route == "/api/tags":
            return {}
        assert route == "/api/case-ids-by-filter"
        if params == {"age_range": "25-29"}:
            return {"case_ids": AGE_25_29, "count": len(AGE_25_29)}
        if params == {"platform": "kik"}:
            return {"case_ids": PLATFORM_KIK, "count": len(PLATFORM_KIK)}
        raise AssertionError(params)

    monkeypatch.setattr(server, "api_post", fake_post)
    monkeypatch.setattr(server, "api_get", fake_get)
    return calls


def _run(**kwargs):
    fn = getattr(server.build_conduct_cohort, "fn", server.build_conduct_cohort)
    return asyncio.run(fn(**kwargs))


def test_intersects_steps_and_reports_counts(api):
    out = _run(tags=["sextortion", "snapchat"], age_range="25-29", locations=["Tennessee"])
    assert "error" not in out, out
    assert out["case_ids"] == ["c1"]
    assert out["count"] == 1
    assert [(s["step"], s["count_after"], s["excluded"]) for s in out["steps"]] == [
        ("tags", 4, None),
        ("age_range", 3, 1),
        ("locations", 1, 2),
    ]
    assert out["resolved_tags"] == [
        {"tag": "sextortion", "category": "case_topics"},
        {"tag": "snapchat", "category": "platforms_used"},
    ]
    assert out["interpretation_kind"] == "conduct_filter_intersection"
    assert "not a validated same-conduct" in out["interpretation_note"]
    assert "raw" in out["interpretation_note"]


def test_locations_are_exact_raw_strings_unioned(api):
    out = _run(tags=["sextortion"], locations=["Tennessee", "TENNESSEE"])
    assert out["case_ids"] == ["c1", "c2", "c4"]
    only_title_case = _run(tags=["sextortion"], locations=["Tennessee"])
    assert only_title_case["case_ids"] == ["c1", "c2"]


def test_platform_step_uses_case_ids_filter(api):
    out = _run(tags=["sextortion"], platform="kik")
    assert out["case_ids"] == ["c1", "c3"]
    assert ("GET", "/api/case-ids-by-filter", {"platform": "kik"}) in api


def test_unknown_tag_fails_closed(api):
    out = _run(tags=["sextortion", "notarealtag"], age_range="25-29")
    assert out["unknown_tags"] == ["notarealtag"]
    assert out["error"]
    assert out["failed_step"] == "tags"
    assert out["case_ids"] == []
    assert not [c for c in api if c[1] != "/api/tags"]


def test_step_error_has_a_message(api, monkeypatch):
    async def timeout(route, params=None, **_):
        if route == "/api/tags":
            return {}
        raise httpx.ReadTimeout("")

    monkeypatch.setattr(server, "api_get", timeout)
    out = _run(tags=["sextortion"], age_range="25-29")
    assert out["failed_step"] == "age_range"
    assert out["error"].startswith("ReadTimeout")
    assert out["case_ids"] == []
    assert [s["step"] for s in out["steps"]] == ["tags"]


def test_requires_a_filter(api):
    out = _run(locations=["Tennessee"])
    assert out["error"]
    assert out["case_ids"] == []
    assert api == []
