"""Main-pipeline regression coverage for provenance sidecar paths."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class _SingleRowFrame:
    def __init__(self, row: dict):
        self._row = row
        self.iloc = self

    def __getitem__(self, index: int) -> dict:
        assert index == 0
        return self._row

    def __len__(self) -> int:
        return 1


def _load_main(monkeypatch):
    processing = types.ModuleType("processing")
    processing.process_cases = lambda _frame: [{"id": "other_2026_001"}]
    monkeypatch.setitem(sys.modules, "processing", processing)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    path = ROOT / "src" / "main.py"
    spec = importlib.util.spec_from_file_location("caselinker_main_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def test_main_forwards_cli_paths_to_store_cases(monkeypatch):
    main_module = _load_main(monkeypatch)
    ingest_path = str(Path("scrape_output") / "batch.pdf")
    frame = _SingleRowFrame(
        {
            "extracted_text": "Case 1: fixture",
            "source": "Other",
            "source_url": None,
        }
    )

    ingestion = types.ModuleType("ingestion")

    def _ingest_file(_path, *, file_type):
        assert file_type == "pdf"
        return frame

    ingestion.ingest_file = _ingest_file
    ingestion.ingest_multiple_pdfs = lambda _paths: frame
    monkeypatch.setitem(sys.modules, "ingestion", ingestion)

    analysis = types.ModuleType("analysis")
    analysis.run_automated_analysis = lambda _cases: {}
    monkeypatch.setitem(sys.modules, "analysis", analysis)

    class _Storage:
        def __init__(self, *_args, **_kwargs):
            pass

        def store_precomputed_clusters(self, _clusters, _case_count):
            return True

    captured = {}

    def _store_cases(cases, db_path, *, ingest_paths=None):
        captured["cases"] = cases
        captured["db_path"] = db_path
        captured["ingest_paths"] = ingest_paths
        return len(cases)

    monkeypatch.setattr(main_module, "CaseStorage", _Storage)
    monkeypatch.setattr(main_module, "get_database_path", lambda: "fixture.db")
    monkeypatch.setattr(main_module, "get_all_stored_cases", lambda _db_path: [])
    monkeypatch.setattr(main_module, "store_cases", _store_cases)
    monkeypatch.setattr(sys, "argv", ["src/main.py", ingest_path])

    main_module.main()

    assert captured["ingest_paths"] == [ingest_path]
