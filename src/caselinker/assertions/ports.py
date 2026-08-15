"""Persistence boundary for immutable assertions and review decisions."""

from __future__ import annotations

from typing import Protocol

from caselinker.assertions.models import Assertion, ReviewDecision
from caselinker.documents.ports import InsertOutcome


class AssertionRepository(Protocol):
    def add_assertion(self, assertion: Assertion) -> InsertOutcome: ...

    def get_assertion(self, assertion_id: str) -> Assertion | None: ...

    def add_review_decision(self, decision: ReviewDecision) -> InsertOutcome: ...

    def list_review_decisions(self, assertion_id: str) -> tuple[ReviewDecision, ...]: ...
