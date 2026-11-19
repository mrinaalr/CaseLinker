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


def test_docket_parser_reads_both_entry_layouts():
    two_line = "03/04/2024\n1  INDICTMENT as to the defendant (1).\n"
    one_line = "03/04/2024 INDICTMENT returned as to the defendant (1).\n"
    for page in (two_line, one_line):
        (act,) = C.docket_acts(page)["acts"]
        assert act["action"] == "PROC_CHARGE" and act["date"]["from"] == "2024-03-04"
        assert E.locate(page, act["quote"])


def test_model_coded_procedure_needs_a_date_and_is_kept_once():
    case = "synth_001"
    sources = json.loads((DATA / case / "sources.json").read_text())
    doc = next(d for d in sources["documents"] if d["doc_id"] == "sof")
    page = 1
    text = E.read_page(case, "sof", page, DATA)
    first = " ".join(E.normalize(text).split(". ")[1].split()[:8])
    answers = [(doc, page, text, {"acts": [{"s": first, "a": "PROC_PLEA"}]})]
    bundle, quotes, log = C.assemble(case, sources, answers, "coder_A", C.MODELS["coders"]["coder_A"])
    assert not any(e["action"] == "PROC_PLEA" for e in bundle["events"])
    assert any("procedure act without a stated date" in line for line in log)


def test_a_quote_stops_at_its_sentence_even_when_the_words_run_past_it():
    page = "The next day, the defendant drove to the hotel. At the hotel, the defendant met Minor Victim 1."
    s, e, q = C.locate_sentence(page, "The next day, the defendant drove to the hotel. At the")
    assert q == "The next day, the defendant drove to the hotel."


def test_a_word_broken_across_a_line_is_still_found_exactly():
    page = "The parties agree. On May 2, 2020, the defendant asked Minor Victim 1 to send sexually expl-\nicit images. Then more."
    s, e, q = C.locate_sentence(page, "On May 2, 2020, the defendant asked Minor Victim 1 to send sexually explicit")
    assert q == "On May 2, 2020, the defendant asked Minor Victim 1 to send sexually expl- icit images." and E.normalize(page)[s:e] == q
    assert C.locate_sentence(page, "On May 2, 2020, the defendant asked Minor Victim 1 to send sexually expl-icit")[2] == q
    with pytest.raises(E.QuoteNotFound):                                    # other words are still not on the page
        C.locate_sentence(page, "On May 2, 2020, the defendant asked Minor Victim 1 to send sexually explicit videos")
    with pytest.raises(E.QuoteNotFound):                                    # and an ambiguous start is still refused
        C.locate_sentence("He asked for expl-\nicit images now. He asked for explicit images now.", "He asked for explicit images")


def test_an_offender_act_coded_on_a_rule_statement_is_dropped_and_logged(monkeypatch):
    case = "synth_001"
    pg, first = _sentence(case, "sof", "first contacted")
    sources, answers = _answers(case, {("sof", pg): [{"s": first, "a": "INITIATE_CONTACT", "by": "the defendant", "r": "offender"}]})
    spec = C.MODELS["coders"]["coder_A"]
    kept, _, _ = C.assemble(case, sources, answers, "coder_A", spec)
    assert [e["action"] for e in kept["events"]] == ["INITIATE_CONTACT"]
    monkeypatch.setattr(C, "states_a_rule_not_conduct", lambda sentence: True)      # as if the sentence were "the Terms of Service prohibit ..."
    dropped, _, log = C.assemble(case, sources, answers, "coder_A", spec)
    assert dropped["events"] == [] and any("states a rule or policy, not conduct" in line for line in log)


def test_a_coders_event_records_how_its_actor_was_set_and_the_agreed_act_does_not():
    """The disputed record needs to know whether a model named the defendant, named a caption name, named no one, or named a victim."""
    from state_machines.coding.resolve import resolve
    case = "synth_001"
    pg, first = _sentence(case, "sof", "first contacted")
    pg2, second = _sentence(case, "sof", "told Minor Victim 1 that he was")
    spec = C.MODELS["coders"]["coder_A"]

    def coded(by_first, by_second):
        acts = {("sof", pg): [dict({"s": first, "a": "INITIATE_CONTACT"}, **({"by": by_first} if by_first else {}))]}
        acts.setdefault(("sof", pg2), []).append(dict({"s": second, "a": "MISREPRESENT_IDENTITY"}, **({"by": by_second} if by_second else {})))
        sources, answers = _answers(case, acts)
        bundle, _, _ = C.assemble(case, sources, answers, "coder_A", spec, caption_names={"jordan", "example"})
        return bundle, {e["action"]: e.get("notes") for e in bundle["events"]}
    _, notes = coded(None, "Jordan Example")
    assert notes == {"INITIATE_CONTACT": "actor-not-named", "MISREPRESENT_IDENTITY": "actor-named-in-caption"}
    _, notes = coded("the defendant", "Minor Victim 1")
    assert notes == {"INITIATE_CONTACT": None, "MISREPRESENT_IDENTITY": "actor-renamed-from-victim"}     # named as the defendant: no note
    _, notes = coded("Sam Other", "an undercover officer")
    assert notes["INITIATE_CONTACT"] is None and notes["MISREPRESENT_IDENTITY"] == "actor-renamed-from-undercover"
    assert set(n for n in notes.values() if n) <= set(C.ACTOR_NOTES)
    a, _ = coded(None, None)
    b = json.loads(json.dumps(a))
    b["coding"]["coder_id"] = "coder_B"
    agreed, _ = resolve(a, b)
    assert agreed["events"] and all("notes" not in e or not str(e["notes"]).startswith("actor-") for e in agreed["events"])
