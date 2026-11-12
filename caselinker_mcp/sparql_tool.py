"""SPARQL query backends for the CaseLinker MCP ``sparql_query`` tool.

Backends
--------
- ``live`` — POST ``{CASELINKER_API_URL}/sparql`` (public Railway proxy → Oxigraph).
- ``oxigraph`` — POST ``{OXIGRAPH_URL|/query}`` or ``http://127.0.0.1:7878/query``
  (local RocksDB store under ``caselinker_oxigraph/``, not in-process N-Quads).
- ``nq`` — load a local N-Quads file into rdflib and evaluate in-process
  (fine for samples; full ~1 GB corpus prefers ``live`` or a local Oxigraph).
- ``auto`` — ``OXIGRAPH_URL`` if set, else local ``127.0.0.1:7878`` when reachable,
  else ``live``.

Policy (all backends): SPARQL 1.1 Query only; Update (INSERT/DELETE/LOAD/DROP/…)
and SERVICE rejected via ``prepare_sparql_query``. Default outer LIMIT 1000
(max 10_000). Default HTTP timeout 90s (clamped 1–600).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
import rdflib
from rdflib import BNode, Literal, URIRef
from rdflib.query import Result

from caselinker_mcp.client import BASE_URL

# Reuse the same Query-only policy as the public /sparql proxy (run/ on sys.path).
from sparql_proxy import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    SparqlRejected,
    prepare_sparql_query,
)

_DEFAULT_LOCAL_OXIGRAPH = "http://127.0.0.1:7878"
PUBLIC_SPARQL_URL = "https://caselinker.up.railway.app/sparql"
_CANCELLED_MARK = "operation has been cancelled"
_SCOPE_HINT = (
    "Each case is one named graph. Put the join inside GRAPH ?g { ... } so it "
    "stays within a case, start from a selective class, and aggregate with "
    "COUNT(DISTINCT ?g). Joins across the union default graph fan out over "
    "shared platform, agency and location nodes."
)
_DEFAULT_TIMEOUT_S = 90.0
_MIN_TIMEOUT_S = 1.0
_MAX_TIMEOUT_S = 600.0
_NQ_SOFT_MAX_BYTES = int(os.getenv("CASELINKER_NQ_SOFT_MAX_BYTES", str(250 * 1024 * 1024)))


def clamp_timeout_s(timeout_s: float) -> float:
    try:
        value = float(timeout_s)
    except (TypeError, ValueError):
        value = _DEFAULT_TIMEOUT_S
    return max(_MIN_TIMEOUT_S, min(_MAX_TIMEOUT_S, value))


def oxigraph_base(endpoint: str = "") -> str:
    raw = (endpoint or os.getenv("OXIGRAPH_URL", "") or _DEFAULT_LOCAL_OXIGRAPH).strip()
    return raw.rstrip("/")


def local_oxigraph_reachable(timeout: float = 0.35) -> bool:
    """True when a local Oxigraph answers ASK on /query (best-effort, sync)."""
    base = oxigraph_base()
    url = base if base.endswith("/query") else f"{base}/query"
    try:
        response = httpx.post(
            url,
            content=b"ASK { ?s ?p ?o }",
            headers={
                "Content-Type": "application/sparql-query",
                "Accept": "application/sparql-results+json",
            },
            timeout=timeout,
        )
        return response.status_code < 500
    except httpx.HTTPError:
        return False


def resolve_backend(backend: str) -> str:
    choice = (backend or "auto").strip().lower() or "auto"
    if choice == "auto":
        if os.getenv("OXIGRAPH_URL", "").strip():
            return "oxigraph"
        if local_oxigraph_reachable():
            return "oxigraph"
        return "live"
    if choice not in {"live", "oxigraph", "nq", "auto"}:
        raise ValueError(
            f"Unknown backend {backend!r}; use live, oxigraph, nq, or auto."
        )
    return choice

def live_sparql_url(endpoint: str = "") -> str:
    if endpoint.strip():
        return endpoint.strip().rstrip("/")
    return f"{BASE_URL.rstrip('/')}/sparql"


def default_nq_path(nq_path: str = "") -> Path:
    if nq_path.strip():
        return Path(nq_path).expanduser().resolve()
    env = os.getenv("CASELINKER_NQ", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    # Common local rebuild artifact (optional).
    home = Path.home() / "CaseLinker-backups" / "caselinker-2026-10-19-passage-pacer.nq"
    if home.is_file():
        return home
    raise FileNotFoundError(
        "No N-Quads path. Pass nq_path= or set CASELINKER_NQ to a .nq file."
    )


def _term_to_binding(term: Any) -> dict[str, str] | None:
    if term is None:
        return None
    if isinstance(term, URIRef):
        return {"type": "uri", "value": str(term)}
    if isinstance(term, BNode):
        return {"type": "bnode", "value": str(term)}
    if isinstance(term, Literal):
        cell: dict[str, str] = {"type": "literal", "value": str(term)}
        if term.datatype:
            cell["datatype"] = str(term.datatype)
        if term.language:
            cell["xml:lang"] = term.language
        return cell
    return {"type": "literal", "value": str(term)}


def _bindings_from_rdflib_result(result: Result) -> dict[str, Any]:
    """Build a SPARQL Results JSON dict from an rdflib SELECT Result."""
    vars_ = [str(v) for v in (result.vars or [])]
    bindings = []
    for row in result:
        item: dict[str, Any] = {}
        for name in vars_:
            try:
                term = row[name]
            except Exception:
                term = None
            cell = _term_to_binding(term)
            if cell is not None:
                item[name] = cell
        bindings.append(item)
    return {"head": {"vars": vars_}, "results": {"bindings": bindings}}


async def run_sparql(
    query: str,
    *,
    backend: str = "auto",
    endpoint: str = "",
    nq_path: str = "",
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    """Run a SPARQL 1.1 Query. Returns Results JSON plus ``backend`` / ``endpoint``."""
    text = (query or "").strip()
    if not text:
        return {"error": "query is required"}

    timeout_s = clamp_timeout_s(timeout_s)

    try:
        prepared = prepare_sparql_query(text)
    except SparqlRejected as exc:
        return {"error": exc.detail, "status_code": exc.status_code}

    try:
        chosen = resolve_backend(backend)
    except ValueError as exc:
        return {"error": str(exc)}

    meta = {
        "limit_injected": prepared.limit_injected,
        "outer_limit": prepared.outer_limit,
        "timeout_s": timeout_s,
        "default_limit": DEFAULT_LIMIT,
        "max_limit": MAX_LIMIT,
    }

    if chosen == "nq":
        out = await _run_nq(prepared.query, nq_path=nq_path, kind=prepared.kind)
        if isinstance(out, dict) and "error" not in out:
            out.update(meta)
        return out

    if chosen == "live":
        url = live_sparql_url(endpoint)
        out = await _run_http(
            url,
            prepared.query,
            timeout_s=timeout_s,
            backend="live",
            content_type="application/sparql-query",
        )
    else:
        # oxigraph Graph Store /query
        base = oxigraph_base(endpoint)
        url = base if base.endswith("/query") else f"{base}/query"
        out = await _run_http(
            url,
            prepared.query,
            timeout_s=timeout_s,
            backend="oxigraph",
            content_type="application/sparql-query",
        )
    if isinstance(out, dict) and "error" not in out:
        out.update(meta)
    elif isinstance(out, dict):
        out["timeout_s"] = timeout_s
    return out


async def _run_http(
    url: str,
    query: str,
    *,
    timeout_s: float,
    backend: str,
    content_type: str,
) -> dict[str, Any]:
    headers = {
        "Content-Type": content_type,
        "Accept": "application/sparql-results+json",
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s, connect=15.0)) as client:
            response = await client.post(url, content=query.encode("utf-8"), headers=headers)
    except httpx.HTTPError as exc:
        return {
            "error": f"SPARQL transport failed: {exc}",
            "backend": backend,
            "endpoint": url,
        }

    body_text = response.text
    payload: Any
    try:
        payload = response.json()
    except ValueError:
        # Oxigraph streams results: a query it stops mid-way arrives as HTTP 200
        # with half a JSON document. That is a failed query, not a result.
        if response.status_code < 400 and (
            _CANCELLED_MARK in body_text or body_text.lstrip().startswith('{"head"')
        ):
            return {
                "error": (
                    "The SPARQL store stopped the query before it finished "
                    "(timeout or cancel). No rows are returned; the partial "
                    "result is not usable."
                ),
                "hint": _SCOPE_HINT,
                "backend": backend,
                "endpoint": url,
                "status_code": response.status_code,
            }
        payload = {"raw": body_text[:4000]}

    if response.status_code >= 400:
        out = {
            "error": f"HTTP {response.status_code}",
            "detail": payload if isinstance(payload, dict) else body_text[:2000],
            "backend": backend,
            "endpoint": url,
            "status_code": response.status_code,
        }
        if response.status_code == 503 and "not configured" in body_text:
            out["hint"] = (
                "This API has no SPARQL store behind it. Start a local Oxigraph on "
                f"127.0.0.1:7878, or pass endpoint='{PUBLIC_SPARQL_URL}' to query "
                "the hosted corpus."
            )
        return out

    if isinstance(payload, dict):
        out = dict(payload)
        out["backend"] = backend
        out["endpoint"] = url
        # Cold-start envelope from CaseLinker /sparql
        if out.get("retry") or out.get("status") == "waking":
            out["note"] = "Oxigraph is waking; retry the same query shortly."
        return out
    return {"backend": backend, "endpoint": url, "data": payload}


async def _run_nq(query: str, *, nq_path: str, kind: str) -> dict[str, Any]:
    try:
        path = default_nq_path(nq_path)
    except FileNotFoundError as exc:
        return {"error": str(exc), "backend": "nq"}

    if not path.is_file():
        return {"error": f"N-Quads file not found: {path}", "backend": "nq"}

    size = path.stat().st_size
    if size > _NQ_SOFT_MAX_BYTES and not os.getenv("CASELINKER_NQ_ALLOW_LARGE", "").strip():
        return {
            "error": (
                f"N-Quads file is {size / 1024**2:.0f} MiB; in-process load is capped at "
                f"{_NQ_SOFT_MAX_BYTES / 1024**2:.0f} MiB. Use backend='live' or "
                f"backend='oxigraph', or set CASELINKER_NQ_ALLOW_LARGE=1."
            ),
            "backend": "nq",
            "nq_path": str(path),
            "size_bytes": size,
        }

    def _eval() -> dict[str, Any]:
        dataset = rdflib.Dataset()
        dataset.parse(path, format="nquads")
        result = dataset.query(query)
        # rdflib algebra names: SelectQuery, AskQuery, ConstructQuery, DescribeQuery
        if kind in {"ASK", "AskQuery"}:
            return {
                "head": {},
                "boolean": bool(result),
                "backend": "nq",
                "nq_path": str(path),
                "size_bytes": size,
            }
        if kind in {"SELECT", "SelectQuery"}:
            data = _bindings_from_rdflib_result(result)
            data["backend"] = "nq"
            data["nq_path"] = str(path)
            data["size_bytes"] = size
            return data
        # CONSTRUCT / DESCRIBE → Turtle snippet
        graph = getattr(result, "graph", None) or result
        turtle = graph.serialize(format="turtle")
        if isinstance(turtle, bytes):
            turtle = turtle.decode("utf-8")
        return {
            "backend": "nq",
            "nq_path": str(path),
            "size_bytes": size,
            "format": "text/turtle",
            "turtle": turtle,
        }

    try:
        import asyncio

        return await asyncio.to_thread(_eval)
    except Exception as exc:
        return {
            "error": f"Local N-Quads query failed: {exc}",
            "backend": "nq",
            "nq_path": str(path),
        }


def describe_backends() -> dict[str, Any]:
    """Helpful discovery payload for agents."""
    return {
        "backends": {
            "live": live_sparql_url(),
            "oxigraph": f"{oxigraph_base()}/query",
            "nq": os.getenv("CASELINKER_NQ") or "(pass nq_path= or set CASELINKER_NQ)",
            "auto": "OXIGRAPH_URL → local :7878 if up → live",
        },
        "default_api": BASE_URL,
        "policy": (
            "Query only (SELECT/CONSTRUCT/ASK/DESCRIBE); "
            "Update (INSERT/DELETE/LOAD/DROP/CLEAR/…) and SERVICE rejected."
        ),
        "default_limit": DEFAULT_LIMIT,
        "max_limit": MAX_LIMIT,
        "default_timeout_s": _DEFAULT_TIMEOUT_S,
        "timeout_clamp_s": [_MIN_TIMEOUT_S, _MAX_TIMEOUT_S],
        "local_store": "caselinker_oxigraph/ (see scripts/run/local_oxigraph.sh)",
    }
