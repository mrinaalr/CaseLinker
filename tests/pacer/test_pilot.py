"""Pilot compiler, agreement and agreed core, on the fictional case."""
from __future__ import annotations

import copy

from tests.pacer import fixtures as F
from state_machines.coding.pilot import agreement, compile_draft
from state_machines.coding.pilot_report import agreed_core
from state_machines.evidence.validate import validate


def _draft(bundle, quotes):
    d = copy.deepcopy(bundle)
    for p in d["passages"]:
        for k in ("char_start", "char_end", "quote_sha256", "quote_word_count", "verification"):
            p.pop(k, None)
        p["quote"] = quotes[p["passage_id"]]
    return d


def test_compile_draft_restores_offsets_and_drops_quote_text(tmp_path):
    F.write_pages(tmp_path)
    bundle, quotes = F.build()
    compiled, q, problems = compile_draft(_draft(bundle, quotes), tmp_path)
    assert problems == [] and q == quotes
    assert [(p["char_start"], p["quote_sha256"]) for p in compiled["passages"]] == \
           [(p["char_start"], p["quote_sha256"]) for p in bundle["passages"]]
    assert all("quote" not in p for p in compiled["passages"])
    assert [f for f in validate(compiled, text_root=tmp_path) if f.severity == "error"] == []


def test_compile_draft_reports_quotes_not_on_the_page(tmp_path):
    F.write_pages(tmp_path)
    bundle, quotes = F.build()
    draft = _draft(bundle, quotes)
    draft["passages"][0]["quote"] = "words that are not on this page at all"
    _, _, problems = compile_draft(draft, tmp_path)
    assert len(problems) == 1 and problems[0].startswith("p01")


def test_agreement_and_agreed_core_keep_only_what_both_coders_coded():
    a, _ = F.build()
    b = copy.deepcopy(a)
    b["coding"]["coder_id"] = "coder_B"
    next(e for e in b["events"] if e["event_id"] == "e03")["action"] = "DIRECT_CONDUCT"   # disagree on e03
    next(e for e in b["events"] if e["event_id"] == "e05")["affordances"] = []              # disagree on anonymity
    b["events"] = [e for e in b["events"] if e["event_id"] != "e08"]                        # B missed e08
    agree = agreement(a, b)
    assert agree["events"]["matched"] == 7 and agree["action_code"]["exact"] == 6
    core = agreed_core(a, b, agree["pairs"])
    ids = {e["event_id"] for e in core["events"]}
    assert "e03" not in ids and "e08" not in ids
    e05 = next(e for e in core["events"] if e["event_id"] == "e05")
    assert e05["affordances"] == [] and e05["review"]["status"] == "agreed"


def test_agreed_core_keeps_passages_its_mentions_cite(tmp_path):
    from state_machines.evidence.validate import validate
    F.write_pages(tmp_path)
    a, _ = F.build()
    next(e for e in a["events"] if e["event_id"] == "e01")["platform_mentions"] = [
        {"platform_surface": "messaging application", "passage_ids": ["p11"]}]   # p11 cited only here and by r01
    a["relations"] = [r for r in a["relations"] if r["relation_id"] != "r01"]
    b = copy.deepcopy(a)
    core = agreed_core(a, b, agreement(a, b)["pairs"])
    assert "p11" in {p["passage_id"] for p in core["passages"]}
    assert [f for f in validate(core, text_root=tmp_path) if f.severity == "error"] == []
