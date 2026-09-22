"""Server-side Oxigraph cold-start retry and the agent-facing waking payload."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "run"
if str(RUN) not in sys.path:
    sys.path.insert(0, str(RUN))

from oxigraph_wake import (  # noqa: E402
    WAKE_MESSAGE,
    WAKE_REASON,
    WAKE_RETRY_AFTER_S,
    aquery_once_then_retry,
    is_wake_http,
    query_once_then_retry,
    sparql_waking_body,
    waking_envelope,
    waking_headers,
    warm_until_ready,
)

requests = pytest.importorskip("requests")


class _Resp:
    def __init__(self, status_code: int):
        self.status_code = status_code


def test_waking_envelope_is_machine_readable():
    body = waking_envelope()
    assert body["status"] == "waking"
    assert body["retry"] is True
    assert body["retry_after_seconds"] == WAKE_RETRY_AFTER_S
    assert isinstance(body["retry_after_seconds"], int)
    assert body["reason"] == WAKE_REASON
    assert "shortly" in body["message"]
    assert body["message"] == WAKE_MESSAGE
    headers = waking_headers()
    assert headers["Retry-After"] == str(WAKE_RETRY_AFTER_S)
    assert headers["X-CaseLinker-Status"] == "waking"
    assert headers["X-CaseLinker-Reason"] == WAKE_REASON


def test_sparql_waking_body_is_empty_results_plus_retry():
    body = sparql_waking_body()
    assert body["head"] == {"vars": []}
    assert body["results"] == {"bindings": []}
    assert body["retry"] is True
    assert body["reason"] == "oxigraph_cold_start"


def test_wake_http_statuses():
    assert is_wake_http(502)
    assert is_wake_http(503)
    assert is_wake_http(504)
    assert not is_wake_http(200)
    assert not is_wake_http(400)
    assert not is_wake_http(500)


def test_sync_retries_once_then_returns_success():
    calls = {"n": 0}
    sleeps = []

    def call():
        calls["n"] += 1
        if calls["n"] == 1:
            return _Resp(502)
        return _Resp(200)

    kind, resp = query_once_then_retry(call, sleep=sleeps.append, retry_s=2.5)
    assert kind == "ok"
    assert resp.status_code == 200
    assert calls["n"] == 2
    assert sleeps == [2.5]


def test_sync_second_failure_is_waking_not_the_502():
    def call():
        raise requests.ConnectionError("connection refused")

    kind, resp = query_once_then_retry(call, sleep=lambda _s: None, retry_s=2.5)
    assert kind == "waking"
    assert resp is None


def test_sync_query_error_is_not_a_cold_start():
    calls = {"n": 0}

    def call():
        calls["n"] += 1
        return _Resp(400)

    kind, resp = query_once_then_retry(call, sleep=lambda _s: (_ for _ in ()).throw(AssertionError("retried")), retry_s=2.5)
    assert kind == "ok"
    assert resp.status_code == 400
    assert calls["n"] == 1


def test_async_retries_gateway_timeout_then_ok():
    calls = {"n": 0}

    async def call():
        calls["n"] += 1
        if calls["n"] == 1:
            raise requests.ConnectionError("connection refused")
        return _Resp(200)

    async def sleep(_s):
        return None

    kind, resp = asyncio.run(
        aquery_once_then_retry(call, sleep=sleep, retry_s=2.5)
    )
    assert kind == "ok"
    assert resp.status_code == 200
    assert calls["n"] == 2


def test_async_disconnect_skips_retry():
    calls = {"n": 0}

    async def call():
        calls["n"] += 1
        return None

    async def sleep(_s):
        raise AssertionError("slept after disconnect")

    kind, resp = asyncio.run(
        aquery_once_then_retry(call, sleep=sleep, is_disconnected=None)
    )
    assert kind == "disconnected"
    assert resp is None
    assert calls["n"] == 1


def test_async_two_502s_are_waking():
    async def call():
        return _Resp(503)

    kind, resp = asyncio.run(
        aquery_once_then_retry(call, sleep=lambda _s: _async_none(), retry_s=2.5)
    )
    assert kind == "waking"
    assert resp is None


async def _async_none():
    return None


def test_warm_returns_awake_when_the_process_answers():
    calls = {"n": 0}

    async def call():
        calls["n"] += 1
        if calls["n"] == 1:
            return _Resp(502)
        return _Resp(200)

    async def sleep(_s):
        return None

    body = asyncio.run(
        warm_until_ready(call, sleep=sleep, budget_s=30, gap_s=2.5, clock=lambda: 0.0)
    )
    assert body["status"] == "awake"
    assert body["retry"] is False
    assert body["reason"] == "oxigraph_ready"
    assert body["attempts"] == 2


def test_warm_budget_returns_waking_envelope():
    clock = {"t": 0.0}

    def now():
        return clock["t"]

    async def call():
        return _Resp(502)

    async def sleep(_s):
        clock["t"] += 2.5

    body = asyncio.run(
        warm_until_ready(call, sleep=sleep, budget_s=5, gap_s=2.5, clock=now)
    )
    assert body["status"] == "waking"
    assert body["retry"] is True
    assert body["reason"] == "oxigraph_cold_start"
    assert body["retry_after_seconds"] == WAKE_RETRY_AFTER_S
    assert body["attempts"] >= 1
    assert body["results"]["bindings"] == []
