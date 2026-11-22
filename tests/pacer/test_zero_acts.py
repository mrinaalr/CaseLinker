"""A case both coders leave empty is recorded and can be drawn. Synthetic text only."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from state_machines.coding import coder as C
from state_machines.coding.pipeline import code, resolve_cases
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
    recorded = json.loads(decision.read_text(encoding="utf-8"))
    assert recorded["events"] == [] and recorded["no_acts"] is True and recorded["reason"] == "no_acts"
    assert recorded["pages"] == 1 and recorded["model_pages"] == 1 and recorded["unparsable"] == 0
    released = {item["case_id"]: item for item in json.loads((release / "manifest.json").read_text(encoding="utf-8"))["cases"]}
    assert released[zero]["no_acts"] is True and "no_agreed_acts" not in released[zero]
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


def test_an_unparsable_reply_fails_before_a_zero_act_record(tmp_path, monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setattr(C, "check_model", lambda coder: {"model": "stub", "digest": "sha256:0"})
    monkeypatch.setattr(C, "ask", lambda spec, prompt, cache: {"acts": [], "unparsed": True})
    case = "garbled"
    text_root = tmp_path / "text"
    _sources(text_root, case, "The hearing was continued.")
    out = tmp_path / "coded"
    status = code([case], text_root, out)
    assert "did not parse" in (out / "coder_A" / f"{case}.failed").read_text(encoding="utf-8")
    assert not (out / "coder_A" / f"{case}.json").is_file()
    assert status[f"coder_A/{case}"]["failed"]
    decisions, observations = tmp_path / "decisions", tmp_path / "observations"
    decisions.mkdir()
    observations.mkdir()
    proc = subprocess.run(
        [sys.executable, "-m", "state_machines.observations.gold_sample", "population",
         "--text-root", str(text_root), "--out", str(tmp_path / "units.json"),
         "--decisions", str(decisions), "--observations", str(observations),
         "--decisions-v2", str(decisions), "--observations-v2", str(observations), case],
        cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True)
    assert proc.returncode == 1
    assert "decision file" in proc.stderr + proc.stdout


def test_no_agreed_acts_is_a_different_record_and_the_draw_completes(tmp_path, monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("CASELINKER_DISAGREEMENT", "1")
    case = "split_case"
    text_root = tmp_path / "text"
    docs = _sources(text_root, case, "The hearing was continued.")
    out = tmp_path / "coded"

    def bundle(coder, action):
        return {"case_id": case, "documents": docs, "passages": [
                    {"passage_id": "p1", "doc_id": "sof", "pdf_page": 1, "char_start": 0, "char_end": 28}],
                "participants": [{"participant_ref": "P1", "kind": "person"}],
                "events": [{"event_id": "e1", "action": action, "status": "DIRECT", "notes": "",
                            "actor": {"participant_ref": "P1", "role": "offender"}, "targets": [], "co_actors": [],
                            "support": [{"passage_id": "p1", "facet": "action", "status": "DIRECT"}],
                            "affordances": [], "candidate_affordances": [], "harms": [], "access": [],
                            "time": {"assertions": []}}],
                "relations": [], "tracks": [], "coding": {"coder_id": coder},
                "coding_counts": {"pages": 1, "model_pages": 1, "unparsable": 0}}

    for coder, action in (("coder_A", "STORE_MATERIAL"), ("coder_B", "DISTRIBUTE_MATERIAL")):
        folder = out / coder
        folder.mkdir(parents=True)
        (folder / f"{case}.json").write_text(json.dumps(bundle(coder, action)), encoding="utf-8")
    summary = resolve_cases([case], out, None)
    assert summary[case]["no_agreed_acts"] is True
    assert (out / "disagreement_sheets" / case / "disagreements.csv").is_file()
    record = json.loads((out / "resolved" / f"{case}.json").read_text(encoding="utf-8"))
    assert record["reason"] == "no_agreed_acts" and record["no_agreed_acts"] is True
    assert "no_acts" not in record and record["events"] == []
    data_root = tmp_path / "data"
    cases = data_root / "rel" / "cases"
    cases.mkdir(parents=True)
    (cases / f"{case}.json").write_text(json.dumps(record), encoding="utf-8")
    build("rel", data_root=data_root, text_root=text_root, mode="machine", observations=True,
          coders_root=out, allow_empty_registry=True)
    release = data_root / "rel"
    listed = next(item for item in json.loads((release / "manifest.json").read_text(encoding="utf-8"))["cases"]
                  if item["case_id"] == case)
    assert listed["no_agreed_acts"] is True and "no_acts" not in listed
    units = tmp_path / "units.json"
    assert gold_main(["population", "--text-root", str(text_root), "--out", str(units),
                      "--decisions", str(release / "cases"), "--observations", str(release / "observations"),
                      "--decisions-v2", str(release / "cases"), "--observations-v2", str(release / "observations"),
                      case]) == 0
    population = json.loads(units.read_text(encoding="utf-8"))
    assert population and all(row["stratum"] == f"{case}:other" for row in population)
    manifest = S.seal([case, "case_02", "case_03", "case_04"], exclusion_ids=[], seed=1,
                      held_out_size=1, gold_frame_size=1, code_version="test")
    manifest = dict(manifest, gold_frame_ids=[case], held_out_ids=["case_02"])
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
    assert any(item["stratum"] == f"{case}:act" and item["population"] == 0 and item["asked"] == 2 and item["drawn"] == 0
               for item in sample["shortfalls"])
    assert sample["rows"] and all(row["case_id"] == case and row["stratum"].endswith(":other") for row in sample["rows"])
    key = json.loads((record_dir / "key.json").read_text(encoding="utf-8"))
    graded = {"units": [{"unit_id": unit["unit_id"], "gold": {"act": "", "means_tie": False, "level_c": False}}
                        for unit in key["units"]]}
    graded_path = tmp_path / "graded.json"
    graded_path.write_text(json.dumps(graded), encoding="utf-8")
    assert gold_main(["score", "--graded", str(graded_path), "--key", str(record_dir / "key.json"),
                      "--draw", str(record_dir / "draw.json"), "--sealed", str(sealed), "--replicates", "10"]) == 0
