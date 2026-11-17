"""Localhost access is decided by the connection peer, never by X-Forwarded-For."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "run"
SPOOF = {"X-Forwarded-For": "127.0.0.1"}


def _load_main(name: str, trusted_proxies: str | None):
    # Load by path (src/main.py shares the name). Proxy trust is read at import.
    old = os.environ.pop("CASELINKER_TRUSTED_PROXIES", None)
    if trusted_proxies is not None:
        os.environ["CASELINKER_TRUSTED_PROXIES"] = trusted_proxies
    try:
        spec = importlib.util.spec_from_file_location(name, RUN / "main.py")
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        os.environ.pop("CASELINKER_TRUSTED_PROXIES", None)
        if old is not None:
            os.environ["CASELINKER_TRUSTED_PROXIES"] = old


class _FakeStorage:
    def get_case(self, case_id):
        return {
            "case_id": case_id,
            "raw_data": "narrative",
            "extracted_features": {"raw_data": "narrative", "case_text": "narrative"},
        }

    def get_all_cases(self, include_raw_data=False):
        return [self.get_case("c1")]

    def get_case_count(self):
        return 1


# Default trust (loopback only) and full trust (how Railway is configured).
DEFAULT = _load_main("caselinker_run_main_peer_default", None)
TRUST_ALL = _load_main("caselinker_run_main_peer_trust_all", "*")


@pytest.fixture(params=[DEFAULT, TRUST_ALL], ids=["default", "trust_all"])
def main(request, monkeypatch):
    mod = request.param
    monkeypatch.setattr(mod, "storage", _FakeStorage())
    monkeypatch.setattr(mod, "REDIS_AVAILABLE", False)
    monkeypatch.setattr(mod, "_cases_cache", {"include_raw_true": None, "include_raw_false": None})
    monkeypatch.setattr(mod, "CASELINKER_TRUSTED_KEYS", {"k-test"})
    mod._case_id_daily_counts.clear()
    mod._llm_daily_counts.clear()
    mod.limiter.reset()
    return mod


def _remote(main):
    return TestClient(main.app, client=("203.0.113.9", 50000))


def _loopback(main):
    return TestClient(main.app, client=("127.0.0.1", 50000))


def test_spoofed_forwarded_for_is_not_local(main):
    c = _remote(main)
    assert c.get("/api/cases", headers=SPOOF).status_code == 403
    assert c.get("/api/cases?include_raw_data=true", headers=SPOOF).status_code == 403
    assert c.get("/api/corpus", headers=SPOOF).status_code == 403
    assert c.get("/api/lifecycle/cases", headers=SPOOF).status_code == 403
    one = c.get("/api/cases/c1", headers=SPOOF).json()
    assert "raw_data" not in one and "raw_data" not in one["extracted_features"]


def test_spoofed_forwarded_for_does_not_skip_daily_caps(main):
    c = _remote(main)
    for _ in range(main._CASE_ID_DAILY_LIMIT):
        assert c.get("/api/cases/c1", headers=SPOOF).status_code == 200
    assert c.get("/api/cases/c1", headers=SPOOF).status_code == 429

    req = _as_request(main, c, SPOOF)
    for _ in range(main._LLM_DAILY_LIMIT):
        main._enforce_llm_daily_limit(req)
    with pytest.raises(main.HTTPException) as exc:
        main._enforce_llm_daily_limit(req)
    assert exc.value.status_code == 429


def _as_request(main, client, headers):
    # Run a throwaway route through the full middleware stack and hand back its Request.
    seen = {}

    @main.app.get("/__peer_probe")
    def _probe(request: Request):
        seen["r"] = request
        return {}

    client.get("/__peer_probe", headers=headers)
    main.app.router.routes.pop()
    return seen["r"]


def test_loopback_peer_is_local(main):
    c = _loopback(main)
    assert c.get("/api/cases?include_raw_data=true").status_code == 200
    assert c.get("/api/cases/c1").json()["raw_data"] == "narrative"
    for _ in range(main._CASE_ID_DAILY_LIMIT + 1):
        assert c.get("/api/cases/c1").status_code == 200


def test_trusted_key_works_behind_proxy(main):
    c = _remote(main)
    h = {**SPOOF, "CaseLinker-Key": "k-test"}
    assert c.get("/api/cases?include_raw_data=true", headers=h).status_code == 200
    assert c.get("/api/cases/c1", headers=h).json()["raw_data"] == "narrative"


def test_untrusted_peer_cannot_rotate_forwarded_for_past_daily_cap(monkeypatch):
    main = DEFAULT
    monkeypatch.setattr(main, "storage", _FakeStorage())
    main._case_id_daily_counts.clear()
    c = _remote(main)
    codes = [
        c.get("/api/cases/c1", headers={"X-Forwarded-For": f"198.51.100.{i}"}).status_code
        for i in range(main._CASE_ID_DAILY_LIMIT + 1)
    ]
    assert codes[-1] == 429


def test_trusted_proxy_forwards_client_ip():
    # Behind a trusted proxy the client IP comes from X-Forwarded-For (rate-limit keys),
    # but a forwarded 127.0.0.1 still does not count as local.
    c = _remote(TRUST_ALL)
    r = _as_request(TRUST_ALL, c, {"X-Forwarded-For": "127.0.0.1"})
    assert r.client.host == "127.0.0.1"
    assert TRUST_ALL._is_local_request(r) is False
