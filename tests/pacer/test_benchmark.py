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
    assert len(golds) == 60
    for g in golds:
        assert errors(validate(g, text_root=DATA, require_verified=True)) == [], g["case_id"]


def test_splits_and_the_heldout_register():
    m = json.loads((DATA / "MANIFEST.json").read_text())
    assert sum(v == "heldout" for v in m["splits"].values()) == 20
    dev_text = " ".join(p.read_text() for c, s in m["splits"].items() if s == "dev" for p in (DATA / c).glob("*/p*.txt"))
    held_text = " ".join(p.read_text() for c, s in m["splits"].items() if s == "heldout" for p in (DATA / c).glob("*/p*.txt"))
    for marker in ("MV-1", "DEFENDANT", "initiated contact with"):
        assert marker in held_text and marker not in dev_text


def _split_text(split):
    m = json.loads((DATA / "MANIFEST.json").read_text())
    return " ".join(" ".join(p.read_text().split()) for c, s in sorted(m["splits"].items()) if s == split
                    for p in sorted((DATA / c).glob("*/p*.txt")))


def test_the_confirm_split_has_its_own_register():
    m = json.loads((DATA / "MANIFEST.json").read_text())
    assert sum(v == "confirm" for v in m["splits"].values()) == 20
    assert [c for c, s in m["splits"].items() if s == "confirm"] == [f"synth_{i:03d}" for i in range(41, 61)]
    assert m["confirm_seed"] == G.CONFIRM_SEED != m["seed"]
    dev, held, confirm = _split_text("dev"), _split_text("heldout"), _split_text("confirm")
    for marker in ("the accused", "Jane Doe 1", "count(s)"):                 # the confirm register, and only there
        assert marker in confirm and marker not in dev and marker not in held, marker
    for marker in ("the defendant", "Minor Victim 1", "DEFENDANT", "MV-1", "undercover agent"):   # no dev or held-out party names
        assert marker not in confirm, marker
    assert "the defendant" in dev and "Minor Victim 1" in dev and "DEFENDANT" not in dev      # dev and held-out are as they were
    assert "DEFENDANT" in held and "MV-1" in held and "the defendant" not in held and "Minor Victim 1" not in held
    for g in _golds():
        version = G.CONFIRM_VERSION if m["splits"][g["case_id"]] == "confirm" else G.BENCHMARK_VERSION
        assert g["coding"]["note"].startswith(version + ":"), g["case_id"]


def test_the_confirm_register_rewrites_every_template_and_keeps_what_gold_quotes():
    import random
    for seed in range(60):
        dev = G.build_case("x", random.Random(seed))
        con = G._build_case("x", random.Random(seed), style="confirm")          # the same case, before its extra fillers
        assert [(e["event_id"], e["action"], e["outcome"]) for e in dev.events] == [(e["event_id"], e["action"], e["outcome"]) for e in con.events]
        for doc_id, sentences in dev.sentences.items():
            for a, b in zip(sentences, con.sentences[doc_id]):
                assert a != b and G.heldout_style(a) != b, a
                assert [p for p in G.PLATFORMS if p in a] == [p for p in G.PLATFORMS if p in b], a
        where = {p["passage_id"]: con.sentences[p["doc_id"]][p["index"]] for p in con.passages}
        for e in con.events:
            for t in e["time"]["assertions"]:
                assert t["expression"] in where[t["passage_ids"][0]], e["event_id"]
            for a in e["affordances"]:
                assert a["feature_term"] in where[a["support"][0]["passage_id"]], e["event_id"]


def test_confirm_cases_do_not_move_the_first_forty(tmp_path):
    G.generate(out=tmp_path / "with")
    G.generate(out=tmp_path / "without", confirm=0)
    for i in range(1, 41):
        a, b = tmp_path / "with" / f"synth_{i:03d}", tmp_path / "without" / f"synth_{i:03d}"
        for f in sorted(p.relative_to(a) for p in a.rglob("*") if p.is_file()):
            assert (a / f).read_bytes() == (b / f).read_bytes(), (i, f)
    assert not (tmp_path / "without" / "synth_041").exists()


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
    assert s["order_claims"]["correct"]["rate"] == 1.0 and s["order_pairs"]["of_all_gold_pairs"]["rate"] == 1.0


def test_an_order_claim_is_judged_against_the_whole_documented_order():
    g = next(x for x in _golds() if sum(r["type"] == "BEFORE" for r in x["relations"]) >= 2)
    k = copy.deepcopy(g)
    first = next(r for r in k["relations"] if r["type"] == "BEFORE")
    first["from_event"], first["to_event"] = first["to_event"], first["from_event"]       # one stated relation reversed
    s = summarize(score_case(g, k))
    assert s["order_claims"]["reversed"] >= 1 and s["order_claims"]["correct"]["rate"] < 1.0
    k = copy.deepcopy(g)
    k["relations"] = [r for r in k["relations"] if r["type"] not in ("BEFORE", "MEETS")]   # no stated order: dates still order some pairs
    s = summarize(score_case(g, k))
    assert s["order"]["recall"]["n"] == 0 and s["order_pairs"]["of_all_gold_pairs"]["rate"] < 1.0


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
