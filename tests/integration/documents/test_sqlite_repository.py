from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from caselinker.documents.models import SourceDocument, SourceDocumentVersion
from caselinker.documents.ports import (
    ImmutableConflictError,
    InsertOutcome,
    MissingDocumentError,
)
from caselinker.documents.sqlite_repository import SQLiteDocumentRepository, apply_migration

NOW = datetime(2026, 8, 15, 8, 0, tzinfo=UTC)
MIGRATION = Path("migrations/sqlite/0001_source_documents.sql")


@pytest.fixture
def connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    apply_migration(connection, MIGRATION.read_text(encoding="utf-8"))
    yield connection
    connection.close()


@pytest.fixture
def repository(connection: sqlite3.Connection) -> SQLiteDocumentRepository:
    return SQLiteDocumentRepository(connection)


def _document(**changes: object) -> SourceDocument:
    document = SourceDocument(
        document_id="doc_example_001",
        source_id="doj_ceos",
        canonical_url="https://www.justice.gov/example/1",
        canonicalization_version="2",
        document_type="press_release",
        recorded_at=NOW,
    )
    return replace(document, **changes)


def _version(**changes: object) -> SourceDocumentVersion:
    version = SourceDocumentVersion.capture(
        version_id="docv_example_001",
        document_id="doc_example_001",
        content=b"retrieved public fixture",
        retrieved_at=NOW,
        published_at=NOW - timedelta(days=2),
        recorded_at=NOW + timedelta(seconds=1),
        mime_type="text/html",
        http_status=200,
        http_etag='"fixture"',
        http_last_modified=NOW - timedelta(days=1),
        parser_name="trafilatura",
        parser_version="2.0.0",
        normalized_text="Retrieved public fixture",
    )
    return replace(version, **changes)


def test_migration_is_idempotent(connection: sqlite3.Connection) -> None:
    apply_migration(connection, MIGRATION.read_text(encoding="utf-8"))

    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    assert {"source_documents", "source_document_versions"}.issubset(tables)


def test_migration_preserves_representative_legacy_table() -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE cases (id TEXT PRIMARY KEY, source_url TEXT, raw_data TEXT)")
    legacy_row = (
        "legacy-case-1",
        "https://example.org/legacy",
        '{"source_file":"legacy.pdf"}',
    )
    connection.execute("INSERT INTO cases VALUES (?, ?, ?)", legacy_row)
    columns_before = connection.execute("PRAGMA table_info(cases)").fetchall()

    apply_migration(connection, MIGRATION.read_text(encoding="utf-8"))

    assert connection.execute("SELECT * FROM cases").fetchall() == [legacy_row]
    assert connection.execute("PRAGMA table_info(cases)").fetchall() == columns_before
    connection.close()


def test_document_insert_and_exact_retry_are_idempotent(
    repository: SQLiteDocumentRepository,
) -> None:
    document = _document()

    assert repository.add_document(document) is InsertOutcome.CREATED
    assert repository.add_document(document) is InsertOutcome.EXISTING
    assert repository.get_document(document.document_id) == document
    assert repository.get_document("doc_missing_001") is None


def test_document_id_cannot_be_reused(repository: SQLiteDocumentRepository) -> None:
    repository.add_document(_document())

    with pytest.raises(ImmutableConflictError, match="different metadata"):
        repository.add_document(_document(source_id="ncmec"))


def test_canonical_url_cannot_identify_two_documents(
    repository: SQLiteDocumentRepository,
) -> None:
    repository.add_document(_document())

    with pytest.raises(ImmutableConflictError, match="already belongs"):
        repository.add_document(_document(document_id="doc_example_002"))


def test_unexpected_document_constraint_is_mapped_to_repository_error(
    connection: sqlite3.Connection,
    repository: SQLiteDocumentRepository,
) -> None:
    connection.executescript(
        """
        CREATE TRIGGER reject_document_insert
        BEFORE INSERT ON source_documents
        BEGIN
            SELECT RAISE(ABORT, 'fixture rejection');
        END;
        """
    )

    with pytest.raises(ImmutableConflictError, match="database constraint"):
        repository.add_document(_document())


