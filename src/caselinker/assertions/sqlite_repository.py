"""SQLite adapter for immutable assertions, evidence, lineage, and reviews."""

from __future__ import annotations

import sqlite3
from datetime import date

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
from caselinker.assertions.ports import (
    AssertionConflictError,
    EvidenceMismatchError,
    MissingLineageError,
    ReviewChainError,
)
from caselinker.documents.models import canonical_utc, parse_canonical_utc
from caselinker.documents.ports import InsertOutcome

ASSERTION_COLUMNS = """
assertion_id, subject_id, predicate, value_kind, value_text, state, polarity,
valid_from, valid_to, method_family, method_name, method_version, run_id,
code_revision, confidence_dimension, confidence_score_millionths,
confidence_calibration_id, supersedes_assertion_id, created_at
"""
EVIDENCE_COLUMNS = """
document_version_id, basis_sha256, page_number, start_char, end_char,
span_sha256, unavailable_reason
"""
REVIEW_COLUMNS = """
decision_id, assertion_id, outcome, reviewer_id, reviewer_role, rationale,
decided_at, supersedes_decision_id
"""


def _optional_date(value: object) -> date | None:
    return date.fromisoformat(str(value)) if value is not None else None


def _evidence_from_row(row: tuple[object, ...]) -> EvidenceReference:
    return EvidenceReference(
        document_version_id=str(row[0]),
        basis_sha256=str(row[1]) if row[1] is not None else None,
        page_number=int(str(row[2])) if row[2] is not None else None,
        start_char=int(str(row[3])) if row[3] is not None else None,
        end_char=int(str(row[4])) if row[4] is not None else None,
        span_sha256=str(row[5]) if row[5] is not None else None,
        unavailable_reason=(SpanUnavailableReason(str(row[6])) if row[6] is not None else None),
    )


def _review_from_row(row: tuple[object, ...]) -> ReviewDecision:
    return ReviewDecision(
        decision_id=str(row[0]),
        assertion_id=str(row[1]),
        outcome=ReviewOutcome(str(row[2])),
        reviewer_id=str(row[3]),
        reviewer_role=ReviewerRole(str(row[4])),
        rationale=str(row[5]),
        decided_at=parse_canonical_utc(str(row[6])),
        supersedes_decision_id=str(row[7]) if row[7] is not None else None,
    )


