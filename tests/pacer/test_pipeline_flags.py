"""Each extraction flag changes what the pipeline writes, and changes nothing when it is unset."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from state_machines.coding import coder as C
from state_machines.coding import pipeline as P
from state_machines.evidence import evidence as E
from state_machines.observations import observe as O

FLAGS = (
    "CASELINKER_SECTION_FILTER", "CASELINKER_COREFERENCE",
    "CASELINKER_ADJACENT_LEVEL", "CASELINKER_EXTRACTOR",
    "CASELINKER_ACT_POLICY", "CASELINKER_MEANS_PARSER", "CASELINKER_MEANS_PARSER_FALLBACK",
    "CASELINKER_MEANS_SPACY_MODEL", "CASELINKER_MEANS_RULE", "CASELINKER_DISAGREEMENT",
)
# observe + relate on the Kitebox fixture below, flags unset, run on fix/generic-platform-tags
# at 3f43d9e724128706d95286fee1829c575254809c. Recomputed there, not from this branch.
_FLAGS_OFF_SHA256 = "e632063b64d05f489215a2ff668bcc86a3262f611fa4974436a1b08813200899"
_KITEBOX = (
    "STATEMENT OF FACTS. On May 2, 2020, the defendant asked Minor Victim 1 for images through the Kitebox application. "
    "The defendant had the Snapwire application installed on his phone. Minor Victim 1 did not reply on Kitebox. "
    "He used the disappearing-message feature on Kitebox to ask Minor Victim 1 for more images. "
    "A forensic report describes a group chat found on the phone."
)


def _clear(monkeypatch):
    for name in FLAGS:
        monkeypatch.delenv(name, raising=False)


def _store(tmp: Path, case: str, text: str, doc_type: str = "statement_of_facts") -> list:
    E.write_page(case, "sof", 1, text, tmp)
    norm = E.normalize(text)
    docs = [{"doc_id": "sof", "doc_type": doc_type, "source_path": f"FICTIONAL/{case}.pdf",
             "sha256": E.sha256_text(case), "ecf_document_number": None, "filed_date": None, "page_count": 1,
             "pages": [{"pdf_page": 1, "text_method": "text_layer", "page_text_sha256": E.sha256_text(norm),
                        "court_page_label": None, "ocr_engine": None, "ocr_mean_confidence": None,
                        "image_checked": False, "limitations": []}]}]
    (tmp / case / "sources.json").write_text(json.dumps({"case_id": case, "documents": docs}), encoding="utf-8")
    return docs


def _cite(case: str, docs: list, doc: dict, term: str) -> dict:
    obs = next(o for o in doc["observations"] if o.get("feature_term") == term or o.get("named_as") == term)
    return {"case_id": case, "documents": docs, "participants": [
                {"participant_ref": "P1", "kind": "person", "role": "offender"}],
            "passages": [{"passage_id": "q1", "doc_id": "sof", "pdf_page": 1,
                          "char_start": obs["char_start"], "char_end": obs["char_end"]}],
            "events": [{"event_id": "e1", "action": "STORE_MATERIAL", "notes": "",
                        "actor": {"role": "offender", "participant_ref": "P1"},
                        "support": [{"passage_id": "q1", "facet": "action", "status": "DIRECT"}]}]}


def _means_of(tmp, case, text, monkeypatch, **env):
    _clear(monkeypatch)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    docs = _store(tmp, case, text)
    doc = O.observe(case, tmp)
    return O.relate(doc, _cite(case, docs, doc, "encrypted"), tmp)


def test_flags_off_observe_output_is_byte_identical(tmp_path, monkeypatch):
    _clear(monkeypatch)
    case = "obs_case"
    docs = _store(tmp_path, case, _KITEBOX)
    doc = O.observe(case, tmp_path)
    page = E.normalize(_KITEBOX)
    start = page.index("He used the disappearing-message")
    end = page.index(".", start) + 1
    bundle = {"case_id": case, "documents": docs, "participants": [
                  {"participant_ref": "P1", "kind": "person", "role": "offender"}],
              "passages": [{"passage_id": "q1", "doc_id": "sof", "pdf_page": 1, "char_start": start, "char_end": end}],
              "events": [{"event_id": "e1", "action": "SOLICIT_IMAGERY", "notes": "",
                          "actor": {"role": "offender", "participant_ref": "P1"},
                          "support": [{"passage_id": "q1", "facet": "action", "status": "DIRECT"}]}]}
    out = O.relate(doc, bundle, tmp_path)
    blob = json.dumps(out, sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(blob.encode()).hexdigest() == _FLAGS_OFF_SHA256
    assert "adjacent_sentence" not in out


def _they(tmp, monkeypatch, text, case, **env):
    off = _means_of(tmp / "off", case, text, monkeypatch)
    on = _means_of(tmp / "on", case, text, monkeypatch, **env)
    assert off["observations"]
    assert all(not o["relations"] for o in off["observations"])
    tied = [o for o in on["observations"] if o["relations"]]
    assert tied and tied[0]["relations"][0]["relationship"] == "Supports_Action"
    assert "adjacent-sentence" not in json.dumps(tied[0]["relations"])
    return tied


def test_e009_they_means_the_defendant(tmp_path, monkeypatch):
    _they(tmp_path, monkeypatch,
          "The defendant opened an account, and they sent files via an encrypted channel.",
          "e009", CASELINKER_COREFERENCE="1")


def test_e026_on_is_a_means_cue_only_when_the_recall_rule_is_on(tmp_path, monkeypatch):
    text = "The defendant communicated on an encrypted messaging application."
    off = _means_of(tmp_path / "off", "e026", text, monkeypatch)
    on = _means_of(tmp_path / "on", "e026", text, monkeypatch, CASELINKER_MEANS_RULE="1.4-recall")
    assert all(not o["relations"] for o in off["observations"])
    tied = [o for o in on["observations"] if o.get("feature_term") == "encrypted" and o["relations"]]
    assert tied and tied[0]["relations"][0]["cue"] == "on"
    assert tied[0]["relations"][0]["relationship"] == "Supports_Action"


def test_e149_virtual_private_networks_are_tied_to_the_act(tmp_path, monkeypatch):
    text = "The defendant utilized virtual private networks to hide the address."
    _clear(monkeypatch)
    _store(tmp_path / "off", "e149", text)
    off = O.observe("e149", tmp_path / "off")
    assert all(o.get("feature_term") != "virtual private networks" for o in off["observations"])
    monkeypatch.setenv("CASELINKER_MEANS_RULE", "1.4-recall")
    docs = _store(tmp_path / "on", "e149", text)
    on = O.observe("e149", tmp_path / "on")
    tied = O.relate(on, _cite("e149", docs, on, "virtual private networks"), tmp_path / "on")
    hit = [o for o in tied["observations"] if o.get("feature_term") == "virtual private networks" and o["relations"]]
    assert hit and hit[0]["relations"][0]["relationship"] == "Supports_Action"


def _require_spacy_model():
    pytest.importorskip("spacy")
    import spacy
    try:
        spacy.load("en_core_web_sm")
    except Exception as exc:
        pytest.skip(f"en_core_web_sm is not installed: {exc}")


def test_means_parser_finds_the_parenthetical_the_window_misses(tmp_path, monkeypatch):
    _require_spacy_model()
    text = "The defendant utilized the service (a private encrypted channel) to hide the files."
    off = _means_of(tmp_path / "off", "parser", text, monkeypatch)
    on = _means_of(tmp_path / "on", "parser", text, monkeypatch, CASELINKER_MEANS_PARSER="dep")
    assert all(not o["relations"] for o in off["observations"])
    tied = [o for o in on["observations"] if o.get("feature_term") == "encrypted" and o["relations"]]
    assert tied and tied[0]["relations"][0]["cue"] == "utilized"
    assert tied[0]["relations"][0]["parser"] == "dep"
    assert tied[0]["relations"][0]["model"] == "en_core_web_sm"
    assert tied[0]["relations"][0]["model_version"] == "3.8.0"


def test_adjacent_level_is_not_level_c(tmp_path, monkeypatch):
    text = "The defendant opened an encrypted channel. He sent the files through that channel."
    off = _means_of(tmp_path / "off", "adj", text, monkeypatch)
    on = _means_of(tmp_path / "on", "adj", text, monkeypatch, CASELINKER_ADJACENT_LEVEL="1")
    assert "adjacent_sentence" not in off
    assert on["adjacent_sentence"]
    assert all(link["level"] == "adjacent-sentence" for link in on["adjacent_sentence"])
    assert "adjacent-sentence" not in json.dumps([o["relations"] for o in on["observations"]])


def _stub_model(monkeypatch, text):
    monkeypatch.setattr(C, "check_model", lambda coder: {"model": "stub", "digest": "sha256:0"})
    words = " ".join(text.split()[:8])
    monkeypatch.setattr(C, "ask", lambda spec, prompt, cache: {
        "acts": [{"start": words, "action": "STORE_MATERIAL", "actor": "the defendant"}]})


def _coded(tmp, case, text, monkeypatch, **env):
    _clear(monkeypatch)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    _stub_model(monkeypatch, text)
    _store(tmp, case, text)
    bundle, _quotes, _log = C.code_case(case, "coder_A", tmp, deny=[])
    return bundle


def test_e071_tor_explainer_yields_no_acts(tmp_path, monkeypatch):
    text = "Tor is a browser that routes packets through a network of relays."
    off = _coded(tmp_path / "off", "e071", text, monkeypatch)
    on = _coded(tmp_path / "on", "e071", text, monkeypatch, CASELINKER_SECTION_FILTER="1")
    assert off["events"] and on["events"] == []


def test_affiant_background_yields_no_acts(tmp_path, monkeypatch):
    text = "I know from my training and experience that the account was used to send files."
    off = _coded(tmp_path / "off", "affiant", text, monkeypatch)
    on = _coded(tmp_path / "on", "affiant", text, monkeypatch, CASELINKER_SECTION_FILTER="1")
    assert off["events"] and on["events"] == []


def test_affiant_boilerplate_yields_no_acts(tmp_path, monkeypatch):
    text = "I have been a special agent for twelve years and I reviewed the files."
    off = _coded(tmp_path / "off", "e075", text, monkeypatch)
    on = _coded(tmp_path / "on", "e075", text, monkeypatch, CASELINKER_SECTION_FILTER="1")
    assert off["events"] and on["events"] == []


def _plain_frame(quote: str, code: str, actor: str, *, means: str = "encrypted",
                 means_level: str = "C", object_text: str = "the files") -> dict:
    """What a model may return: plain text only. No hash, offset, id, or class."""
    return {"act": code, "actor": actor, "object": object_text, "quote": quote,
            "means": means, "means_level": means_level}


def _ask_frames(monkeypatch, frames):
    monkeypatch.setattr(C, "check_model", lambda coder: {"model": "stub", "digest": "sha256:0"})
    monkeypatch.setattr(C, "ask", lambda spec, prompt, cache, frames=frames: {"frames": frames})


def _page(body: str, names: str = "Michael Smith") -> str:
    if body.lower().startswith("united states"):
        return body
    return f"United States v. {names}, Defendant. {body}"


def _deny_for(tmp, case, text, monkeypatch):
    from state_machines.coding.workflow import build_deny
    _store(tmp, case, text)
    return build_deny(case, tmp)


def _framed(tmp, case, text, monkeypatch, frame, names="Michael Smith"):
    from state_machines.coding.workflow import build_deny
    page = _page(text, names)
    _clear(monkeypatch)
    monkeypatch.setenv("CASELINKER_EXTRACTOR", "frame-1.0")
    _ask_frames(monkeypatch, [frame])
    _store(tmp / "on", case, page)
    on, _, log = C.code_case(case, "coder_A", tmp / "on", deny=build_deny(case, tmp / "on"))
    _clear(monkeypatch)
    _stub_model(monkeypatch, page)
    _store(tmp / "off", case, page)
    off, _, _ = C.code_case(case, "coder_A", tmp / "off", deny=build_deny(case, tmp / "off"))
    return off, on, log


def test_o0005_acquire_material_keeps_the_defendant_when_the_sender_is_the_subject(tmp_path, monkeypatch):
    text = "The defendant received the files from the facilitator via an encrypted channel."
    frame = _plain_frame(text, "ACQUIRE_MATERIAL", "The defendant")
    off, on, _log = _framed(tmp_path, "o0005", text, monkeypatch, frame)
    assert [e["action"] for e in off["events"]] == ["STORE_MATERIAL"]
    event = next(e for e in on["events"] if e["action"] == "ACQUIRE_MATERIAL")
    assert event["actor"]["role"] == "offender"
    assert event["affordances"][0]["feature_term"] == "encrypted"
    assert event["affordances"][0]["status"] == "DIRECT"
    start, end, quote = E.locate(_page(text), text)
    passage = next(p for p in on["passages"] if p["char_start"] == start and p["char_end"] == end)
    assert "facilitator" in quote and "defendant" in quote
    assert passage["char_start"] == start


def test_o0002_seek_targets_is_a_public_post_with_a_means(tmp_path, monkeypatch):
    text = "The defendant made a public post in a public group."
    frame = _plain_frame(text, "SEEK_TARGETS", "The defendant", means="public group", object_text="public post")
    off, on, _log = _framed(tmp_path, "o0002", text, monkeypatch, frame)
    assert [e["action"] for e in off["events"]] == ["STORE_MATERIAL"]
    event = next(e for e in on["events"] if e["action"] == "SEEK_TARGETS")
    assert event["actor"]["role"] == "offender"
    assert event["affordances"][0]["feature_term"] == "public group"
    assert event["affordances"][0]["affordance"] == "contact_discovery"


def _empty(case, coder):
    return {"case_id": case, "documents": [], "passages": [], "participants": [], "events": [],
            "relations": [], "tracks": [], "coding": {"coder_id": coder}}


def _event_bundle(case, coder, action):
    return {"case_id": case, "documents": [], "passages": [
                {"passage_id": "p1", "doc_id": "sof", "pdf_page": 1, "char_start": 0, "char_end": 80}],
            "participants": [{"participant_ref": "P1", "kind": "person"}],
            "events": [{"event_id": "e1", "action": action, "status": "DIRECT", "notes": "",
                        "actor": {"participant_ref": "P1", "role": "offender"}, "targets": [], "co_actors": [],
                        "support": [{"passage_id": "p1", "facet": "action", "status": "DIRECT"}],
                        "affordances": [], "candidate_affordances": [], "harms": [], "access": [],
                        "time": {"assertions": []}}],
            "relations": [], "tracks": [], "coding": {"coder_id": coder}}


def test_a_victim_frame_is_not_an_offender_act(tmp_path, monkeypatch):
    text = "Minor Victim 1 sent the files to other users via an encrypted channel."
    _clear(monkeypatch)
    monkeypatch.setenv("CASELINKER_EXTRACTOR", "frame-1.0")
    monkeypatch.setattr(C, "check_model", lambda coder: {"model": "stub", "digest": "sha256:0"})
    frame = _plain_frame(text, "DISTRIBUTE_MATERIAL", "Minor Victim 1")
    monkeypatch.setattr(C, "ask", lambda spec, prompt, cache, frame=frame: {"frames": [frame]})
    _store(tmp_path, "victim", text)
    bundle, _, _ = C.code_case("victim", "coder_A", tmp_path, deny=[])
    assert bundle["events"] == []
    assert all(e["actor"]["role"] != "offender" for e in bundle["events"])


def test_a_verbatim_frame_is_kept_and_a_paraphrase_is_not_found(tmp_path, monkeypatch):
    text = "The defendant sent the files to other users via an encrypted channel."
    _clear(monkeypatch)
    monkeypatch.setenv("CASELINKER_EXTRACTOR", "frame-1.0")
    good = _plain_frame(text, "DISTRIBUTE_MATERIAL", "The defendant")
    bad = _plain_frame("The defendant obtained the materials through a hidden route.",
                       "RECEIVE_SELF_GENERATED", "The defendant", means="hidden route", object_text="the materials")
    _ask_frames(monkeypatch, [bad, good])
    _store(tmp_path, "verify", _page(text))
    from state_machines.coding.workflow import build_deny
    bundle, _, log = C.code_case("verify", "coder_A", tmp_path, deny=build_deny("verify", tmp_path))
    assert [e["action"] for e in bundle["events"]] == ["DISTRIBUTE_MATERIAL"]
    assert any("not_found=1" in line for line in log)


def test_frame_coders_disagree_and_intersection_drops_the_act(tmp_path, monkeypatch):
    text = "The defendant sent the files to other users via an encrypted channel."
    case = "two_coders"
    _clear(monkeypatch)
    monkeypatch.setenv("CASELINKER_EXTRACTOR", "frame-1.0")
    monkeypatch.setattr(C, "check_model", lambda coder: {"model": "stub", "digest": "sha256:0"})
    _store(tmp_path, case, _page(text))
    from state_machines.coding.workflow import build_deny
    deny = build_deny(case, tmp_path)
    monkeypatch.setattr(C, "ask", lambda spec, prompt, cache: {
        "frames": [_plain_frame(text, "RECEIVE_SELF_GENERATED", "The defendant")]})
    a, _, _ = C.code_case(case, "coder_A", tmp_path, deny=deny)
    monkeypatch.setattr(C, "ask", lambda spec, prompt, cache: {
        "frames": [_plain_frame(text, "DISTRIBUTE_MATERIAL", "The defendant")]})
    b, _, _ = C.code_case(case, "coder_B", tmp_path, deny=deny)
    assert [e["action"] for e in a["events"]] == ["RECEIVE_SELF_GENERATED"]
    assert [e["action"] for e in b["events"]] == ["DISTRIBUTE_MATERIAL"]
    out = tmp_path / "coded"
    for coder, bundle in (("coder_A", a), ("coder_B", b)):
        (out / coder).mkdir(parents=True)
        (out / coder / f"{case}.json").write_text(json.dumps(bundle), encoding="utf-8")
    summary = P.resolve_cases([case], out, None)
    assert summary[case].get("events", 0) == 0 or summary[case].get("failed")
    kappa = summary[case]["report"]["agreement_model_coded"]["action_code"]["kappa"]
    assert kappa == 0
    assert not (out / "resolved" / f"{case}.json").exists()


def test_propose_verify_recovers_a_missed_act(tmp_path, monkeypatch):
    case = "missed"
    text = _page("The defendant sent the files to other users via an encrypted channel.")
    _clear(monkeypatch)

    def run(root, policy):
        if policy:
            monkeypatch.setenv("CASELINKER_ACT_POLICY", policy)
        else:
            monkeypatch.delenv("CASELINKER_ACT_POLICY", raising=False)
        _store(root, case, text)
        out = root / "coded"
        for coder in ("coder_A", "coder_B"):
            (out / coder).mkdir(parents=True)
            (out / coder / f"{case}.json").write_text(json.dumps(_empty(case, coder)), encoding="utf-8")
        return P.resolve_cases([case], out, root)

    off = run(tmp_path / "off", None)
    on = run(tmp_path / "on", "propose-verify-1.0")
    assert "published" not in off[case]
    published = json.loads((tmp_path / "on" / "coded" / "resolved" / f"{case}.json").read_text(encoding="utf-8"))
    assert on[case]["published"] >= 1
    recovered = [frame for frame in published["recovered"]
                 if frame["act"]["code"] == "DISTRIBUTE_MATERIAL" and frame["reason_code"] == "missed_act"]
    assert recovered
    assert recovered[0]["actor"]["id"] == "defendant"
    assert recovered[0]["actor"]["text"] == "the defendant"


def test_disagreement_export_appears_only_when_the_flag_is_on(tmp_path, monkeypatch):
    case = "contest"
    _clear(monkeypatch)

    def run(root, flag):
        if flag:
            monkeypatch.setenv("CASELINKER_DISAGREEMENT", "1")
        else:
            monkeypatch.delenv("CASELINKER_DISAGREEMENT", raising=False)
        out = root / "coded"
        for coder, action in (("coder_A", "STORE_MATERIAL"), ("coder_B", "DISTRIBUTE_MATERIAL")):
            (out / coder).mkdir(parents=True)
            (out / coder / f"{case}.json").write_text(
                json.dumps(_event_bundle(case, coder, action)), encoding="utf-8")
        summary = P.resolve_cases([case], out, None)
        sheet = out / "disagreement_sheets" / case / "disagreements.csv"
        return summary, sheet

    off_summary, off_sheet = run(tmp_path / "off", False)
    on_summary, on_sheet = run(tmp_path / "on", True)
    assert "disagreement_rows" not in off_summary[case] and not off_sheet.exists()
    assert on_summary[case]["disagreement_rows"] >= 1 and on_sheet.is_file()
    assert "STORE_MATERIAL" in on_sheet.read_text(encoding="utf-8")


def _recover(tmp, case, text, monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("CASELINKER_ACT_POLICY", "propose-verify-1.0")
    _store(tmp, case, text)
    out = tmp / "coded"
    for coder in ("coder_A", "coder_B"):
        (out / coder).mkdir(parents=True)
        (out / coder / f"{case}.json").write_text(json.dumps(_empty(case, coder)), encoding="utf-8")
    P.resolve_cases([case], out, tmp)
    return json.loads((out / "resolved" / f"{case}.json").read_text(encoding="utf-8"))


def test_a_missed_act_publishes_only_a_defendant(tmp_path, monkeypatch):
    pronoun = _recover(tmp_path / "he", "missed_he",
                       "He sent the files to other users via an encrypted channel.", monkeypatch)
    assert pronoun["recovered"] == []
    dated = _recover(tmp_path / "date", "missed_date",
                     _page("On May 2, 2021, the defendant sent the files to other users via an encrypted channel."),
                     monkeypatch)
    assert dated["recovered"]
    assert all(frame["actor"]["text"] == "the defendant" for frame in dated["recovered"])
    assert all(frame["act"]["code"] != "OTHER_OFFENDER_ACTION" for frame in dated["recovered"])


def test_section_filter_drops_only_the_blocked_sentence(tmp_path, monkeypatch):
    text = ("I know from my training and experience that the defendant sent files via an encrypted channel. "
            "The defendant sent the files to other users via an encrypted channel.")
    _clear(monkeypatch)
    monkeypatch.setattr(C, "check_model", lambda coder: {"model": "stub", "digest": "sha256:0"})
    monkeypatch.setattr(C, "ask", lambda spec, prompt, cache: {"acts": [
        {"start": "I know from my training", "action": "STORE_MATERIAL", "actor": "the defendant"},
        {"start": "The defendant sent the files", "action": "DISTRIBUTE_MATERIAL", "actor": "the defendant"},
    ]})
    _store(tmp_path / "off", "mixed", text)
    off, _, _ = C.code_case("mixed", "coder_A", tmp_path / "off", deny=[])
    monkeypatch.setenv("CASELINKER_SECTION_FILTER", "1")
    _store(tmp_path / "on", "mixed", text)
    on, _, log = C.code_case("mixed", "coder_A", tmp_path / "on", deny=[])
    assert {e["action"] for e in off["events"]} == {"STORE_MATERIAL", "DISTRIBUTE_MATERIAL"}
    assert [e["action"] for e in on["events"]] == ["DISTRIBUTE_MATERIAL"]
    assert any("section filter" in line and "affiant_background" in line for line in log)


def _caption(body: str, names: str = "Michael Smith") -> str:
    return f"United States v. {names}. {body}"


def _parser_up():
    try:
        import spacy
        spacy.load("en_core_web_sm")
        return True
    except Exception:
        return False


def test_caption_names_match_and_a_possessive_does_not(tmp_path, monkeypatch):
    from state_machines.coding.workflow import build_deny
    body = "Smith uploaded the files using an encrypted app."
    text = _caption(body)
    _clear(monkeypatch)
    monkeypatch.setenv("CASELINKER_EXTRACTOR", "frame-1.0")
    _ask_frames(monkeypatch, [_plain_frame(body, "STORE_MATERIAL", "Smith")])
    _store(tmp_path / "smith", "named", text)
    assert build_deny("named", tmp_path / "smith") == ["michael", "smith"]
    bundle, _, log = C.code_case("named", "coder_A", tmp_path / "smith", deny=[])
    if _parser_up():
        assert [e["action"] for e in bundle["events"]] == ["STORE_MATERIAL"]
        assert len(bundle["participants"]) == 1
    else:
        assert bundle["events"] == []
        assert C.drops_from_log(log)["no_parser"] >= 1
    full = "Defendant Michael Smith uploaded the files using an encrypted app."
    _clear(monkeypatch)
    monkeypatch.setenv("CASELINKER_EXTRACTOR", "frame-1.0")
    _ask_frames(monkeypatch, [_plain_frame(full, "STORE_MATERIAL", "Defendant Michael Smith")])
    _store(tmp_path / "full", "full", _caption(full))
    published, _, _log = C.code_case("full", "coder_A", tmp_path / "full", deny=[])
    assert published["events"] and len(published["participants"]) == 1
    given = "Michael uploaded the files using an encrypted app."
    _clear(monkeypatch)
    monkeypatch.setenv("CASELINKER_EXTRACTOR", "frame-1.0")
    _ask_frames(monkeypatch, [_plain_frame(given, "STORE_MATERIAL", "Michael")])
    _store(tmp_path / "given", "given", _caption(given))
    rejected, _, log = C.code_case("given", "coder_A", tmp_path / "given", deny=[])
    assert rejected["events"] == []
    assert C.drops_from_log(log)["surname_not_established"] >= 1
    mother = "The defendant's mother sent the files to other users via an encrypted channel."
    _clear(monkeypatch)
    monkeypatch.setenv("CASELINKER_EXTRACTOR", "frame-1.0")
    _ask_frames(monkeypatch, [_plain_frame(mother, "DISTRIBUTE_MATERIAL", "The defendant's mother")])
    _store(tmp_path / "mother", "mother", _caption(mother))
    bundle, _, log = C.code_case("mother", "coder_A", tmp_path / "mother", deny=[])
    assert bundle["events"] == []
    assert any("actor_rejected=1" in line for line in log)


def test_one_defendant_is_one_participant_and_two_stay_two(tmp_path, monkeypatch):
    text = _caption(
        "The defendant uploaded the files using an encrypted app. "
        "Smith sent the files to other users via an encrypted channel. "
        "Defendant SMITH received the files from the sender via an encrypted channel.")
    frames = [
        _plain_frame("The defendant uploaded the files using an encrypted app.", "STORE_MATERIAL", "The defendant"),
        _plain_frame("Smith sent the files to other users via an encrypted channel.", "DISTRIBUTE_MATERIAL", "Smith"),
        _plain_frame("Defendant SMITH received the files from the sender via an encrypted channel.",
                     "ACQUIRE_MATERIAL", "Defendant SMITH"),
    ]
    _clear(monkeypatch)
    monkeypatch.setenv("CASELINKER_EXTRACTOR", "frame-1.0")
    _ask_frames(monkeypatch, frames)
    _store(tmp_path / "one", "one", text)
    bundle, _, log = C.code_case("one", "coder_A", tmp_path / "one", deny=[])
    if _parser_up():
        assert len(bundle["events"]) == 3
    else:
        assert [e["action"] for e in bundle["events"]] == ["STORE_MATERIAL", "ACQUIRE_MATERIAL"]
        assert C.drops_from_log(log)["no_parser"] >= 1
    assert sum(p["legal_status"][0]["status"] == "charged_defendant" for p in bundle["participants"]) == 1
    pair = _caption(
        "Smith uploaded the files using an encrypted app. "
        "Porter sent the files to other users via an encrypted channel.",
        "Michael Smith and Robert Porter")
    frames = [
        _plain_frame("Smith uploaded the files using an encrypted app.", "STORE_MATERIAL", "Smith"),
        _plain_frame("Porter sent the files to other users via an encrypted channel.", "DISTRIBUTE_MATERIAL", "Porter"),
    ]
    _clear(monkeypatch)
    monkeypatch.setenv("CASELINKER_EXTRACTOR", "frame-1.0")
    _ask_frames(monkeypatch, frames)
    _store(tmp_path / "two", "two", pair)
    bundle, _, log = C.code_case("two", "coder_A", tmp_path / "two", deny=[])
    if _parser_up():
        assert len(bundle["events"]) == 2
        assert sum(p["legal_status"][0]["status"] == "charged_defendant" for p in bundle["participants"]) == 2
    else:
        assert bundle["events"] == []
        assert C.drops_from_log(log)["no_parser"] >= 1


def test_he_resolves_to_the_named_defendant_only_with_coreference(tmp_path, monkeypatch):
    body = "Smith opened an account on the service. He sent the files to other users via an encrypted channel."
    text = _caption(body)
    quote = "He sent the files to other users via an encrypted channel."
    frame = _plain_frame(quote, "DISTRIBUTE_MATERIAL", "He")
    _clear(monkeypatch)
    monkeypatch.setenv("CASELINKER_EXTRACTOR", "frame-1.0")
    _ask_frames(monkeypatch, [frame])
    _store(tmp_path / "off", "pronoun", text)
    off, _, _ = C.code_case("pronoun", "coder_A", tmp_path / "off", deny=[])
    assert off["events"] == []
    monkeypatch.setenv("CASELINKER_COREFERENCE", "1")
    _store(tmp_path / "on", "pronoun", text)
    on, _, _ = C.code_case("pronoun", "coder_A", tmp_path / "on", deny=[])
    assert [e["action"] for e in on["events"]] == ["DISTRIBUTE_MATERIAL"]
    assert sum(p["legal_status"][0]["status"] == "charged_defendant" for p in on["participants"]) == 1
    relate = "United States v. Michael Smith. Smith created an account and they sent files via an encrypted channel."
    off_doc = _means_of(tmp_path / "they_off", "they", relate, monkeypatch)
    on_doc = _means_of(tmp_path / "they_on", "they", relate, monkeypatch, CASELINKER_COREFERENCE="1")
    assert all(not o["relations"] for o in off_doc["observations"])
    tied = [o for o in on_doc["observations"] if o.get("feature_term") == "encrypted" and o["relations"]]
    assert tied and tied[0]["relations"][0]["relationship"] == "Supports_Action"


def test_frame_request_sends_the_frames_schema(tmp_path, monkeypatch):
    text = "The defendant sent the files to other users via an encrypted channel."
    _clear(monkeypatch)
    monkeypatch.setenv("CASELINKER_EXTRACTOR", "frame-1.0")
    monkeypatch.setattr(C, "check_model", lambda coder: {"model": "stub", "digest": "sha256:0"})
    monkeypatch.setattr(C, "wait_for_memory", lambda *a, **k: None)
    captured = {}

    class _Resp:
        def read(self):
            payload = {"frames": [_plain_frame(text, "DISTRIBUTE_MATERIAL", "The defendant")]}
            return json.dumps({"message": {"content": json.dumps(payload)}}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def _urlopen(req, timeout=900):
        captured["body"] = json.loads(req.data.decode())
        return _Resp()

    monkeypatch.setattr(C.urllib.request, "urlopen", _urlopen)
    page = _page(text)
    _store(tmp_path, "schema", page)
    from state_machines.coding.workflow import build_deny
    bundle, _, _log = C.code_case("schema", "coder_A", tmp_path, cache=C.Cache(tmp_path / "cache.db"),
                                  deny=build_deny("schema", tmp_path))
    body = captured["body"]
    assert body["format"]["required"] == ["frames"]
    props = body["format"]["properties"]["frames"]["items"]["properties"]
    assert {"act", "actor", "object", "quote", "means", "means_level"} <= set(props)
    assert "means_level" in body["messages"][0]["content"]
    assert "passage_hash" not in json.dumps(body["format"])
    assert [e["action"] for e in bundle["events"]] == ["DISTRIBUTE_MATERIAL"]
    start, end, _quote = E.locate(page, text)
    assert bundle["passages"][0]["char_start"] == start and bundle["passages"][0]["char_end"] == end


def test_spans_are_relocated_from_the_page_text(tmp_path, monkeypatch):
    from state_machines.coding.frames import ground_frame, locate_span

    broken = "The defendant sent the files\nto other users via an encrypted channel."
    straight = "The defendant sent the files to other users via an encrypted channel."
    frame = _plain_frame(straight, "DISTRIBUTE_MATERIAL", "The defendant")
    _off, on, log = _framed(tmp_path / "break", "break", broken, monkeypatch, frame)
    assert [e["action"] for e in on["events"]] == ["DISTRIBUTE_MATERIAL"]
    assert "not_found=0" in "\n".join(log)
    curly = "The defendant sent the \u201cfiles\u201d to other users via an encrypted channel."
    curly_quote = 'The defendant sent the "files" to other users via an encrypted channel.'
    curly_frame = _plain_frame(curly_quote, "DISTRIBUTE_MATERIAL", "The defendant", object_text='"files"')
    from state_machines.coding.workflow import defendant_records_in
    one = defendant_records_in("United States v. Michael Smith, Defendant.")
    curly_page = _page(curly)
    grounded, reason, _amb = ground_frame(curly_page, curly_frame, one)
    assert reason == ""
    assert "\u201cfiles\u201d" in curly_page[grounded["sentence"]["start"]:grounded["sentence"]["end"]]
    hyphen = "The defendant sent the files to other users via an encrypted distrib-\nution channel."
    hyphen_quote = "The defendant sent the files to other users via an encrypted distribution channel."
    hyphen_frame = _plain_frame(hyphen_quote, "DISTRIBUTE_MATERIAL", "The defendant")
    hyphen_page = _page(hyphen)
    grounded, reason, _amb = ground_frame(hyphen_page, hyphen_frame, one)
    assert reason == ""
    assert "distrib-\nution" in hyphen_page[grounded["sentence"]["start"]:grounded["sentence"]["end"]]
    _off, published, _log = _framed(tmp_path / "hyphen", "hyphen", hyphen, monkeypatch, hyphen_frame)
    assert [e["action"] for e in published["events"]] == ["DISTRIBUTE_MATERIAL"]
    repeated = ("The defendant sent the files to other users via an encrypted channel. "
                "The defendant sent the files to other users via an encrypted channel.")
    shared = "The defendant sent the files to other users via an encrypted channel."
    repeated_frame = _plain_frame(shared, "DISTRIBUTE_MATERIAL", "The defendant")
    _off, kept, coverage = _framed(tmp_path / "repeat", "repeat", repeated, monkeypatch, repeated_frame)
    assert [e["action"] for e in kept["events"]] == ["DISTRIBUTE_MATERIAL"]
    assert "ambiguous=0" in "\n".join(coverage) or "ambiguous" not in "\n".join(coverage)
    assert locate_span("The end-to-\nend channel was used.", "end-to-end")
    assert locate_span("A peer-\nto-peer transfer moved the files.", "peer-to-peer")
    assert locate_span("The co-\nconspirator sent the files.", "co-conspirator")
    assert locate_span("The defendant's files were sent via an encrypted channel.", "The defendant")


def test_a_missing_spacy_model_fails_and_the_fallback_is_named(tmp_path, monkeypatch):
    from state_machines.observations import means_parse as MP

    monkeypatch.setenv("CASELINKER_MEANS_PARSER", "dep")
    monkeypatch.delenv("CASELINKER_MEANS_PARSER_FALLBACK", raising=False)
    monkeypatch.setattr(MP, "_NLP", None)
    monkeypatch.setattr(MP, "_LOADS", 0)

    def boom(name):
        raise OSError("model missing")

    monkeypatch.setattr(MP, "load_spacy_model", boom)
    with pytest.raises(SystemExit, match="python -m spacy download en_core_web_sm"):
        MP.require_spacy_model()
    with pytest.raises(SystemExit, match="did not load"):
        P.main(["preflight", "no_case", "--text-root", str(tmp_path), "--out", str(tmp_path / "out")])
    monkeypatch.setattr(MP, "_NLP", None)
    with pytest.raises(SystemExit):
        MP.tokens_for("The defendant utilized the service.")

    text = "The defendant utilized the service (a private encrypted channel) to hide the files."
    monkeypatch.setattr(MP, "load_spacy_model", boom)
    fallback = _means_of(tmp_path / "fb", "fallback", text, monkeypatch,
                         CASELINKER_MEANS_PARSER="dep", CASELINKER_MEANS_PARSER_FALLBACK="1")
    tied = [o for o in fallback["observations"] if o.get("feature_term") == "encrypted" and o["relations"]]
    assert tied and tied[0]["relations"][0]["parser"] == "fallback"
    assert tied[0]["relations"][0]["cue"] == "utilized"
    assert all(row.get("parser") != "dep" for row in tied[0]["relations"])

    calls = []
    _require_spacy_model()
    monkeypatch.setattr(MP, "_NLP", None)
    monkeypatch.setattr(MP, "_LOADS", 0)
    monkeypatch.delenv("CASELINKER_MEANS_PARSER_FALLBACK", raising=False)

    def counting(name):
        calls.append(name)
        import spacy
        return spacy.load(name)

    monkeypatch.setattr(MP, "load_spacy_model", counting)
    MP.tokens_for("The defendant sent the files.")
    MP.tokens_for("The defendant sent the files again.")
    assert calls == ["en_core_web_sm"]
    assert MP._LOADS == 1


def test_flags_off_deny_matches_base_and_flags_on_is_a_superset(tmp_path, monkeypatch):
    from state_machines.coding.workflow import build_deny
    pages = {
        "a_smith": ("UNITED STATES v. MICHAEL A. SMITH, Defendant.", ["michael", "smith"]),
        "m_smith": ("UNITED STATES v. M. SMITH, Defendant.", ["smith"]),
        "surname_first": ("UNITED STATES v. SMITH, MICHAEL, Defendant.", ["michael", "smith"]),
        "junior": ("United States v. John Smith Jr., Defendant.", []),
        "two": ("United States v. Michael Smith and Robert Brown, Defendants.", ["michael", "smith"]),
        "alias": ("UNITED STATES v. Jordan Example a/k/a Jay Sample, Defendant.",
                  ["example", "jay", "jordan", "sample"]),
        "cite": ("United States v. Michael Smith. The defendant sent the files. "
                 "See United States v. Booker, 543 U.S. 220 (2005) and Gall v. United States, 552 U.S. 38 (2007).",
                 ["michael", "smith"]),
    }
    _clear(monkeypatch)
    for case, (text, expected) in pages.items():
        _store(tmp_path / "off" / case, case, text)
        assert build_deny(case, tmp_path / "off" / case) == expected
    from state_machines.coding.workflow import defendant_records_in
    cite = defendant_records_in(pages["cite"][0])
    assert [record["full"] for record in cite] == ["Michael Smith"]
    surname_first = defendant_records_in(pages["surname_first"][0])
    assert len(surname_first) == 1 and surname_first[0]["full"] == "MICHAEL SMITH"
    assert surname_first[0]["surname"] == "SMITH"
    middle = defendant_records_in(pages["a_smith"][0])
    assert middle[0]["full"] == "MICHAEL SMITH" and middle[0]["surname"] == "SMITH"
    initial = defendant_records_in(pages["m_smith"][0])
    assert initial[0]["surname"] == "SMITH"
    alias = defendant_records_in(pages["alias"][0])
    assert len(alias) == 1 and alias[0]["aliases"] == ["Jay Sample"]
    monkeypatch.setenv("CASELINKER_EXTRACTOR", "frame-1.0")
    for case, (text, expected) in pages.items():
        _store(tmp_path / "on" / case, case, text)
        got = build_deny(case, tmp_path / "on" / case)
        assert set(expected) <= set(got)


def test_flags_off_two_defendant_caption_does_not_name_the_second(tmp_path, monkeypatch):
    text = "United States v. Michael Smith and Robert Brown, Defendants. Robert Brown sent the files."
    _clear(monkeypatch)
    _store(tmp_path, "pair", text)
    from state_machines.coding.workflow import build_deny
    deny = build_deny("pair", tmp_path)
    assert deny == ["michael", "smith"]
    monkeypatch.setattr(C, "check_model", lambda coder: {"model": "stub", "digest": "sha256:0"})
    monkeypatch.setattr(C, "ask", lambda spec, prompt, cache: {
        "acts": [{"start": "Robert Brown sent the files", "action": "DISTRIBUTE_MATERIAL", "actor": "Robert Brown"}]})
    bundle, _, _ = C.code_case("pair", "coder_A", tmp_path, deny=deny)
    assert bundle["events"]
    assert all(event.get("notes") != "actor-named-in-caption" for event in bundle["events"])


def test_verification_compares_which_defendant(tmp_path, monkeypatch):
    from state_machines.coding.propose_verify import from_bundles
    _clear(monkeypatch)
    monkeypatch.setenv("CASELINKER_ACT_POLICY", "propose-verify-1.0")

    def bundle(coder, ref):
        return {"case_id": "who", "documents": [], "passages": [
                    {"passage_id": "p1", "doc_id": "sof", "pdf_page": 1, "char_start": 0, "char_end": 40}],
                "participants": [{"participant_ref": ref, "kind": "person"}],
                "events": [{"event_id": "e1", "action": "STORE_MATERIAL", "status": "DIRECT", "notes": "",
                            "actor": {"participant_ref": ref, "role": "offender"}, "targets": [], "co_actors": [],
                            "support": [{"passage_id": "p1", "facet": "action", "status": "DIRECT"}],
                            "affordances": [], "candidate_affordances": [], "harms": [], "access": [],
                            "time": {"assertions": []}}],
                "relations": [], "tracks": [], "coding": {"coder_id": coder}}

    result = from_bundles(bundle("coder_A", "P1"), bundle("coder_B", "P2"))
    assert result["published"] == []
    assert result["rejected"][0]["reason_code"] == "wrong_actor"
    with pytest.raises(ValueError, match="case id"):
        from_bundles(bundle("coder_A", "P1"), bundle("coder_B", "P2"), pages=["The defendant sent files."])


def test_frame_drops_are_in_the_manifest_only_when_the_flag_is_on(tmp_path, monkeypatch):
    pytest.importorskip("case_uco")
    from state_machines.graphs.release import build
    from tests.pacer import fixtures as F
    from tests.pacer.test_release import _adjudicated, _release
    _clear(monkeypatch)
    monkeypatch.setattr("state_machines.trajectories.affordances.load", lambda paths=None: {"platforms": {"one": {}}})
    bundle = _adjudicated(F.build()[0])
    root = _release(tmp_path / "off", bundle, release="drops-off")
    off = build("drops-off", data_root=root, text_root=tmp_path / "off" / "text", frame_drops={"not_found": 1})
    assert "frame_drops" not in off
    monkeypatch.setenv("CASELINKER_EXTRACTOR", "frame-1.0")
    root = _release(tmp_path / "on", bundle, release="drops-on")
    on = build("drops-on", data_root=root, text_root=tmp_path / "on" / "text",
               frame_drops={"not_found": 1, "ambiguous": 0})
    assert on["frame_drops"]["not_found"] == 1
    assert on["spacy_model"]["model"] == "en_core_web_sm"
    assert on["spacy_model"]["model_version"]
    assert "spacy_model" not in off


def test_repeated_quotes_that_disagree_are_ambiguous(tmp_path, monkeypatch):
    text = ("The defendant sent the files to other users via an encrypted channel. "
            "I know from my training and experience that the defendant sent the files to other users via an encrypted channel.")
    quote = "sent the files to other users via an encrypted channel"
    _clear(monkeypatch)
    monkeypatch.setenv("CASELINKER_EXTRACTOR", "frame-1.0")
    monkeypatch.setenv("CASELINKER_SECTION_FILTER", "1")
    _ask_frames(monkeypatch, [_plain_frame(quote, "DISTRIBUTE_MATERIAL", "the defendant")])
    _store(tmp_path / "sec", "sec", text)
    bundle, _, log = C.code_case("sec", "coder_A", tmp_path / "sec", deny=[])
    assert bundle["events"] == []
    drops = C.drops_from_log(log)
    assert drops["ambiguous"] >= 1
    pair = _caption(
        "Smith sent the files to other users via an encrypted channel. "
        "Porter sent the files to other users via an encrypted channel.",
        "Michael Smith and Robert Porter")
    _clear(monkeypatch)
    monkeypatch.setenv("CASELINKER_EXTRACTOR", "frame-1.0")
    _ask_frames(monkeypatch, [_plain_frame("sent the files to other users via an encrypted channel",
                                           "DISTRIBUTE_MATERIAL", "Smith")])
    _store(tmp_path / "who", "who", pair)
    bundle, _, log = C.code_case("who", "coder_A", tmp_path / "who", deny=[])
    assert bundle["events"] == []
    assert C.drops_from_log(log)["ambiguous"] >= 1


def test_frame_drops_are_counted_by_reason(tmp_path, monkeypatch):
    text = ("The defendant sent the files to other users via an encrypted channel. "
            "The defendant sent the files to other users via an encrypted channel.")
    _clear(monkeypatch)
    monkeypatch.setenv("CASELINKER_EXTRACTOR", "frame-1.0")
    page = _page(text)
    sentence = "The defendant sent the files to other users via an encrypted channel."
    _ask_frames(monkeypatch, [
        _plain_frame("The defendant obtained nothing.", "STORE_MATERIAL", "The defendant", means="", object_text=""),
        _plain_frame(sentence, "DISTRIBUTE_MATERIAL", "The defendant"),
    ])
    _store(tmp_path, "drops", page)
    from state_machines.coding.workflow import build_deny
    bundle, _, log = C.code_case("drops", "coder_A", tmp_path, deny=build_deny("drops", tmp_path))
    drops = C.drops_from_log(log)
    assert drops["not_found"] >= 1
    assert drops["duplicate_sentence"] == 0
    assert [e["action"] for e in bundle["events"]] == ["DISTRIBUTE_MATERIAL"]
    assert "unparsable_reply" in drops and "verify_failed" in drops


def _store_pages(tmp: Path, case: str, pages: list) -> None:
    listed = []
    for number, text in enumerate(pages, 1):
        E.write_page(case, "sof", number, text, tmp)
        listed.append({"pdf_page": number, "text_method": "text_layer",
                       "page_text_sha256": E.sha256_text(E.normalize(text)),
                       "court_page_label": None, "ocr_engine": None, "ocr_mean_confidence": None,
                       "image_checked": False, "limitations": []})
    docs = [{"doc_id": "sof", "doc_type": "statement_of_facts", "source_path": f"FICTIONAL/{case}.pdf",
             "sha256": E.sha256_text(case), "ecf_document_number": None, "filed_date": None,
             "page_count": len(pages), "pages": listed}]
    (tmp / case / "sources.json").write_text(json.dumps({"case_id": case, "documents": docs}), encoding="utf-8")


def test_setup_installs_the_pinned_model_wheel():
    script = (Path(__file__).resolve().parents[2] / "setup.sh").read_text(encoding="utf-8")
    wheel = "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
    assert wheel in script
    assert "spacy download en_core_web_sm-3.8.0" not in script
    assert "1932429db727d4bff3deed6b34cfc05df17794f4a52eeb26cf8928f7c1a0fb85" in script
    assert "sha256sum -c" in script
