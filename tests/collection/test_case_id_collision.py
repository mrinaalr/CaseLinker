"""A case id already held by another source file fails the ingest."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
STORAGE = ROOT / "src" / "Storage Layer"
if str(STORAGE) not in sys.path:
    sys.path.insert(0, str(STORAGE))

from case_storage_utils import CaseIdCollision  # noqa: E402
from storage import CaseStorage  # noqa: E402


def _case(case_id: str, source_file: str) -> dict:
    return {
        "id": case_id,
        "source": "DOJ SAFE CHILDHOOD",
        "source_url": "https://www.justice.gov/usao-ndia/pr/example",
        "date_range": {"start": "2026-09-11", "end": None},
        "victim_count": None,
        "relationship_to_victim": None,
        "platforms_used": [],
        "severity_indicators": [],
        "case_topics": [],
        "tags": [],
        "notes": None,
        "raw_data": {
            "source_file": source_file,
            "case_text": "A public press release.",
            "case_id": case_id,
        },
        "perpetrator_age": None,
    }


def test_same_source_file_can_store_the_id_again(tmp_path: Path):
    storage = CaseStorage(str(tmp_path / "t.db"))
    case = _case("doj_safe_childhood_2026_001", "DOJ_SAFE_CHILDHOOD.pdf")
    assert storage.store_case(case) is True
    assert storage.store_case(case) is True


def test_different_source_file_raises_and_store_cases_does_not_swallow_it(tmp_path: Path):
    storage = CaseStorage(str(tmp_path / "t.db"))
    storage.store_case(_case("doj_safe_childhood_2026_001", "DOJ_AI_CSAM_All.pdf"))
    with pytest.raises(CaseIdCollision) as exc:
        storage.store_cases([
            _case("doj_safe_childhood_2026_001", "DOJ_SAFE_CHILDHOOD.pdf"),
        ])
    err = exc.value
    assert err.case_id == "doj_safe_childhood_2026_001"
    assert err.existing_source_file == "DOJ_AI_CSAM_All.pdf"
    assert err.new_source_file == "DOJ_SAFE_CHILDHOOD.pdf"
    assert storage.get_case("doj_safe_childhood_2026_001")["raw_data"]["source_file"] == (
        "DOJ_AI_CSAM_All.pdf"
    )


def _load_main(monkeypatch):
    processing = types.ModuleType("processing")
    processing.process_cases = lambda _frame: []
    monkeypatch.setitem(sys.modules, "processing", processing)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    path = ROOT / "src" / "main.py"
    spec = importlib.util.spec_from_file_location("caselinker_main_collision_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def test_pipeline_exits_nonzero_on_case_id_collision(monkeypatch, capsys):
    main = _load_main(monkeypatch)

    def boom(_paths):
        raise CaseIdCollision(
            "doj_safe_childhood_2026_001",
            "DOJ_AI_CSAM_All.pdf",
            "DOJ_SAFE_CHILDHOOD.pdf",
        )

    monkeypatch.setattr(main, "run_pipeline", boom)
    monkeypatch.setattr(sys, "argv", ["main.py", "DOJ_SAFE_CHILDHOOD.pdf"])
    with pytest.raises(SystemExit) as exc:
        main.main()
    assert exc.value.code == 1
    assert "Case ID collision" in capsys.readouterr().out