class SQLiteAssertionRepository:
    """Atomic append-only repository implementing the assertion storage port."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._connection.execute("PRAGMA foreign_keys = ON")

    def _document_version_text_hash(self, version_id: str) -> tuple[bool, str | None]:
        row = self._connection.execute(
            """
            SELECT normalized_text_sha256
            FROM source_document_versions
            WHERE version_id = ?
            """,
            (version_id,),
        ).fetchone()
        return (False, None) if row is None else (True, str(row[0]) if row[0] else None)

    def add_assertion(self, assertion: Assertion) -> InsertOutcome:
        existing = self.get_assertion(assertion.assertion_id)
        if existing is not None:
            if existing == assertion:
                return InsertOutcome.EXISTING
            raise AssertionConflictError(
                f"assertion_id {assertion.assertion_id} already identifies different content"
            )

        version_hashes = {
            evidence.document_version_id: self._document_version_text_hash(
                evidence.document_version_id
            )
            for evidence in assertion.evidence
        }
        missing_versions = sorted(
            version_id for version_id, (exists, _) in version_hashes.items() if not exists
        )
        if missing_versions:
            raise MissingLineageError(
                f"document version lineage is missing: {', '.join(missing_versions)}"
            )
        mismatched_versions = sorted(
            evidence.document_version_id
            for evidence in assertion.evidence
            if evidence.basis_sha256 is not None
            and version_hashes[evidence.document_version_id][1] != evidence.basis_sha256
        )
        if mismatched_versions:
            raise EvidenceMismatchError(
                "evidence basis does not match normalized document text: "
                + ", ".join(mismatched_versions)
            )
        required_assertions = set(assertion.input_assertion_ids)
        if assertion.supersedes_assertion_id is not None:
            required_assertions.add(assertion.supersedes_assertion_id)
        missing_assertions = sorted(
            assertion_id
            for assertion_id in required_assertions
            if self.get_assertion(assertion_id) is None
        )
        if missing_assertions:
            raise MissingLineageError(
                f"assertion lineage is missing: {', '.join(missing_assertions)}"
            )

        confidence = assertion.confidence
        try:
            with self._connection:
                self._connection.execute(
                    """
                    INSERT INTO assertions (
                        assertion_id, subject_id, predicate, value_kind, value_text,
                        state, polarity, valid_from, valid_to, method_family, method_name,
                        method_version, run_id, code_revision, confidence_dimension,
                        confidence_score_millionths, confidence_calibration_id,
                        supersedes_assertion_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        assertion.assertion_id,
                        assertion.subject_id,
                        assertion.predicate,
                        assertion.value.kind.value,
                        assertion.value.value,
                        assertion.state.value,
                        assertion.polarity.value,
                        assertion.valid_from.isoformat() if assertion.valid_from else None,
                        assertion.valid_to.isoformat() if assertion.valid_to else None,
                        assertion.method.family.value,
                        assertion.method.name,
                        assertion.method.version,
                        assertion.method.run_id,
                        assertion.method.code_revision,
                        confidence.dimension.value if confidence else None,
                        confidence.score_millionths if confidence else None,
                        confidence.calibration_id if confidence else None,
                        assertion.supersedes_assertion_id,
                        canonical_utc(assertion.created_at),
                    ),
                )
                self._connection.executemany(
                    """
                    INSERT INTO assertion_evidence (
                        assertion_id, ordinal, document_version_id, basis_sha256,
                        page_number, start_char, end_char, span_sha256, unavailable_reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            assertion.assertion_id,
                            ordinal,
                            evidence.document_version_id,
                            evidence.basis_sha256,
                            evidence.page_number,
                            evidence.start_char,
                            evidence.end_char,
                            evidence.span_sha256,
                            (
                                evidence.unavailable_reason.value
                                if evidence.unavailable_reason
                                else None
                            ),
                        )
                        for ordinal, evidence in enumerate(assertion.evidence)
                    ],
                )
                self._connection.executemany(
                    """
                    INSERT INTO assertion_inputs (assertion_id, ordinal, input_assertion_id)
                    VALUES (?, ?, ?)
                    """,
                    [
                        (assertion.assertion_id, ordinal, input_assertion_id)
                        for ordinal, input_assertion_id in enumerate(assertion.input_assertion_ids)
                    ],
                )
        except sqlite3.IntegrityError as exc:
            current = self.get_assertion(assertion.assertion_id)
            if current == assertion:
                return InsertOutcome.EXISTING
            raise AssertionConflictError(
                "assertion violated an immutable database constraint"
            ) from exc
        return InsertOutcome.CREATED

    def get_assertion(self, assertion_id: str) -> Assertion | None:
        row = self._connection.execute(
            f"SELECT {ASSERTION_COLUMNS} FROM assertions WHERE assertion_id = ?",
            (assertion_id,),
        ).fetchone()
        if row is None:
            return None
        evidence_rows = self._connection.execute(
            f"""
            SELECT {EVIDENCE_COLUMNS}
            FROM assertion_evidence
            WHERE assertion_id = ?
            ORDER BY ordinal ASC
            """,
            (assertion_id,),
        ).fetchall()
        input_rows = self._connection.execute(
            """
            SELECT input_assertion_id
            FROM assertion_inputs
            WHERE assertion_id = ?
            ORDER BY ordinal ASC
            """,
            (assertion_id,),
        ).fetchall()
        confidence = (
            Confidence(
                dimension=ConfidenceDimension(str(row[14])),
                score_millionths=int(str(row[15])) if row[15] is not None else None,
                calibration_id=str(row[16]) if row[16] is not None else None,
            )
            if row[14] is not None
            else None
        )
        return Assertion(
            assertion_id=str(row[0]),
            subject_id=str(row[1]),
            predicate=str(row[2]),
            value=AssertionValue(ValueKind(str(row[3])), str(row[4])),
            state=AssertionState(str(row[5])),
            polarity=Polarity(str(row[6])),
            valid_from=_optional_date(row[7]),
            valid_to=_optional_date(row[8]),
            method=AssertionMethod(
                family=MethodFamily(str(row[9])),
                name=str(row[10]),
                version=str(row[11]),
                run_id=str(row[12]),
                code_revision=str(row[13]),
            ),
            confidence=confidence,
            evidence=tuple(_evidence_from_row(evidence_row) for evidence_row in evidence_rows),
            input_assertion_ids=tuple(str(input_row[0]) for input_row in input_rows),
            supersedes_assertion_id=str(row[17]) if row[17] is not None else None,
            created_at=parse_canonical_utc(str(row[18])),
        )

    def add_review_decision(self, decision: ReviewDecision) -> InsertOutcome:
        existing_row = self._connection.execute(
            f"SELECT {REVIEW_COLUMNS} FROM review_decisions WHERE decision_id = ?",
            (decision.decision_id,),
        ).fetchone()
        if existing_row is not None:
            existing = _review_from_row(existing_row)
            if existing == decision:
                return InsertOutcome.EXISTING
            raise AssertionConflictError(
                f"decision_id {decision.decision_id} already identifies a different review"
            )
        if self.get_assertion(decision.assertion_id) is None:
            raise MissingLineageError(
                f"assertion_id {decision.assertion_id} must exist before review"
            )

        current = self.current_review_decision(decision.assertion_id)
        if current is None:
            if decision.supersedes_decision_id is not None:
                raise ReviewChainError(
                    "the first review decision cannot supersede another decision"
                )
        else:
            if decision.supersedes_decision_id != current.decision_id:
                raise ReviewChainError(
                    f"review must supersede current decision_id {current.decision_id}"
                )
            if decision.decided_at <= current.decided_at:
                raise ReviewChainError("review decision time must advance monotonically")

        try:
            with self._connection:
                self._connection.execute(
                    """
                    INSERT INTO review_decisions (
                        decision_id, assertion_id, outcome, reviewer_id, reviewer_role,
                        rationale, decided_at, supersedes_decision_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        decision.decision_id,
                        decision.assertion_id,
                        decision.outcome.value,
                        decision.reviewer_id,
                        decision.reviewer_role.value,
                        decision.rationale,
                        canonical_utc(decision.decided_at),
                        decision.supersedes_decision_id,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            row = self._connection.execute(
                f"SELECT {REVIEW_COLUMNS} FROM review_decisions WHERE decision_id = ?",
                (decision.decision_id,),
            ).fetchone()
            if row is not None and _review_from_row(row) == decision:
                return InsertOutcome.EXISTING
            raise AssertionConflictError(
                "review decision violated an immutable database constraint"
            ) from exc
        return InsertOutcome.CREATED

    def list_review_decisions(self, assertion_id: str) -> tuple[ReviewDecision, ...]:
        rows = self._connection.execute(
            f"""
            SELECT {REVIEW_COLUMNS}
            FROM review_decisions
            WHERE assertion_id = ?
            ORDER BY decided_at ASC, decision_id ASC
            """,
            (assertion_id,),
        ).fetchall()
        return tuple(_review_from_row(row) for row in rows)

    def current_review_decision(self, assertion_id: str) -> ReviewDecision | None:
        decisions = self.list_review_decisions(assertion_id)
        return decisions[-1] if decisions else None
