from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from caselinker.assertions.models import (
    Assertion,
    AssertionState,
    ConfidenceDimension,
    MethodFamily,
    Polarity,
    ValueKind,
)
from caselinker.documents.models import SourceDocumentVersion
from caselinker.extraction import AttributedSubject, ExtractionRun, LegalEventExtractor
from caselinker.extraction.legal_events import (
    REPORTED_EVENT_DATE_PREDICATE,
    REPORTED_EVENT_TYPE_PREDICATE,
    REPORTED_SUBJECT_PREDICATE,
)

FIXTURE_PATH = Path("data/fixtures/vnext/extraction/legal_events.v1.json")
CREATED_AT = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


def _payload() -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0.0"
    assert payload["rule_set"] == "legal_events.v1"
    return payload


def _subject() -> AttributedSubject:
    source = _payload()["subject"]
    return AttributedSubject(source["subject_id"], tuple(source["aliases"]))


def _version(text: str, *, include_text_hash: bool = True) -> SourceDocumentVersion:
    return SourceDocumentVersion.capture(
        version_id="docv_legal_fixture_001",
        document_id="doc_legal_fixture_001",
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


def _run(run_id: str = "run_legal_fixture_001") -> ExtractionRun:
    return ExtractionRun(run_id, "test-revision", CREATED_AT)


def _span(assertion: Assertion, text: str, ordinal: int = 0) -> str:
    evidence = assertion.evidence[ordinal]
    assert evidence.start_char is not None
    assert evidence.end_char is not None
    assert evidence.matches(text)
    return text[evidence.start_char : evidence.end_char]


def _actual_events(assertions: tuple[Assertion, ...], text: str) -> list[dict[str, str]]:
    relations = [
        assertion for assertion in assertions if assertion.predicate == REPORTED_SUBJECT_PREDICATE
    ]
    actual = []
    for relation in relations:
        event_id = relation.value.value
        event_type = next(
            assertion
            for assertion in assertions
            if assertion.subject_id == event_id
            and assertion.predicate == REPORTED_EVENT_TYPE_PREDICATE
        )
        dates = [
            assertion
            for assertion in assertions
            if assertion.subject_id == event_id
            and assertion.predicate == REPORTED_EVENT_DATE_PREDICATE
        ]
        item = {
            "event_type": event_type.value.value,
            "span": _span(relation, text),
        }
        if dates:
            assert len(dates) == 1
            item["date"] = dates[0].value.value
            item["date_span"] = _span(dates[0], text, 1)
            assert _span(dates[0], text, 0) == item["span"]
        actual.append(item)
    return actual


@pytest.mark.parametrize(
    "fixture",
    _payload()["cases"],
    ids=lambda item: item["fixture_id"],
)
def test_golden_legal_events(fixture: dict[str, Any]) -> None:
    text = fixture["text"]
    assertions = LegalEventExtractor().extract(
        subject=_subject(),
        document_version=_version(text),
        normalized_text=text,
        run=_run(),
    )

    assert _actual_events(assertions, text) == fixture["expected"]
    for assertion in assertions:
        assert assertion.state is AssertionState.EXTRACTED
        assert assertion.polarity is Polarity.AFFIRMED
        assert assertion.method.family is MethodFamily.DETERMINISTIC_PATTERN
        assert assertion.confidence is not None
        assert assertion.confidence.dimension is ConfidenceDimension.EXTRACTION
        assert assertion.confidence.score_millionths is None
        assert assertion.input_assertion_ids == ()
        assert assertion.supersedes_assertion_id is None
        assert all(evidence.matches(text) for evidence in assertion.evidence)
        if assertion.predicate == REPORTED_EVENT_DATE_PREDICATE:
            assert assertion.value.kind is ValueKind.DATE
            assert len(assertion.evidence) == 2
        else:
            assert assertion.value.kind is ValueKind.ENTITY
            assert len(assertion.evidence) == 1


def test_event_identity_survives_a_distinct_extraction_run() -> None:
    text = "Example Defendant was charged."
    extractor = LegalEventExtractor()
    common = {
        "subject": _subject(),
        "document_version": _version(text),
        "normalized_text": text,
    }

    first = extractor.extract(**common, run=_run("run_first"))
    second = extractor.extract(**common, run=_run("run_second"))

    first_relation = next(item for item in first if item.predicate == REPORTED_SUBJECT_PREDICATE)
    second_relation = next(item for item in second if item.predicate == REPORTED_SUBJECT_PREDICATE)
    assert first_relation.value.value == second_relation.value.value
    assert first_relation.assertion_id != second_relation.assertion_id


@pytest.mark.parametrize(
    ("subject_id", "aliases", "message"),
    [
        ("not-opaque", ("Example Defendant",), "subject_id"),
        ("party_example_001", (), "between 1 and 16"),
        ("party_example_001", ("Defendant",), "two lexical words"),
        ("party_example_001", ("Example Defendant", "example defendant"), "unique"),
        ("party_example_001", (" Example Defendant",), "trimmed"),
    ],
)
def test_attributed_subject_rejects_unsafe_alias_contracts(
    subject_id: str,
    aliases: tuple[str, ...],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        AttributedSubject(subject_id, aliases)


def test_rejects_text_from_another_document_version() -> None:
    with pytest.raises(ValueError, match="does not match"):
        LegalEventExtractor().extract(
            subject=_subject(),
            document_version=_version("Example Defendant was charged."),
            normalized_text="Example Defendant was arrested.",
            run=_run(),
        )


def test_rejects_document_version_without_normalized_text_identity() -> None:
    text = "Example Defendant was charged."
    with pytest.raises(ValueError, match="does not identify"):
        LegalEventExtractor().extract(
            subject=_subject(),
            document_version=_version(text, include_text_hash=False),
            normalized_text=text,
            run=_run(),
        )
