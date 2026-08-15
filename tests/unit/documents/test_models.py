from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from caselinker.documents.models import (
    SourceDocument,
    SourceDocumentVersion,
    canonical_utc,
    parse_canonical_utc,
)

NOW = datetime(2026, 8, 15, 8, 0, tzinfo=UTC)


def _document() -> SourceDocument:
    return SourceDocument(
        document_id="doc_example_001",
        source_id="doj_ceos",
        canonical_url="https://www.justice.gov/example?id=1",
        canonicalization_version="2",
        document_type="press_release",
        recorded_at=NOW,
    )


def _version() -> SourceDocumentVersion:
    return SourceDocumentVersion.capture(
        version_id="docv_example_001",
        document_id="doc_example_001",
        content=b"public synthetic fixture",
        retrieved_at=NOW,
        published_at=NOW - timedelta(days=1),
        recorded_at=NOW + timedelta(seconds=1),
        mime_type="text/html",
        http_status=200,
        http_etag='"fixture-v1"',
        http_last_modified=NOW - timedelta(days=1),
        parser_name="trafilatura",
        parser_version="2.0.0",
        normalized_text="Public synthetic fixture",
    )


def test_document_accepts_stable_identity() -> None:
    assert _document().document_id == "doc_example_001"


def test_capture_derives_all_content_addressed_values() -> None:
    version = _version()
    expected_content_hash = hashlib.sha256(b"public synthetic fixture").hexdigest()

    assert version.content_sha256 == expected_content_hash
    assert version.byte_length == 24
    assert version.storage_key == f"sha256/{expected_content_hash[:2]}/{expected_content_hash}"
    assert version.normalized_text_sha256 == hashlib.sha256(b"Public synthetic fixture").hexdigest()


def test_capture_without_normalized_text_records_no_text_hash() -> None:
    version = SourceDocumentVersion.capture(
        version_id="docv_example_002",
        document_id="doc_example_001",
        content=b"bytes",
        retrieved_at=NOW,
        published_at=None,
        recorded_at=NOW,
        mime_type="application/pdf",
        http_status=200,
        http_etag=None,
        http_last_modified=None,
        parser_name="identity",
        parser_version="1",
        normalized_text=None,
    )

    assert version.normalized_text_sha256 is None


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("document_id", "case_001", "doc_ identifier"),
        ("source_id", "DOJ CEOS", "stable lowercase"),
        ("canonical_url", "file:///tmp/source", "absolute HTTP"),
        ("canonical_url", "https://user:secret@example.org/a", "credentials"),
        (
            "canonical_url",
            "https://example.org/a?access_token=secret",
            "sensitive query",
        ),
        ("canonical_url", "https://example.org/a#span", "fragment"),
        ("canonicalization_version", "bad version", "stable token"),
        ("document_type", "Press Release", "snake_case"),
        ("recorded_at", datetime(2026, 8, 15), "timezone-aware UTC"),
    ],
)
def test_document_rejects_ambiguous_identity(field: str, value: object, message: str) -> None:
    values = {
        "document_id": "doc_example_001",
        "source_id": "doj_ceos",
        "canonical_url": "https://example.org/a",
        "canonicalization_version": "2",
        "document_type": "press_release",
        "recorded_at": NOW,
    }
    values[field] = value

    with pytest.raises(ValueError, match=message):
        SourceDocument(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("version_id", "version_001", "docv_ identifier"),
        ("document_id", "bad", "doc_ identifier"),
        ("content_sha256", "bad", "SHA-256"),
        ("byte_length", -1, "non-negative integer"),
        ("byte_length", True, "non-negative integer"),
        ("storage_key", "elsewhere", "content-addressed"),
        ("retrieved_at", datetime(2026, 8, 15), "timezone-aware UTC"),
        ("published_at", datetime(2026, 8, 14), "timezone-aware UTC"),
        ("recorded_at", NOW.astimezone(timezone(timedelta(hours=-8))), "timezone-aware UTC"),
        ("mime_type", "text/html; charset=utf-8", "valid media type"),
        ("http_status", 304, "complete retrieval"),
        ("http_etag", " bad ", "trimmed"),
        ("http_last_modified", datetime(2026, 8, 14), "timezone-aware UTC"),
        ("parser_name", "bad parser", "stable token"),
        ("parser_version", "", "stable token"),
        ("normalized_text_sha256", "bad", "SHA-256"),
    ],
)
def test_version_rejects_invalid_provenance(field: str, value: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_version(), **{field: value})


def test_canonical_timestamp_round_trip_is_stable() -> None:
    serialized = canonical_utc(NOW)

    assert serialized == "2026-08-15T08:00:00.000000Z"
    assert parse_canonical_utc(serialized) == NOW


def test_timestamp_parser_rejects_noncanonical_offset() -> None:
    with pytest.raises(ValueError, match="end in Z"):
        parse_canonical_utc("2026-08-15T08:00:00+00:00")
