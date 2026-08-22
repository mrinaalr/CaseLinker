from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class ScrapeIngestBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            processing_dir = ROOT / "src" / "Processing Layer"
            if str(processing_dir) not in sys.path:
                sys.path.insert(0, str(processing_dir))
            cls.scraper = load_module(
                "caselinker_scrape_pdf", ROOT / "scripts" / "scraper" / "scrape_pdf.py"
            )
            cls.ingestion = load_module(
                "caselinker_ingestion",
                ROOT / "src" / "Ingestion Layer" / "ingestion.py",
            )
            cls.processing = load_module(
                "caselinker_processing",
                ROOT / "src" / "Processing Layer" / "processing.py",
            )
        except (ImportError, SystemExit) as exc:
            raise unittest.SkipTest(
                f"existing scraper dependencies are unavailable: {exc}"
            )

    def test_scraper_sidecar_is_loaded_by_pdf_ingest(self) -> None:
        url = "https://example.com/public-release"
        body = (
            "This is a synthetic public-record test narrative used only to verify that "
            "the scraper PDF and its provenance sidecar travel through ingestion together."
        )
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            article_pdf = output_dir / "tmp" / "0001.pdf"
            article_pdf.parent.mkdir(parents=True)
            self.assertTrue(
                self.scraper.write_pdf(
                    article_pdf,
                    "Synthetic release",
                    "Test agency",
                    body,
                    url,
                    date(2026, 8, 22),
                )
            )
            resource = self.scraper.FetchedResource(
                content=b"<html><body>Synthetic source bytes</body></html>",
                text="Synthetic source bytes",
                retrieved_at=datetime(2026, 8, 22, 7, 0, tzinfo=UTC),
                status_code=200,
                content_type="text/html; charset=utf-8",
                etag='"synthetic"',
                last_modified="Sat, 22 Aug 2026 07:00:00 GMT",
                final_url=url,
            )
            record = self.scraper._capture_success(
                out_dir=output_dir,
                per_url_pdf=article_pdf,
                source_url=url,
                resource=resource,
                parser_name="case-linker-html",
                normalized_text=body,
                published_at=date(2026, 8, 22),
            )
            self.assertIsNotNone(record)

            merged_pdf = output_dir / "batch.pdf"
            self.assertTrue(self.scraper.merge([article_pdf], merged_pdf))
            self.scraper.provenance.write_capture_manifest(merged_pdf, [record])

            frame = self.ingestion.ingest_file(str(merged_pdf), file_type="pdf")
            records = frame.iloc[0]["provenance_records"]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["version_id"], record["version_id"])
            self.assertEqual(records[0]["canonical_url"], url)

            self.processing.create_primary_ner_extractor = lambda: None
            self.processing.SemanticConcepts = lambda: (_ for _ in ()).throw(
                RuntimeError("disabled in focused provenance test")
            )
            cases = self.processing.process_cases(frame)
            self.assertEqual(len(cases), 1)
            self.assertEqual(
                cases[0]["_provenance"]["version_id"], record["version_id"]
            )


if __name__ == "__main__":
    unittest.main()
