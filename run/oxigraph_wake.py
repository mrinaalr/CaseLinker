"""Oxigraph cold-start handling for the public SPARQL proxy.

Railway Serverless sleeps Oxigraph after idle time. The first request then
502s or hangs while RocksDB reopens the store. Callers include the browser
and MCP / tool-calling agents, which must not be left with a raw 502.

Contract for a still-asleep store, after one server-side retry:

- HTTP 200 (so clients that only raise on non-2xx still receive a body)
- ``Retry-After`` and ``X-CaseLinker-Status: waking``
- JSON fields an agent can branch on without reading prose:

  status = "waking"
  retry = true
  retry_after_seconds = <int>
  reason = "oxigraph_cold_start"

``results`` / ``cases`` are empty on purpose. Check ``status`` or ``retry``
before treating an empty binding list as a real answer.
"""

from __future__ import annotations

import os
from typing import Any, Awaitable, Callable, Optional

WAKE_STATUS = "waking"
WAKE_REASON = "oxigraph_cold_start"
WAKE_MESSAGE = "Graph store is waking up. Try again shortly."
WAKE_HTTP_STATUS = frozenset({502, 503, 504})
WAKE_RETRY_S = float(os.environ.get("OXIGRAPH_WAKE_RETRY_S", "2.5"))
WAKE_RETRY_AFTER_S = int(os.environ.get("OXIGRAPH_WAKE_RETRY_AFTER_S", "5"))


def waking_envelope() -> dict[str, Any]:
    """Machine-readable 'try again shortly' fields. Stable for agents."""
    return {
        "status": WAKE_STATUS,
        "retry": True,
        "retry_after_seconds": WAKE_RETRY_AFTER_S,
        "reason": WAKE_REASON,
        "message": WAKE_MESSAGE,
    }


def sparql_waking_body() -> dict[str, Any]:
    """SPARQL Results JSON plus the wake envelope.

    Empty bindings are not a corpus answer. Agents must honor ``retry``.
    """
    body = waking_envelope()
    body["head"] = {"vars": []}
    body["results"] = {"bindings": []}
    return body


def waking_headers() -> dict[str, str]:
    return {
        "Retry-After": str(WAKE_RETRY_AFTER_S),
        "X-CaseLinker-Status": WAKE_STATUS,
        "X-CaseLinker-Reason": WAKE_REASON,
    }


def is_wake_http(status_code: Optional[int]) -> bool:
    return status_code in WAKE_HTTP_STATUS


def _wake_exception_types() -> tuple[type[BaseException], ...]:
    types: list[type[BaseException]] = []
    try:
        import httpx

        types.append(httpx.TimeoutException)
        types.append(httpx.RequestError)
    except ImportError:
        pass
    try:
        import requests

        types.append(requests.Timeout)
        types.append(requests.ConnectionError)
    except ImportError:
        pass
    return tuple(types)


def is_wake_exception(exc: BaseException) -> bool:
    return isinstance(exc, _wake_exception_types())


async def aquery_once_then_retry(
    call: Callable[[], Awaitable[Any]],
    *,
    sleep: Callable[[float], Awaitable[None]],
    retry_s: float = WAKE_RETRY_S,
    is_disconnected: Optional[Callable[[], Awaitable[bool]]] = None,
) -> tuple[str, Any]:
    """Run ``call`` once, and once more after ``retry_s`` if the store is waking.

    ``call`` returns a response (``.status_code``) or None when the HTTP client
    already went away. Returns ``("ok", response)``, ``("disconnected", None)``,
    or ``("waking", None)``.
    """

    async def _attempt() -> tuple[str, Any]:
        try:
            resp = await call()
        except Exception as exc:
            if is_wake_exception(exc):
                return "wake", None
            raise
        if resp is None:
            return "disconnected", None
        if is_wake_http(getattr(resp, "status_code", None)):
            return "wake", resp
        return "ok", resp

    kind, resp = await _attempt()
    if kind != "wake":
        return kind, resp
    if is_disconnected is not None and await is_disconnected():
        return "disconnected", None
    await sleep(retry_s)
    if is_disconnected is not None and await is_disconnected():
        return "disconnected", None
    kind, resp = await _attempt()
    if kind == "wake":
        return "waking", None
    return kind, resp


def query_once_then_retry(
    call: Callable[[], Any],
    *,
    sleep: Callable[[float], None],
    retry_s: float = WAKE_RETRY_S,
) -> tuple[str, Any]:
    """Synchronous twin of :func:`aquery_once_then_retry`."""

    def _attempt() -> tuple[str, Any]:
        try:
            resp = call()
        except Exception as exc:
            if is_wake_exception(exc):
                return "wake", None
            raise
        if resp is None:
            return "disconnected", None
        if is_wake_http(getattr(resp, "status_code", None)):
            return "wake", resp
        return "ok", resp

    kind, resp = _attempt()
    if kind != "wake":
        return kind, resp
    sleep(retry_s)
    kind, resp = _attempt()
    if kind == "wake":
        return "waking", None
    return kind, resp


async def warm_until_ready(
    call: Callable[[], Awaitable[Any]],
    *,
    sleep: Callable[[float], Awaitable[None]],
    budget_s: float = 45.0,
    gap_s: float = WAKE_RETRY_S,
    clock: Optional[Callable[[], float]] = None,
) -> dict[str, Any]:
    """Ping until Oxigraph answers or ``budget_s`` runs out.

    Any HTTP status outside 502/503/504 counts as awake (the process replied).
    """
    import time

    now = clock or time.monotonic
    start = now()
    attempts = 0
    while True:
        attempts += 1
        try:
            resp = await call()
        except Exception as exc:
            if not is_wake_exception(exc):
                raise
            resp = None
        status = getattr(resp, "status_code", None) if resp is not None else None
        if resp is not None and not is_wake_http(status):
            return {
                "status": "awake",
                "retry": False,
                "reason": "oxigraph_ready",
                "attempts": attempts,
                "upstream_status": status,
                "message": "Oxigraph is awake.",
            }
        elapsed = now() - start
        if elapsed + gap_s > budget_s:
            break
        await sleep(gap_s)
    body = sparql_waking_body()
    body["attempts"] = attempts
    return body
