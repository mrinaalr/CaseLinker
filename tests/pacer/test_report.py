"""The run report's comparisons (state_machines/coding/report.py)."""
from __future__ import annotations

import copy
import json

from state_machines.coding import report as R
from state_machines.evidence import vocab as V
from tests.pacer import fixtures as F


def _write(folder, bundle):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{bundle['case_id']}.json").write_text(json.dumps(bundle), encoding="utf-8")


def test_reference_comparison_counts_sentences_and_codes(tmp_path):
    ours, _ = F.build()
    for e in ours["events"]:
        e["review"] = {"status": "agreed", "coders": ["coder_A", "coder_B"], "adjudicator": None, "note": "coded by both coders"}
    ref = copy.deepcopy(ours)
    acts = [e for e in ref["events"] if V.FAMILY_OF[e["action"]] != "procedure"]
    acts[0]["action"] = "BUILD_RAPPORT"                                   # the reference reads one sentence differently
    ref["events"] = [e for e in ref["events"] if e["event_id"] != acts[1]["event_id"]]   # and does not code another
    _write(tmp_path / "resolved", ours)
    _write(tmp_path / "pilot", ref)
    c = R.reference_comparison(tmp_path / "resolved", tmp_path / "pilot")["counts"]
    n = len(acts)
    assert c["agreed: published acts"] == n
    assert c["agreed: reference coded an act in the same sentence"] == n - 1
    assert c["agreed: reference gave the same action code there"] == n - 2
    assert c["reference acts"] == n - 1 and c["reference acts in a sentence the dataset also cites"] == n - 1


def test_benchmark_tables_keep_every_measure_apart_and_label_the_candidate():
    rate = {"rate": 0.5, "n": 1, "of": 2}
    overall = {"events": {"recall": rate, "precision": rate, "f1": 0.5}, "action": rate, "actor": rate, "standing": rate, "dates": rate,
               "order": {"recall": rate, "precision": rate}, "order_claims": {"correct": rate, "reversed": 0, "not_documented": 1, "endpoint_not_gold": 0},
               "order_pairs": {"of_pairs_with_both_acts_coded": rate, "of_all_gold_pairs": rate},
               "level_c": {"recall": rate, "precision": rate}, "harms": {"recall": rate, "precision": rate}, "same_act": rate,
               "by_tag": {"undercover": rate}}
    md = "\n".join(R._benchmark_md({"resolve-9.9.9.confirm": {"resolved": overall, "resolved_2b": overall, "_note": "scored once"}}))
    for words in ("resolve-9.9.9", "scored once", "gold acts found (recall)", "order relations: reversed", "harms correct (precision)",
                  "| resolved | resolved_2b |", "undercover 0.5 (1/2)", "not published"):
        assert words in md, words
