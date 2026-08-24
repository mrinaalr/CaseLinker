"""SPARQL Query policy for the public /sparql proxy.

Uses rdflib's SPARQL parser (parseQuery / parseUpdate / algebra), not regex,
to classify queries, reject Update and SERVICE, and decide LIMIT injection.
"""

from __future__ import annotations

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
      is appended after the parser confirms it is missing. rdflib has no SPARQL
      serializer, so injection is a clause append gated by that parse — not a
      regex search for the word LIMIT.
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

    algebra = translateQuery(parsed).algebra
    if _algebra_has_service(algebra):
        raise SparqlRejected(400, _SERVICE_REJECTED)

    outer_limit = _outer_limit(qpart)
    limit_injected = False
    out = text

    if kind in _LIMITABLE:
        if outer_limit is None:
            out = text.rstrip() + f"\nLIMIT {int(default_limit)}"
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


def _algebra_has_service(node: object) -> bool:
    if isinstance(node, CompValue):
        if node.name == "ServiceGraphPattern":
            return True
        return any(_algebra_has_service(v) for v in node.values())
    if isinstance(node, (list, tuple)):
        return any(_algebra_has_service(v) for v in node)
    return False