def test_version_requires_document_identity(repository: SQLiteDocumentRepository) -> None:
    with pytest.raises(MissingDocumentError, match="must exist"):
        repository.add_version(_version())


def test_version_round_trip_and_exact_retry_are_idempotent(
    repository: SQLiteDocumentRepository,
) -> None:
    document = _document()
    version = _version()
    repository.add_document(document)

    assert repository.add_version(version) is InsertOutcome.CREATED
    assert repository.add_version(version) is InsertOutcome.EXISTING
    assert repository.get_version(version.version_id) == version
    assert repository.get_version("docv_missing_001") is None


def test_version_id_cannot_be_reused(repository: SQLiteDocumentRepository) -> None:
    repository.add_document(_document())
    repository.add_version(_version())

    with pytest.raises(ImmutableConflictError, match="different bytes or metadata"):
        repository.add_version(_version(http_etag='"changed"'))


def test_unexpected_version_constraint_is_mapped_to_repository_error(
    connection: sqlite3.Connection,
    repository: SQLiteDocumentRepository,
) -> None:
    repository.add_document(_document())
    connection.executescript(
        """
        CREATE TRIGGER reject_version_insert
        BEFORE INSERT ON source_document_versions
        BEGIN
            SELECT RAISE(ABORT, 'fixture rejection');
        END;
        """
    )

    with pytest.raises(ImmutableConflictError, match="database constraint"):
        repository.add_version(_version())


def test_versions_are_returned_in_retrieval_order(
    repository: SQLiteDocumentRepository,
) -> None:
    repository.add_document(_document())
    later = _version(version_id="docv_example_002", retrieved_at=NOW + timedelta(days=1))
    earlier = _version()
    repository.add_version(later)
    repository.add_version(earlier)

    assert repository.list_versions("doc_example_001") == (earlier, later)
    assert repository.list_versions("doc_missing_001") == ()


@pytest.mark.parametrize("table", ["source_documents", "source_document_versions"])
def test_database_triggers_reject_updates_and_deletes(
    connection: sqlite3.Connection,
    repository: SQLiteDocumentRepository,
    table: str,
) -> None:
    repository.add_document(_document())
    repository.add_version(_version())
    identity_column = "document_id" if table == "source_documents" else "version_id"
    identity = "doc_example_001" if table == "source_documents" else "docv_example_001"

    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute(
            f"UPDATE {table} SET {identity_column} = {identity_column} WHERE {identity_column} = ?",
            (identity,),
        )
    connection.rollback()

    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute(f"DELETE FROM {table} WHERE {identity_column} = ?", (identity,))
    connection.rollback()


def test_database_rejects_non_content_addressed_storage_key(
    connection: sqlite3.Connection,
    repository: SQLiteDocumentRepository,
) -> None:
    repository.add_document(_document())
    version = _version()

    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint"):
        connection.execute(
            """
            INSERT INTO source_document_versions (
                version_id, document_id, content_sha256, byte_length, storage_key,
                retrieved_at, recorded_at, mime_type, http_status, parser_name, parser_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                version.version_id,
                version.document_id,
                version.content_sha256,
                version.byte_length,
                "mutable/location",
                "2026-08-15T08:00:00.000000Z",
                "2026-08-15T08:00:01.000000Z",
                version.mime_type,
                version.http_status,
                version.parser_name,
                version.parser_version,
            ),
        )


def test_database_foreign_key_rejects_orphan_version(
    connection: sqlite3.Connection,
) -> None:
    version = _version(document_id="doc_missing_001")

    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint"):
        connection.execute(
            """
            INSERT INTO source_document_versions (
                version_id, document_id, content_sha256, byte_length, storage_key,
                retrieved_at, recorded_at, mime_type, http_status, parser_name, parser_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                version.version_id,
                version.document_id,
                version.content_sha256,
                version.byte_length,
                version.storage_key,
                "2026-08-15T08:00:00.000000Z",
                "2026-08-15T08:00:01.000000Z",
                version.mime_type,
                version.http_status,
                version.parser_name,
                version.parser_version,
            ),
        )
