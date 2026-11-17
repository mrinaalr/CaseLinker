"""The synthetic gold benchmark and its scorer."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from state_machines.benchmark import generate as G
from state_machines.benchmark.score import score_case, summarize
from state_machines.evidence.validate import errors, validate

DATA = Path(G.__file__).resolve().parent / "data"


def _golds():
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(DATA.glob("synth_*/gold.json"))]


def test_committed_benchmark_is_what_the_generator_writes(tmp_path):
    G.generate(out=tmp_path)
    for p in sorted(DATA.glob("synth_*/gold.json")):
        assert json.loads((tmp_path / p.parent.name / "gold.json").read_text()) == json.loads(p.read_text()), p.parent.name


def test_every_gold_case_validates_against_its_own_pages():
    golds = _golds()
    assert len(golds) == 40
    for g in golds:
        assert errors(validate(g, text_root=DATA, require_verified=True)) == [], g["case_id"]


def test_splits_and_the_heldout_register():
    m = json.loads((DATA / "MANIFEST.json").read_text())
    assert sum(v == "heldout" for v in m["splits"].values()) == 20
    dev_text = " ".join(p.read_text() for c, s in m["splits"].items() if s == "dev" for p in (DATA / c).glob("*/p*.txt"))
    held_text = " ".join(p.read_text() for c, s in m["splits"].items() if s == "heldout" for p in (DATA / c).glob("*/p*.txt"))
    for marker in ("MV-1", "DEFENDANT", "initiated contact with"):
        assert marker in held_text and marker not in dev_text


def test_gold_holds_the_hard_cases():
    tags = {t for g in _golds() for e in g["events"] for t in e["notes"].split()}
    assert {"explicit_order", "retelling", "allegation_only", "mention_only", "level_c", "no_level_c",
            "undercover", "interrupted", "harm"} <= tags
    assert sum(r["type"] == "SAME_ACT" for g in _golds() for r in g["relations"]) >= 20


def test_scoring_gold_against_itself_is_perfect():
    g = _golds()[0]
    s = summarize(score_case(g, copy.deepcopy(g)))
    assert s["events"]["f1"] == 1.0 and s["action"]["rate"] == 1.0 and s["actor"]["rate"] == 1.0
    assert s["order"]["recall"]["rate"] == 1.0 and s["same_act"]["rate"] == 1.0


def test_scoring_counts_what_a_coder_misses_or_gets_wrong():
    g = _golds()[0]
    k = copy.deepcopy(g)
    k["events"] = k["events"][1:]                                 # one act missed
    k["events"][0]["action"] = "COMMUNICATE"                      # one code wrong
    k["relations"] = []                                           # no order coded
    s = summarize(score_case(g, k))
    assert s["events"]["recall"]["n"] == len(g["events"]) - 1
    assert s["action"]["rate"] < 1.0 and s["order"]["recall"]["n"] == 0


def test_a_case_without_output_counts_as_missing_all_its_acts(tmp_path):
    from state_machines.benchmark.score import score_dir
    (tmp_path / "coded").mkdir()
    out = score_dir(tmp_path / "coded", "dev")
    assert out["missing"] and out["overall"]["events"]["recall"]["n"] == 0
    assert out["overall"]["events"]["recall"]["of"] == sum(len(g["events"]) for g in _golds()
                                                          if json.loads((DATA / "MANIFEST.json").read_text())["splits"][g["case_id"]] == "dev")
