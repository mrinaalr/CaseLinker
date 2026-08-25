"""SPARQL Query policy for the public /sparql proxy.

Uses rdflib's SPARQL parser (parseQuery / parseUpdate / algebra), not regex,
to classify queries, reject Update and SERVICE, and decide LIMIT injection.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from rdflib.plugins.sparql.algebra import translateQuery
from rdflib.plugins.sparql.parser import parseQuery, parseUpdate
from rdflib.plugins.sparql.parserutils import CompValue

DEFAULT_LIMIT = 1000
MAX_LIMIT = 10_000

_LIMITABLE = frozenset({"SelectQuery", "ConstructQuery", "DescribeQuery"})

_UPDATE_REJECTED = (
    "SPARQL Update is not allowed on this endpoint. "
    "Submit a SPARQL 1.1 Query (SELECT, CONSTRUCT, ASK, or DESCRIBE)."
)
_SERVICE_REJECTED = (
    "SPARQL SERVICE (federation) is not allowed on this endpoint."
)
_LIMIT_TOO_LARGE = (
    "LIMIT {limit} exceeds the maximum of {max_limit}. "
    "Resubmit with LIMIT {max_limit} or lower."
)
_ALGEBRA_FAILED = (
    "Could not compile SPARQL query: {err}"
)

# SPARQL 1.1 Query ::= Prologue (SelectQuery|ConstructQuery|DescribeQuery|AskQuery) ValuesClause
# SelectQuery     ::= SelectClause DatasetClause* WhereClause SolutionModifier
# SolutionModifier ::= GroupClause? HavingClause? OrderClause? LimitOffsetClauses?
# ValuesClause    ::= ( 'VALUES' DataBlock )?
# LimitOffset     ::= Limit Offset? | Offset Limit?
#
# So the only legal place for a new LIMIT is after GROUP/HAVING/ORDER/OFFSET
# and before a query-level VALUES. Appending after VALUES is a syntax error.


class SparqlRejected(Exception):
    """Query rejected by policy (Update, SERVICE, oversized LIMIT, or parse error)."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class PreparedSparql:
    query: str
    kind: str
    limit_injected: bool
    outer_limit: Optional[int]


def prepare_sparql_query(
    query: str,
    *,
    default_limit: int = DEFAULT_LIMIT,
    max_limit: int = MAX_LIMIT,
) -> PreparedSparql:
    """Parse *query*, enforce policy, and return SPARQL text safe to forward.

    LIMIT handling is parser-driven:
    - Outer LIMIT is read from the rdflib parse tree (``limitoffset``), which
      ignores LIMIT clauses inside subqueries.
    - If a SELECT/CONSTRUCT/DESCRIBE has no outer LIMIT, ``LIMIT {default_limit}``
      is inserted immediately before a query-level VALUES clause when one is
      present (SPARQL 1.1: LimitOffset before ValuesClause). Otherwise it is
      appended. Insertion is gated by the parse tree, not a regex search for
      the word LIMIT. A brace/string-aware scan finds the query-level VALUES
      token so inline VALUES inside WHERE is not used as the splice point.
    - If an outer LIMIT is present and exceeds *max_limit*, the query is rejected
      (400) rather than rewritten.
    ASK queries are not given a LIMIT.
    """
    text = (query or "").strip()
    if not text:
        raise SparqlRejected(400, "Missing SPARQL query.")

    parsed = _parse_query_or_reject_update(text)
    qpart = parsed[1]
    kind = str(qpart.name)

    try:
        algebra = translateQuery(parsed).algebra
        has_service = _algebra_has_service(algebra)
    except SparqlRejected:
        raise
    except Exception as exc:
        raise SparqlRejected(400, _ALGEBRA_FAILED.format(err=exc)) from exc

    if has_service:
        raise SparqlRejected(400, _SERVICE_REJECTED)

    outer_limit = _outer_limit(qpart)
    limit_injected = False
    out = text

    if kind in _LIMITABLE:
        if outer_limit is None:
            out = _inject_default_limit(text, qpart, int(default_limit))
            try:
                parseQuery(out)
            except Exception as exc:
                raise SparqlRejected(
                    400,
                    f"Failed to apply default LIMIT to parsed query: {exc}",
                ) from exc
            limit_injected = True
            outer_limit = int(default_limit)
        elif outer_limit > max_limit:
            raise SparqlRejected(
                400,
                _LIMIT_TOO_LARGE.format(limit=outer_limit, max_limit=max_limit),
            )

    return PreparedSparql(
        query=out,
        kind=kind,
        limit_injected=limit_injected,
        outer_limit=outer_limit,
    )


