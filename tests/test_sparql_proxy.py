"""SPARQL proxy policy: rdflib parser, not regex."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "run"
if str(RUN) not in sys.path:
    sys.path.insert(0, str(RUN))

from sparql_proxy import (  # noqa: E402
    DEFAULT_LIMIT,
    MAX_LIMIT,
    SparqlRejected,
    prepare_sparql_query,
)


def test_select_without_limit_appends_default():
    q = "SELECT ?s ?p ?o WHERE { ?s ?p ?o }"
    prepared = prepare_sparql_query(q)
    assert prepared.kind == "SelectQuery"
    assert prepared.limit_injected is True
    assert prepared.outer_limit == DEFAULT_LIMIT
    assert prepared.query.rstrip().endswith(f"LIMIT {DEFAULT_LIMIT}")
    # Original query is preserved; LIMIT is a new trailing clause.
    assert q in prepared.query


def test_existing_limit_under_max_is_kept():
    q = "SELECT ?s WHERE { ?s ?p ?o } LIMIT 25"
    prepared = prepare_sparql_query(q)
    assert prepared.limit_injected is False
    assert prepared.outer_limit == 25
    assert prepared.query == q.strip()


def test_limit_in_string_literal_is_not_an_outer_limit():
    q = 'SELECT ?s WHERE { ?s ?p "LIMIT 10" }'
    prepared = prepare_sparql_query(q)
    assert prepared.limit_injected is True
    assert prepared.outer_limit == DEFAULT_LIMIT


def test_limit_in_trailing_comment_is_not_an_outer_limit():
    q = "SELECT ?s WHERE { ?s ?p ?o } # LIMIT 10"
    prepared = prepare_sparql_query(q)
    assert prepared.limit_injected is True
    assert "\nLIMIT " in prepared.query


def test_subquery_limit_does_not_count_as_outer_limit():
    q = "SELECT * WHERE { { SELECT ?s WHERE { ?s ?p ?o } LIMIT 5 } }"
    prepared = prepare_sparql_query(q)
    assert prepared.limit_injected is True
    assert prepared.outer_limit == DEFAULT_LIMIT


def test_offset_only_gets_default_limit():
    q = "SELECT ?s WHERE { ?s ?p ?o } OFFSET 5"
    prepared = prepare_sparql_query(q)
    assert prepared.limit_injected is True
    assert prepared.query.rstrip().endswith(f"LIMIT {DEFAULT_LIMIT}")


def test_oversized_outer_limit_rejected():
    q = f"SELECT ?s WHERE {{ ?s ?p ?o }} LIMIT {MAX_LIMIT + 1}"
    with pytest.raises(SparqlRejected) as exc:
        prepare_sparql_query(q)
    assert exc.value.status_code == 400
    assert str(MAX_LIMIT) in exc.value.detail


def test_update_insert_rejected():
    with pytest.raises(SparqlRejected) as exc:
        prepare_sparql_query("INSERT DATA { <http://ex.org/s> <http://ex.org/p> <http://ex.org/o> }")
    assert exc.value.status_code == 405
    assert "Update" in exc.value.detail


def test_update_clear_rejected():
    with pytest.raises(SparqlRejected) as exc:
        prepare_sparql_query("CLEAR ALL")
    assert exc.value.status_code == 405


def test_service_rejected():
    q = "SELECT * WHERE { SERVICE <http://example.org/sparql> { ?s ?p ?o } }"
    with pytest.raises(SparqlRejected) as exc:
        prepare_sparql_query(q)
    assert exc.value.status_code == 400
    assert "SERVICE" in exc.value.detail


def test_ask_does_not_inject_limit():
    q = "ASK { ?s ?p ?o }"
    prepared = prepare_sparql_query(q)
    assert prepared.kind == "AskQuery"
    assert prepared.limit_injected is False
    assert "LIMIT" not in prepared.query


def test_construct_without_limit_injects():
    q = "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }"
    prepared = prepare_sparql_query(q)
    assert prepared.kind == "ConstructQuery"
    assert prepared.limit_injected is True


def test_syntax_error():
    with pytest.raises(SparqlRejected) as exc:
        prepare_sparql_query("SELECT WHERE this is not sparql")
    assert exc.value.status_code == 400


def test_empty_query():
    with pytest.raises(SparqlRejected) as exc:
        prepare_sparql_query("  ")
    assert exc.value.status_code == 400
