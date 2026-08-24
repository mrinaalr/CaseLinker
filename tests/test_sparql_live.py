"""Live production checks for GET|POST /sparql.

Skipped unless CASELINKER_SPARQL_LIVE=1 so a normal pytest run does not
hammer caselinker.up.railway.app (30/minute). Concurrent + burst tests are
opt-in via CASELINKER_SPARQL_LIVE_ALL=1 so they do not 429 the rest of this
file in the same window.

  CASELINKER_SPARQL_LIVE=1 pytest tests/test_sparql_live.py -q
  CASELINKER_SPARQL_LIVE=1 CASELINKER_SPARQL_LIVE_ALL=1 pytest tests/test_sparql_live.py -q
"""

from __future__ import annotations

import json
import os
from collections import Counter

import pytest

httpx = pytest.importorskip("httpx")

LIVE = os.environ.get("CASELINKER_SPARQL_LIVE") == "1"
LIVE_ALL = os.environ.get("CASELINKER_SPARQL_LIVE_ALL") == "1"
URL = os.environ.get("CASELINKER_SPARQL_URL", "https://caselinker.up.railway.app/sparql")

pytestmark = pytest.mark.skipif(
    not LIVE,
    reason="set CASELINKER_SPARQL_LIVE=1 to hit production /sparql",
)

Q_JSON = {
    "Content-Type": "application/sparql-query",
    "Accept": "application/sparql-results+json",
}


@pytest.fixture(scope="module")
def client():
    with httpx.Client(timeout=httpx.Timeout(45.0, connect=10.0), follow_redirects=True) as c:
        yield c


def post(client: httpx.Client, query: str, headers: dict | None = None) -> httpx.Response:
    return client.post(URL, content=query.encode("utf-8"), headers=headers or Q_JSON)


def test_q1_platform_count_social_media_261(client):
    q = """PREFIX cac: <https://cacontology.projectvic.org#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?platform ?label (COUNT(DISTINCT ?case) AS ?cases)
WHERE {
  ?event cac:usesChannel ?platform .
  ?platform rdfs:label ?label .
  ?case a cac:CACInvestigation ; cac:hasStep ?event .
}
GROUP BY ?platform ?label
ORDER BY DESC(?cases)
LIMIT 8"""
    r = post(client, q)
    assert r.status_code == 200, r.text
    rows = r.json()["results"]["bindings"]
    social = next(
        b for b in rows if b["platform"]["value"].endswith("/social-media")
    )
    assert social["cases"]["value"] == "261"


def test_q3_named_graph_mega_encryption(client):
    q = """SELECT ?p ?o
WHERE {
  GRAPH <https://caselinker.up.railway.app/resource/case/nj_ag_2017_001> {
    <https://caselinker.up.railway.app/resource/platform/meganz> ?p ?o .
  }
}"""
    r = post(client, q)
    assert r.status_code == 200, r.text
    pairs = {(b["p"]["value"], b["o"]["value"]) for b in r.json()["results"]["bindings"]}
    assert any(
        p.endswith("encryptionLevel") and o == "end-to-end" for p, o in pairs
    )


@pytest.mark.parametrize(
    "query",
    [
        "INSERT DATA { <http://example.org/s> <http://example.org/p> <http://example.org/o> }",
        "DELETE DATA { <http://example.org/s> <http://example.org/p> <http://example.org/o> }",
        "LOAD <http://example.org/data.ttl>",
        "CLEAR ALL",
        "DROP ALL",
    ],
)
def test_update_verbs_405(client, query):
    r = post(client, query)
    assert r.status_code == 405, r.text
    assert "Update" in r.text


def test_update_content_type_405(client):
    r = client.post(
        URL,
        content=b"CLEAR ALL",
        headers={"Content-Type": "application/sparql-update"},
    )
    assert r.status_code == 405, r.text


def test_service_federation_400(client):
    r = post(
        client,
        "SELECT * WHERE { SERVICE <http://example.org/sparql> { ?s ?p ?o } }",
    )
    assert r.status_code == 400, r.text
    assert "SERVICE" in r.text


def test_unbounded_select_injects_limit_1000(client):
    r = post(client, "SELECT * WHERE { ?s ?p ?o }")
    assert r.status_code == 200, r.text
    assert len(r.json()["results"]["bindings"]) == 1000


def test_limit_50000_rejected(client):
    r = post(client, "SELECT * WHERE { ?s ?p ?o } LIMIT 50000")
    assert r.status_code == 400, r.text
    assert "10000" in r.text


def test_explicit_limit_10_untouched(client):
    r = post(client, "SELECT ?s WHERE { ?s ?p ?o } LIMIT 10")
    assert r.status_code == 200, r.text
    assert len(r.json()["results"]["bindings"]) == 10


def test_garbage_syntax_400(client):
    r = post(client, "this is not sparql at all ;;; !!!")
    assert r.status_code == 400, r.text
    assert r.status_code != 500


