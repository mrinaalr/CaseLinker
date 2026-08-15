from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from caselinker.assertions.models import (
    ReviewDecision,
    ReviewerRole,
    ReviewOutcome,
)
from caselinker.assertions.sqlite_repository import SQLiteAssertionRepository
from caselinker.documents.models import SourceDocument, SourceDocumentVersion
from caselinker.documents.ports import InsertOutcome
from caselinker.documents.sqlite_repository import SQLiteDocumentRepository, apply_migration
from caselinker.extraction import AttributedSubject, ExtractionRun, LegalEventExtractor
from caselinker.resolution import (
    EligibilityReason,
    LegalEventResolutionService,
    LegalEventResolver,
    ResearchPublicationEligibilityPolicy,
    ResolutionRun,
    ReviewNotAcceptedError,
)

NOW = datetime(2026, 8, 15, 16, 0, tzinfo=UTC)
TEXT = "On March 4, 2026, Example Defendant was charged."
MIGRATIONS = (
    Path("migrations/sqlite/0001_source_documents.sql"),
    Path("migrations/sqlite/0002_assertion_ledger.sql"),
    Path("migrations/sqlite/0003_assertion_review_lineage.sql"),
)


def test_reviewed_event_resolution_is_reproducible_and_revocably_eligible() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        for migration in MIGRATIONS:
            apply_migration(connection, migration.read_text(encoding="utf-8"))

        documents = SQLiteDocumentRepository(connection)
        document = SourceDocument(
            document_id="doc_resolution_e2e_001",
            source_id="policy_safe_fixture",
            canonical_url="https://example.org/public-record/resolution-1",
            canonicalization_version="1",
            document_type="press_release",
            recorded_at=NOW,
        )
        version = SourceDocumentVersion.capture(
            version_id="docv_resolution_e2e_001",
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

        repository = SQLiteAssertionRepository(connection)
        candidates = LegalEventExtractor().extract(
            subject=AttributedSubject("party_resolution_e2e_001", ("Example Defendant",)),
            document_version=version,
            normalized_text=TEXT,
            run=ExtractionRun("run_resolution_extract_001", "extract-revision", NOW),
        )
        assert repository.add_assertions(candidates) == (InsertOutcome.CREATED,) * 3

        decisions = []
        for ordinal, candidate in enumerate(candidates, start=1):
            decision = ReviewDecision(
                decision_id=f"rvw_resolution_e2e_{ordinal:03d}",
                assertion_id=candidate.assertion_id,
                outcome=ReviewOutcome.ACCEPTED,
                reviewer_id="reviewer_resolution_e2e_001",
                reviewer_role=ReviewerRole.DOMAIN_REVIEWER,
                rationale="The synthetic exact spans support this procedural candidate.",
                decided_at=NOW + timedelta(minutes=ordinal),
                supersedes_decision_id=None,
            )
            repository.add_review_decision(decision)
            decisions.append(decision)

        service = LegalEventResolutionService(
            resolver=LegalEventResolver(),
            store=repository,
        )
        request = {
            "candidate_ids": tuple(candidate.assertion_id for candidate in candidates),
            "run": ResolutionRun(
                "run_resolution_e2e_001",
                "resolve-revision",
                NOW + timedelta(hours=1),
            ),
        }

        first = service.resolve_and_store(**request)
        retry = service.resolve_and_store(**request)

        assert len(first.assertions) == 3
        assert first.outcomes == (InsertOutcome.CREATED,) * 3
        assert retry.assertions == first.assertions
        assert retry.outcomes == (InsertOutcome.EXISTING,) * 3
        assert connection.execute("SELECT COUNT(*) FROM assertion_review_inputs").fetchone() == (9,)

        policy = ResearchPublicationEligibilityPolicy()
        assert all(
            policy.evaluate(assertion=assertion, reviews=repository).eligible
            for assertion in first.assertions
        )

        rejected = ReviewDecision(
            decision_id="rvw_resolution_e2e_rejected_001",
            assertion_id=candidates[0].assertion_id,
            outcome=ReviewOutcome.REJECTED,
            reviewer_id="reviewer_resolution_e2e_001",
            reviewer_role=ReviewerRole.DOMAIN_REVIEWER,
            rationale="A later review found the first candidate should not be used.",
            decided_at=NOW + timedelta(hours=2),
            supersedes_decision_id=decisions[0].decision_id,
        )
        repository.add_review_decision(rejected)

        eligibility = policy.evaluate(assertion=first.assertions[0], reviews=repository)
        assert not eligibility.eligible
        assert eligibility.reasons == (EligibilityReason.REVIEW_NOT_CURRENT,)
        with pytest.raises(ReviewNotAcceptedError, match="current accepted review"):
            service.resolve_and_store(
                candidate_ids=request["candidate_ids"],
                run=ResolutionRun(
                    "run_resolution_after_rejection_001",
                    "resolve-revision",
                    NOW + timedelta(hours=3),
                ),
            )
    finally:
        connection.close()
