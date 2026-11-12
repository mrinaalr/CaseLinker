"""MCP sparql_query backends: policy + local nq + live URL resolution."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _path():
    import sys

    sys.path.insert(0, str(ROOT / "run"))
    sys.path.insert(0, str(ROOT))
    yield


def test_sparql_nq_backend_counts_quads(tmp_path, monkeypatch):
    from caselinker_mcp.sparql_tool import run_sparql

    nq = tmp_path / "tiny.nq"
    g1 = "https://w3id.org/caselinker/resource/case/demo_1"
    g2 = "https://w3id.org/caselinker/resource/case/demo_2"
    lines = [
        f'<http://ex/s1> <http://ex/p> "a" <{g1}> .',
        f'<http://ex/s2> <http://ex/p> "b" <{g1}> .',
        f'<http://ex/s3> <http://ex/p> "c" <{g2}> .',
    ]
    nq.write_text("\n".join(lines) + "\n", encoding="utf-8")
    monkeypatch.delenv("CASELINKER_NQ_ALLOW_LARGE", raising=False)

    out = asyncio.run(
        run_sparql(
            "SELECT (COUNT(*) AS ?n) WHERE { GRAPH ?g { ?s ?p ?o } }",
            backend="nq",
            nq_path=str(nq),
        )
    )
    assert out.get("backend") == "nq"
    assert "error" not in out
    n = out["results"]["bindings"][0]["n"]["value"]
    assert n == "3"
    assert out.get("outer_limit") == 1000
    assert out.get("timeout_s") == 90.0


@pytest.mark.parametrize(
    "query",
    [
        "INSERT DATA { <a> <b> <c> }",
        "DELETE DATA { <a> <b> <c> }",
        "LOAD <http://example.org/data.ttl>",
        "DROP ALL",
        "CLEAR GRAPH <http://example.org/g>",
        "CREATE GRAPH <http://example.org/g>",
        "DELETE WHERE { ?s ?p ?o }",
        "WITH <http://example.org/g> DELETE { ?s ?p ?o } WHERE { ?s ?p ?o }",
    ],
)
def test_sparql_rejects_update_verbs(query):
    from caselinker_mcp.sparql_tool import run_sparql

    out = asyncio.run(run_sparql(query, backend="live"))
    assert "error" in out
    assert out.get("status_code") == 405
    assert "Update" in out["error"]


def test_sparql_rejects_service():
    from caselinker_mcp.sparql_tool import run_sparql

    out = asyncio.run(
        run_sparql(
            "SELECT * WHERE { SERVICE <http://example.org/sparql> { ?s ?p ?o } }",
            backend="live",
        )
    )
    assert "error" in out
    assert out.get("status_code") == 400
    assert "SERVICE" in out["error"]


def test_default_limit_injected_on_select():
    from sparql_proxy import DEFAULT_LIMIT, prepare_sparql_query

    prepared = prepare_sparql_query(
        "SELECT ?s WHERE { ?s ?p ?o }"
    )
    assert prepared.limit_injected is True
    assert prepared.outer_limit == DEFAULT_LIMIT
    assert prepared.query.rstrip().endswith(f"LIMIT {DEFAULT_LIMIT}")


def test_oversized_limit_rejected():
    from caselinker_mcp.sparql_tool import run_sparql

    out = asyncio.run(
        run_sparql("SELECT ?s WHERE { ?s ?p ?o } LIMIT 99999", backend="live")
    )
    assert "error" in out
    assert out.get("status_code") == 400
    assert "LIMIT" in out["error"]


def test_timeout_clamped():
    from caselinker_mcp.sparql_tool import clamp_timeout_s

    assert clamp_timeout_s(90) == 90.0
    assert clamp_timeout_s(0) == 1.0
    assert clamp_timeout_s(9999) == 600.0


def test_live_url_defaults_to_caselinker_sparql():
    from caselinker_mcp.sparql_tool import live_sparql_url

    url = live_sparql_url()
    assert url.endswith("/sparql")


def test_auto_prefers_oxigraph_env(monkeypatch):
    from caselinker_mcp.sparql_tool import resolve_backend

    monkeypatch.setenv("OXIGRAPH_URL", "http://127.0.0.1:7878")
    assert resolve_backend("auto") == "oxigraph"
    monkeypatch.delenv("OXIGRAPH_URL", raising=False)
    monkeypatch.setattr(
        "caselinker_mcp.sparql_tool.local_oxigraph_reachable", lambda: False
    )
    assert resolve_backend("auto") == "live"


def test_auto_uses_local_oxigraph_when_reachable(monkeypatch):
    from caselinker_mcp.sparql_tool import resolve_backend

    monkeypatch.delenv("OXIGRAPH_URL", raising=False)
    monkeypatch.setattr(
        "caselinker_mcp.sparql_tool.local_oxigraph_reachable", lambda: True
    )
    assert resolve_backend("auto") == "oxigraph"


def test_describe_backends_exposes_limits():
    from caselinker_mcp.sparql_tool import describe_backends

    info = describe_backends()
    assert info["default_limit"] == 1000
    assert info["max_limit"] == 10_000
    assert info["default_timeout_s"] == 90.0


def _fake_post(monkeypatch, status_code: int, body: str):
    import httpx

    from caselinker_mcp import sparql_tool

    def handler(request):
        return httpx.Response(status_code, text=body)

    real = httpx.AsyncClient

    def client(**kwargs):
        return real(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(sparql_tool.httpx, "AsyncClient", client)
    return sparql_tool


def test_cancelled_query_is_an_error_not_partial_rows(monkeypatch):
    # What hosted Oxigraph sends when it stops a long query: HTTP 200, half a document.
    body = '{"head":{"vars":["a"]},"results":{"bindings":[The SPARQL operation has been cancelled'
    tool = _fake_post(monkeypatch, 200, body)
    out = asyncio.run(tool.run_sparql("SELECT ?a WHERE { ?a ?b ?c }", backend="live"))
    assert "error" in out and "raw" not in out
    assert "GRAPH ?g" in out["hint"]


def test_complete_result_still_passes_through(monkeypatch):
    body = '{"head":{"vars":["a"]},"results":{"bindings":[]}}'
    tool = _fake_post(monkeypatch, 200, body)
    out = asyncio.run(tool.run_sparql("SELECT ?a WHERE { ?a ?b ?c }", backend="live"))
    assert "error" not in out and out["results"] == {"bindings": []}


def test_unconfigured_store_says_where_to_query(monkeypatch):
    body = '{"detail":"SPARQL store is not configured (set OXIGRAPH_URL)."}'
    tool = _fake_post(monkeypatch, 503, body)
    out = asyncio.run(tool.run_sparql("SELECT ?a WHERE { ?a ?b ?c }", backend="live"))
    assert out["status_code"] == 503 and tool.PUBLIC_SPARQL_URL in out["hint"]
