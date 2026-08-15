"""Live publication-eligibility policy, separate from review and resolution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from caselinker.assertions.models import Assertion, AssertionState, ReviewDecision, ReviewOutcome


class EligibilityReason(StrEnum):
    STATE_NOT_ELIGIBLE = "state_not_eligible"
    MISSING_ASSERTION_LINEAGE = "missing_assertion_lineage"
    MISSING_REVIEW_LINEAGE = "missing_review_lineage"
    INCOMPLETE_REVIEW_LINEAGE = "incomplete_review_lineage"
    REVIEW_NOT_CURRENT = "review_not_current"
    REVIEW_NOT_ACCEPTED = "review_not_accepted"


@dataclass(frozen=True, slots=True)
class PublicationEligibility:
    eligible: bool
    reasons: tuple[EligibilityReason, ...]

    def __post_init__(self) -> None:
        if self.eligible == bool(self.reasons):
            raise ValueError(
                "eligible decisions have no reasons; ineligible decisions require reasons"
            )


class CurrentReviewReader(Protocol):
    def current_review_decision(self, assertion_id: str) -> ReviewDecision | None: ...


class ResearchPublicationEligibilityPolicy:
    """Necessary evidence-state gate; not disclosure authorization or access control."""

    def evaluate(
        self,
        *,
        assertion: Assertion,
        reviews: CurrentReviewReader,
    ) -> PublicationEligibility:
        reasons: list[EligibilityReason] = []
        if assertion.state is not AssertionState.RESOLVED:
            reasons.append(EligibilityReason.STATE_NOT_ELIGIBLE)
        if not assertion.input_assertion_ids:
            reasons.append(EligibilityReason.MISSING_ASSERTION_LINEAGE)
        if not assertion.review_decision_ids:
            reasons.append(EligibilityReason.MISSING_REVIEW_LINEAGE)
        if len(assertion.input_assertion_ids) != len(assertion.review_decision_ids):
            reasons.append(EligibilityReason.INCOMPLETE_REVIEW_LINEAGE)
        else:
            for input_id, expected_decision_id in zip(
                assertion.input_assertion_ids,
                assertion.review_decision_ids,
                strict=True,
            ):
                current = reviews.current_review_decision(input_id)
                if current is None or current.decision_id != expected_decision_id:
                    reasons.append(EligibilityReason.REVIEW_NOT_CURRENT)
                    continue
                if current.outcome is not ReviewOutcome.ACCEPTED:
                    reasons.append(EligibilityReason.REVIEW_NOT_ACCEPTED)

        unique_reasons = tuple(dict.fromkeys(reasons))
        return PublicationEligibility(eligible=not unique_reasons, reasons=unique_reasons)
