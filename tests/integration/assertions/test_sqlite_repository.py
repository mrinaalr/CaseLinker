from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from caselinker.assertions.models import (
    Assertion,
    AssertionMethod,
    AssertionState,
    AssertionValue,
    Confidence,
    ConfidenceDimension,
    EvidenceReference,
    MethodFamily,
    Polarity,
    ReviewDecision,
    ReviewerRole,
    ReviewOutcome,
    SpanUnavailableReason,
    ValueKind,
)
from caselinker.assertions.ports import (
    AssertionConflictError,
    EvidenceMismatchError,
    LineageCycleError,
    MissingLineageError,
    ReviewChainError,
)
from caselinker.assertions.sqlite_repository import SQLiteAssertionRepository
from caselinker.documents.models import SourceDocument, SourceDocumentVersion
from caselinker.documents.ports import InsertOutcome
from caselinker.documents.sqlite_repository import SQLiteDocumentRepository, apply_migration

NOW = datetime(2026, 8, 15, 8, 0, tzinfo=UTC)
TEXT = "A synthetic public record referenced Example Platform in this fixture."
MIGRATION_1 = Path("migrations/sqlite/0001_source_documents.sql")
MIGRATION_2 = Path("migrations/sqlite/0002_assertion_ledger.sql")


@pytest.fixture
def connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    apply_migration(connection, MIGRATION_1.read_text(encoding="utf-8"))
    apply_migration(connection, MIGRATION_2.read_text(encoding="utf-8"))
    yield connection
    connection.close()


@pytest.fixture
def repository(connection: sqlite3.Connection) -> SQLiteAssertionRepository:
    _seed_document_version(connection)
    return SQLiteAssertionRepository(connection)


def _seed_document_version(connection: sqlite3.Connection) -> SourceDocumentVersion:
    documents = SQLiteDocumentRepository(connection)
    document = SourceDocument(
        document_id="doc_example_001",
        source_id="doj_ceos",
        canonical_url="https://example.org/public-record/1",
        canonicalization_version="2",
        document_type="press_release",
        recorded_at=NOW,
    )
    version = SourceDocumentVersion.capture(
        version_id="docv_example_001",
        document_id=document.document_id,
        content=TEXT.encode("utf-8"),
        retrieved_at=NOW,
        published_at=date_to_datetime(date(2026, 8, 14)),
        recorded_at=NOW,
        mime_type="text/plain",
        http_status=200,
        http_etag=None,
        http_last_modified=None,
        parser_name="identity",
        parser_version="1",
        normalized_text=TEXT,
    )
    documents.add_document(document)
    documents.add_version(version)
    return version


def date_to_datetime(value: date) -> datetime:
    return datetime(value.year, value.month, value.day, tzinfo=UTC)


def _evidence(**changes: object) -> EvidenceReference:
    start = TEXT.index("Example Platform")
    evidence = EvidenceReference.from_text(
        document_version_id="docv_example_001",
        normalized_text=TEXT,
        start_char=start,
        end_char=start + len("Example Platform"),
        page_number=1,
    )
    return replace(evidence, **changes)


def _assertion(**changes: object) -> Assertion:
    assertion = Assertion(
        assertion_id="asrt_example_001",
        subject_id="case_example_001",
        predicate="cac:platformReferenced",
        value=AssertionValue(ValueKind.ENTITY, "platform_example_001"),
        state=AssertionState.EXTRACTED,
        polarity=Polarity.AFFIRMED,
        valid_from=date(2026, 8, 1),
        valid_to=date(2026, 8, 15),
        method=AssertionMethod(
            family=MethodFamily.DETERMINISTIC_PATTERN,
            name="platform_reference",
            version="1.0.0",
            run_id="run_001",
            code_revision="75e19d9",
        ),
        confidence=Confidence(ConfidenceDimension.EXTRACTION, 980_000, "cal_fixture_1"),
        evidence=(_evidence(),),
        input_assertion_ids=(),
        supersedes_assertion_id=None,
        created_at=NOW,
    )
    return replace(assertion, **changes)


def _review(**changes: object) -> ReviewDecision:
    decision = ReviewDecision(
        decision_id="rvw_example_001",
        assertion_id="asrt_example_001",
        outcome=ReviewOutcome.ACCEPTED,
        reviewer_id="reviewer_example_001",
        reviewer_role=ReviewerRole.DOMAIN_REVIEWER,
        rationale="The synthetic evidence span supports the typed value.",
        decided_at=NOW + timedelta(minutes=1),
        supersedes_decision_id=None,
    )
    return replace(decision, **changes)


