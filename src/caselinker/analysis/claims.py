"""Content-addressed claim cards with mandatory scope and limitations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from caselinker.analysis.cohorts import CohortResult
from caselinker.snapshots.manifest import canonical_json, sha256_bytes

CLAIM_SCHEMA_VERSION: Final = "1.0"
LIMITATIONS: Final = (
    "The snapshot is a selected public-enforcement corpus, not a population sample.",
    (
        "Counts describe distinct eligible legal-event units, not people, cases, "
        "documents, risk, causation, or prevalence."
    ),
    (
        "An event appears only when public source text supported extraction, human "
        "acceptance, resolution, graph projection, and SHACL validation."
    ),
)
_LABELS: Final = {
    "legal_event_arrest": "arrest",
    "legal_event_charge": "charging",
    "legal_event_indictment": "indictment",
    "legal_event_guilty_plea": "guilty-plea",
    "legal_event_conviction": "conviction",
    "legal_event_sentencing": "sentencing",
}


@dataclass(frozen=True, slots=True)
class ClaimCard:
    claim_id: str
    claim_text: str
    result: CohortResult
    limitations: tuple[str, ...]
    schema_version: str = CLAIM_SCHEMA_VERSION

    def to_dict(self, *, include_claim_id: bool = True) -> dict[str, object]:
        value: dict[str, object] = {
            "schema_version": self.schema_version,
            "claim_text": self.claim_text,
            "snapshot_id": self.result.snapshot.snapshot_id,
            "snapshot_manifest_sha256": self.result.snapshot.manifest_sha256,
            "query_id": self.result.query.query_id,
            "query_sha256": self.result.query.sha256,
            "unit": self.result.query.unit,
            "numerator": self.result.numerator,
            "denominator": self.result.denominator,
            "numerator_event_ids": list(self.result.numerator_event_ids),
            "denominator_event_ids": list(self.result.denominator_event_ids),
            "projection_sha256s": list(self.result.projection_sha256s),
            "shapes_sha256": self.result.shapes_sha256,
            "limitations": list(self.limitations),
        }
        if include_claim_id:
            value["claim_id"] = self.claim_id
        return value


class ClaimCardBuilder:
    def build(self, result: CohortResult) -> ClaimCard:
        label = _LABELS[result.query.event_type]
        text = (
            f"Within snapshot {result.snapshot.snapshot_id}, {result.numerator} of "
            f"{result.denominator} distinct eligible legal-event units were classified as "
            f"{label} events."
        )
        provisional = ClaimCard("claim_pending", text, result, LIMITATIONS)
        claim_id = "claim_" + sha256_bytes(
            canonical_json(provisional.to_dict(include_claim_id=False))
        )
        return ClaimCard(claim_id, text, result, LIMITATIONS)
