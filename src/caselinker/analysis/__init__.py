"""Snapshot-scoped cohort analysis and auditable research claims."""

from caselinker.analysis.claims import ClaimCard, ClaimCardBuilder
from caselinker.analysis.cohorts import (
    CohortAnalysisError,
    CohortQuery,
    CohortResult,
    LegalEventCohortAnalyzer,
    SnapshotReference,
    ValidatedProjection,
)
from caselinker.analysis.evidence_pack import EvidencePack, EvidencePackAssembler

__all__ = [
    "ClaimCard",
    "ClaimCardBuilder",
    "CohortAnalysisError",
    "CohortQuery",
    "CohortResult",
    "EvidencePack",
    "EvidencePackAssembler",
    "LegalEventCohortAnalyzer",
    "SnapshotReference",
    "ValidatedProjection",
]
