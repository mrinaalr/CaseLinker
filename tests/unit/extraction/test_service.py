from __future__ import annotations

from datetime import UTC, datetime

import pytest

from caselinker.assertions.models import Assertion
from caselinker.documents.models import SourceDocumentVersion
from caselinker.documents.ports import InsertOutcome
from caselinker.extraction import (
    ExtractionBatchResult,
    ExtractionRun,
    PlatformMentionExtractor,
    PlatformMentionPipeline,
)

NOW = datetime(2026, 8, 15, 9, 0, tzinfo=UTC)


class RecordingWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[Assertion, ...]] = []

    def add_assertions(self, assertions: tuple[Assertion, ...]) -> tuple[InsertOutcome, ...]:
        self.calls.append(assertions)
        return tuple(InsertOutcome.CREATED for _ in assertions)


def _version(text: str) -> SourceDocumentVersion:
    return SourceDocumentVersion.capture(
        version_id="docv_pipeline_fixture_001",
        document_id="doc_pipeline_fixture_001",
        content=text.encode(),
        retrieved_at=NOW,
        published_at=None,
        recorded_at=NOW,
        mime_type="text/plain",
        http_status=200,
        http_etag=None,
        http_last_modified=None,
        parser_name="fixture_parser",
        parser_version="1.0.0",
        normalized_text=text,
    )


def test_pipeline_submits_one_complete_ordered_batch() -> None:
    text = "Snapchat and Discord were named."
    writer = RecordingWriter()
    pipeline = PlatformMentionPipeline(
        extractor=PlatformMentionExtractor(),
        writer=writer,
    )

    result = pipeline.extract_and_store(
        subject_id="case_pipeline_fixture_001",
        document_version=_version(text),
        normalized_text=text,
        run=ExtractionRun("run_pipeline_001", "test-revision", NOW),
    )

    assert writer.calls == [result.assertions]
    assert [assertion.value.value for assertion in result.assertions] == [
        "platform_snapchat",
        "platform_discord",
    ]
    assert result.outcomes == (InsertOutcome.CREATED, InsertOutcome.CREATED)


def test_pipeline_submits_empty_batch_explicitly() -> None:
    writer = RecordingWriter()
    pipeline = PlatformMentionPipeline(
        extractor=PlatformMentionExtractor(),
        writer=writer,
    )

    result = pipeline.extract_and_store(
        subject_id="case_pipeline_fixture_001",
        document_version=_version("No allowlisted names."),
        normalized_text="No allowlisted names.",
        run=ExtractionRun("run_pipeline_001", "test-revision", NOW),
    )

    assert result == ExtractionBatchResult(assertions=(), outcomes=())
    assert writer.calls == [()]


def test_result_rejects_partial_outcome_vectors() -> None:
    text = "Snapchat"
    assertion = PlatformMentionExtractor().extract(
        subject_id="case_pipeline_fixture_001",
        document_version=_version(text),
        normalized_text=text,
        run=ExtractionRun("run_pipeline_001", "test-revision", NOW),
    )[0]

    with pytest.raises(ValueError, match="one persistence outcome"):
        ExtractionBatchResult(assertions=(assertion,), outcomes=())
