from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from caselinker.assertions.sqlite_repository import SQLiteAssertionRepository
from caselinker.documents.models import SourceDocument, SourceDocumentVersion
from caselinker.documents.ports import InsertOutcome
from caselinker.documents.sqlite_repository import SQLiteDocumentRepository, apply_migration
from caselinker.extraction import (
    ExtractionRun,
    PlatformMentionExtractor,
    PlatformMentionPipeline,
)

NOW = datetime(2026, 8, 15, 10, 0, tzinfo=UTC)
TEXT = "The public record named Snapchat and Discord."
MIGRATIONS = (
    Path("migrations/sqlite/0001_source_documents.sql"),
    Path("migrations/sqlite/0002_assertion_ledger.sql"),
)


def test_document_to_candidate_ledger_is_exact_and_idempotent() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        for migration in MIGRATIONS:
            apply_migration(connection, migration.read_text(encoding="utf-8"))

        documents = SQLiteDocumentRepository(connection)
        document = SourceDocument(
            document_id="doc_pipeline_e2e_001",
            source_id="policy_safe_fixture",
            canonical_url="https://example.org/public-record/pipeline-1",
            canonicalization_version="1",
            document_type="press_release",
            recorded_at=NOW,
        )
        version = SourceDocumentVersion.capture(
            version_id="docv_pipeline_e2e_001",
            document_id=document.document_id,
            content=TEXT.encode(),
            retrieved_at=NOW,
            published_at=None,
            recorded_at=NOW,
            mime_type="text/plain",
            http_status=200,
            http_etag=None,
            http_last_modified=None,
            parser_name="fixture_parser",
            parser_version="1.0.0",
            normalized_text=TEXT,
        )
        documents.add_document(document)
        documents.add_version(version)

        assertions = SQLiteAssertionRepository(connection)
        pipeline = PlatformMentionPipeline(
            extractor=PlatformMentionExtractor(),
            writer=assertions,
        )
        request = {
            "subject_id": "case_pipeline_e2e_001",
            "document_version": version,
            "normalized_text": TEXT,
            "run": ExtractionRun("run_pipeline_e2e_001", "test-revision", NOW),
        }

        first = pipeline.extract_and_store(**request)
        retry = pipeline.extract_and_store(**request)

        assert first.outcomes == (InsertOutcome.CREATED, InsertOutcome.CREATED)
        assert retry.assertions == first.assertions
        assert retry.outcomes == (InsertOutcome.EXISTING, InsertOutcome.EXISTING)
        assert (
            tuple(
                assertions.get_assertion(assertion.assertion_id) for assertion in first.assertions
            )
            == first.assertions
        )
        assert connection.execute("SELECT COUNT(*) FROM assertions").fetchone() == (2,)
        assert connection.execute("SELECT COUNT(*) FROM assertion_evidence").fetchone() == (2,)
        assert connection.execute("SELECT COUNT(*) FROM review_decisions").fetchone() == (0,)
    finally:
        connection.close()
