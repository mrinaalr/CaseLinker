"""A case both coders leave empty is recorded and can be drawn. Synthetic text only."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from state_machines.coding import coder as C
from state_machines.coding.pipeline import resolve_cases
from state_machines.evidence import evidence as E
from state_machines.evidence.validate import validate
from state_machines.graphs.release import build
from state_machines.observations import seal as S
from state_machines.observations.gold_sample import main as gold_main

FLAGS = (
    "CASELINKER_SECTION_FILTER", "CASELINKER_COREFERENCE",
    "CASELINKER_ADJACENT_LEVEL", "CASELINKER_EXTRACTOR",
    "CASELINKER_ACT_POLICY", "CASELINKER_MEANS_PARSER", "CASELINKER_MEANS_PARSER_FALLBACK",
    "CASELINKER_MEANS_SPACY_MODEL", "CASELINKER_MEANS_RULE", "CASELINKER_DISAGREEMENT",
)


def _clear(monkeypatch):
    for name in FLAGS:
        monkeypatch.delenv(name, raising=False)


def _sources(tmp: Path, case: str, text: str) -> list:
    if text:
        E.write_page(case, "sof", 1, text, tmp)
        norm = E.normalize(text)
        pages = [{"pdf_page": 1, "text_method": "text_layer", "page_text_sha256": E.sha256_text(norm),
                  "court_page_label": None, "ocr_engine": None, "ocr_mean_confidence": None,
                  "image_checked": False, "limitations": []}]
        page_count = 1
    else:
        pages, page_count = [], 0
    docs = [{"doc_id": "sof", "doc_type": "statement_of_facts", "source_path": f"FICTIONAL/{case}.pdf",
             "sha256": E.sha256_text(case), "ecf_document_number": None, "filed_date": None,
             "page_count": page_count, "pages": pages}]
    (tmp / case).mkdir(parents=True, exist_ok=True)
    (tmp / case / "sources.json").write_text(json.dumps({
        "case_id": case, "court": "dcd", "docket_number": f"1:24-cr-{case}", "documents": docs,
    }), encoding="utf-8")
    return docs


def _coder_files(out: Path, case: str, docs: list) -> None:
    body = json.dumps({
        "case_id": case, "events": [], "passages": [], "relations": [], "tracks": [],
        "participants": [], "documents": docs,
    }, indent=1) + "\n"
    for coder in ("coder_A", "coder_B"):
        folder = out / coder
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{case}.json").write_text(body, encoding="utf-8")


def test_a_bundle_with_events_and_no_participants_still_fails_validation():
    findings = validate({"participants": [], "events": [{"event_id": "e1"}]})
    assert any(f.where == "participants" and "non-empty" in f.message for f in findings)


def test_zero_acts_are_recorded_and_the_draw_completes(tmp_path, monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setattr(C, "check_model", lambda coder: {"model": "stub", "digest": "sha256:0"})
    monkeypatch.setattr(C, "ask", lambda spec, prompt, cache: {"acts": []})
    text_root = tmp_path / "text"
    zero, blank = "zero_case", "blank_case"
    _sources(text_root, zero, "The hearing was continued.")
    blank_docs = _sources(text_root, blank, "")
    out = tmp_path / "coded"
    for coder in ("coder_A", "coder_B"):
        bundle, _quotes, _log = C.code_case(zero, coder, text_root, deny=[])
        assert bundle["events"] == []
        folder = out / coder
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{zero}.json").write_text(json.dumps(bundle, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    _coder_files(out, blank, blank_docs)
    summary = resolve_cases([zero, blank], out, text_root)
    assert summary[zero]["no_acts"] is True and summary[blank]["no_acts"] is True
    data_root = tmp_path / "data"
    cases = data_root / "rel" / "cases"
    cases.mkdir(parents=True)
    for case in (zero, blank):
        (cases / f"{case}.json").write_text((out / "resolved" / f"{case}.json").read_text(encoding="utf-8"), encoding="utf-8")
    build("rel", data_root=data_root, text_root=text_root, mode="machine", observations=True,
          coders_root=out, allow_empty_registry=True)
    release = data_root / "rel"
    decision = release / "cases" / f"{zero}.json"
    observed = release / "observations" / f"{zero}.json"
    assert decision.is_file() and observed.is_file()
    assert json.loads(decision.read_text(encoding="utf-8"))["events"] == []
    assert (release / "observations" / f"{blank}.json").is_file()
    units = tmp_path / "units.json"
    assert gold_main(["population", "--text-root", str(text_root), "--out", str(units),
                      "--decisions", str(release / "cases"), "--observations", str(release / "observations"),
                      "--decisions-v2", str(release / "cases"), "--observations-v2", str(release / "observations"),
                      zero, blank]) == 0
    population = json.loads(units.read_text(encoding="utf-8"))
    assert not [row for row in population if row["case_id"] == blank]
    others = [row for row in population if row["case_id"] == zero]
    assert others and all(row["stratum"] == f"{zero}:other" for row in others)
    manifest = S.seal([zero, blank, "case_03", "case_04"], exclusion_ids=[], seed=1,
                      held_out_size=1, gold_frame_size=2, code_version="test")
    manifest = dict(manifest, gold_frame_ids=[zero, blank], held_out_ids=["case_03"])
    manifest["sha256"] = S.manifest_sha256(manifest)
    sealed, config = tmp_path / "sealed.json", tmp_path / "config.json"
    sealed.write_text(json.dumps(manifest), encoding="utf-8")
    config.write_text(json.dumps({"seed": 1}), encoding="utf-8")
    sheet_dir, record_dir = tmp_path / "sheet", tmp_path / "record"
    assert gold_main(["draw", "--population", str(units), "--config", str(config), "--sealed", str(sealed),
                      "--sheet-out", str(sheet_dir), "--record-out", str(record_dir),
                      "--decisions", str(release / "cases"), "--observations", str(release / "observations"),
                      "--decisions-v2", str(release / "cases"), "--observations-v2", str(release / "observations")]) == 0
    sample = json.loads((record_dir / "draw.json").read_text(encoding="utf-8"))
    shortfalls = sample["shortfalls"]
    assert any(item["stratum"] == blank and item["population"] == 0 and item["asked"] == 3 and item["drawn"] == 0
               for item in shortfalls)
    assert not [row for row in sample["rows"] if row["case_id"] == blank]
    drawn = [row for row in sample["rows"] if row["case_id"] == zero]
    assert len(drawn) == min(3, len(others))
    assert any(item["stratum"] == f"{zero}:act" and item["population"] == 0 and item["asked"] == 2 and item["drawn"] == 0
               for item in shortfalls)
    if len(others) < 3:
        assert any(item["stratum"] == f"{zero}:other" and item["population"] == len(others)
                   and item["asked"] == 3 and item["drawn"] == len(others) for item in shortfalls)
    else:
        assert not any(item["stratum"] == f"{zero}:other" for item in shortfalls)
    key = json.loads((record_dir / "key.json").read_text(encoding="utf-8"))
    graded = {"units": [{"unit_id": unit["unit_id"], "gold": {"act": "", "means_tie": False, "level_c": False}}
                        for unit in key["units"]]}
    graded_path = tmp_path / "graded.json"
    graded_path.write_text(json.dumps(graded), encoding="utf-8")
    assert gold_main(["score", "--graded", str(graded_path), "--key", str(record_dir / "key.json"),
                      "--draw", str(record_dir / "draw.json"), "--sealed", str(sealed),
                      "--replicates", "10"]) == 0
    decision.unlink()
    with pytest.raises(SystemExit, match="decision file"):
        gold_main(["draw", "--population", str(units), "--config", str(config), "--sealed", str(sealed),
                   "--sheet-out", str(tmp_path / "sheet2"), "--record-out", str(tmp_path / "record2"),
                   "--decisions", str(release / "cases"), "--observations", str(release / "observations"),
                   "--decisions-v2", str(release / "cases"), "--observations-v2", str(release / "observations")])