def _inject_default_limit(text: str, qpart: CompValue, default_limit: int) -> str:
    clause = f"LIMIT {int(default_limit)}"
    if "valuesClause" in qpart:
        idx = _query_level_values_index(text)
        if idx is None:
            raise SparqlRejected(
                400,
                "Parsed query has a VALUES clause but its source position "
                "could not be located for LIMIT injection.",
            )
        return text[:idx].rstrip() + f"\n{clause}\n" + text[idx:]
    return text.rstrip() + f"\n{clause}"


def _query_level_values_index(text: str) -> Optional[int]:
    """Start index of the query-level VALUES keyword, or None.

    Query-level VALUES is at brace-depth 0. Inline VALUES inside WHERE is
    ignored. IRIs, quoted strings, and ``#`` comments are skipped so a
    ``VALUES`` substring in those contexts is not treated as the keyword.
    """
    i = 0
    n = len(text)
    depth = 0
    found: Optional[int] = None
    while i < n:
        ch = text[i]
        if ch == "#":
            while i < n and text[i] not in "\n\r":
                i += 1
            continue
        if ch == "<":
            i += 1
            while i < n and text[i] != ">":
                i += 1
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            # Long-string quotes ''' / """
            long_q = text[i : i + 3] == quote * 3
            i += 3 if long_q else 1
            closer = quote * 3 if long_q else quote
            while i < n:
                if text.startswith(closer, i):
                    i += len(closer)
                    break
                if text[i] == "\\" and not long_q:
                    i += 2
                    continue
                i += 1
            continue
        if ch == "{":
            depth += 1
            i += 1
            continue
        if ch == "}":
            depth = max(0, depth - 1)
            i += 1
            continue
        if depth == 0 and _keyword_at(text, i, "VALUES"):
            found = i
            i += 6
            continue
        i += 1
    return found


def _keyword_at(text: str, i: int, word: str) -> bool:
    end = i + len(word)
    if end > len(text) or text[i:end].upper() != word.upper():
        return False
    if i > 0 and (text[i - 1].isalnum() or text[i - 1] == "_"):
        return False
    if end < len(text) and (text[end].isalnum() or text[end] == "_"):
        return False
    return True


def _parse_query_or_reject_update(text: str):
    try:
        return parseQuery(text)
    except Exception as query_err:
        try:
            parseUpdate(text)
        except Exception:
            raise SparqlRejected(
                400,
                f"Could not parse SPARQL query: {query_err}",
            ) from query_err
        raise SparqlRejected(405, _UPDATE_REJECTED) from query_err


def _outer_limit(qpart: CompValue) -> Optional[int]:
    """Return the outer-query LIMIT from the parse tree, or None if absent.

    Subquery LIMIT clauses live inside ``where`` and are not on this node.
    """
    if "limitoffset" not in qpart:
        return None
    lo = qpart["limitoffset"]
    if not isinstance(lo, CompValue) or "limit" not in lo:
        return None
    return int(lo["limit"])


def sparql_cors_allow_origin(origin: Optional[str]) -> Optional[str]:
    """Return the origin to echo for /sparql, or None to omit CORS headers.

    Agents, curl, and MCP servers do not use CORS. Browser SPARQL UIs hosted
    off-origin (e.g. YASGUI) will be blocked; that is intentional.
    Extra origins can be added via SPARQL_CORS_ORIGINS (comma-separated).
    """
    if not origin:
        return None
    extra = {
        o.strip()
        for o in os.environ.get("SPARQL_CORS_ORIGINS", "").split(",")
        if o.strip()
    }
    allowed = {
        "https://caselinker.up.railway.app",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        *extra,
    }
    return origin if origin in allowed else None


def _algebra_has_service(node: object) -> bool:
    if isinstance(node, CompValue):
        if node.name == "ServiceGraphPattern":
            return True
        return any(_algebra_has_service(v) for v in node.values())
    if isinstance(node, (list, tuple)):
        return any(_algebra_has_service(v) for v in node)
    return False
