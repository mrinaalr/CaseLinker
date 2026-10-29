"""Person names a reader tied to an age (``entity``) never leave localhost."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "run"
NAME = "Jordan Example"


def _load_main():
    # Load by path (src/main.py shares the name).
    spec = importlib.util.spec_from_file_location("caselinker_run_main_names", RUN / "main.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["caselinker_run_main_names"] = mod
    spec.loader.exec_module(mod)
    return mod


def _age_final():
    return {
        "victims": [],
        "perpetrators": [32],
        "perpetrator_entities": [{"entity": NAME, "age": 32, "other_ages": []}],
        "excluded": [],
        "contested": {},
        "unresolved": [],
    }


class _FakeStorage:
    def get_case(self, case_id):
        return {"case_id": case_id}

    def get_case_assertions(self, case_id, field=None):
        return {
            "case_id": case_id,
            "assertions": [{
                "field": "age", "method": "regex", "value": 32, "role": "perpetrator",
                "span_start": 10, "span_end": 12, "span_text": "32",
                "extras": {"shape": "name_comma", "entity": NAME},
            }],
            "resolutions": {"age": {"status": "resolved", "final_value": _age_final()}},
        }

    def get_field_disagreements(self, field=None, status=None, limit=50, offset=0):
        return {
            "items": [{"case_id": "c1", "field": "age", "status": "partial",
                       "final_value": _age_final(), "disagreement": {}}],
            "limit": limit, "offset": offset, "status_counts": {"age": {"partial": 1}},
        }


MAIN = _load_main()


@pytest.fixture
def main(monkeypatch):
    monkeypatch.setattr(MAIN, "storage", _FakeStorage())
    monkeypatch.setattr(MAIN, "CASELINKER_TRUSTED_KEYS", {"k-test"})
    MAIN._case_id_daily_counts.clear()
    MAIN.limiter.reset()
    return MAIN


def _remote(main):
    return TestClient(main.app, client=("203.0.113.9", 50000))


def _loopback(main):
    return TestClient(main.app, client=("127.0.0.1", 50000))


ROUTES = ["/api/cases/c1/assertions", "/api/assertions/disagreements"]


@pytest.mark.parametrize("route", ROUTES)
def test_public_caller_gets_no_names(main, route):
    r = _remote(main).get(route)
    assert r.status_code == 200
    assert NAME not in r.text
    assert '"entity"' not in r.text
    assert "32" in r.text  # ages still served


@pytest.mark.parametrize("route", ROUTES)
def test_trusted_key_gets_no_names(main, route):
    r = _remote(main).get(route, headers={"CaseLinker-Key": "k-test"})
    assert r.status_code == 200
    assert NAME not in r.text


def test_trusted_key_still_gets_span_text(main):
    body = _remote(main).get("/api/cases/c1/assertions", headers={"CaseLinker-Key": "k-test"}).json()
    assert body["assertions"][0]["span_text"] == "32"
    assert "entity" not in body["assertions"][0]["extras"]


@pytest.mark.parametrize("route", ROUTES)
def test_localhost_keeps_names_for_internal_review(main, route):
    assert NAME in _loopback(main).get(route).text
