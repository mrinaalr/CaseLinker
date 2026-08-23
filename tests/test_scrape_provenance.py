"""Scraper provenance: fake HttpFetch, no network. Sidecar is a side artifact."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path

from provenance import (
    DEFAULT_DOCUMENT_TYPE,
    JINA_DOCUMENT_TYPE,
    JINA_PARSER_NAME,
    SCRAPE_PARSER_NAME,
    load_provenance_sidecar,
    provenance_sidecar_path,
    sha256_bytes,
    write_provenance_sidecar,
)


def _load_scrape_pdf():
    path = Path(__file__).resolve().parents[1] / "scripts" / "scraper" / "scrape_pdf.py"
    spec = importlib.util.spec_from_file_location("scrape_pdf", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_scrape_sidecar_leaves_merged_pdf_bytes_unchanged(tmp_path: Path):
    scrape = _load_scrape_pdf()
    merged = tmp_path / "scraped_cases.pdf"
    merged.write_bytes(b"%PDF-1.4\n%merged-fixture\n")
    before = merged.read_bytes()
    before_digest = hashlib.sha256(before).hexdigest()

    fetched = scrape.HttpFetch(
        content=b"<html>agency press release</html>",
        text="<html>agency press release</html>",
        status=200,
        mime_type="text/html",
        etag='"abc"',
        last_modified=None,
        retrieved_at=datetime(2026, 8, 22, 16, 0, tzinfo=UTC),
        via_jina=False,
    )
    row = scrape._capture_row_from_fetch(
        "https://agency.gov/news/one",
        fetched,
        "agency press release",
        None,
    )
    assert row is not None
    assert row["parser_name"] == SCRAPE_PARSER_NAME
    assert row["document_type"] == DEFAULT_DOCUMENT_TYPE
    assert row["content_sha256"] == sha256_bytes(fetched.content)

    sidecar = write_provenance_sidecar(merged, [row])
    assert sidecar == provenance_sidecar_path(merged)
    assert sidecar.is_file()
    assert load_provenance_sidecar(sidecar)[0]["canonical_url"] == "https://agency.gov/news/one"
    assert merged.read_bytes() == before
    assert hashlib.sha256(merged.read_bytes()).hexdigest() == before_digest


def test_jina_fetch_is_labeled_and_not_the_agency_document():
    scrape = _load_scrape_pdf()
    jina_payload = b"Title: Example\nMarkdown Content:\nproxy of the page\n"
    fetched = scrape.HttpFetch(
        content=jina_payload,
        text=jina_payload.decode("utf-8"),
        status=200,
        mime_type="text/plain",
        etag=None,
        last_modified=None,
        retrieved_at=datetime(2026, 8, 22, 16, 0, tzinfo=UTC),
        via_jina=True,
    )
    row = scrape._capture_row_from_fetch(
        "https://agency.gov/news/blocked",
        fetched,
        "proxy of the page",
        None,
    )
    assert row is not None
    assert row["parser_name"] == JINA_PARSER_NAME
    assert row["document_type"] == JINA_DOCUMENT_TYPE
    assert row["document_type"] != DEFAULT_DOCUMENT_TYPE
    assert row["content_sha256"] == sha256_bytes(jina_payload)
    assert row["content_sha256"] != sha256_bytes(b"<html>original agency page</html>")
