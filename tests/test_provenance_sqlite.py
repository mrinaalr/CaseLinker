"""Integration tests: provenance tables and ingest linkage against temp SQLite."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from provenance import (
    FetchedCapture,
    attach_ingest_provenance,
    load_provenance_sidecar,
    write_provenance_sidecar,
)
from storage import CaseStorage


def _utc() -> datetime:
    return datetime(2026, 8, 22, 15, 30, 0, tzinfo=UTC)


def _minimal_case(*, case_id: str, url: str | None, source_file: str) -> dict:
    return {
        "id": case_id,
        "source": "Other",
        "source_url": url,
        "date_range": {"start": "2026-01-01", "end": None},
        "victim_count": None,
        "relationship_to_victim": None,
        "platforms_used": [],
        "severity_indicators": [],
        "case_topics": [],
        "tags": [],
        "notes": None,
        "raw_data": {
            "source_file": source_file,
            "source_url": url,
            "case_text": "A public press release.",
        },
        "perpetrator_age": None,
    }


def test_empty_db_store_case_without_provenance_is_unchanged(tmp_path: Path):
    db = tmp_path / "caselinker.db"
    storage = CaseStorage(str(db))
    case = _minimal_case(case_id="other_2026_001", url=None, source_file="agency.pdf")
    assert storage.store_case(case) is True
    stored = storage.get_case("other_2026_001")
    assert stored is not None
    assert stored["source"] == "Other"
    assert stored.get("document_version_id") in (None, "")
    assert stored.get("extraction_run_id") in (None, "")
    conn = sqlite3.connect(db)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "source_documents" in tables
        assert "source_document_versions" in tables
        assert "extraction_runs" in tables
        assert conn.execute("SELECT COUNT(*) FROM source_documents").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM extraction_runs").fetchone()[0] == 0
    finally:
        conn.close()


def test_immutability_trigger_rejects_update(tmp_path: Path):
    db = tmp_path / "caselinker.db"
    storage = CaseStorage(str(db))
    capture = FetchedCapture(
        url="https://agency.gov/news/one",
        content=b"article-bytes-1",
        retrieved_at=_utc(),
        mime_type="text/html",
        normalized_text="one",
    )
    document, version = capture.to_models()
    storage.persist_provenance_models(document, version)
    conn = sqlite3.connect(db)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute(
                "UPDATE source_documents SET source_id = 'mutated' WHERE document_id = ?",
                (document.document_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute(
                "UPDATE source_document_versions SET http_status = 200 WHERE version_id = ?",
                (version.version_id,),
            )
    finally:
        conn.close()


def test_scrape_sidecar_ingest_links_version_and_run(tmp_path: Path):
    db = tmp_path / "caselinker.db"
    storage = CaseStorage(str(db))
    pdf = tmp_path / "scraped_cases.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    url = "https://agency.gov/news/linked-case"
    capture = FetchedCapture(
        url=url,
        content=b"<html>linked article</html>",
        retrieved_at=_utc(),
        mime_type="text/html",
        http_etag='"etag-1"',
        normalized_text="linked article",
    )
    sidecar = write_provenance_sidecar(pdf, [capture.to_sidecar_row()])
    assert sidecar.is_file()
    rows = load_provenance_sidecar(sidecar)
    assert len(rows) == 1
    assert rows[0]["canonical_url"] == url

    case = _minimal_case(
        case_id="other_2026_002",
        url=url,
        source_file=str(pdf),
    )
    run_id = attach_ingest_provenance(storage, [case], repo_root=Path(__file__).resolve().parents[1])
    assert run_id
    assert case["extraction_run_id"] == run_id
    assert case["document_version_id"]
    assert storage.store_case(case) is True

    stored = storage.get_case("other_2026_002")
    assert stored["document_version_id"] == case["document_version_id"]
    assert stored["extraction_run_id"] == run_id
    assert storage.get_document_version_id_for_url(url) == stored["document_version_id"]

    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM source_documents").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM source_document_versions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM extraction_runs").fetchone()[0] == 1
        run = conn.execute(
            "SELECT code_revision, pattern_layer_version, ner_backend, "
            "semantic_model, victim_age_gate_version, source_files "
            "FROM extraction_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        assert run[1] == "pattern_processing"
        assert run[2] == "stanza"
        assert run[3] == "all-MiniLM-L6-v2"
        assert run[4] == "v2"
        assert "scraped_cases.pdf" in run[5]
    finally:
        conn.close()

    # Re-store without provenance fields must keep the existing links.
    again = _minimal_case(
        case_id="other_2026_002",
        url=url,
        source_file=str(pdf),
    )
    assert storage.store_case(again) is True
    preserved = storage.get_case("other_2026_002")
    assert preserved["document_version_id"] == stored["document_version_id"]
    assert preserved["extraction_run_id"] == run_id


def test_persist_same_capture_is_idempotent(tmp_path: Path):
    db = tmp_path / "caselinker.db"
    storage = CaseStorage(str(db))
    capture = FetchedCapture(
        url="https://agency.gov/news/dup",
        content=b"same-bytes",
        retrieved_at=_utc(),
        mime_type="text/html",
    )
    first = storage.persist_provenance_models(*capture.to_models())
    second = storage.persist_provenance_models(*capture.to_models())
    assert first == second
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM source_document_versions").fetchone()[0] == 1
    finally:
        conn.close()
