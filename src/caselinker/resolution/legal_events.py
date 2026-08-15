"""Resolve coherently reviewed reported-event candidates without mutation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Final, Protocol

from caselinker.assertions.models import (
    Assertion,
    AssertionMethod,
    AssertionState,
    AssertionValue,
    Confidence,
    ConfidenceDimension,
    MethodFamily,
    Polarity,
    ReviewDecision,
    ReviewOutcome,
    ValueKind,
)
from caselinker.documents.ports import InsertOutcome
from caselinker.extraction.legal_events import (
    REPORTED_EVENT_DATE_PREDICATE,
    REPORTED_EVENT_TYPE_PREDICATE,
    REPORTED_SUBJECT_PREDICATE,
)
from caselinker.resolution.models import ResolutionRun

SUBJECT_OF_EVENT_PREDICATE: Final = "caselinker:subjectOfLegalEvent"
EVENT_TYPE_PREDICATE: Final = "caselinker:legalEventType"
EVENT_DATE_PREDICATE: Final = "caselinker:eventDate"
_RESOLUTION_VERSION: Final = "1.0.0"
_EVENT_TYPES: Final = frozenset(
    {
        "legal_event_arrest",
        "legal_event_charge",
        "legal_event_indictment",
        "legal_event_guilty_plea",
        "legal_event_conviction",
        "legal_event_sentencing",
    }
)


class LegalEventResolutionError(RuntimeError):
    """Base error for rejected legal-event resolution requests."""


class CandidateBundleError(LegalEventResolutionError):
    """Candidate assertions do not form one coherent reported event."""


class ReviewNotAcceptedError(LegalEventResolutionError):
    """A candidate lacks a current accepted review decision."""


@dataclass(frozen=True, slots=True)
class CandidateReview:
    assertion: Assertion
    current_review: ReviewDecision | None

    def __post_init__(self) -> None:
        if (
            self.current_review is not None
            and self.current_review.assertion_id != self.assertion.assertion_id
        ):
            raise ValueError("current review must govern its paired assertion")


class ResolutionStore(Protocol):
    def get_assertion(self, assertion_id: str) -> Assertion | None: ...

    def current_review_decision(self, assertion_id: str) -> ReviewDecision | None: ...

    def add_assertions(self, assertions: tuple[Assertion, ...]) -> tuple[InsertOutcome, ...]: ...


@dataclass(frozen=True, slots=True)
class ResolutionBatchResult:
    assertions: tuple[Assertion, ...]
    outcomes: tuple[InsertOutcome, ...]

    def __post_init__(self) -> None:
        if len(self.assertions) != len(self.outcomes):
            raise ValueError("every resolved assertion must have one persistence outcome")


def _stable_id(prefix: str, identity: dict[str, object]) -> str:
    canonical = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return prefix + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _one(
    by_predicate: dict[str, list[CandidateReview]],
    predicate: str,
    *,
    required: bool,
) -> CandidateReview | None:
    matches = by_predicate.get(predicate, [])
    if len(matches) > 1 or (required and not matches):
        expectation = "exactly one" if required else "at most one"
        raise CandidateBundleError(f"event bundle requires {expectation} {predicate} assertion")
    return matches[0] if matches else None


class LegalEventResolver:
    """Create canonical assertions from one fully accepted candidate bundle."""

    def resolve(
        self,
        *,
        reviewed_candidates: tuple[CandidateReview, ...],
        run: ResolutionRun,
    ) -> tuple[Assertion, ...]:
        if len(reviewed_candidates) not in {2, 3}:
            raise CandidateBundleError(
                "event bundle must contain two or three candidate assertions"
            )
        candidate_ids = [item.assertion.assertion_id for item in reviewed_candidates]
        if len(set(candidate_ids)) != len(candidate_ids):
            raise CandidateBundleError("event bundle cannot repeat candidate assertions")

        allowed_predicates = {
            REPORTED_SUBJECT_PREDICATE,
            REPORTED_EVENT_TYPE_PREDICATE,
            REPORTED_EVENT_DATE_PREDICATE,
        }
        by_predicate: dict[str, list[CandidateReview]] = {}
        for item in reviewed_candidates:
            assertion = item.assertion
            if assertion.predicate not in allowed_predicates:
                raise CandidateBundleError(f"unexpected event predicate: {assertion.predicate}")
            if assertion.state is not AssertionState.EXTRACTED:
                raise CandidateBundleError("only extracted candidates may enter this resolver")
            if assertion.polarity is not Polarity.AFFIRMED:
                raise CandidateBundleError("legal-event candidates must be explicitly affirmed")
            review = item.current_review
            if review is None or review.outcome is not ReviewOutcome.ACCEPTED:
                raise ReviewNotAcceptedError(
                    f"candidate {assertion.assertion_id} lacks a current accepted review"
                )
            by_predicate.setdefault(assertion.predicate, []).append(item)

        relation = _one(by_predicate, REPORTED_SUBJECT_PREDICATE, required=True)
        event_type = _one(by_predicate, REPORTED_EVENT_TYPE_PREDICATE, required=True)
        event_date = _one(by_predicate, REPORTED_EVENT_DATE_PREDICATE, required=False)
        assert relation is not None
        assert event_type is not None

        relation_assertion = relation.assertion
        type_assertion = event_type.assertion
        if relation_assertion.value.kind is not ValueKind.ENTITY:
            raise CandidateBundleError("reported subject relation must identify an event entity")
        event_id = relation_assertion.value.value
        if type_assertion.subject_id != event_id:
            raise CandidateBundleError("event type belongs to a different event entity")
        if (
            type_assertion.value.kind is not ValueKind.ENTITY
            or type_assertion.value.value not in _EVENT_TYPES
        ):
            raise CandidateBundleError("event type is not in the canonical procedural allowlist")

        event_evidence = relation_assertion.evidence
        if len(event_evidence) != 1 or type_assertion.evidence != event_evidence:
            raise CandidateBundleError("subject and event type must share one exact event span")

        ordered = [relation, event_type]
        if event_date is not None:
            date_assertion = event_date.assertion
            if date_assertion.subject_id != event_id:
                raise CandidateBundleError("event date belongs to a different event entity")
            if date_assertion.value.kind is not ValueKind.DATE:
                raise CandidateBundleError("event date must use a canonical date value")
            if len(date_assertion.evidence) != 2 or date_assertion.evidence[0] != event_evidence[0]:
                raise CandidateBundleError(
                    "event date must cite the same event span and a date span"
                )
            ordered.append(event_date)

        method_signatures = {
            (
                item.assertion.method.family,
                item.assertion.method.name,
                item.assertion.method.version,
                item.assertion.method.run_id,
                item.assertion.method.code_revision,
            )
            for item in ordered
        }
        if len(method_signatures) != 1:
            raise CandidateBundleError(
                "event candidates must come from one extraction rule execution"
            )

        input_ids = tuple(item.assertion.assertion_id for item in ordered)
        decision_ids = tuple(
            item.current_review.decision_id for item in ordered if item.current_review
        )
        if len(set(decision_ids)) != len(decision_ids):
            raise CandidateBundleError("event bundle cannot reuse a review decision")
        outputs = [
            (
                "subject",
                relation_assertion.subject_id,
                SUBJECT_OF_EVENT_PREDICATE,
                AssertionValue(ValueKind.ENTITY, event_id),
            ),
            (
                "type",
                event_id,
                EVENT_TYPE_PREDICATE,
                type_assertion.value,
            ),
        ]
        if event_date is not None:
            outputs.append(("date", event_id, EVENT_DATE_PREDICATE, event_date.assertion.value))

        resolved = []
        for role, subject_id, predicate, value in outputs:
            assertion_id = _stable_id(
                "asrt_",
                {
                    "decision_ids": decision_ids,
                    "input_ids": input_ids,
                    "predicate": predicate,
                    "resolution_role": role,
                    "resolution_version": _RESOLUTION_VERSION,
                    "run_id": run.run_id,
                    "subject_id": subject_id,
                    "value_kind": value.kind.value,
                    "value": value.value,
                },
            )
            resolved.append(
                Assertion(
                    assertion_id=assertion_id,
                    subject_id=subject_id,
                    predicate=predicate,
                    value=value,
                    state=AssertionState.RESOLVED,
                    polarity=Polarity.AFFIRMED,
                    valid_from=None,
                    valid_to=None,
                    method=AssertionMethod(
                        family=MethodFamily.RESOLUTION_RULE,
                        name="reported_legal_event_bundle",
                        version=_RESOLUTION_VERSION,
                        run_id=run.run_id,
                        code_revision=run.code_revision,
                    ),
                    confidence=Confidence(ConfidenceDimension.RESOLUTION, None, None),
                    evidence=(),
                    input_assertion_ids=input_ids,
                    supersedes_assertion_id=None,
                    created_at=run.created_at,
                    review_decision_ids=decision_ids,
                )
            )
        return tuple(resolved)


class LegalEventResolutionService:
    """Load current reviews, resolve one bundle, and store outputs atomically."""

    def __init__(self, *, resolver: LegalEventResolver, store: ResolutionStore) -> None:
        self._resolver = resolver
        self._store = store

    def resolve_and_store(
        self,
        *,
        candidate_ids: tuple[str, ...],
        run: ResolutionRun,
    ) -> ResolutionBatchResult:
        if len(set(candidate_ids)) != len(candidate_ids):
            raise CandidateBundleError("candidate_ids must not repeat")
        reviewed = []
        for candidate_id in candidate_ids:
            assertion = self._store.get_assertion(candidate_id)
            if assertion is None:
                raise CandidateBundleError(f"candidate assertion is missing: {candidate_id}")
            reviewed.append(
                CandidateReview(
                    assertion=assertion,
                    current_review=self._store.current_review_decision(candidate_id),
                )
            )
        assertions = self._resolver.resolve(reviewed_candidates=tuple(reviewed), run=run)
        outcomes = self._store.add_assertions(assertions)
        return ResolutionBatchResult(assertions=assertions, outcomes=outcomes)
