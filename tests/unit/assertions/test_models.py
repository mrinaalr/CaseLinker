from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

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

NOW = datetime(2026, 8, 15, 8, 0, tzinfo=UTC)
TEXT = "A synthetic public record referenced Example Platform in this fixture."


def _evidence() -> EvidenceReference:
    start = TEXT.index("Example Platform")
    return EvidenceReference.from_text(
        document_version_id="docv_example_001",
        normalized_text=TEXT,
        start_char=start,
        end_char=start + len("Example Platform"),
        page_number=1,
    )


def _method() -> AssertionMethod:
    return AssertionMethod(
        family=MethodFamily.DETERMINISTIC_PATTERN,
        name="platform_reference",
        version="1.0.0",
        run_id="run_001",
        code_revision="784c16b",
    )


def _assertion(**changes: object) -> Assertion:
    assertion = Assertion(
        assertion_id="asrt_example_001",
        subject_id="case_example_001",
        predicate="cac:platformReferenced",
        value=AssertionValue(ValueKind.ENTITY, "platform_example_001"),
        state=AssertionState.EXTRACTED,
        polarity=Polarity.AFFIRMED,
        valid_from=None,
        valid_to=None,
        method=_method(),
        confidence=Confidence(ConfidenceDimension.EXTRACTION, 980_000, "cal_fixture_1"),
        evidence=(_evidence(),),
        input_assertion_ids=(),
        supersedes_assertion_id=None,
        created_at=NOW,
    )
    return replace(assertion, **changes)


def test_exact_evidence_span_binds_offsets_and_complete_text() -> None:
    evidence = _evidence()

    assert evidence.matches(TEXT)
    assert not evidence.matches(TEXT.replace("Platform", "Service"))
    assert evidence.start_char == 37
    assert evidence.end_char == 53


def test_span_factory_rejects_offsets_outside_text() -> None:
    with pytest.raises(ValueError, match="within normalized_text"):
        EvidenceReference.from_text(
            document_version_id="docv_example_001",
            normalized_text=TEXT,
            start_char=0,
            end_char=len(TEXT) + 1,
        )


def test_unavailable_span_is_explicit_and_never_matches_text() -> None:
    evidence = EvidenceReference(
        document_version_id="docv_legacy_001",
        basis_sha256=None,
        page_number=None,
        start_char=None,
        end_char=None,
        span_sha256=None,
        unavailable_reason=SpanUnavailableReason.LEGACY_UNANCHORED,
    )

    assert not evidence.matches(TEXT)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"document_version_id": "bad"}, "docv_ identifier"),
        ({"end_char": None}, "must be complete"),
        ({"unavailable_reason": SpanUnavailableReason.NON_TEXTUAL_SOURCE}, "exactly one"),
        ({"page_number": 0}, "positive integer"),
        ({"basis_sha256": None}, "required for an exact span"),
        ({"basis_sha256": "bad"}, "SHA-256"),
        ({"start_char": -1}, "non-empty span"),
        ({"span_sha256": "bad"}, "SHA-256"),
    ],
)
def test_evidence_rejects_ambiguous_anchors(changes: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_evidence(), **changes)


@pytest.mark.parametrize(
    ("kind", "value", "message"),
    [
        (ValueKind.ENTITY, "Example Platform", "opaque identifiers"),
        (ValueKind.INTEGER, "01", "canonical base-10"),
        (ValueKind.BOOLEAN, "yes", "true or false"),
        (ValueKind.DATE, "08/15/2026", "ISO 8601"),
        (ValueKind.IRI, "relative/path", "absolute"),
        (ValueKind.TEXT, " bad ", "trimmed"),
    ],
)
def test_typed_values_reject_noncanonical_forms(kind: ValueKind, value: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        AssertionValue(kind, value)


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        (ValueKind.TEXT, "Example Platform"),
        (ValueKind.INTEGER, "-12"),
        (ValueKind.BOOLEAN, "false"),
        (ValueKind.DATE, "2026-08-15"),
        (ValueKind.IRI, "urn:example:platform"),
    ],
)
def test_typed_values_accept_canonical_forms(kind: ValueKind, value: str) -> None:
    assert AssertionValue(kind, value).value == value


def test_unquantified_confidence_has_no_fake_probability() -> None:
    confidence = Confidence(ConfidenceDimension.RESOLUTION, None, None)

    assert confidence.score_millionths is None


