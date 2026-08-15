from __future__ import annotations

import json
from pathlib import Path

import pytest

from caselinker.analysis import ClaimCardBuilder, EvidencePack, EvidencePackAssembler
from caselinker.analysis.claims import LIMITATIONS
from caselinker.analysis.cohorts import CohortResult, LegalEventCohortAnalyzer
from tests.unit.analysis.test_cohorts import query, snapshot, validated_projection


def result() -> CohortResult:
    projections = (
        validated_projection("event_analysis_001", "legal_event_charge", assertion_suffix="001"),
        validated_projection("event_analysis_002", "legal_event_arrest", assertion_suffix="002"),
    )
    return LegalEventCohortAnalyzer().analyze(
        snapshot=snapshot(projections),
        query=query(),
        projections=projections,
    )


def test_claim_card_names_scope_unit_numerator_denominator_and_limitations() -> None:
    card = ClaimCardBuilder().build(result())

    assert card.claim_id.startswith("claim_")
    assert card.claim_text == (
        "Within snapshot snap_analysis_fixture_001, 1 of 2 distinct eligible legal-event "
        "units were classified as charging events."
    )
    assert card.limitations == LIMITATIONS
    payload = card.to_dict()
    assert payload["unit"] == "legal_event"
    assert (payload["numerator"], payload["denominator"]) == (1, 2)
    assert "prevalence" in " ".join(payload["limitations"])  # type: ignore[arg-type]


def test_claim_and_evidence_pack_are_byte_reproducible_and_content_addressed() -> None:
    card = ClaimCardBuilder().build(result())
    first = EvidencePackAssembler().assemble(card)
    second = EvidencePackAssembler().assemble(card)

    assert first == second
    assert first.pack_id == f"epack_{first.sha256}"
    payload = json.loads(first.canonical_json)
    assert payload["claim_card"]["claim_id"] == card.claim_id
    assert payload["contents"]["snapshot_manifest_sha256"] == "b" * 64
    assert payload["exclusions"] == [
        "source_text",
        "personal_display_labels",
        "disclosure_authorization",
    ]


def test_claim_and_pack_match_pinned_golden_identity() -> None:
    expected = json.loads(
        Path("data/fixtures/vnext/analysis/legal_event_claim_v1.golden.json").read_text()
    )
    card = ClaimCardBuilder().build(result())
    pack = EvidencePackAssembler().assemble(card)

    assert card.claim_id == expected["claim_id"]
    assert pack.pack_id == expected["evidence_pack_id"]
    assert card.result.numerator == expected["numerator"]
    assert card.result.denominator == expected["denominator"]
    assert card.result.query.unit == expected["unit"]
    assert card.result.query.sha256 == expected["query_sha256"]


@pytest.mark.parametrize(
    ("pack_id", "digest", "message"),
    [
        ("epack_wrong", "0" * 64, "sha256"),
        ("epack_wrong", None, "pack_id"),
    ],
)
def test_evidence_pack_rejects_invalid_identity(
    pack_id: str, digest: str | None, message: str
) -> None:
    payload = b"{}"
    import hashlib

    actual = hashlib.sha256(payload).hexdigest()
    with pytest.raises(ValueError, match=message):
        EvidencePack(pack_id, payload, actual if digest is None else digest)