def _insert_review_raw(connection: sqlite3.Connection, decision: ReviewDecision) -> None:
    connection.execute(
        """
        INSERT INTO review_decisions (
            decision_id, assertion_id, outcome, reviewer_id, reviewer_role,
            rationale, decided_at, supersedes_decision_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            decision.decision_id,
            decision.assertion_id,
            decision.outcome.value,
            decision.reviewer_id,
            decision.reviewer_role.value,
            decision.rationale,
            decision.decided_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            decision.supersedes_decision_id,
        ),
    )


def test_migration_is_idempotent_and_preserves_prior_tables(
    connection: sqlite3.Connection,
) -> None:
    connection.execute("CREATE TABLE legacy_fixture (id TEXT PRIMARY KEY, value TEXT)")
    connection.execute("INSERT INTO legacy_fixture VALUES ('legacy-1', 'unchanged')")
    before = connection.execute("SELECT * FROM legacy_fixture").fetchall()

    apply_migration(connection, MIGRATION_2.read_text(encoding="utf-8"))

    assert connection.execute("SELECT * FROM legacy_fixture").fetchall() == before
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    assert {"assertions", "assertion_evidence", "assertion_inputs", "review_decisions"} <= tables


def test_source_assertion_round_trip_and_retry_are_idempotent(
    repository: SQLiteAssertionRepository,
) -> None:
    assertion = _assertion()

    assert repository.add_assertion(assertion) is InsertOutcome.CREATED
    assert repository.add_assertion(assertion) is InsertOutcome.EXISTING
    assert repository.get_assertion(assertion.assertion_id) == assertion
    assert repository.get_assertion("asrt_missing_001") is None


def test_empty_assertion_batch_is_a_no_op(repository: SQLiteAssertionRepository) -> None:
    assert repository.add_assertions(()) == ()


def test_batch_preserves_outcome_order_and_is_idempotent(
    repository: SQLiteAssertionRepository,
) -> None:
    existing = _assertion()
    created = _assertion(assertion_id="asrt_example_002")
    repository.add_assertion(existing)

    assert repository.add_assertions((existing, created)) == (
        InsertOutcome.EXISTING,
        InsertOutcome.CREATED,
    )
    assert repository.add_assertions((existing, created)) == (
        InsertOutcome.EXISTING,
        InsertOutcome.EXISTING,
    )


def test_batch_inserts_lineage_in_dependency_order(
    repository: SQLiteAssertionRepository,
) -> None:
    source = _assertion()
    derived = _assertion(
        assertion_id="asrt_derived_001",
        state=AssertionState.DERIVED,
        evidence=(),
        input_assertion_ids=(source.assertion_id,),
        confidence=None,
    )

    outcomes = repository.add_assertions((derived, source))

    assert outcomes == (InsertOutcome.CREATED, InsertOutcome.CREATED)
    assert repository.get_assertion(derived.assertion_id) == derived


def test_batch_rejects_duplicate_identity_without_writes(
    repository: SQLiteAssertionRepository,
) -> None:
    assertion = _assertion()

    with pytest.raises(AssertionConflictError, match="batch repeats"):
        repository.add_assertions((assertion, assertion))

    assert repository.get_assertion(assertion.assertion_id) is None


def test_batch_rejects_lineage_cycles_without_writes(
    repository: SQLiteAssertionRepository,
) -> None:
    first = _assertion(
        assertion_id="asrt_cycle_001",
        state=AssertionState.DERIVED,
        evidence=(),
        input_assertion_ids=("asrt_cycle_002",),
        confidence=None,
    )
    second = _assertion(
        assertion_id="asrt_cycle_002",
        state=AssertionState.DERIVED,
        evidence=(),
        input_assertion_ids=("asrt_cycle_001",),
        confidence=None,
    )

    with pytest.raises(LineageCycleError, match="lineage cycle"):
        repository.add_assertions((first, second))

    assert repository.get_assertion(first.assertion_id) is None
    assert repository.get_assertion(second.assertion_id) is None


def test_database_failure_rolls_back_entire_batch(
    connection: sqlite3.Connection,
    repository: SQLiteAssertionRepository,
) -> None:
    first = _assertion(assertion_id="asrt_batch_first_001")
    second = _assertion(assertion_id="asrt_batch_fail_001")
    connection.execute(
        """
        CREATE TRIGGER fail_selected_assertion
        BEFORE INSERT ON assertions
        WHEN NEW.assertion_id = 'asrt_batch_fail_001'
        BEGIN
            SELECT RAISE(ABORT, 'synthetic second-write failure');
        END
        """
    )

    with pytest.raises(AssertionConflictError, match="batch violated"):
        repository.add_assertions((first, second))

    assert repository.get_assertion(first.assertion_id) is None
    assert repository.get_assertion(second.assertion_id) is None


def test_unavailable_span_round_trips(repository: SQLiteAssertionRepository) -> None:
    unavailable = EvidenceReference(
        document_version_id="docv_example_001",
        basis_sha256=None,
        page_number=1,
        start_char=None,
        end_char=None,
        span_sha256=None,
        unavailable_reason=SpanUnavailableReason.PARSER_DID_NOT_PRESERVE_OFFSETS,
    )
    assertion = _assertion(assertion_id="asrt_example_002", evidence=(unavailable,))

    repository.add_assertion(assertion)

    assert repository.get_assertion(assertion.assertion_id) == assertion


def test_assertion_id_cannot_be_reused(repository: SQLiteAssertionRepository) -> None:
    repository.add_assertion(_assertion())

    with pytest.raises(AssertionConflictError, match="different content"):
        repository.add_assertion(_assertion(polarity=Polarity.NEGATED))


def test_missing_document_version_is_rejected(repository: SQLiteAssertionRepository) -> None:
    assertion = _assertion(evidence=(_evidence(document_version_id="docv_missing_001"),))

    with pytest.raises(MissingLineageError, match="document version lineage"):
        repository.add_assertion(assertion)
    assert repository.get_assertion(assertion.assertion_id) is None


def test_evidence_basis_must_match_document_version(
    repository: SQLiteAssertionRepository,
) -> None:
    assertion = _assertion(evidence=(_evidence(basis_sha256="0" * 64),))

    with pytest.raises(EvidenceMismatchError, match="normalized document text"):
        repository.add_assertion(assertion)


def test_missing_input_assertion_is_rejected(repository: SQLiteAssertionRepository) -> None:
    derived = _assertion(
        assertion_id="asrt_derived_001",
        state=AssertionState.DERIVED,
        evidence=(),
        input_assertion_ids=("asrt_missing_001",),
        confidence=None,
    )

    with pytest.raises(MissingLineageError, match="assertion lineage"):
        repository.add_assertion(derived)


def test_derived_lineage_round_trips_in_declared_order(
    repository: SQLiteAssertionRepository,
) -> None:
    first = _assertion()
    second = _assertion(assertion_id="asrt_example_002", polarity=Polarity.NEGATED)
    repository.add_assertion(first)
    repository.add_assertion(second)
    derived = _assertion(
        assertion_id="asrt_derived_001",
        state=AssertionState.DERIVED,
        value=AssertionValue(ValueKind.INTEGER, "2"),
        evidence=(),
        input_assertion_ids=(second.assertion_id, first.assertion_id),
        confidence=None,
    )

    repository.add_assertion(derived)

    assert repository.get_assertion(derived.assertion_id) == derived


def test_superseded_assertion_must_exist(repository: SQLiteAssertionRepository) -> None:
    assertion = _assertion(supersedes_assertion_id="asrt_missing_001")

    with pytest.raises(MissingLineageError, match="assertion lineage"):
        repository.add_assertion(assertion)


def test_first_review_round_trip_and_retry_are_idempotent(
    repository: SQLiteAssertionRepository,
) -> None:
    repository.add_assertion(_assertion())
    decision = _review()

    assert repository.add_review_decision(decision) is InsertOutcome.CREATED
    assert repository.add_review_decision(decision) is InsertOutcome.EXISTING
    assert repository.list_review_decisions(decision.assertion_id) == (decision,)
    assert repository.current_review_decision(decision.assertion_id) == decision


def test_review_requires_assertion(repository: SQLiteAssertionRepository) -> None:
    with pytest.raises(MissingLineageError, match="must exist before review"):
        repository.add_review_decision(_review(assertion_id="asrt_missing_001"))


def test_review_id_cannot_be_reused(repository: SQLiteAssertionRepository) -> None:
    repository.add_assertion(_assertion())
    repository.add_review_decision(_review())

    with pytest.raises(AssertionConflictError, match="different review"):
        repository.add_review_decision(_review(outcome=ReviewOutcome.REJECTED))


def test_first_review_cannot_claim_supersession(repository: SQLiteAssertionRepository) -> None:
    repository.add_assertion(_assertion())

    with pytest.raises(ReviewChainError, match="first review"):
        repository.add_review_decision(_review(supersedes_decision_id="rvw_missing_001"))


def test_review_history_is_linear_and_monotonic(repository: SQLiteAssertionRepository) -> None:
    repository.add_assertion(_assertion())
    first = _review()
    repository.add_review_decision(first)
    second = _review(
        decision_id="rvw_example_002",
        outcome=ReviewOutcome.NEEDS_CHANGES,
        decided_at=NOW + timedelta(minutes=2),
        supersedes_decision_id=first.decision_id,
    )

    repository.add_review_decision(second)

    assert repository.list_review_decisions(first.assertion_id) == (first, second)
    assert repository.current_review_decision(first.assertion_id) == second


def test_review_must_supersede_current_head(repository: SQLiteAssertionRepository) -> None:
    repository.add_assertion(_assertion())
    repository.add_review_decision(_review())

    with pytest.raises(ReviewChainError, match="must supersede current"):
        repository.add_review_decision(
            _review(decision_id="rvw_example_002", supersedes_decision_id=None)
        )


def test_review_time_must_advance(repository: SQLiteAssertionRepository) -> None:
    repository.add_assertion(_assertion())
    first = _review()
    repository.add_review_decision(first)

    with pytest.raises(ReviewChainError, match="advance monotonically"):
        repository.add_review_decision(
            _review(
                decision_id="rvw_example_002",
                decided_at=first.decided_at,
                supersedes_decision_id=first.decision_id,
            )
        )


def test_database_allows_only_one_review_root(
    connection: sqlite3.Connection,
    repository: SQLiteAssertionRepository,
) -> None:
    repository.add_assertion(_assertion())
    repository.add_review_decision(_review())

    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint"):
        _insert_review_raw(
            connection,
            _review(decision_id="rvw_example_002", decided_at=NOW + timedelta(minutes=2)),
        )


def test_database_prevents_review_forks(
    connection: sqlite3.Connection,
    repository: SQLiteAssertionRepository,
) -> None:
    repository.add_assertion(_assertion())
    first = _review()
    repository.add_review_decision(first)
    second = _review(
        decision_id="rvw_example_002",
        decided_at=NOW + timedelta(minutes=2),
        supersedes_decision_id=first.decision_id,
    )
    repository.add_review_decision(second)

    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint"):
        _insert_review_raw(
            connection,
            _review(
                decision_id="rvw_example_003",
                decided_at=NOW + timedelta(minutes=3),
                supersedes_decision_id=first.decision_id,
            ),
        )


def test_database_rejects_cross_assertion_review_supersession(
    connection: sqlite3.Connection,
    repository: SQLiteAssertionRepository,
) -> None:
    repository.add_assertion(_assertion())
    repository.add_assertion(_assertion(assertion_id="asrt_example_002"))
    first = _review()
    repository.add_review_decision(first)

    with pytest.raises(sqlite3.IntegrityError, match="within one assertion"):
        _insert_review_raw(
            connection,
            _review(
                decision_id="rvw_example_002",
                assertion_id="asrt_example_002",
                decided_at=NOW + timedelta(minutes=2),
                supersedes_decision_id=first.decision_id,
            ),
        )


def test_database_enforces_monotonic_review_time(
    connection: sqlite3.Connection,
    repository: SQLiteAssertionRepository,
) -> None:
    repository.add_assertion(_assertion())
    first = _review()
    repository.add_review_decision(first)

    with pytest.raises(sqlite3.IntegrityError, match="advance monotonically"):
        _insert_review_raw(
            connection,
            _review(
                decision_id="rvw_example_002",
                decided_at=first.decided_at,
                supersedes_decision_id=first.decision_id,
            ),
        )


def test_empty_review_history_has_no_current_decision(
    repository: SQLiteAssertionRepository,
) -> None:
    assert repository.list_review_decisions("asrt_missing_001") == ()
    assert repository.current_review_decision("asrt_missing_001") is None


@pytest.mark.parametrize(
    ("table", "identity_column"),
    [
        ("assertions", "assertion_id"),
        ("assertion_evidence", "assertion_id"),
        ("review_decisions", "decision_id"),
    ],
)
def test_database_rejects_mutation_and_deletion(
    connection: sqlite3.Connection,
    repository: SQLiteAssertionRepository,
    table: str,
    identity_column: str,
) -> None:
    repository.add_assertion(_assertion())
    repository.add_review_decision(_review())
    identity = "rvw_example_001" if table == "review_decisions" else "asrt_example_001"

    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute(
            f"UPDATE {table} SET {identity_column} = {identity_column} WHERE {identity_column} = ?",
            (identity,),
        )
    connection.rollback()

    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute(f"DELETE FROM {table} WHERE {identity_column} = ?", (identity,))
    connection.rollback()


def test_input_edges_are_immutable(
    connection: sqlite3.Connection,
    repository: SQLiteAssertionRepository,
) -> None:
    source = _assertion()
    repository.add_assertion(source)
    derived = _assertion(
        assertion_id="asrt_derived_001",
        state=AssertionState.DERIVED,
        evidence=(),
        input_assertion_ids=(source.assertion_id,),
        confidence=None,
    )
    repository.add_assertion(derived)

    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute(
            "DELETE FROM assertion_inputs WHERE assertion_id = ?",
            (derived.assertion_id,),
        )
