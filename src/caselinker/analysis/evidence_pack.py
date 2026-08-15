"""Deterministic Evidence Pack index assembly without source text or display labels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from caselinker.analysis.claims import ClaimCard
from caselinker.snapshots.manifest import canonical_json, sha256_bytes

EVIDENCE_PACK_SCHEMA_VERSION: Final = "1.0"


@dataclass(frozen=True, slots=True)
class EvidencePack:
    pack_id: str
    canonical_json: bytes
    sha256: str

    def __post_init__(self) -> None:
        if sha256_bytes(self.canonical_json) != self.sha256:
            raise ValueError("sha256 must identify canonical_json")
        if self.pack_id != f"epack_{self.sha256}":
            raise ValueError("pack_id must be content-addressed by sha256")


class EvidencePackAssembler:
    def assemble(self, claim: ClaimCard) -> EvidencePack:
        payload = {
            "schema_version": EVIDENCE_PACK_SCHEMA_VERSION,
            "claim_card": claim.to_dict(),
            "contents": {
                "snapshot_manifest_sha256": claim.result.snapshot.manifest_sha256,
                "query_sha256": claim.result.query.sha256,
                "projection_sha256s": list(claim.result.projection_sha256s),
                "shapes_sha256": claim.result.shapes_sha256,
            },
            "exclusions": [
                "source_text",
                "personal_display_labels",
                "disclosure_authorization",
            ],
        }
        serialized = canonical_json(payload)
        digest = sha256_bytes(serialized)
        return EvidencePack(f"epack_{digest}", serialized, digest)
