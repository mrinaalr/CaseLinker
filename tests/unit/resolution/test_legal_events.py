from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from caselinker.assertions.models import (
    Assertion,
    AssertionMethod,
    AssertionState,
    AssertionValue,
    MethodFamily,
    Polarity,
    ReviewDecision,
    ReviewerRole,
    ReviewOutcome,
    ValueKind,
)
from caselinker.documents.models import SourceDocumentVersion
from caselinker.documents.ports import InsertOutcome
from caselinker.extraction import AttributedSubject, ExtractionRun, LegalEventExtractor
from caselinker.resolution import (
    CandidateBundleError,
    CandidateReview,
    LegalEventResolutionService,
    LegalEventResolver,
    ResolutionBatchResult,
    ResolutionRun,
    ReviewNotAcceptedError,
)
from caselinker.resolution.legal_events import (
    EVENT_DATE_PREDICATE,
    EVENT_TYPE_PREDICATE,
    SUBJECT_OF_EVENT_PREDICATE,
)

NOW = datetime(2026, 8, 15, 14, 0, tzinfo=UTC)
TEXT = "On March 4, 2026, Example Defendant was charged."


def _version() -> SourceDocumentVersion:
    return SourceDocumentVersion.capture(
        version_id="docv_resolution_fixture_001",
        document_id="doc_resolution_fixture_001",
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


def _candidates() -> tuple[Assertion, ...]:
    return LegalEventExtractor().extract(
        subject=AttributedSubject("party_resolution_fixture_001", ("Example Defendant",)),
        document_version=_version(),
        normalized_text=TEXT,
        run=ExtractionRun("run_extraction_001", "extract-revision", NOW),
    )


def _decision(assertion: Assertion, ordinal: int, outcome: ReviewOutcome) -> ReviewDecision:
    return ReviewDecision(
        decision_id=f"rvw_resolution_fixture_{ordinal:03d}",
        assertion_id=assertion.assertion_id,
        outcome=outcome,
        reviewer_id="reviewer_resolution_fixture_001",
        reviewer_role=ReviewerRole.DOMAIN_REVIEWER,
        rationale="Synthetic fixture supports the procedural source report.",
        decided_at=NOW + timedelta(minutes=ordinal),
        supersedes_decision_id=None,
    )


def _reviewed(
    candidates: tuple[Assertion, ...] | None = None,
    *,
    outcome: ReviewOutcome = ReviewOutcome.ACCEPTED,
) -> tuple[CandidateReview, ...]:
    selected = candidates or _candidates()
    return tuple(
        CandidateReview(assertion, _decision(assertion, ordinal, outcome))
        for ordinal, assertion in enumerate(selected, start=1)
    )


def _run() -> ResolutionRun:
    return ResolutionRun("run_resolution_001", "resolve-revision", NOW + timedelta(hours=1))


def test_resolver_emits_canonical_bundle_with_assertion_and_review_lineage() -> None:
    reviewed = _reviewed()

    resolved = LegalEventResolver().resolve(reviewed_candidates=reviewed, run=_run())

    assert [assertion.predicate for assertion in resolved] == [
        SUBJECT_OF_EVENT_PREDICATE,
        EVENT_TYPE_PREDICATE,
        EVENT_DATE_PREDICATE,
    ]
    input_ids = tuple(item.assertion.assertion_id for item in reviewed)
    decision_ids = tuple(
        item.current_review.decision_id for item in reviewed if item.current_review
    )
    for assertion in resolved:
        assert assertion.state is AssertionState.RESOLVED
        assert assertion.method.family is MethodFamily.RESOLUTION_RULE
        assert assertion.evidence == ()
        assert assertion.input_assertion_ids == input_ids
        assert assertion.review_decision_ids == decision_ids


def test_resolver_is_idempotent_for_one_resolution_run() -> None:
    reviewed = _reviewed()
    resolver = LegalEventResolver()

    assert resolver.resolve(reviewed_candidates=reviewed, run=_run()) == resolver.resolve(
        reviewed_candidates=reviewed,
        run=_run(),
    )


def test_candidate_request_order_does_not_change_canonical_output() -> None:
    reviewed = _reviewed()
    resolver = LegalEventResolver()

    assert resolver.resolve(reviewed_candidates=reviewed, run=_run()) == resolver.resolve(
        reviewed_candidates=tuple(reversed(reviewed)),
        run=_run(),
    )


@pytest.mark.parametrize("outcome", [ReviewOutcome.REJECTED, ReviewOutcome.NEEDS_CHANGES])
def test_resolver_requires_current_acceptance(outcome: ReviewOutcome) -> None:
    with pytest.raises(ReviewNotAcceptedError, match="current accepted review"):
        LegalEventResolver().resolve(
            reviewed_candidates=_reviewed(outcome=outcome),
            run=_run(),
        )


def test_resolver_rejects_partial_event_bundle() -> None:
    candidates = _candidates()

    with pytest.raises(CandidateBundleError, match="two or three"):
        LegalEventResolver().resolve(
            reviewed_candidates=_reviewed(candidates[:1]),
            run=_run(),
        )


def test_resolver_rejects_event_spliced_from_different_identity() -> None:
    candidates = list(_candidates())
    candidates[1] = replace(candidates[1], subject_id="event_different_001")

    with pytest.raises(CandidateBundleError, match="different event entity"):
        LegalEventResolver().resolve(
            reviewed_candidates=_reviewed(tuple(candidates)),
            run=_run(),
        )


def test_resolver_rejects_mixed_extraction_executions() -> None:
    candidates = list(_candidates())
    candidates[1] = replace(
        candidates[1],
        method=AssertionMethod(
            family=MethodFamily.DETERMINISTIC_PATTERN,
            name=candidates[1].method.name,
            version=candidates[1].method.version,
            run_id="run_different_001",
            code_revision=candidates[1].method.code_revision,
        ),
    )

    with pytest.raises(CandidateBundleError, match="one extraction rule execution"):
        LegalEventResolver().resolve(
            reviewed_candidates=_reviewed(tuple(candidates)),
            run=_run(),
        )


def test_resolver_rejects_reused_review_decision_identity() -> None:
    reviewed = list(_reviewed())
    assert reviewed[0].current_review is not None
    assert reviewed[1].current_review is not None
    reviewed[1] = CandidateReview(
        reviewed[1].assertion,
        replace(
            reviewed[1].current_review,
            decision_id=reviewed[0].current_review.decision_id,
        ),
    )

    with pytest.raises(CandidateBundleError, match="cannot reuse"):
        LegalEventResolver().resolve(
            reviewed_candidates=tuple(reviewed),
            run=_run(),
        )


def test_candidate_review_rejects_cross_assertion_pairing() -> None:
    first, second, _ = _candidates()

    with pytest.raises(ValueError, match="paired assertion"):
        CandidateReview(first, _decision(second, 1, ReviewOutcome.ACCEPTED))


def _replace_candidate(
    reviewed: list[CandidateReview],
    index: int,
    **changes: object,
) -> None:
    current = reviewed[index]
    assert current.current_review is not None
    assertion = replace(current.assertion, **changes)
    reviewed[index] = CandidateReview(
        assertion,
        replace(current.current_review, assertion_id=assertion.assertion_id),
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("unexpected_predicate", "unexpected event predicate"),
        ("wrong_state", "only extracted"),
        ("negated", "explicitly affirmed"),
        ("relation_text", "identify an event entity"),
        ("unknown_type", "procedural allowlist"),
        ("different_evidence", "share one exact event span"),
        ("date_event", "date belongs to a different"),
        ("date_text", "canonical date value"),
        ("date_evidence", "same event span"),
    ],
)
def test_resolver_rejects_malformed_bundle_components(mutation: str, message: str) -> None:
    reviewed = list(_reviewed())
    if mutation == "unexpected_predicate":
        _replace_candidate(reviewed, 0, predicate="caselinker:unexpected")
    elif mutation == "wrong_state":
        _replace_candidate(reviewed, 0, state=AssertionState.OBSERVED)
    elif mutation == "negated":
        _replace_candidate(reviewed, 0, polarity=Polarity.NEGATED)
    elif mutation == "relation_text":
        _replace_candidate(reviewed, 0, value=AssertionValue(ValueKind.TEXT, "event text"))
    elif mutation == "unknown_type":
        _replace_candidate(
            reviewed,
            1,
            value=AssertionValue(ValueKind.ENTITY, "legal_event_unknown"),
        )
    elif mutation == "different_evidence":
        _replace_candidate(reviewed, 1, evidence=(reviewed[2].assertion.evidence[1],))
    elif mutation == "date_event":
        _replace_candidate(reviewed, 2, subject_id="event_different_001")
    elif mutation == "date_text":
        _replace_candidate(
            reviewed,
            2,
            value=AssertionValue(ValueKind.TEXT, "March 4, 2026"),
        )
    else:
        _replace_candidate(reviewed, 2, evidence=(reviewed[2].assertion.evidence[1],))

    with pytest.raises(CandidateBundleError, match=message):
        LegalEventResolver().resolve(reviewed_candidates=tuple(reviewed), run=_run())


