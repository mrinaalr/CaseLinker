from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from caselinker.assertions.models import (
    AssertionState,
    ConfidenceDimension,
    MethodFamily,
    Polarity,
)
from caselinker.documents.models import SourceDocumentVersion
from caselinker.extraction import ExtractionRun, PlatformMentionExtractor

FIXTURE_PATH = Path("data/fixtures/vnext/extraction/platform_mentions.v1.json")
CREATED_AT = datetime(2026, 8, 15, 7, 0, tzinfo=UTC)


def _document_version(text: str, *, include_text_hash: bool = True) -> SourceDocumentVersion:
    return SourceDocumentVersion.capture(
        version_id="docv_platform_fixture_001",
        document_id="doc_platform_fixture_001",
        content=text.encode(),
        retrieved_at=CREATED_AT,
        published_at=None,
        recorded_at=CREATED_AT,
        mime_type="text/plain",
        http_status=200,
        http_etag=None,
        http_last_modified=None,
        parser_name="fixture_parser",
        parser_version="1.0.0",
        normalized_text=text if include_text_hash else None,
    )


def _run(run_id: str = "run_platform_fixture_001") -> ExtractionRun:
    return ExtractionRun(run_id=run_id, code_revision="test-revision", created_at=CREATED_AT)


def _fixture_cases() -> list[dict[str, Any]]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0.0"
    assert payload["rule_set"] == "platform_mentions.v1"
    return list(payload["cases"])


@pytest.mark.parametrize("fixture", _fixture_cases(), ids=lambda item: item["fixture_id"])
def test_golden_platform_mentions(fixture: dict[str, Any]) -> None:
    text = fixture["text"]
    assertions = PlatformMentionExtractor().extract(
        subject_id="case_platform_fixture_001",
        document_version=_document_version(text),
        normalized_text=text,
        run=_run(),
    )

    actual = []
    for assertion in assertions:
        evidence = assertion.evidence[0]
        assert evidence.start_char is not None
        assert evidence.end_char is not None
        assert evidence.matches(text)
        actual.append(
            {
                "entity_id": assertion.value.value,
                "span": text[evidence.start_char : evidence.end_char],
            }
        )

        assert assertion.state is AssertionState.EXTRACTED
        assert assertion.polarity is Polarity.AFFIRMED
        assert assertion.method.family is MethodFamily.DETERMINISTIC_PATTERN
        assert assertion.confidence is not None
        assert assertion.confidence.dimension is ConfidenceDimension.EXTRACTION
        assert assertion.confidence.score_millionths is None
        assert assertion.input_assertion_ids == ()
        assert assertion.supersedes_assertion_id is None

    assert actual == fixture["expected"]


def test_same_run_is_byte_for_byte_idempotent() -> None:
    text = "Snapchat and Discord"
    extractor = PlatformMentionExtractor()
    arguments = {
        "subject_id": "case_platform_fixture_001",
        "document_version": _document_version(text),
        "normalized_text": text,
        "run": _run(),
    }

    assert extractor.extract(**arguments) == extractor.extract(**arguments)


def test_distinct_runs_have_distinct_candidate_identity() -> None:
    text = "Snapchat"
    extractor = PlatformMentionExtractor()
    common = {
        "subject_id": "case_platform_fixture_001",
        "document_version": _document_version(text),
        "normalized_text": text,
    }

    first = extractor.extract(**common, run=_run("run_first"))
    second = extractor.extract(**common, run=_run("run_second"))

    assert first[0].assertion_id != second[0].assertion_id


def test_rejects_text_from_another_document_version() -> None:
    with pytest.raises(ValueError, match="does not match"):
        PlatformMentionExtractor().extract(
            subject_id="case_platform_fixture_001",
            document_version=_document_version("Snapchat"),
            normalized_text="Discord",
            run=_run(),
        )


def test_rejects_document_version_without_normalized_text_identity() -> None:
    with pytest.raises(ValueError, match="does not identify"):
        PlatformMentionExtractor().extract(
            subject_id="case_platform_fixture_001",
            document_version=_document_version("Snapchat", include_text_hash=False),
            normalized_text="Snapchat",
            run=_run(),
        )


def test_empty_text_still_validates_subject_identity() -> None:
    with pytest.raises(ValueError, match="subject_id"):
        PlatformMentionExtractor().extract(
            subject_id="not-opaque",
            document_version=_document_version(""),
            normalized_text="",
            run=_run(),
        )


@pytest.mark.parametrize(
    ("run_id", "code_revision", "created_at", "message"),
    [
        ("bad run", "revision", CREATED_AT, "run_id"),
        ("run_valid", " revision", CREATED_AT, "code_revision"),
        (
            "run_valid",
            "revision",
            datetime(2026, 8, 15, 7, 0),
            "created_at",
        ),
    ],
)
def test_extraction_run_rejects_unstable_metadata(
    run_id: str,
    code_revision: str,
    created_at: datetime,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ExtractionRun(run_id=run_id, code_revision=code_revision, created_at=created_at)
