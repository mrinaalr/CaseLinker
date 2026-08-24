"""Unit tests for document identity, URL canonicalization, and content addressing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from provenance import (
    CANONICALIZATION_VERSION,
    DEFAULT_DOCUMENT_TYPE,
    JINA_DOCUMENT_TYPE,
    JINA_PARSER_NAME,
    FetchedCapture,
    SourceDocument,
    SourceDocumentVersion,
    canonicalize_url,
    document_id_for,
    models_from_sidecar_row,
    provenance_sidecar_path,
    sha256_bytes,
    source_id_for_url,
    storage_key_for,
    version_id_for,
    write_provenance_sidecar,
)


def _utc(year=2026, month=8, day=22, hour=12) -> datetime:
    return datetime(year, month, day, hour, 0, 0, tzinfo=UTC)


def test_canonicalize_url_lowers_host_and_drops_fragment_and_slash():
    raw = "HTTPS://News.Example.GOV/Press/Release/?utm_source=x&keep=1#section"
    assert canonicalize_url(raw) == "https://news.example.gov/Press/Release?keep=1"


def test_canonicalize_url_strips_default_port_and_credentials_rejected():
    assert canonicalize_url("https://agency.gov:443/a") == "https://agency.gov/a"
    with pytest.raises(ValueError):
        canonicalize_url("https://user:pass@agency.gov/a")


def test_canonicalize_url_drops_sensitive_query_and_sorts():
    raw = "https://agency.gov/p?token=secret&b=2&a=1"
    assert canonicalize_url(raw) == "https://agency.gov/p?a=1&b=2"


def test_source_id_and_document_id_are_stable():
    url = "https://www.njoag.gov/press/example"
    canonical = canonicalize_url(url)
    assert source_id_for_url(canonical) == "njoag.gov"
    assert document_id_for(canonical) == document_id_for(canonical)
    assert document_id_for(canonical).startswith("doc_")


def test_capture_derives_sha256_and_storage_key():
    content = b"<html>press release</html>"
    digest = sha256_bytes(content)
    document_id = document_id_for("https://agency.gov/release")
    version = SourceDocumentVersion.capture(
        version_id=version_id_for(document_id, digest),
        document_id=document_id,
        content=content,
        retrieved_at=_utc(),
        published_at=None,
        recorded_at=_utc(),
        mime_type="text/html",
        http_status=200,
        http_etag='"abc"',
        http_last_modified=None,
        parser_name="scrape_pdf",
        parser_version="v1",
        normalized_text="press release",
    )
    assert version.content_sha256 == digest
    assert version.byte_length == len(content)
    assert version.storage_key == storage_key_for(digest)
    assert version.storage_key == f"sha256/{digest[:2]}/{digest}"


def test_capture_rejects_non_utc_and_non_200():
    document_id = document_id_for("https://agency.gov/release")
    with pytest.raises(ValueError):
        SourceDocumentVersion.capture(
            version_id=version_id_for(document_id, sha256_bytes(b"x")),
            document_id=document_id,
            content=b"x",
            retrieved_at=datetime(2026, 8, 22, 12, 0, 0),
            published_at=None,
            recorded_at=_utc(),
            mime_type="text/html",
            http_status=200,
            http_etag=None,
            http_last_modified=None,
            parser_name="scrape_pdf",
            parser_version="v1",
            normalized_text=None,
        )
    with pytest.raises(ValueError):
        SourceDocumentVersion.capture(
            version_id=version_id_for(document_id, sha256_bytes(b"x")),
            document_id=document_id,
            content=b"x",
            retrieved_at=_utc(),
            published_at=None,
            recorded_at=_utc(),
            mime_type="text/html",
            http_status=404,
            http_etag=None,
            http_last_modified=None,
            parser_name="scrape_pdf",
            parser_version="v1",
            normalized_text=None,
        )


def test_source_document_rejects_naive_timestamp():
    with pytest.raises(ValueError):
        SourceDocument(
            document_id=document_id_for("https://agency.gov/a"),
            source_id="agency.gov",
            canonical_url="https://agency.gov/a",
            canonicalization_version=CANONICALIZATION_VERSION,
            document_type="press_release",
            recorded_at=datetime.now() + timedelta(seconds=0),
        )


def test_fetched_capture_sidecar_roundtrip(tmp_path: Path):
    capture = FetchedCapture(
        url="HTTPS://Agency.GOV/News/Item/?utm_campaign=x",
        content=b"bytes-of-article",
        retrieved_at=_utc(),
        mime_type="text/html",
        normalized_text="article body",
    )
    row = capture.to_sidecar_row()
    assert row["canonical_url"] == "https://agency.gov/News/Item"
    assert row["canonicalization_version"] == CANONICALIZATION_VERSION
    document, version = models_from_sidecar_row(row)
    assert document.canonical_url == row["canonical_url"]
    assert version.content_sha256 == sha256_bytes(b"bytes-of-article")

    pdf = tmp_path / "batch.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    sidecar = write_provenance_sidecar(pdf, [row])
    assert sidecar == provenance_sidecar_path(pdf)
    assert sidecar.name == "batch.provenance.json"


def test_jina_payload_is_not_typed_as_agency_document():
    jina_bytes = b"Title: X\nMarkdown Content:\nproxy\n"
    capture = FetchedCapture(
        url="https://agency.gov/blocked",
        content=jina_bytes,
        retrieved_at=_utc(),
        mime_type="text/plain",
        parser_name=JINA_PARSER_NAME,
        document_type=JINA_DOCUMENT_TYPE,
    )
    document, version = capture.to_models()
    assert document.document_type == JINA_DOCUMENT_TYPE
    assert document.document_type != DEFAULT_DOCUMENT_TYPE
    assert version.parser_name == JINA_PARSER_NAME
    assert version.content_sha256 == sha256_bytes(jina_bytes)
