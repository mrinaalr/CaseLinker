"""Court-record collector guards. No network."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _cases2records():
    path = ROOT / "collector" / "pacer" / "cases2records.py"
    name = "cases2records_pacer"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_spend_cap_refuses_the_purchase_that_would_exceed_it():
    mod = _cases2records()
    assert mod.BULK_DIR == ROOT / "ontology" / "PACER" / "BULK_FOLDER"
    cap = mod.SpendCap(3.0)
    assert cap.allows(3.0)
    cap.commit(0.10)
    assert cap.allows(2.90)
    assert not cap.allows(2.91)
    assert cap.spent == 0.10


def test_charge_pacer_without_max_spend_exits(monkeypatch):
    mod = _cases2records()
    monkeypatch.setattr(
        sys,
        "argv",
        ["cases2records.py", "--preset", "wayerski", "--charge-pacer"],
    )
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code != 0


def test_key_docs_skip_transcripts_and_transcripts_flag_keeps_eligible_ones():
    mod = _cases2records()
    entries = {
        "2": "INDICTMENT as to John Smith",
        "9": (
            "TRANSCRIPT of Proceedings as to John Smith held on 3/1/2020 "
            "before Judge X. Change of Plea Hearing. Release of Transcript "
            "Restriction set for 6/1/2020. Page Nos: 1-40"
        ),
        "10": "NOTICE of transcript of proceedings",
        "11": "TRANSCRIPT of Proceedings held on 4/1/2020. Jury Trial. Page Nos: 1-20",
    }
    key = mod.select_key_entry_targets(entries, max_docs=4)
    assert [item[2] for item in key] == ["indictment"]
    transcripts = mod.select_key_entry_targets(entries, max_docs=4, transcripts_only=True)
    assert len(transcripts) == 1
    assert transcripts[0][0] == "9"
    assert transcripts[0][2] == "transcript"
    plea = mod.assess_transcript(entries["9"], today=mod.date(2020, 7, 1))
    assert plea["eligible"] is True
    assert plea["page_count"] == 40
    trial = mod.assess_transcript(entries["11"], today=mod.date(2021, 1, 1))
    assert trial["eligible"] is False
    assert trial["reason"] == "trial"


def test_transcript_cost_has_no_three_dollar_cap():
    import importlib.util

    path = ROOT / "collector" / "pacer" / "pacer_cost.py"
    spec = importlib.util.spec_from_file_location("pacer_cost_mod", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.estimate_pacer_pdf_cost(80) == 3.0
    assert mod.estimate_transcript_pacer_cost(80) == 8.0
    assert mod.estimate_transcript_pacer_cost(None) is None


def test_download_free_recap_is_off_when_write_is_disabled(monkeypatch):
    monkeypatch.setenv("MCP_COLLECTOR_WRITE", "0")
    from caselinker_mcp.collector_tools import download_free_recap

    out = download_free_recap(document_id="123")
    assert out["collector_write_enabled"] is False
    assert out["pacer_purchases"] == 0


def test_download_free_recap_refuses_a_non_recap_url(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_COLLECTOR_WRITE", "1")

    async def _not_recap(_document_id: str):
        return {
            "is_available": True,
            "download_url": "https://example.com/secret.pdf",
            "filepath_local": "recap/secret.pdf",
        }

    monkeypatch.setattr(
        "caselinker_mcp.public_records.resolve_free_recap_download",
        _not_recap,
    )
    from caselinker_mcp.collector_tools import download_free_recap

    out = download_free_recap(document_id="123", out_dir=str(tmp_path))
    assert out["pacer_purchases"] == 0
    assert "storage.courtlistener.com" in out["error"]
    assert list(tmp_path.iterdir()) == []


def test_fetch_free_key_docs_is_off_when_write_is_disabled(monkeypatch):
    monkeypatch.setenv("MCP_COLLECTOR_WRITE", "0")
    from caselinker_mcp.collector_tools import fetch_free_key_docs

    out = fetch_free_key_docs(docket_id="99")
    assert out["collector_write_enabled"] is False
    assert out["pacer_purchases"] == 0


def test_save_free_key_targets_writes_free_pdfs_and_lists_the_rest(tmp_path):
    from caselinker_mcp.collector_tools import save_free_key_targets

    docs = {
        "1": {"id": 10, "is_available": True, "filepath_local": "recap/indictment.pdf"},
        "4": {"id": 11, "is_available": False, "filepath_local": None},
    }

    def lookup(entry):
        return docs.get(str(entry))

    def download(filepath):
        assert filepath == "recap/indictment.pdf"
        return b"%PDF-1.7 fake"

    out = save_free_key_targets(
        [("1", "Indictment", "indictment"), ("4", "Plea agreement", "plea agreement")],
        lookup,
        download,
        tmp_path,
    )
    assert out["pacer_purchases"] == 0
    assert out["saved"][0]["action"] == "indictment"
    assert (tmp_path / "indictment.pdf").read_bytes().startswith(b"%PDF")
    assert out["needs_pacer"][0]["action"] == "plea agreement"
    assert out["needs_pacer"][0]["entry_number"] == "4"


def test_download_free_recap_refuses_a_paid_document(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_COLLECTOR_WRITE", "1")

    async def _needs_pacer(_document_id: str):
        return {
            "is_available": False,
            "download_url": None,
            "cost": "not free via RECAP (would require PACER)",
        }

    monkeypatch.setattr(
        "caselinker_mcp.public_records.resolve_free_recap_download",
        _needs_pacer,
    )
    from caselinker_mcp.collector_tools import download_free_recap

    out = download_free_recap(document_id="123", out_dir=str(tmp_path))
    assert out["pacer_purchases"] == 0
    assert out["is_available"] is False
    assert list(tmp_path.iterdir()) == []
