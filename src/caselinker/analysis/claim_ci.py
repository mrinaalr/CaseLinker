"""Executable regression contracts for snapshot-scoped research claims."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, TypedDict

from caselinker.analysis.claims import ClaimCard
from caselinker.analysis.evidence_pack import EvidencePack, EvidencePackAssembler
from caselinker.snapshots.manifest import SHA256_PATTERN, canonical_json, sha256_bytes

EXPECTATION_SCHEMA_VERSION: Final = "1.0"
EXPECTATION_ID_PATTERN: Final = re.compile(r"^expect_[0-9a-f]{64}$")


def _sequence_digest(values: tuple[str, ...]) -> str:
    return sha256_bytes(canonical_json(list(values)))


class _ExpectationValues(TypedDict):
    schema_version: str
    snapshot_manifest_sha256: str
    query_sha256: str
    unit: str
    numerator: int
    denominator: int
    numerator_membership_sha256: str
    denominator_membership_sha256: str
    projections_sha256: str
    shapes_sha256: str
    limitations_sha256: str
    claim_id: str
    evidence_pack_id: str


class ClaimDrift(StrEnum):
    SNAPSHOT = "snapshot"
    QUERY = "query"
    UNIT = "unit"
    COUNTS = "counts"
    NUMERATOR_MEMBERSHIP = "numerator_membership"
    DENOMINATOR_MEMBERSHIP = "denominator_membership"
    PROJECTIONS = "projections"
    SHAPES = "shapes"
    LIMITATIONS = "limitations"
    CLAIM_ID = "claim_id"
    CLAIM_CONTENT_IDENTITY = "claim_content_identity"
    EVIDENCE_PACK_ID = "evidence_pack_id"
    EVIDENCE_PACK_CONTENT = "evidence_pack_content"


@dataclass(frozen=True, slots=True)
class ClaimExpectation:
    expectation_id: str
    snapshot_manifest_sha256: str
    query_sha256: str
    unit: str
    numerator: int
    denominator: int
    numerator_membership_sha256: str
    denominator_membership_sha256: str
    projections_sha256: str
    shapes_sha256: str
    limitations_sha256: str
    claim_id: str
    evidence_pack_id: str
    schema_version: str = EXPECTATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if EXPECTATION_ID_PATTERN.fullmatch(self.expectation_id) is None:
            raise ValueError("expectation_id must be content-addressed")
        if self.schema_version != EXPECTATION_SCHEMA_VERSION:
            raise ValueError("unsupported expectation schema_version")
        for field, value in (
            ("snapshot_manifest_sha256", self.snapshot_manifest_sha256),
            ("query_sha256", self.query_sha256),
            ("numerator_membership_sha256", self.numerator_membership_sha256),
            ("denominator_membership_sha256", self.denominator_membership_sha256),
            ("projections_sha256", self.projections_sha256),
            ("shapes_sha256", self.shapes_sha256),
            ("limitations_sha256", self.limitations_sha256),
        ):
            if SHA256_PATTERN.fullmatch(value) is None:
                raise ValueError(f"{field} must be a lowercase SHA-256 digest")
        if self.unit != "legal_event":
            raise ValueError("Claim CI currently supports legal_event units only")
        if self.denominator < 1 or not 0 <= self.numerator <= self.denominator:
            raise ValueError("expected counts must define a nonempty valid ratio")
        if not self.claim_id.startswith("claim_"):
            raise ValueError("claim_id must use the claim_ namespace")
        if not self.evidence_pack_id.startswith("epack_"):
            raise ValueError("evidence_pack_id must use the epack_ namespace")
        expected_id = "expect_" + sha256_bytes(
            canonical_json(self.to_dict(include_expectation_id=False))
        )
        if self.expectation_id != expected_id:
            raise ValueError("expectation_id does not identify the expectation content")

    def to_dict(self, *, include_expectation_id: bool = True) -> dict[str, object]:
        value: dict[str, object] = {
            "schema_version": self.schema_version,
            "snapshot_manifest_sha256": self.snapshot_manifest_sha256,
            "query_sha256": self.query_sha256,
            "unit": self.unit,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "numerator_membership_sha256": self.numerator_membership_sha256,
            "denominator_membership_sha256": self.denominator_membership_sha256,
            "projections_sha256": self.projections_sha256,
            "shapes_sha256": self.shapes_sha256,
            "limitations_sha256": self.limitations_sha256,
            "claim_id": self.claim_id,
            "evidence_pack_id": self.evidence_pack_id,
        }
        if include_expectation_id:
            value["expectation_id"] = self.expectation_id
        return value

    @classmethod
    def pin(cls, *, claim: ClaimCard, evidence_pack: EvidencePack) -> ClaimExpectation:
        values = cls._values(claim=claim, evidence_pack=evidence_pack)
        expectation_id = "expect_" + sha256_bytes(canonical_json(values))
        return cls(expectation_id=expectation_id, **values)

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> ClaimExpectation:
        allowed = {
            "expectation_id",
            "schema_version",
            "snapshot_manifest_sha256",
            "query_sha256",
            "unit",
            "numerator",
            "denominator",
            "numerator_membership_sha256",
            "denominator_membership_sha256",
            "projections_sha256",
            "shapes_sha256",
            "limitations_sha256",
            "claim_id",
            "evidence_pack_id",
        }
        if set(value) != allowed:
            raise ValueError("claim expectation fields do not match the v1 contract")

        def text(field: str) -> str:
            raw = value[field]
            if not isinstance(raw, str):
                raise ValueError(f"{field} must be a string")
            return raw

        def integer(field: str) -> int:
            raw = value[field]
            if isinstance(raw, bool) or not isinstance(raw, int):
                raise ValueError(f"{field} must be an integer")
            return raw

        return cls(
            expectation_id=text("expectation_id"),
            schema_version=text("schema_version"),
            snapshot_manifest_sha256=text("snapshot_manifest_sha256"),
            query_sha256=text("query_sha256"),
            unit=text("unit"),
            numerator=integer("numerator"),
            denominator=integer("denominator"),
            numerator_membership_sha256=text("numerator_membership_sha256"),
            denominator_membership_sha256=text("denominator_membership_sha256"),
            projections_sha256=text("projections_sha256"),
            shapes_sha256=text("shapes_sha256"),
            limitations_sha256=text("limitations_sha256"),
            claim_id=text("claim_id"),
            evidence_pack_id=text("evidence_pack_id"),
        )

    @staticmethod
    def _values(*, claim: ClaimCard, evidence_pack: EvidencePack) -> _ExpectationValues:
        result = claim.result
        return {
            "schema_version": EXPECTATION_SCHEMA_VERSION,
            "snapshot_manifest_sha256": result.snapshot.manifest_sha256,
            "query_sha256": result.query.sha256,
            "unit": result.query.unit,
            "numerator": result.numerator,
            "denominator": result.denominator,
            "numerator_membership_sha256": _sequence_digest(result.numerator_event_ids),
            "denominator_membership_sha256": _sequence_digest(result.denominator_event_ids),
            "projections_sha256": _sequence_digest(result.projection_sha256s),
            "shapes_sha256": result.shapes_sha256,
            "limitations_sha256": _sequence_digest(claim.limitations),
            "claim_id": claim.claim_id,
            "evidence_pack_id": evidence_pack.pack_id,
        }


@dataclass(frozen=True, slots=True)
class ClaimCiReport:
    expectation_id: str
    observed_claim_id: str
    observed_evidence_pack_id: str
    findings: tuple[ClaimDrift, ...]

    def __post_init__(self) -> None:
        if EXPECTATION_ID_PATTERN.fullmatch(self.expectation_id) is None:
            raise ValueError("expectation_id must use the expect_ content namespace")
        if not self.observed_claim_id.startswith("claim_"):
            raise ValueError("observed_claim_id must use the claim_ namespace")
        if not self.observed_evidence_pack_id.startswith("epack_"):
            raise ValueError("observed_evidence_pack_id must use the epack_ namespace")
        if len(set(self.findings)) != len(self.findings):
            raise ValueError("Claim CI findings must not repeat")

    @property
    def passed(self) -> bool:
        return not self.findings

    def to_dict(self) -> dict[str, object]:
        return {
            "expectation_id": self.expectation_id,
            "observed_claim_id": self.observed_claim_id,
            "observed_evidence_pack_id": self.observed_evidence_pack_id,
            "passed": self.passed,
            "findings": [finding.value for finding in self.findings],
        }


class ClaimCiEvaluator:
    """Compare regenerated artifacts with an explicitly reviewed expectation."""

    def evaluate(
        self,
        *,
        expectation: ClaimExpectation,
        claim: ClaimCard,
        evidence_pack: EvidencePack,
    ) -> ClaimCiReport:
        result = claim.result
        findings: list[ClaimDrift] = []

        def differs(observed: object, expected: object, drift: ClaimDrift) -> None:
            if observed != expected:
                findings.append(drift)

        differs(
            result.snapshot.manifest_sha256,
            expectation.snapshot_manifest_sha256,
            ClaimDrift.SNAPSHOT,
        )
        differs(result.query.sha256, expectation.query_sha256, ClaimDrift.QUERY)
        differs(result.query.unit, expectation.unit, ClaimDrift.UNIT)
        differs(
            (result.numerator, result.denominator),
            (expectation.numerator, expectation.denominator),
            ClaimDrift.COUNTS,
        )
        differs(
            _sequence_digest(result.numerator_event_ids),
            expectation.numerator_membership_sha256,
            ClaimDrift.NUMERATOR_MEMBERSHIP,
        )
        differs(
            _sequence_digest(result.denominator_event_ids),
            expectation.denominator_membership_sha256,
            ClaimDrift.DENOMINATOR_MEMBERSHIP,
        )
        differs(
            _sequence_digest(result.projection_sha256s),
            expectation.projections_sha256,
            ClaimDrift.PROJECTIONS,
        )
        differs(result.shapes_sha256, expectation.shapes_sha256, ClaimDrift.SHAPES)
        differs(
            _sequence_digest(claim.limitations),
            expectation.limitations_sha256,
            ClaimDrift.LIMITATIONS,
        )
        differs(claim.claim_id, expectation.claim_id, ClaimDrift.CLAIM_ID)
        expected_claim_id = "claim_" + sha256_bytes(
            canonical_json(claim.to_dict(include_claim_id=False))
        )
        differs(claim.claim_id, expected_claim_id, ClaimDrift.CLAIM_CONTENT_IDENTITY)
        differs(
            evidence_pack.pack_id,
            expectation.evidence_pack_id,
            ClaimDrift.EVIDENCE_PACK_ID,
        )
        rebuilt_pack = EvidencePackAssembler().assemble(claim)
        differs(
            (evidence_pack.pack_id, evidence_pack.canonical_json),
            (rebuilt_pack.pack_id, rebuilt_pack.canonical_json),
            ClaimDrift.EVIDENCE_PACK_CONTENT,
        )
        return ClaimCiReport(
            expectation.expectation_id,
            claim.claim_id,
            evidence_pack.pack_id,
            tuple(findings),
        )
