from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROVENANCE_PATH = ROOT / "src" / "Storage Layer" / "provenance.py"


def load_provenance():
    spec = importlib.util.spec_from_file_location(
        "caselinker_provenance", PROVENANCE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProvenanceModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.provenance = load_provenance()

    def test_canonical_url_is_stable_and_drops_tracking(self) -> None:
        canonical = self.provenance.canonicalize_url(
            "HTTPS://Example.COM:443/news/item/?utm_source=test&b=2&a=1#section"
        )
        self.assertEqual(canonical, "https://example.com/news/item?a=1&b=2")

    def test_capture_identity_is_content_addressed(self) -> None:
        captured_at = datetime(2026, 8, 22, 7, 0, tzinfo=UTC)
        first = self.provenance.build_capture_record(
            source_url="https://example.com/a",
            content=b"source bytes",
            retrieved_at=captured_at,
            mime_type="text/html",
            http_status=200,
            http_etag='"abc"',
            http_last_modified="Wed, 19 Aug 2026 12:00:00 GMT",
            final_url="https://example.com/a",
            parser_name="case-linker-html",
            parser_version="1",
            normalized_text="normalized article",
        )
        second = self.provenance.build_capture_record(
            source_url="https://example.com/a#ignored",
            content=b"source bytes",
            retrieved_at=captured_at,
            mime_type="text/html; charset=utf-8",
            http_status=200,
            http_etag='"abc"',
            http_last_modified="Wed, 19 Aug 2026 12:00:00 GMT",
            final_url="https://example.com/a",
            parser_name="case-linker-html",
            parser_version="1",
            normalized_text="normalized article",
        )
        self.assertEqual(first["document_id"], second["document_id"])
        self.assertEqual(first["version_id"], second["version_id"])
        self.assertEqual(first["content_sha256"], second["content_sha256"])
        self.assertEqual(first["byte_length"], len(b"source bytes"))

    def test_sidecar_is_byte_stable_and_matches_canonical_url(self) -> None:
        captured_at = datetime(2026, 8, 22, 7, 0, tzinfo=UTC)
        record = self.provenance.build_capture_record(
            source_url="https://example.com/a?b=2&a=1",
            content=b"source bytes",
            retrieved_at=captured_at,
            mime_type="text/html",
            http_status=200,
            http_etag=None,
            http_last_modified=None,
            final_url="https://example.com/a?a=1&b=2",
            parser_name="case-linker-html",
            parser_version="1",
            normalized_text="normalized article",
        )
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "batch.pdf"
            sidecar = self.provenance.write_capture_manifest(pdf, [record])
            first_bytes = sidecar.read_bytes()
            self.provenance.write_capture_manifest(pdf, [record])
            self.assertEqual(first_bytes, sidecar.read_bytes())
            payload = json.loads(first_bytes)
            self.assertEqual(payload["schema_version"], "caselinker-capture-v1")
            loaded = self.provenance.load_capture_manifest(pdf)
            matched = self.provenance.match_capture_for_url(
                loaded, "HTTPS://EXAMPLE.COM/a?a=1&b=2#fragment"
            )
            self.assertEqual(matched["version_id"], record["version_id"])

    def test_sensitive_query_credentials_are_not_recorded(self) -> None:
        with self.assertRaises(ValueError):
            self.provenance.canonicalize_url(
                "https://example.com/a?access_token=secret"
            )

    def test_manifest_rejects_tampered_version_identity(self) -> None:
        record = self.provenance.build_capture_record(
            source_url="https://example.com/a",
            content=b"source bytes",
            retrieved_at=datetime(2026, 8, 22, 7, 0, tzinfo=UTC),
            mime_type="text/html",
            http_status=200,
            http_etag=None,
            http_last_modified=None,
            final_url="https://example.com/a",
            parser_name="case-linker-html",
            parser_version="1",
            normalized_text="normalized",
        )
        record["version_id"] = "docv_00000000000000000000000000000000"
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            self.provenance.write_capture_manifest(Path(tmp) / "batch.pdf", [record])


if __name__ == "__main__":
    unittest.main()
