"""ingest_grouped.py --done-file records stored PDFs and skips them on the next run."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "run" / "ingest_grouped.py"


def _load():
    spec = importlib.util.spec_from_file_location("ingest_grouped_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(monkeypatch, tmp_path, list_file, done_file, fail_on=None):
    seen = []

    def run_pipeline(group):
        if fail_on and fail_on in group:
            raise RuntimeError("hang")
        seen.extend(group)

    monkeypatch.setitem(sys.modules, "main", types.SimpleNamespace(run_pipeline=run_pipeline))
    monkeypatch.setattr(sys, "argv", ["ingest_grouped.py", "--list", str(list_file), "--done-file", str(done_file)])
    monkeypatch.chdir(tmp_path)
    mod = _load()
    monkeypatch.setattr(mod.os, "chdir", lambda _p: None)
    return mod.main(), seen


def test_resume_skips_pdfs_already_stored(monkeypatch, tmp_path):
    pdfs = [str(tmp_path / f"{n}.pdf") for n in ("a", "b", "c")]
    list_file = tmp_path / "pdfs.txt"
    list_file.write_text("\n".join(pdfs) + "\n", encoding="utf-8")
    done_file = tmp_path / "done.txt"

    code, seen = _run(monkeypatch, tmp_path, list_file, done_file, fail_on=pdfs[1])
    assert code == 1
    assert seen == pdfs[:1]
    assert done_file.read_text(encoding="utf-8").split() == pdfs[:1]

    code, seen = _run(monkeypatch, tmp_path, list_file, done_file)
    assert code == 0
    assert seen == pdfs[1:]
    assert done_file.read_text(encoding="utf-8").split() == pdfs


def test_nothing_left_returns_zero_without_loading_the_pipeline(monkeypatch, tmp_path):
    pdf = str(tmp_path / "a.pdf")
    list_file = tmp_path / "pdfs.txt"
    list_file.write_text(pdf + "\n", encoding="utf-8")
    done_file = tmp_path / "done.txt"
    done_file.write_text(pdf + "\n", encoding="utf-8")

    code, seen = _run(monkeypatch, tmp_path, list_file, done_file)
    assert code == 0
    assert seen == []
