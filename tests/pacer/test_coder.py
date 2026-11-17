"""The local coder's code paths that need no model: locating sentences, the docket parser,
turning model answers into a valid bundle, and the model pin."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from state_machines.coding import coder as C
from state_machines.evidence import evidence as E
from state_machines.benchmark import generate as G

DATA = Path(G.__file__).resolve().parent / "data"


def test_sentence_is_found_from_its_first_words_and_stops_at_its_end():
    page = "The parties agree. On May 2, 2020, the defendant asked U.S. persons for images over Chirpline. Then more."
    s, e, q = C.locate_sentence(page, "On May 2, 2020, the defendant asked")
    assert q == "On May 2, 2020, the defendant asked U.S. persons for images over Chirpline."
    assert E.normalize(page)[s:e] == q
    with pytest.raises(E.QuoteNotFound):
        C.locate_sentence(page, "the defendant sent images to")          # not on the page
    with pytest.raises(E.QuoteNotFound):
        C.locate_sentence("He asked her. He asked her again.", "He asked her")   # too short and ambiguous


def test_docket_parser_codes_only_procedure_with_dates():
    page = ("Date Filed # Docket Text\n03/04/2024\n1  INDICTMENT as to the defendant (1) count(s) 1-3.\n"
            "03/09/2024\n4  ORDER setting conditions of release.\n06/10/2024\n12  PLEA AGREEMENT as to the defendant (1).\n"
            "09/01/2024\n20  JUDGMENT as to the defendant (1).\n")
    acts = C.docket_acts(page)["acts"]
    assert [(a["action"], a["date"]["from"]) for a in acts] == [
        ("PROC_CHARGE", "2024-03-04"), ("PROC_PLEA", "2024-06-10"), ("PROC_SENTENCE", "2024-09-01")]
    assert all(E.locate(page, a["quote"]) for a in acts)


def _answers(case_id, acts_by_page):
    sources = json.loads((DATA / case_id / "sources.json").read_text())
    out = []
    for doc in sources["documents"]:
        for p in doc["pages"]:
            text = E.read_page(case_id, doc["doc_id"], p["pdf_page"], DATA)
            out.append((doc, p["pdf_page"], text, {"acts": acts_by_page.get((doc["doc_id"], p["pdf_page"]), [])}))
    return sources, out


def _sentence(case_id, doc_id, contains):
    sources = json.loads((DATA / case_id / "sources.json").read_text())
    doc = next(d for d in sources["documents"] if d["doc_id"] == doc_id)
    for p in doc["pages"]:
        page = E.normalize(E.read_page(case_id, doc_id, p["pdf_page"], DATA))
        i = page.find(contains)
        if i >= 0:
            start = page.rfind(". ", 0, i)
            start = 0 if start < 0 else start + 2
            return p["pdf_page"], " ".join(page[start:].split()[:9])
    raise AssertionError(contains)


def test_answers_become_a_valid_bundle_and_rule_breaking_parts_are_dropped():
    case = "synth_001"
    pg, first = _sentence(case, "sof", "first contacted")
    pg2, second = _sentence(case, "sof", "told Minor Victim 1 that he was")
    acts = {("sof", pg): [
        {"s": first, "a": "INITIATE_CONTACT", "by": "the defendant", "r": "offender",
         "to": [{"w": "Minor Victim 1", "r": "victim"}], "pf": {"n": "text message", "m": "through"},
         "af": {"c": "anonymity", "f": "a hidden identity"}},                 # feature not in the sentence: B0
        {"s": "this sentence is not on the page at all", "a": "FLEE", "by": "the defendant", "r": "offender"},
    ]}
    acts.setdefault(("sof", pg2), []).append(
        {"s": second, "a": "MISREPRESENT_IDENTITY", "by": "John Example", "r": "offender", "to": [{"w": "minor victim 1", "r": "victim"}]})
    sources, answers = _answers(case, acts)
    spec = C.MODELS["coders"]["coder_A"]
    bundle, quotes, log = C.assemble(case, sources, answers, "coder_A", spec)
    bundle, rlog = C.repair(bundle, DATA, [])
    e1 = next(e for e in bundle["events"] if e["action"] == "INITIATE_CONTACT")
    assert e1["affordances"] == [] and e1["platform_interactions"] == []      # B0; SMS is a channel (I3)
    assert e1["channels"][0]["channel"] == "sms"
    assert any("not on this page" in line for line in log)
    text = json.dumps(bundle)
    assert "John Example" not in text and "Minor Victim" not in text           # labels are never stored
    # a personal name is not guessed to be the defendant: it becomes its own participant (never stored by name)
    assert {p["participant_ref"] for p in bundle["participants"]} == {"P1", "P2", "P3"}


def test_a_model_with_a_different_digest_is_refused(monkeypatch):
    pinned = C.MODELS["coders"]["coder_A"]["model"]
    monkeypatch.setattr(C, "_get", lambda path: {"models": [{"name": pinned, "digest": "0" * 64}]})
    with pytest.raises(SystemExit, match="differs from the pinned"):
        C.check_model("coder_A")
    monkeypatch.setattr(C, "_get", lambda path: {"models": []})
    with pytest.raises(SystemExit, match="not pulled"):
        C.check_model("coder_A")


def test_pins_record_digests_and_inference_settings():
    m = C.MODELS
    assert set(m["coders"]) == {"coder_A", "coder_B"}
    for spec in m["coders"].values():
        assert spec["digest"].startswith("sha256:") and len(spec["digest"]) == 71 and spec["quantization"]
    assert m["coders"]["coder_A"]["family"] != m["coders"]["coder_B"]["family"]
    assert {"temperature", "seed", "num_ctx", "num_predict"} <= set(m["options"]) and m["options"]["temperature"] == 0
    assert m["prompt"]["version"] == C.PROMPT_VERSION


def test_repair_drops_only_the_act_with_a_schema_error():
    import copy
    gold = json.loads((DATA / "synth_001" / "gold.json").read_text())
    bad = copy.deepcopy(gold)
    victim = next(e for e in bad["events"] if e["affordances"])
    victim["affordances"][0]["platform_surface"] = None          # schema error at events/<i>/affordances/0
    fixed, log = C.repair(bad, DATA, [])
    assert victim["event_id"] not in {e["event_id"] for e in fixed["events"]}
    assert len(fixed["events"]) == len(gold["events"]) - 1 and any("T01" in line for line in log)
