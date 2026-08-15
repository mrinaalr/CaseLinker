"""Snapshot-scoped cohort analysis and auditable research claims."""

from caselinker.analysis.claim_ci import (
    ClaimCiEvaluator,
    ClaimCiReport,
    ClaimDrift,
    ClaimExpectation,
)
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
from caselinker.analysis.pipeline import ClaimPipeline, ClaimPipelineError, PipelineResult

__all__ = [
    "ClaimCard",
    "ClaimCardBuilder",
    "ClaimCiEvaluator",
    "ClaimCiReport",
    "ClaimDrift",
    "ClaimExpectation",
    "ClaimPipeline",
    "ClaimPipelineError",
    "CohortAnalysisError",
    "CohortQuery",
    "CohortResult",
    "EvidencePack",
    "EvidencePackAssembler",
    "LegalEventCohortAnalyzer",
    "PipelineResult",
    "SnapshotReference",
    "ValidatedProjection",
]
