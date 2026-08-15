"""Immutable assertion provenance, evidence anchors, and review decisions."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Final, Self
from urllib.parse import urlsplit

from caselinker.documents.models import VERSION_ID_PATTERN

ASSERTION_ID_PATTERN: Final = re.compile(r"^asrt_[a-z0-9][a-z0-9._-]{2,127}$")
DECISION_ID_PATTERN: Final = re.compile(r"^rvw_[a-z0-9][a-z0-9._-]{2,127}$")
OPAQUE_ID_PATTERN: Final = re.compile(r"^[a-z][a-z0-9]*_[a-z0-9][a-z0-9._-]{2,127}$")
PREDICATE_PATTERN: Final = re.compile(r"^[a-z][a-z0-9._-]*(?::[A-Za-z][A-Za-z0-9._-]*)?$")
TOKEN_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")
INTEGER_PATTERN: Final = re.compile(r"^-?(0|[1-9][0-9]*)$")


class AssertionState(StrEnum):
    OBSERVED = "observed"
    EXTRACTED = "extracted"
    RESOLVED = "resolved"
    DERIVED = "derived"
    INFERRED = "inferred"
    AUTHORED = "authored"
    CONTESTED = "contested"
    RETRACTED = "retracted"


class Polarity(StrEnum):
    AFFIRMED = "affirmed"
    NEGATED = "negated"
    UNCERTAIN = "uncertain"


class ValueKind(StrEnum):
    ENTITY = "entity"
    TEXT = "text"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    DATE = "date"
    IRI = "iri"


class SpanUnavailableReason(StrEnum):
    NON_TEXTUAL_SOURCE = "non_textual_source"
    PARSER_DID_NOT_PRESERVE_OFFSETS = "parser_did_not_preserve_offsets"
    LEGACY_UNANCHORED = "legacy_unanchored"
    SOURCE_VERSION_UNAVAILABLE = "source_version_unavailable"


class MethodFamily(StrEnum):
    DETERMINISTIC_PATTERN = "deterministic_pattern"
    NLP_MODEL = "nlp_model"
    MANUAL_OBSERVATION = "manual_observation"
    RESOLUTION_RULE = "resolution_rule"
    COMPUTATION = "computation"
    STATISTICAL_MODEL = "statistical_model"
    RESEARCHER_AUTHORSHIP = "researcher_authorship"


class ConfidenceDimension(StrEnum):
    EXTRACTION = "extraction"
    RESOLUTION = "resolution"
    INFERENCE = "inference"


class ReviewOutcome(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NEEDS_CHANGES = "needs_changes"


class ReviewerRole(StrEnum):
    DOMAIN_REVIEWER = "domain_reviewer"
    CORPUS_CURATOR = "corpus_curator"
    POLICY_REVIEWER = "policy_reviewer"


def _validate_utc(value: datetime, *, field: str) -> None:
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise ValueError(f"{field} must be timezone-aware UTC")


def _validate_sha256(value: str, *, field: str) -> None:
    if SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


def _validate_text(value: str, *, field: str, maximum: int) -> None:
    if not value or value != value.strip():
        raise ValueError(f"{field} must be a non-empty trimmed string")
    if len(value) > maximum:
        raise ValueError(f"{field} must not exceed {maximum} characters")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"{field} must not contain control characters")


@dataclass(frozen=True, slots=True)
class AssertionValue:
    kind: ValueKind
    value: str

    def __post_init__(self) -> None:
        _validate_text(self.value, field="assertion value", maximum=512)
        if self.kind is ValueKind.ENTITY and OPAQUE_ID_PATTERN.fullmatch(self.value) is None:
            raise ValueError("entity assertion values must be opaque identifiers")
        if self.kind is ValueKind.INTEGER and INTEGER_PATTERN.fullmatch(self.value) is None:
            raise ValueError("integer assertion values must use canonical base-10 form")
        if self.kind is ValueKind.BOOLEAN and self.value not in {"true", "false"}:
            raise ValueError("boolean assertion values must be true or false")
        if self.kind is ValueKind.DATE:
            try:
                parsed = date.fromisoformat(self.value)
            except ValueError as exc:
                raise ValueError("date assertion values must use ISO 8601") from exc
            if parsed.isoformat() != self.value:
                raise ValueError("date assertion values must use canonical ISO 8601")
        if self.kind is ValueKind.IRI and not urlsplit(self.value).scheme:
            raise ValueError("IRI assertion values must be absolute")


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """Either an exact text span or a typed explanation for its absence."""

    document_version_id: str
    basis_sha256: str | None
    page_number: int | None
    start_char: int | None
    end_char: int | None
    span_sha256: str | None
    unavailable_reason: SpanUnavailableReason | None

    def __post_init__(self) -> None:
        if VERSION_ID_PATTERN.fullmatch(self.document_version_id) is None:
            raise ValueError("document_version_id must be an opaque docv_ identifier")
        coordinates = (self.start_char, self.end_char, self.span_sha256)
        has_span = all(value is not None for value in coordinates)
        has_partial_span = any(value is not None for value in coordinates) and not has_span
        if has_partial_span:
            raise ValueError("evidence span coordinates and hash must be complete")
        if has_span == (self.unavailable_reason is not None):
            raise ValueError("evidence must have exactly one span or unavailable reason")
        if self.page_number is not None and (
            isinstance(self.page_number, bool) or self.page_number < 1
        ):
            raise ValueError("page_number must be a positive integer")
        if has_span:
            if self.basis_sha256 is None:
                raise ValueError("basis_sha256 is required for an exact span")
            _validate_sha256(self.basis_sha256, field="basis_sha256")
            assert self.start_char is not None
            assert self.end_char is not None
            assert self.span_sha256 is not None
            if self.start_char < 0 or self.end_char <= self.start_char:
                raise ValueError("evidence character offsets must define a non-empty span")
            _validate_sha256(self.span_sha256, field="span_sha256")
        elif self.basis_sha256 is not None:
            _validate_sha256(self.basis_sha256, field="basis_sha256")

    @classmethod
    def from_text(
        cls,
        *,
        document_version_id: str,
        normalized_text: str,
        start_char: int,
        end_char: int,
        page_number: int | None = None,
    ) -> Self:
        if start_char < 0 or end_char <= start_char or end_char > len(normalized_text):
            raise ValueError("evidence offsets must fall within normalized_text")
        span = normalized_text[start_char:end_char]
        return cls(
            document_version_id=document_version_id,
            basis_sha256=hashlib.sha256(normalized_text.encode("utf-8")).hexdigest(),
            page_number=page_number,
            start_char=start_char,
            end_char=end_char,
            span_sha256=hashlib.sha256(span.encode("utf-8")).hexdigest(),
            unavailable_reason=None,
        )

    def matches(self, normalized_text: str) -> bool:
        if self.unavailable_reason is not None:
            return False
        assert self.start_char is not None
        assert self.end_char is not None
        basis = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
        span = hashlib.sha256(
            normalized_text[self.start_char : self.end_char].encode("utf-8")
        ).hexdigest()
        return basis == self.basis_sha256 and span == self.span_sha256


@dataclass(frozen=True, slots=True)
class AssertionMethod:
    family: MethodFamily
    name: str
    version: str
    run_id: str
    code_revision: str

    def __post_init__(self) -> None:
        for field, value in (
            ("method name", self.name),
            ("method version", self.version),
            ("run_id", self.run_id),
        ):
            if TOKEN_PATTERN.fullmatch(value) is None:
                raise ValueError(f"{field} must be a stable token")
        _validate_text(self.code_revision, field="code_revision", maximum=128)


@dataclass(frozen=True, slots=True)
class Confidence:
    dimension: ConfidenceDimension
    score_millionths: int | None
    calibration_id: str | None

    def __post_init__(self) -> None:
        if self.score_millionths is None:
            if self.calibration_id is not None:
                raise ValueError("calibration_id requires a quantified confidence score")
            return
        if (
            isinstance(self.score_millionths, bool)
            or not isinstance(self.score_millionths, int)
            or not 0 <= self.score_millionths <= 1_000_000
        ):
            raise ValueError("score_millionths must be an integer from 0 through 1000000")
        if self.calibration_id is None or TOKEN_PATTERN.fullmatch(self.calibration_id) is None:
            raise ValueError("quantified confidence requires a stable calibration_id")


@dataclass(frozen=True, slots=True)
class Assertion:
    assertion_id: str
    subject_id: str
    predicate: str
    value: AssertionValue
    state: AssertionState
    polarity: Polarity
    valid_from: date | None
    valid_to: date | None
    method: AssertionMethod
    confidence: Confidence | None
    evidence: tuple[EvidenceReference, ...]
    input_assertion_ids: tuple[str, ...]
    supersedes_assertion_id: str | None
    created_at: datetime
    review_decision_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if ASSERTION_ID_PATTERN.fullmatch(self.assertion_id) is None:
            raise ValueError("assertion_id must be an opaque asrt_ identifier")
        if OPAQUE_ID_PATTERN.fullmatch(self.subject_id) is None:
            raise ValueError("subject_id must be an opaque identifier")
        if PREDICATE_PATTERN.fullmatch(self.predicate) is None:
            raise ValueError("predicate must be a stable namespaced token")
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_to < self.valid_from
        ):
            raise ValueError("valid_to must not precede valid_from")
        if len(set(self.evidence)) != len(self.evidence):
            raise ValueError("evidence references must not be duplicated")
        if len(set(self.input_assertion_ids)) != len(self.input_assertion_ids):
            raise ValueError("input_assertion_ids must not be duplicated")
        if len(set(self.review_decision_ids)) != len(self.review_decision_ids):
            raise ValueError("review_decision_ids must not be duplicated")
        for assertion_id in self.input_assertion_ids:
            if ASSERTION_ID_PATTERN.fullmatch(assertion_id) is None:
                raise ValueError("input_assertion_ids must contain opaque asrt_ identifiers")
            if assertion_id == self.assertion_id:
                raise ValueError("an assertion cannot depend on itself")
        for decision_id in self.review_decision_ids:
            if DECISION_ID_PATTERN.fullmatch(decision_id) is None:
                raise ValueError("review_decision_ids must contain opaque rvw_ identifiers")
        source_states = {AssertionState.OBSERVED, AssertionState.EXTRACTED}
        lineage_states = {
            AssertionState.RESOLVED,
            AssertionState.DERIVED,
            AssertionState.CONTESTED,
            AssertionState.RETRACTED,
        }
        if self.state in source_states and not self.evidence:
            raise ValueError(f"{self.state.value} assertions require document evidence")
        if self.state in source_states and self.review_decision_ids:
            raise ValueError(f"{self.state.value} assertions cannot cite later review decisions")
        if self.state in lineage_states and not self.input_assertion_ids:
            raise ValueError(f"{self.state.value} assertions require input assertions")
        if not self.evidence and not self.input_assertion_ids:
            raise ValueError("every assertion requires evidence or input assertion lineage")
        if self.state is AssertionState.RETRACTED:
            if self.supersedes_assertion_id is None:
                raise ValueError("retracted assertions must identify the retracted assertion")
            if self.supersedes_assertion_id not in self.input_assertion_ids:
                raise ValueError("the retracted assertion must appear in input_assertion_ids")
        if self.supersedes_assertion_id is not None:
            if ASSERTION_ID_PATTERN.fullmatch(self.supersedes_assertion_id) is None:
                raise ValueError("supersedes_assertion_id must be an opaque asrt_ identifier")
            if self.supersedes_assertion_id == self.assertion_id:
                raise ValueError("an assertion cannot supersede itself")
        _validate_utc(self.created_at, field="created_at")


@dataclass(frozen=True, slots=True)
class ReviewDecision:
    decision_id: str
    assertion_id: str
    outcome: ReviewOutcome
    reviewer_id: str
    reviewer_role: ReviewerRole
    rationale: str
    decided_at: datetime
    supersedes_decision_id: str | None

    def __post_init__(self) -> None:
        if DECISION_ID_PATTERN.fullmatch(self.decision_id) is None:
            raise ValueError("decision_id must be an opaque rvw_ identifier")
        if ASSERTION_ID_PATTERN.fullmatch(self.assertion_id) is None:
            raise ValueError("assertion_id must be an opaque asrt_ identifier")
        if OPAQUE_ID_PATTERN.fullmatch(self.reviewer_id) is None:
            raise ValueError("reviewer_id must be an opaque identifier")
        _validate_text(self.rationale, field="rationale", maximum=1000)
        _validate_utc(self.decided_at, field="decided_at")
        if self.supersedes_decision_id is not None:
            if DECISION_ID_PATTERN.fullmatch(self.supersedes_decision_id) is None:
                raise ValueError("supersedes_decision_id must be an opaque rvw_ identifier")
            if self.supersedes_decision_id == self.decision_id:
                raise ValueError("a review decision cannot supersede itself")