def test_empty_body_400(client):
    r = client.post(URL, content=b"", headers={"Content-Type": "application/sparql-query"})
    assert r.status_code == 400, r.text


def test_get_missing_query_400(client):
    r = client.get(URL)
    assert r.status_code == 400, r.text


def test_accept_json_is_valid_sparql_json(client):
    r = post(client, "SELECT ?s WHERE { ?s ?p ?o } LIMIT 2")
    assert r.status_code == 200, r.text
    assert "sparql-results+json" in r.headers.get("content-type", "")
    body = r.json()
    assert "results" in body


def test_no_accept_header_still_json(client):
    r = client.post(
        URL,
        content=b"SELECT ?s WHERE { ?s ?p ?o } LIMIT 2",
        headers={"Content-Type": "application/sparql-query"},
    )
    assert r.status_code == 200, r.text
    assert r.status_code < 500
    json.loads(r.text)


def test_unsupported_accept_not_500(client):
    r = client.post(
        URL,
        content=b"SELECT ?s WHERE { ?s ?p ?o } LIMIT 2",
        headers={
            "Content-Type": "application/sparql-query",
            "Accept": "application/vnd.caselinker.test+xml",
        },
    )
    assert r.status_code < 500, r.text
    assert r.status_code in (200, 406)


def test_construct_returns_turtle_graph(client):
    q = """PREFIX cac: <https://cacontology.projectvic.org#>
CONSTRUCT { ?s a cac:CACInvestigation }
WHERE { ?s a cac:CACInvestigation }
LIMIT 5"""
    r = client.post(
        URL,
        content=q.encode(),
        headers={"Content-Type": "application/sparql-query", "Accept": "text/turtle"},
    )
    assert r.status_code == 200, r.text
    assert "turtle" in r.headers.get("content-type", "")
    assert "CACInvestigation" in r.text


def test_ask_returns_boolean_true(client):
    r = post(
        client,
        "ASK { ?s a <https://cacontology.projectvic.org#CACInvestigation> }",
    )
    assert r.status_code == 200, r.text
    assert r.json()["boolean"] is True


@pytest.mark.skipif(not LIVE_ALL, reason="set CASELINKER_SPARQL_LIVE_ALL=1 (own rate-limit window)")
def test_concurrent_ten_distinct_queries(client):
    import asyncio

    queries = [
        "ASK { ?s ?p ?o }",
        "SELECT (COUNT(*) AS ?n) WHERE { ?s a <https://cacontology.projectvic.org#CACInvestigation> }",
        "SELECT ?id WHERE { ?s <http://purl.org/dc/terms/identifier> ?id } LIMIT 3",
        "ASK { GRAPH <https://caselinker.up.railway.app/resource/case/nj_ag_2017_001> { ?s ?p ?o } }",
        "SELECT ?l WHERE { <https://caselinker.up.railway.app/resource/platform/kik> <http://www.w3.org/2000/01/rdf-schema#label> ?l } LIMIT 1",
        "SELECT ?s WHERE { ?s a <https://cacontology.projectvic.org/multi-jurisdiction#FederalAgency> } LIMIT 2",
        "ASK { ?s <https://cacontology.projectvic.org#usesChannel> ?o }",
        "SELECT ?g WHERE { GRAPH ?g { ?s a <https://cacontology.projectvic.org#CACInvestigation> } } LIMIT 2",
        "CONSTRUCT { ?s a ?t } WHERE { ?s a ?t } LIMIT 1",
        "SELECT * WHERE { ?s ?p ?o } LIMIT 1",
    ]

    async def _run():
        async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=10.0)) as ac:
            async def one(q: str):
                return await ac.post(
                    URL,
                    content=q.encode(),
                    headers={
                        "Content-Type": "application/sparql-query",
                        "Accept": "application/sparql-results+json, text/turtle;q=0.8, */*;q=0.1",
                    },
                )

            return await asyncio.gather(*[one(q) for q in queries])

    responses = asyncio.run(_run())
    for r in responses:
        assert r.status_code == 200, r.text
        assert r.elapsed.total_seconds() < 30


@pytest.mark.skipif(not LIVE_ALL, reason="set CASELINKER_SPARQL_LIVE_ALL=1 (own rate-limit window)")
def test_rate_limit_burst_429s(client):
    import asyncio

    async def _run():
        async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=10.0)) as ac:
            async def one():
                return await ac.post(
                    URL,
                    content=b"ASK { ?s ?p ?o }",
                    headers=Q_JSON,
                )

            return await asyncio.gather(*[one() for _ in range(35)])

    responses = asyncio.run(_run())
    codes = Counter(r.status_code for r in responses)
    assert codes.get(200, 0) <= 30
    assert codes.get(429, 0) >= 1
    sample = next(r for r in responses if r.status_code == 429)
    assert "Traceback" not in sample.text
    body = sample.json()
    assert "error" in body or "detail" in body
