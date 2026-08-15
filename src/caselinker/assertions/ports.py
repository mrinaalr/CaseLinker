"""Persistence boundary for immutable assertions and review decisions."""

from __future__ import annotations

from typing import Protocol

from caselinker.assertions.models import Assertion, ReviewDecision
from caselinker.documents.ports import InsertOutcome


class AssertionRepositoryError(RuntimeError):
    """Base error for assertion persistence contract violations."""


class AssertionConflictError(AssertionRepositoryError):
    """An immutable assertion or review ID was reused inconsistently."""


class MissingLineageError(AssertionRepositoryError):
    """Referenced document, assertion, or review lineage is absent."""


class EvidenceMismatchError(AssertionRepositoryError):
    """Evidence offsets were created against a different normalized text."""


class ReviewChainError(AssertionRepositoryError):
    """A review decision does not extend the current linear review history."""


class AssertionRepository(Protocol):
    def add_assertion(self, assertion: Assertion) -> InsertOutcome: ...

    def get_assertion(self, assertion_id: str) -> Assertion | None: ...

    def add_review_decision(self, decision: ReviewDecision) -> InsertOutcome: ...

    def list_review_decisions(self, assertion_id: str) -> tuple[ReviewDecision, ...]: ...

    def current_review_decision(self, assertion_id: str) -> ReviewDecision | None: ...
