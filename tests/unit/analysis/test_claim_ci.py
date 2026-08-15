from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from caselinker.analysis import (
    ClaimCard,
    ClaimCardBuilder,
    ClaimCiEvaluator,
    ClaimDrift,
    ClaimExpectation,
    CohortQuery,
    EvidencePack,
    EvidencePackAssembler,
    SnapshotReference,
)
from caselinker.analysis.claim_ci import ClaimCiReport
from caselinker.snapshots.manifest import sha256_bytes
from tests.unit.analysis.test_claims_and_pack import result


def artifacts() -> tuple[ClaimCard, EvidencePack, ClaimExpectation]:
    claim = ClaimCardBuilder().build(result())
    pack = EvidencePackAssembler().assemble(claim)
    return claim, pack, ClaimExpectation.pin(claim=claim, evidence_pack=pack)


def test_pinned_claim_passes_without_findings() -> None:
    claim, pack, expectation = artifacts()

    report = ClaimCiEvaluator().evaluate(expectation=expectation, claim=claim, evidence_pack=pack)

    assert report.passed
    assert report.findings == ()
    assert report.to_dict()["passed"] is True


def test_pinned_expectation_matches_reviewed_golden_contract() -> None:
    _, _, expectation = artifacts()
    expected = json.loads(
        Path(
            "data/fixtures/vnext/analysis/legal_event_claim_expectation_v1.golden.json"
        ).read_text()
    )

    assert expectation.to_dict() == expected


def test_snapshot_query_counts_and_membership_drift_are_distinguished() -> None:
    claim, _, expectation = artifacts()
    original = claim.result
    changed_snapshot = replace(
        original.snapshot,
        manifest_sha256="c" * 64,
    )
    changed_result = replace(
        original,
        snapshot=changed_snapshot,
        query=CohortQuery("qry_ci_sentencing_001", "legal_event_sentencing"),
        numerator=0,
        numerator_event_ids=(),
        denominator_event_ids=("event_analysis_001", "event_analysis_003"),
    )
    changed_claim = replace(claim, result=changed_result)

    report = ClaimCiEvaluator().evaluate(
        expectation=expectation,
        claim=changed_claim,
        evidence_pack=EvidencePackAssembler().assemble(changed_claim),
    )

    assert ClaimDrift.SNAPSHOT in report.findings
    assert ClaimDrift.QUERY in report.findings
    assert ClaimDrift.COUNTS in report.findings
    assert ClaimDrift.NUMERATOR_MEMBERSHIP in report.findings
    assert ClaimDrift.DENOMINATOR_MEMBERSHIP in report.findings
    assert ClaimDrift.CLAIM_CONTENT_IDENTITY in report.findings


def test_projection_shapes_limitations_and_claim_identity_drift_are_detected() -> None:
    claim, _, expectation = artifacts()
    original = claim.result
    changed_result = replace(
        original,
        projection_sha256s=("9" * 64,),
        shapes_sha256="8" * 64,
    )
    changed_claim = replace(
        claim,
        claim_id="claim_tampered",
        result=changed_result,
        limitations=("A materially different limitation.",),
    )
    changed_pack = EvidencePackAssembler().assemble(changed_claim)

    report = ClaimCiEvaluator().evaluate(
        expectation=expectation, claim=changed_claim, evidence_pack=changed_pack
    )

    assert ClaimDrift.PROJECTIONS in report.findings
    assert ClaimDrift.SHAPES in report.findings
    assert ClaimDrift.LIMITATIONS in report.findings
    assert ClaimDrift.CLAIM_ID in report.findings
    assert ClaimDrift.CLAIM_CONTENT_IDENTITY in report.findings
    assert ClaimDrift.EVIDENCE_PACK_ID in report.findings


def test_evidence_pack_must_be_the_exact_rebuild_for_claim() -> None:
    claim, _, expectation = artifacts()
    payload = b"{}"
    digest = sha256_bytes(payload)
    unrelated = EvidencePack(f"epack_{digest}", payload, digest)

    report = ClaimCiEvaluator().evaluate(
        expectation=expectation,
        claim=claim,
        evidence_pack=unrelated,
    )

    assert ClaimDrift.EVIDENCE_PACK_ID in report.findings
    assert ClaimDrift.EVIDENCE_PACK_CONTENT in report.findings


def test_expectation_identity_cannot_be_reused_after_edit() -> None:
    _, _, expectation = artifacts()

    with pytest.raises(ValueError, match="does not identify"):
        replace(expectation, numerator=0)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"expectation_id": "bad"}, "content-addressed"),
        ({"schema_version": "2.0"}, "schema_version"),
        ({"query_sha256": "bad"}, "query_sha256"),
        ({"unit": "case"}, "legal_event"),
        ({"denominator": 0}, "nonempty valid ratio"),
        ({"claim_id": "bad"}, "claim_ namespace"),
        ({"evidence_pack_id": "bad"}, "epack_ namespace"),
    ],
)
def test_expectation_boundaries_fail_closed(changes: dict[str, object], message: str) -> None:
    _, _, expectation = artifacts()

    with pytest.raises(ValueError, match=message):
        replace(expectation, **changes)


def test_expectation_serialization_includes_content_identity() -> None:
    _, _, expectation = artifacts()

    assert expectation.to_dict()["expectation_id"] == expectation.expectation_id


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.pop("query_sha256"),
        lambda value: value.update({"query_sha256": 42}),
        lambda value: value.update({"numerator": True}),
    ],
)
def test_expectation_deserialization_rejects_contract_errors(mutation: object) -> None:
    _, _, expectation = artifacts()
    value = expectation.to_dict()
    mutation(value)  # type: ignore[operator]

    with pytest.raises(ValueError):
        ClaimExpectation.from_dict(value)


def test_report_rejects_duplicate_findings() -> None:
    _, _, expectation = artifacts()

    with pytest.raises(ValueError, match="must not repeat"):
        ClaimCiReport(
            expectation.expectation_id,
            expectation.claim_id,
            expectation.evidence_pack_id,
            (ClaimDrift.COUNTS, ClaimDrift.COUNTS),
        )


@pytest.mark.parametrize(
    ("expectation_id", "claim_id", "pack_id", "message"),
    [
        ("bad", "claim_valid", "epack_valid", "expect_"),
        ("expect_" + "1" * 64, "bad", "epack_valid", "claim_"),
        ("expect_" + "1" * 64, "claim_valid", "bad", "epack_"),
    ],
)
def test_report_identifiers_are_namespaced(
    expectation_id: str, claim_id: str, pack_id: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        ClaimCiReport(expectation_id, claim_id, pack_id, ())


def test_snapshot_output_inventory_remains_part_of_typed_claim_input() -> None:
    claim, _, _ = artifacts()
    snapshot = claim.result.snapshot

    assert isinstance(snapshot, SnapshotReference)
    assert set(claim.result.projection_sha256s) <= set(snapshot.output_sha256s)