def test_resolver_rejects_duplicate_candidate_identity() -> None:
    reviewed = _reviewed()

    with pytest.raises(CandidateBundleError, match="cannot repeat"):
        LegalEventResolver().resolve(
            reviewed_candidates=(reviewed[0], reviewed[0], reviewed[1]),
            run=_run(),
        )


def test_resolver_requires_the_event_type_role() -> None:
    reviewed = _reviewed()

    with pytest.raises(CandidateBundleError, match="exactly one"):
        LegalEventResolver().resolve(
            reviewed_candidates=(reviewed[0], reviewed[2]),
            run=_run(),
        )


class MissingStore:
    def get_assertion(self, assertion_id: str) -> Assertion | None:
        return None

    def current_review_decision(self, assertion_id: str) -> ReviewDecision | None:
        return None

    def add_assertions(self, assertions: tuple[Assertion, ...]) -> tuple[InsertOutcome, ...]:
        raise AssertionError("missing candidates must fail before persistence")


def test_resolution_service_rejects_duplicate_request_ids() -> None:
    service = LegalEventResolutionService(resolver=LegalEventResolver(), store=MissingStore())

    with pytest.raises(CandidateBundleError, match="must not repeat"):
        service.resolve_and_store(candidate_ids=("asrt_missing_001",) * 2, run=_run())


def test_resolution_service_rejects_missing_candidate() -> None:
    service = LegalEventResolutionService(resolver=LegalEventResolver(), store=MissingStore())

    with pytest.raises(CandidateBundleError, match="is missing"):
        service.resolve_and_store(candidate_ids=("asrt_missing_001",), run=_run())


def test_resolution_result_rejects_partial_outcomes() -> None:
    with pytest.raises(ValueError, match="one persistence outcome"):
        ResolutionBatchResult(assertions=(_candidates()[0],), outcomes=())


@pytest.mark.parametrize(
    ("run_id", "revision", "created_at", "message"),
    [
        ("bad run", "revision", NOW, "run_id"),
        ("run_valid", " revision", NOW, "code_revision"),
        ("run_valid", "revision", datetime(2026, 8, 15, 14, 0), "created_at"),
    ],
)
def test_resolution_run_rejects_unstable_metadata(
    run_id: str,
    revision: str,
    created_at: datetime,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ResolutionRun(run_id, revision, created_at)
