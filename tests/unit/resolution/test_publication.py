from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from caselinker.assertions.models import (
    Assertion,
    ReviewDecision,
    ReviewerRole,
    ReviewOutcome,
)
from caselinker.documents.models import SourceDocumentVersion
from caselinker.extraction import AttributedSubject, ExtractionRun, LegalEventExtractor
from caselinker.resolution import (
    CandidateReview,
    EligibilityReason,
    LegalEventResolver,
    PublicationEligibility,
    ResearchPublicationEligibilityPolicy,
    ResolutionRun,
)

NOW = datetime(2026, 8, 15, 15, 0, tzinfo=UTC)
TEXT = "Example Defendant was charged."


class ReviewReader:
    def __init__(self, decisions: tuple[ReviewDecision, ...]) -> None:
        self._decisions = {decision.assertion_id: decision for decision in decisions}

    def current_review_decision(self, assertion_id: str) -> ReviewDecision | None:
        return self._decisions.get(assertion_id)


def _resolved() -> tuple[Assertion, tuple[ReviewDecision, ...], tuple[Assertion, ...]]:
    version = SourceDocumentVersion.capture(
        version_id="docv_publication_fixture_001",
        document_id="doc_publication_fixture_001",
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
    candidates = LegalEventExtractor().extract(
        subject=AttributedSubject("party_publication_fixture_001", ("Example Defendant",)),
        document_version=version,
        normalized_text=TEXT,
        run=ExtractionRun("run_publication_extract_001", "extract-revision", NOW),
    )
    decisions = tuple(
        ReviewDecision(
            decision_id=f"rvw_publication_fixture_{ordinal:03d}",
            assertion_id=assertion.assertion_id,
            outcome=ReviewOutcome.ACCEPTED,
            reviewer_id="reviewer_publication_fixture_001",
            reviewer_role=ReviewerRole.DOMAIN_REVIEWER,
            rationale="Synthetic candidate accepted for resolution.",
            decided_at=NOW + timedelta(minutes=ordinal),
            supersedes_decision_id=None,
        )
        for ordinal, assertion in enumerate(candidates, start=1)
    )
    reviewed = tuple(
        CandidateReview(assertion, decision)
        for assertion, decision in zip(candidates, decisions, strict=True)
    )
    resolved = LegalEventResolver().resolve(
        reviewed_candidates=reviewed,
        run=ResolutionRun("run_publication_resolve_001", "resolve-revision", NOW),
    )
    return resolved[0], decisions, candidates


def test_current_accepted_resolution_is_eligible() -> None:
    assertion, decisions, _ = _resolved()

    result = ResearchPublicationEligibilityPolicy().evaluate(
        assertion=assertion,
        reviews=ReviewReader(decisions),
    )

    assert result == PublicationEligibility(eligible=True, reasons=())


def test_superseded_review_makes_resolution_ineligible() -> None:
    assertion, decisions, _ = _resolved()
    replacement = replace(
        decisions[0],
        decision_id="rvw_publication_replacement_001",
        outcome=ReviewOutcome.REJECTED,
        supersedes_decision_id=decisions[0].decision_id,
        decided_at=decisions[0].decided_at + timedelta(minutes=1),
    )
    current = (replacement, *decisions[1:])

    result = ResearchPublicationEligibilityPolicy().evaluate(
        assertion=assertion,
        reviews=ReviewReader(current),
    )

    assert not result.eligible
    assert result.reasons == (EligibilityReason.REVIEW_NOT_CURRENT,)


def test_current_rejected_review_is_not_eligible() -> None:
    assertion, decisions, _ = _resolved()
    rejected = replace(decisions[0], outcome=ReviewOutcome.REJECTED)

    result = ResearchPublicationEligibilityPolicy().evaluate(
        assertion=assertion,
        reviews=ReviewReader((rejected, *decisions[1:])),
    )

    assert not result.eligible
    assert result.reasons == (EligibilityReason.REVIEW_NOT_ACCEPTED,)


def test_incomplete_review_lineage_is_not_eligible() -> None:
    assertion, decisions, _ = _resolved()
    incomplete = replace(assertion, review_decision_ids=assertion.review_decision_ids[:1])

    result = ResearchPublicationEligibilityPolicy().evaluate(
        assertion=incomplete,
        reviews=ReviewReader(decisions),
    )

    assert not result.eligible
    assert result.reasons == (EligibilityReason.INCOMPLETE_REVIEW_LINEAGE,)


def test_accepted_extracted_candidate_is_not_publication_eligible() -> None:
    _, decisions, candidates = _resolved()

    result = ResearchPublicationEligibilityPolicy().evaluate(
        assertion=candidates[0],
        reviews=ReviewReader(decisions),
    )

    assert not result.eligible
    assert EligibilityReason.STATE_NOT_ELIGIBLE in result.reasons
    assert EligibilityReason.MISSING_REVIEW_LINEAGE in result.reasons


@pytest.mark.parametrize(
    ("eligible", "reasons"),
    [(True, (EligibilityReason.STATE_NOT_ELIGIBLE,)), (False, ())],
)
def test_eligibility_value_rejects_inconsistent_shape(
    eligible: bool,
    reasons: tuple[EligibilityReason, ...],
) -> None:
    with pytest.raises(ValueError, match="ineligible"):
        PublicationEligibility(eligible=eligible, reasons=reasons)