@pytest.mark.parametrize(
    ("score", "calibration", "message"),
    [
        (None, "cal_1", "requires a quantified"),
        (-1, "cal_1", "0 through 1000000"),
        (1_000_001, "cal_1", "0 through 1000000"),
        (500_000, None, "requires a stable"),
    ],
)
def test_confidence_rejects_misleading_quantification(
    score: int | None, calibration: str | None, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        Confidence(ConfidenceDimension.INFERENCE, score, calibration)


def test_source_assertion_requires_document_evidence() -> None:
    with pytest.raises(ValueError, match="extracted assertions require document evidence"):
        _assertion(evidence=(), input_assertion_ids=("asrt_input_001",))


@pytest.mark.parametrize(
    "state",
    [
        AssertionState.RESOLVED,
        AssertionState.DERIVED,
        AssertionState.CONTESTED,
        AssertionState.RETRACTED,
    ],
)
def test_lineage_assertions_require_input_assertions(state: AssertionState) -> None:
    with pytest.raises(ValueError, match="require input assertions"):
        _assertion(state=state)


def test_derived_assertion_can_use_only_assertion_lineage() -> None:
    assertion = _assertion(
        state=AssertionState.DERIVED,
        evidence=(),
        input_assertion_ids=("asrt_input_001", "asrt_input_002"),
        confidence=None,
    )

    assert assertion.state is AssertionState.DERIVED


def test_retraction_is_a_new_assertion_with_explicit_target() -> None:
    assertion = _assertion(
        state=AssertionState.RETRACTED,
        evidence=(),
        input_assertion_ids=("asrt_input_001",),
        supersedes_assertion_id="asrt_input_001",
    )

    assert assertion.supersedes_assertion_id == "asrt_input_001"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"assertion_id": "bad"}, "asrt_ identifier"),
        ({"subject_id": "bad"}, "opaque identifier"),
        ({"predicate": "Bad Predicate"}, "namespaced token"),
        ({"valid_from": date(2026, 8, 16), "valid_to": date(2026, 8, 15)}, "precede"),
        ({"evidence": (_evidence(), _evidence())}, "must not be duplicated"),
        (
            {"input_assertion_ids": ("asrt_input_001", "asrt_input_001")},
            "must not be duplicated",
        ),
        ({"input_assertion_ids": ("bad",)}, "opaque asrt_"),
        ({"input_assertion_ids": ("asrt_example_001",)}, "depend on itself"),
        ({"state": AssertionState.INFERRED, "evidence": (), "input_assertion_ids": ()}, "requires"),
        (
            {
                "state": AssertionState.RETRACTED,
                "evidence": (),
                "input_assertion_ids": ("asrt_input_001",),
            },
            "identify the retracted",
        ),
        (
            {
                "state": AssertionState.RETRACTED,
                "evidence": (),
                "input_assertion_ids": ("asrt_input_001",),
                "supersedes_assertion_id": "asrt_other_001",
            },
            "must appear",
        ),
        ({"supersedes_assertion_id": "bad"}, "opaque asrt_"),
        ({"supersedes_assertion_id": "asrt_example_001"}, "supersede itself"),
        ({"created_at": datetime(2026, 8, 15)}, "timezone-aware UTC"),
    ],
)
def test_assertion_rejects_broken_lineage(changes: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _assertion(**changes)


def test_review_decision_is_separate_from_assertion() -> None:
    decision = ReviewDecision(
        decision_id="rvw_example_001",
        assertion_id="asrt_example_001",
        outcome=ReviewOutcome.ACCEPTED,
        reviewer_id="reviewer_example_001",
        reviewer_role=ReviewerRole.DOMAIN_REVIEWER,
        rationale="Evidence span and typed value agree with the synthetic fixture.",
        decided_at=NOW,
        supersedes_decision_id=None,
    )

    assert decision.outcome is ReviewOutcome.ACCEPTED


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("decision_id", "bad", "rvw_ identifier"),
        ("assertion_id", "bad", "asrt_ identifier"),
        ("reviewer_id", "bad", "opaque identifier"),
        ("rationale", " bad ", "trimmed"),
        ("decided_at", datetime(2026, 8, 15), "timezone-aware UTC"),
        ("supersedes_decision_id", "bad", "rvw_ identifier"),
        ("supersedes_decision_id", "rvw_example_001", "supersede itself"),
    ],
)
def test_review_decision_rejects_invalid_history(field: str, value: object, message: str) -> None:
    decision = ReviewDecision(
        decision_id="rvw_example_001",
        assertion_id="asrt_example_001",
        outcome=ReviewOutcome.ACCEPTED,
        reviewer_id="reviewer_example_001",
        reviewer_role=ReviewerRole.DOMAIN_REVIEWER,
        rationale="Synthetic fixture review.",
        decided_at=NOW,
        supersedes_decision_id=None,
    )

    with pytest.raises(ValueError, match=message):
        replace(decision, **{field: value})
