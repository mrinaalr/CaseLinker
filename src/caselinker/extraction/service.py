"""Application service for atomic platform-mention candidate persistence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from caselinker.assertions.models import Assertion
from caselinker.documents.models import SourceDocumentVersion
from caselinker.documents.ports import InsertOutcome
from caselinker.extraction.legal_events import AttributedSubject, LegalEventExtractor
from caselinker.extraction.models import ExtractionRun
from caselinker.extraction.platform_mentions import PlatformMentionExtractor


class AssertionBatchWriter(Protocol):
    """Minimum persistence capability required by an extraction pipeline."""

    def add_assertions(self, assertions: tuple[Assertion, ...]) -> tuple[InsertOutcome, ...]: ...


@dataclass(frozen=True, slots=True)
class ExtractionBatchResult:
    assertions: tuple[Assertion, ...]
    outcomes: tuple[InsertOutcome, ...]

    def __post_init__(self) -> None:
        if len(self.assertions) != len(self.outcomes):
            raise ValueError("every assertion must have one persistence outcome")


class PlatformMentionPipeline:
    """Extract candidates and submit the complete run as one storage batch."""

    def __init__(
        self,
        *,
        extractor: PlatformMentionExtractor,
        writer: AssertionBatchWriter,
    ) -> None:
        self._extractor = extractor
        self._writer = writer

    def extract_and_store(
        self,
        *,
        subject_id: str,
        document_version: SourceDocumentVersion,
        normalized_text: str,
        run: ExtractionRun,
    ) -> ExtractionBatchResult:
        assertions = self._extractor.extract(
            subject_id=subject_id,
            document_version=document_version,
            normalized_text=normalized_text,
            run=run,
        )
        outcomes = self._writer.add_assertions(assertions)
        return ExtractionBatchResult(assertions=assertions, outcomes=outcomes)


class LegalEventPipeline:
    """Extract attributed reported events and persist the run atomically."""

    def __init__(
        self,
        *,
        extractor: LegalEventExtractor,
        writer: AssertionBatchWriter,
    ) -> None:
        self._extractor = extractor
        self._writer = writer

    def extract_and_store(
        self,
        *,
        subject: AttributedSubject,
        document_version: SourceDocumentVersion,
        normalized_text: str,
        run: ExtractionRun,
    ) -> ExtractionBatchResult:
        assertions = self._extractor.extract(
            subject=subject,
            document_version=document_version,
            normalized_text=normalized_text,
            run=run,
        )
        outcomes = self._writer.add_assertions(assertions)
        return ExtractionBatchResult(assertions=assertions, outcomes=outcomes)
