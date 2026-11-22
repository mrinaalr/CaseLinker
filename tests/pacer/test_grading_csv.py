"""The blind sheet becomes a CSV and comes back as the graded JSON score reads.

Synthetic sentences only. The export is built from the sheet, never from the key.
"""
from __future__ import annotations

import csv
import json

from state_machines.observations import gold_sample as G
from state_machines.observations import seal as S
from state_machines.observations.gold_sample import export_grading_csv, import_graded_csv


def test_the_csv_round_trip_keeps_the_marks_and_leaves_the_key_out(tmp_path):
    sheet = {"units": [{
        "unit_id": "u1",
        "context_before": ["The caption names one defendant."],
        "sentence": "The defendant sent the files through an encrypted channel.",
        "context_after": ["The next sentence is background."],
    }, {
        "unit_id": "u2",
        "context_before": [],
        "sentence": "A later sentence describes the software.",
        "context_after": [],
    }]}
    out = tmp_path / "sheet.csv"
    assert export_grading_csv(sheet, out) == 2
    with out.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert set(rows[0]) == {
        "unit_id", "context_before", "sentence", "context_after",
        "act", "act_code", "actor", "means", "level_c",
    }
    assert "machine" not in rows[0] and "inclusion_probability" not in rows[0]
    assert rows[0]["act"] == "" and rows[0]["means"] == ""
    rows[0]["act"] = "yes"
    rows[0]["act_code"] = "DISTRIBUTE_MATERIAL"
    rows[0]["actor"] = "the defendant"
    rows[0]["means"] = "yes"
    rows[0]["level_c"] = "no"
    rows[1]["act"] = "no"
    filled = tmp_path / "filled.csv"
    with filled.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    graded = import_graded_csv(filled)
    assert graded["units"][0]["gold"] == {
        "act": "DISTRIBUTE_MATERIAL", "means_tie": True, "level_c": False,
    }
    assert graded["units"][0]["actor"] == "the defendant"
    assert graded["units"][1]["gold"]["act"] == ""
    assert graded["units"][1]["gold"]["means_tie"] is False
    again = json.loads(json.dumps(graded))
    assert again == graded


def _write(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_the_filled_csv_scores_and_a_swapped_column_does_not(tmp_path):
    manifest = S.seal(
        ["case_01", "case_02", "case_03", "case_04"], exclusion_ids=[],
        seed=1, held_out_size=1, gold_frame_size=2, code_version="test-commit",
    )
    case_id = manifest["gold_frame_ids"][0]
    population = [{
        "unit_id": "u-send",
        "case_id": case_id,
        "stratum": "published_acts",
        "sentence": "The defendant sent the files through an encrypted channel.",
        "context_before": ["The caption names one defendant."],
        "context_after": ["The next sentence is background."],
        "machine": {"act": "DISTRIBUTE_MATERIAL", "means_tie": False, "level_c": False},
    }, {
        "unit_id": "u-app",
        "case_id": case_id,
        "stratum": "published_acts",
        "sentence": "A later sentence names a messaging application.",
        "context_before": [],
        "context_after": [],
        "machine": {"act": "", "means_tie": True, "level_c": False},
    }]
    sample = G.draw_sample(
        population, {"seed": 1, "strata": {"published_acts": {"n": 2}}}, sealed=manifest)
    sheet = G.grading_sheet(sample)
    blind = tmp_path / "sheet.csv"
    export_grading_csv(sheet, blind)
    raw = blind.read_text(encoding="utf-8")
    assert "DISTRIBUTE_MATERIAL" not in raw
    assert "means_tie" not in raw and "inclusion_probability" not in raw
    with blind.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    by_sentence = {row["sentence"]: row for row in rows}
    send = by_sentence["The defendant sent the files through an encrypted channel."]
    send.update(act="yes", act_code="DISTRIBUTE_MATERIAL", actor="the defendant", means="no", level_c="no")
    app = by_sentence["A later sentence names a messaging application."]
    app.update(act="no", act_code="", actor="", means="yes", level_c="no")
    filled = tmp_path / "filled.csv"
    _write(filled, rows)
    graded = import_graded_csv(filled)
    key = G.key_file(sample)
    result = G.score(graded, key, sealed=manifest, replicates=20, seed=0)
    assert result["precision"]["act"]["precision"] == 1
    assert result["precision"]["means_tie"]["precision"] == 1
    assert result["recall"]["act"]["recall"] == 1
    swapped = {"units": []}
    for row in rows:
        swapped["units"].append({
            "unit_id": row["unit_id"],
            "gold": {
                "act": "yes" if row["act"] == "yes" else "",
                "means_tie": row["act"] == "yes",
                "level_c": False,
            },
        })
    wrong = G.score(swapped, key, sealed=manifest, replicates=20, seed=0)
    assert wrong["precision"]["act"]["precision"] == 0
    assert wrong["precision"]["means_tie"]["precision"] == 0


def test_population_writer_emits_the_file_draw_reads(tmp_path):
    from state_machines.evidence import evidence as E

    case = "stamp"
    E.write_page(case, "sof", 1, "The defendant sent the files. The hearing was continued.", tmp_path)
    (tmp_path / case / "sources.json").write_text(json.dumps({
        "case_id": case,
        "court": "dcd",
        "docket_number": "1:24-cr-9",
        "documents": [{"doc_id": "sof", "sha256": "abc123", "pages": [{"pdf_page": 1}]}],
    }), encoding="utf-8")
    out = tmp_path / "units.json"
    assert G.write_population([case], tmp_path, out) == 2
    rows = json.loads(out.read_text(encoding="utf-8"))
    assert rows[0]["court"] == "dcd" and rows[0]["sentence"]
    assert "machine" not in rows[0]
