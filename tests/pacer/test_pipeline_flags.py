"""Each extraction flag changes what the pipeline writes, and changes nothing when it is unset."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from state_machines.coding import coder as C
from state_machines.coding import pipeline as P
from state_machines.evidence import evidence as E
from state_machines.observations import observe as O

FLAGS = (
    "CASELINKER_SECTION_FILTER", "CASELINKER_SECTION_MODEL", "CASELINKER_COREFERENCE",
    "CASELINKER_COREFERENCE_MODEL", "CASELINKER_ADJACENT_LEVEL", "CASELINKER_EXTRACTOR",
    "CASELINKER_ACT_POLICY", "CASELINKER_MEANS_PARSER", "CASELINKER_MEANS_RULE",
    "CASELINKER_DISAGREEMENT",
)
# observe + relate on the fictional Kitebox page, with every flag unset, before these modules were called.
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


def test_e026_he_after_the_accused_needs_coreference(tmp_path, monkeypatch):
    # The checklist is not in the repo. The actor is only the pronoun, so the means tie needs coreference.
    _they(tmp_path, monkeypatch,
          "The accused registered the account, and they sent files via an encrypted channel.",
          "e026", CASELINKER_COREFERENCE="1")


def test_e149_they_after_the_defendant_needs_coreference(tmp_path, monkeypatch):
    _they(tmp_path, monkeypatch,
          "The defendant met a facilitator, and they sent files via an encrypted channel.",
          "e149", CASELINKER_COREFERENCE="1")


def test_means_parser_finds_the_parenthetical_the_window_misses(tmp_path, monkeypatch):
    text = "The defendant utilized the service (a private encrypted channel) to hide the files."
    off = _means_of(tmp_path / "off", "parser", text, monkeypatch)
    on = _means_of(tmp_path / "on", "parser", text, monkeypatch, CASELINKER_MEANS_PARSER="dep")
    assert all(not o["relations"] for o in off["observations"])
    tied = [o for o in on["observations"] if o.get("feature_term") == "encrypted" and o["relations"]]
    assert tied and tied[0]["relations"][0]["cue"] == "utilized"


def test_adjacent_level_is_not_level_c(tmp_path, monkeypatch):
    text = "The defendant opened an encrypted channel. He sent the files through that channel."
    off = _means_of(tmp_path / "off", "adj", text, monkeypatch)
    on = _means_of(tmp_path / "on", "adj", text, monkeypatch, CASELINKER_ADJACENT_LEVEL="1")
    assert "adjacent_sentence" not in off
    assert on["adjacent_sentence"]
    assert all(link["level"] == "adjacent-sentence" for link in on["adjacent_sentence"])
    assert "adjacent-sentence" not in json.dumps([o["relations"] for o in on["observations"]])


def test_means_rule_adds_the_spelled_out_network(tmp_path, monkeypatch):
    text = "The defendant utilized virtual private networks to hide the address."
    _clear(monkeypatch)
    _store(tmp_path / "off", "vpn", text)
    off = O.observe("vpn", tmp_path / "off")
    monkeypatch.setenv("CASELINKER_MEANS_RULE", "1.4-recall")
    _store(tmp_path / "on", "vpn", text)
    on = O.observe("vpn", tmp_path / "on")
    assert all(o.get("feature_term") != "virtual private networks" for o in off["observations"])
    assert any(o.get("feature_term") == "virtual private networks" for o in on["observations"])


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


def test_e065_tor_explainer_yields_no_acts(tmp_path, monkeypatch):
    text = "Tor is a browser that routes packets through a network of relays."
    off = _coded(tmp_path / "off", "e065", text, monkeypatch)
    on = _coded(tmp_path / "on", "e065", text, monkeypatch, CASELINKER_SECTION_FILTER="1")
    assert off["events"] and on["events"] == []


def test_e071_affiant_background_yields_no_acts(tmp_path, monkeypatch):
    text = "I know from my training and experience that the account was used to send files."
    off = _coded(tmp_path / "off", "e071", text, monkeypatch)
    on = _coded(tmp_path / "on", "e071", text, monkeypatch, CASELINKER_SECTION_FILTER="1")
    assert off["events"] and on["events"] == []


def test_e075_affiant_boilerplate_yields_no_acts(tmp_path, monkeypatch):
    text = "I have been a special agent for twelve years and I reviewed the files."
    off = _coded(tmp_path / "off", "e075", text, monkeypatch)
    on = _coded(tmp_path / "on", "e075", text, monkeypatch, CASELINKER_SECTION_FILTER="1")
    assert off["events"] and on["events"] == []


def _framed(tmp, case, text, monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("CASELINKER_EXTRACTOR", "frame-1.0")
    monkeypatch.setattr(C, "check_model", lambda coder: {"model": "stub", "digest": "sha256:0"})
    monkeypatch.setattr(C, "ask", lambda spec, prompt, cache: {"acts": []})
    _store(tmp / "on", case, text)
    on, _, _ = C.code_case(case, "coder_A", tmp / "on", deny=[])
    _clear(monkeypatch)
    _stub_model(monkeypatch, text)
    _store(tmp / "off", case, text)
    off, _, _ = C.code_case(case, "coder_A", tmp / "off", deny=[])
    return off, on


def test_doj_ceos_2025_023_o0005_receipt_carries_the_means(tmp_path, monkeypatch):
    text = "The defendant received the files from the sender via an encrypted channel."
    off, on = _framed(tmp_path, "receipt", text, monkeypatch)
    assert [e["action"] for e in off["events"]] == ["STORE_MATERIAL"]
    event = next(e for e in on["events"] if e["action"] == "RECEIVE_SELF_GENERATED")
    assert event["actor"]["role"] == "offender"
    assert event["affordances"][0]["feature_term"] == "encrypted"
    assert event["affordances"][0]["status"] == "DIRECT"


def test_ncis_2023_001_o0002_second_instrument(tmp_path, monkeypatch):
    text = "The defendant sent the files to other users via an encrypted channel."
    off, on = _framed(tmp_path, "instrument", text, monkeypatch)
    assert [e["action"] for e in off["events"]] == ["STORE_MATERIAL"]
    event = next(e for e in on["events"] if e["action"] == "DISTRIBUTE_MATERIAL")
    assert event["actor"]["role"] == "offender"
    assert event["affordances"][0]["feature_term"] == "encrypted"


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


def test_propose_verify_recovers_a_missed_act(tmp_path, monkeypatch):
    case = "missed"
    text = "The defendant sent the files to other users via an encrypted channel."
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
    assert any(frame["act"]["code"] == "DISTRIBUTE_MATERIAL" and frame["reason_code"] == "missed_act"
               for frame in published["recovered"])


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
