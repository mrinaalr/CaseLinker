"""SQLite reference adapter for the immutable document repository port."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from caselinker.documents.models import (
    SourceDocument,
    SourceDocumentVersion,
    canonical_utc,
    parse_canonical_utc,
)
from caselinker.documents.ports import (
    ImmutableConflictError,
    InsertOutcome,
    MissingDocumentError,
)

DOCUMENT_COLUMNS = """
document_id, source_id, canonical_url, canonicalization_version, document_type, recorded_at
"""
VERSION_COLUMNS = """
version_id, document_id, content_sha256, byte_length, storage_key,
retrieved_at, published_at, recorded_at, mime_type, http_status, http_etag,
http_last_modified, parser_name, parser_version, normalized_text_sha256
"""


def apply_migration(connection: sqlite3.Connection, sql: str) -> None:
    """Apply an idempotent SQLite migration and enable referential integrity."""
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(sql)


def _optional_timestamp(value: object) -> datetime | None:
    return parse_canonical_utc(str(value)) if value is not None else None


def _document_from_row(row: tuple[object, ...]) -> SourceDocument:
    return SourceDocument(
        document_id=str(row[0]),
        source_id=str(row[1]),
        canonical_url=str(row[2]),
        canonicalization_version=str(row[3]),
        document_type=str(row[4]),
        recorded_at=parse_canonical_utc(str(row[5])),
    )


def _version_from_row(row: tuple[object, ...]) -> SourceDocumentVersion:
    return SourceDocumentVersion(
        version_id=str(row[0]),
        document_id=str(row[1]),
        content_sha256=str(row[2]),
        byte_length=int(str(row[3])),
        storage_key=str(row[4]),
        retrieved_at=parse_canonical_utc(str(row[5])),
        published_at=_optional_timestamp(row[6]),
        recorded_at=parse_canonical_utc(str(row[7])),
        mime_type=str(row[8]),
        http_status=int(str(row[9])),
        http_etag=str(row[10]) if row[10] is not None else None,
        http_last_modified=_optional_timestamp(row[11]),
        parser_name=str(row[12]),
        parser_version=str(row[13]),
        normalized_text_sha256=str(row[14]) if row[14] is not None else None,
    )


class SQLiteDocumentRepository:
    """Fail-closed, idempotent persistence for document identities and versions."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._connection.execute("PRAGMA foreign_keys = ON")

    def add_document(self, document: SourceDocument) -> InsertOutcome:
        existing = self.get_document(document.document_id)
        if existing is not None:
            if existing == document:
                return InsertOutcome.EXISTING
            raise ImmutableConflictError(
                f"document_id {document.document_id} already identifies different metadata"
            )

        conflicting_url = self._connection.execute(
            f"SELECT {DOCUMENT_COLUMNS} FROM source_documents WHERE canonical_url = ?",
            (document.canonical_url,),
        ).fetchone()
        if conflicting_url is not None:
            identified = _document_from_row(conflicting_url)
            raise ImmutableConflictError(
                f"canonical_url already belongs to document_id {identified.document_id}"
            )

        try:
            with self._connection:
                self._connection.execute(
                    """
                    INSERT INTO source_documents (
                        document_id, source_id, canonical_url, canonicalization_version,
                        document_type, recorded_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document.document_id,
                        document.source_id,
                        document.canonical_url,
                        document.canonicalization_version,
                        document.document_type,
                        canonical_utc(document.recorded_at),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            current = self.get_document(document.document_id)
            if current == document:
                return InsertOutcome.EXISTING
            raise ImmutableConflictError(
                "document identity violated a database constraint"
            ) from exc
        return InsertOutcome.CREATED

    def get_document(self, document_id: str) -> SourceDocument | None:
        row = self._connection.execute(
            f"SELECT {DOCUMENT_COLUMNS} FROM source_documents WHERE document_id = ?",
            (document_id,),
        ).fetchone()
        return _document_from_row(row) if row is not None else None

    def add_version(self, version: SourceDocumentVersion) -> InsertOutcome:
        existing = self.get_version(version.version_id)
        if existing is not None:
            if existing == version:
                return InsertOutcome.EXISTING
            raise ImmutableConflictError(
                f"version_id {version.version_id} already identifies different bytes or metadata"
            )
        if self.get_document(version.document_id) is None:
            raise MissingDocumentError(
                f"document_id {version.document_id} must exist before adding a version"
            )

        try:
            with self._connection:
                self._connection.execute(
                    """
                    INSERT INTO source_document_versions (
                        version_id, document_id, content_sha256, byte_length, storage_key,
                        retrieved_at, published_at, recorded_at, mime_type, http_status,
                        http_etag, http_last_modified, parser_name, parser_version,
                        normalized_text_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        version.version_id,
                        version.document_id,
                        version.content_sha256,
                        version.byte_length,
                        version.storage_key,
                        canonical_utc(version.retrieved_at),
                        canonical_utc(version.published_at) if version.published_at else None,
                        canonical_utc(version.recorded_at),
                        version.mime_type,
                        version.http_status,
                        version.http_etag,
                        (
                            canonical_utc(version.http_last_modified)
                            if version.http_last_modified
                            else None
                        ),
                        version.parser_name,
                        version.parser_version,
                        version.normalized_text_sha256,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            current = self.get_version(version.version_id)
            if current == version:
                return InsertOutcome.EXISTING
            raise ImmutableConflictError("document version violated a database constraint") from exc
        return InsertOutcome.CREATED

    def get_version(self, version_id: str) -> SourceDocumentVersion | None:
        row = self._connection.execute(
            f"SELECT {VERSION_COLUMNS} FROM source_document_versions WHERE version_id = ?",
            (version_id,),
        ).fetchone()
        return _version_from_row(row) if row is not None else None

    def list_versions(self, document_id: str) -> tuple[SourceDocumentVersion, ...]:
        rows = self._connection.execute(
            f"""
            SELECT {VERSION_COLUMNS}
            FROM source_document_versions
            WHERE document_id = ?
            ORDER BY retrieved_at ASC, version_id ASC
            """,
            (document_id,),
        ).fetchall()
        return tuple(_version_from_row(row) for row in rows)
