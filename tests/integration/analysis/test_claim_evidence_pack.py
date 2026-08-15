from __future__ import annotations

from pathlib import Path

from rdflib import Graph

from caselinker.analysis import (
    ClaimCardBuilder,
    ClaimCiEvaluator,
    ClaimExpectation,
    CohortQuery,
    EvidencePackAssembler,
    LegalEventCohortAnalyzer,
    SnapshotReference,
    ValidatedProjection,
)
from caselinker.graph import CacLegalEventProjector, ShaclValidator
from tests.unit.graph.test_cac_legal_events import ReviewReader, resolved_bundle


def test_reviewed_assertions_to_validated_claim_evidence_pack() -> None:
    assertions, decisions = resolved_bundle()
    projection = CacLegalEventProjector().project(
        assertions=assertions, reviews=ReviewReader(decisions)
    )
    shapes = Graph()
    shapes.parse(Path("schemas/rdf/cac-legal-event-projection-v1.shacl.ttl"), format="turtle")
    validation = ShaclValidator(shapes=shapes).validate(projection)
    result = LegalEventCohortAnalyzer().analyze(
        snapshot=SnapshotReference("snap_end_to_end_001", "e" * 64, (projection.sha256,)),
        query=CohortQuery("qry_end_to_end_charge_001", "legal_event_charge"),
        projections=(ValidatedProjection(projection, validation),),
    )

    claim = ClaimCardBuilder().build(result)
    pack = EvidencePackAssembler().assemble(claim)
    expectation = ClaimExpectation.pin(claim=claim, evidence_pack=pack)
    ci_report = ClaimCiEvaluator().evaluate(
        expectation=expectation, claim=claim, evidence_pack=pack
    )

    assert validation.conforms
    assert (result.numerator, result.denominator) == (1, 1)
    assert "1 of 1 distinct eligible legal-event units" in claim.claim_text
    assert pack.pack_id == f"epack_{pack.sha256}"
    assert ci_report.passed
