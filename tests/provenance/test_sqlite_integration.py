from __future__ import annotations

import importlib.util
import io
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STORAGE_DIR = ROOT / "src" / "Storage Layer"
if str(STORAGE_DIR) not in sys.path:
    sys.path.insert(0, str(STORAGE_DIR))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SQLiteProvenanceIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.provenance = load_module(
            "caselinker_provenance", STORAGE_DIR / "provenance.py"
        )
        cls.storage_module = load_module(
            "caselinker_storage", STORAGE_DIR / "storage.py"
        )

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "caselinker.db"
        self.storage = self.storage_module.CaseStorage(str(self.db_path))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    @staticmethod
    def sample_case(case_id: str = "test_2026_001") -> dict:
        return {
            "id": case_id,
            "source": "TEST",
            "source_url": "https://example.com/a",
            "date_range": {"start": "2026-08-01", "end": "2026-08-01"},
            "platforms_used": [],
            "severity_indicators": [],
            "case_topics": [],
            "tags": [],
            "raw_data": {
                "source_file": "batch.pdf",
                "source_url": "https://example.com/a",
                "case_text": "Synthetic public test narrative.",
            },
        }

    def test_capture_run_and_case_are_linked(self) -> None:
        captured_at = datetime(2026, 8, 22, 7, 0, tzinfo=UTC)
        record = self.provenance.build_capture_record(
            source_url="https://example.com/a",
            content=b"source bytes",
            retrieved_at=captured_at,
            mime_type="text/html",
            http_status=200,
            http_etag=None,
            http_last_modified=None,
            final_url="https://example.com/a",
            parser_name="case-linker-html",
            parser_version="1",
            normalized_text="Synthetic public test narrative.",
        )
        version_id = self.storage.store_document_capture(record)
        run_id = self.storage.create_extraction_run(
            code_revision="a" * 40,
            started_at=captured_at,
            extractor_versions={
                "pattern_layer": "pattern-processing-v1",
                "ner_backend": "none",
                "semantic_model": "none",
                "victim_age_gate": "victim-age-gate-v1",
            },
            source_files=["batch.pdf"],
        )
        stored = self.storage.store_case(
            self.sample_case(),
            document_version_id=version_id,
            extraction_run_id=run_id,
        )
        self.assertTrue(stored)

        with closing(sqlite3.connect(self.db_path)) as conn:
            refs = conn.execute(
                "SELECT document_version_id, extraction_run_id FROM cases WHERE id = ?",
                ("test_2026_001",),
            ).fetchone()
            self.assertEqual(refs, (version_id, run_id))
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM source_documents").fetchone()[0], 1
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM source_document_versions"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM extraction_runs").fetchone()[0], 1
            )

    def test_document_versions_are_immutable_and_capture_is_idempotent(self) -> None:
        captured_at = datetime(2026, 8, 22, 7, 0, tzinfo=UTC)
        record = self.provenance.build_capture_record(
            source_url="https://example.com/a",
            content=b"source bytes",
            retrieved_at=captured_at,
            mime_type="text/html",
            http_status=200,
            http_etag=None,
            http_last_modified=None,
            final_url="https://example.com/a",
            parser_name="case-linker-html",
            parser_version="1",
            normalized_text="normalized",
        )
        first = self.storage.store_document_capture(record)
        second = self.storage.store_document_capture(record)
        self.assertEqual(first, second)
        with (
            closing(sqlite3.connect(self.db_path)) as conn,
            self.assertRaises(sqlite3.IntegrityError),
        ):
            conn.execute(
                "UPDATE source_document_versions SET byte_length = byte_length + 1 WHERE version_id = ?",
                (first,),
            )

    def test_same_document_can_be_retrieved_again_without_rewriting_history(
        self,
    ) -> None:
        captured_at = datetime(2026, 8, 22, 7, 0, tzinfo=UTC)
        common = {
            "source_url": "https://example.com/a",
            "content": b"source bytes",
            "mime_type": "text/html",
            "http_status": 200,
            "http_etag": None,
            "http_last_modified": None,
            "final_url": "https://example.com/a",
            "parser_name": "case-linker-html",
            "parser_version": "1",
            "normalized_text": "normalized",
        }
        first_record = self.provenance.build_capture_record(
            retrieved_at=captured_at,
            **common,
        )
        later_record = self.provenance.build_capture_record(
            retrieved_at=captured_at + timedelta(days=1),
            **common,
        )
        self.assertEqual(first_record["document_id"], later_record["document_id"])
        self.assertNotEqual(first_record["version_id"], later_record["version_id"])
        self.storage.store_document_capture(first_record)
        self.storage.store_document_capture(later_record)
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM source_documents").fetchone()[0], 1
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM source_document_versions"
                ).fetchone()[0],
                2,
            )

    def test_legacy_case_without_provenance_still_stores(self) -> None:
        self.assertTrue(self.storage.store_case(self.sample_case("legacy_2026_001")))
        with closing(sqlite3.connect(self.db_path)) as conn:
            refs = conn.execute(
                "SELECT document_version_id, extraction_run_id FROM cases WHERE id = ?",
                ("legacy_2026_001",),
            ).fetchone()
        self.assertEqual(refs, (None, None))

    def test_case_rejects_dangling_provenance_references(self) -> None:
        with redirect_stdout(io.StringIO()):
            stored = self.storage.store_case(
                self.sample_case("dangling_2026_001"),
                document_version_id="docv_missing",
                extraction_run_id="run_missing",
            )
        self.assertFalse(stored)
        with closing(sqlite3.connect(self.db_path)) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM cases WHERE id = ?", ("dangling_2026_001",)
            ).fetchone()[0]
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
