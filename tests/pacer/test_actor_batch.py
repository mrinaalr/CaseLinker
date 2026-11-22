"""Actor decisions that go through code_case the way a coder run does."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from state_machines.coding import coder as C
from state_machines.evidence import evidence as E

from tests.pacer.test_actor_regressions import _store_docs
from tests.pacer.test_pipeline_flags import _ask_frames, _clear, _plain_frame

_TAIL = "the files to other users via an encrypted channel."


def code_events(tmp, monkeypatch, case, docs, sentence, actor="the defendant"):
    _clear(monkeypatch)
    monkeypatch.setenv("CASELINKER_EXTRACTOR", "frame-1.0")
    _ask_frames(monkeypatch, [_plain_frame(sentence, "DISTRIBUTE_MATERIAL", actor, means="encrypted")])
    _store_docs(tmp, case, docs)
    from state_machines.coding.workflow import build_deny
    bundle, _, log = C.code_case(case, "coder_A", tmp, deny=build_deny(case, tmp))
    return [event["action"] for event in bundle["events"]], log


def _one(name, sentence, actor="the defendant"):
    return [("sof", "statement_of_facts", [f"United States v. {name}, Defendant. {sentence}"])]


@pytest.mark.parametrize("sentence", [
    f"The victim sent the defendant {_TAIL}",
    f"Minor Victim 1 sent the defendant {_TAIL}",
    "Agent Porter sent the files to the defendant via an encrypted channel.",
    f"The defendant's mother sent {_TAIL}",
    f"The defendant's mother distributed {_TAIL}",
])
def test_the_defendant_is_only_the_grammatical_subject(tmp_path, monkeypatch, sentence):
    events, _log = code_events(tmp_path, monkeypatch, "subj", _one("Michael Smith", sentence), sentence)
    assert events == []


@pytest.mark.parametrize("sentence", [
    f"The defendant's cousin sent {_TAIL}",
    f"The defendant's girlfriend distributed {_TAIL}",
    f"The defendant's stepdaughter sent {_TAIL}",
    f"The defendant's co-conspirator sent {_TAIL}",
    f"The defendant's neighbor sent {_TAIL}",
    f"Smith, the defendant's cousin, sent {_TAIL}",
])
def test_a_possessive_subject_is_not_the_defendant(tmp_path, monkeypatch, sentence):
    actor = "Smith" if sentence.startswith("Smith") else "the defendant"
    events, _log = code_events(tmp_path, monkeypatch, "poss", _one("Michael Smith", sentence), sentence, actor)
    assert events == []


def test_a_snapshot_last_name_drops_a_suffix(tmp_path, monkeypatch):
    snapshot = tmp_path / "parties.json"
    snapshot.write_text(json.dumps([{
        "court": "dcd", "docket_number": "1:24-cr-9",
        "parties": [{"party_id": "p-smith", "name": "SMITH, MICHAEL ALLEN (1) JR.", "role": "defendant"}],
    }]), encoding="utf-8")
    digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    monkeypatch.setenv("CASELINKER_PARTY_SNAPSHOT", str(snapshot))
    monkeypatch.setenv("CASELINKER_PARTY_SNAPSHOT_SHA256", digest)
    monkeypatch.setenv("CASELINKER_EXTRACTOR", "frame-1.0")
    sentence = f"Michael Smith sent {_TAIL}"
    _ask_frames(monkeypatch, [_plain_frame(sentence, "DISTRIBUTE_MATERIAL", "Michael Smith")])
    _store_docs(tmp_path, "suffix", [("sof", "statement_of_facts",
                                      [f"United States v. Michael Smith, Defendant. {sentence}"])])
    sources = json.loads((tmp_path / "suffix" / "sources.json").read_text(encoding="utf-8"))
    sources["court"] = "dcd"
    sources["docket_number"] = "1:24-cr-9"
    (tmp_path / "suffix" / "sources.json").write_text(json.dumps(sources), encoding="utf-8")
    from state_machines.coding.workflow import build_deny, case_defendants
    info = case_defendants("suffix", tmp_path)
    assert info["records"][0]["surname"] == "SMITH"
    assert info["records"][0]["full"] == "MICHAEL ALLEN SMITH"
    deny = build_deny("suffix", tmp_path)
    assert "jr" not in deny and "(1)" not in deny
    bundle, _, _log = C.code_case("suffix", "coder_A", tmp_path, deny=deny)
    assert [event["action"] for event in bundle["events"]] == ["DISTRIBUTE_MATERIAL"]


def test_wrapped_inline_and_company_captions(tmp_path, monkeypatch):
    from state_machines.coding.workflow import case_defendants, defendant_records_in
    wrapped = "UNITED STATES v. MICHAEL SMITH and\n/\nROBERT BROWN, Defendants."
    assert [r["surname"] for r in defendant_records_in(wrapped)] == ["SMITH", "BROWN"]
    inline = "UNITED STATES v. (1) SMITH, (2) PORTER, Defendants."
    assert [r["surname"] for r in defendant_records_in(inline)] == ["SMITH", "PORTER"]
    company = "UNITED STATES v. MICHAEL SMITH and ACME WIDGETS, INC., Defendants."
    assert [r["surname"] for r in defendant_records_in(company)] == ["SMITH"]
    alias = "UNITED STATES v. JOHN DOE, a/k/a JD, a/k/a Johnny, Defendant."
    records = defendant_records_in(alias)
    assert len(records) == 1 and records[0]["aliases"] == ["JD", "Johnny"]
    _store_docs(tmp_path, "wrap", [
        ("indictment", "indictment", [
            "UNITED STATES v. MICHAEL SMITH and",
            "ROBERT BROWN, Defendants. The defendant sent the files.",
        ]),
    ])
    info = case_defendants("wrap", tmp_path)
    assert [r["surname"] for r in info["records"]] == ["SMITH", "BROWN"]
    sentence = f"The defendant sent {_TAIL}"
    events, _log = code_events(
        tmp_path, monkeypatch, "wrap2",
        [("indictment", "indictment", [f"UNITED STATES v. (1) SMITH, (2) PORTER, Defendants. {sentence}"])],
        sentence,
    )
    assert events == []


def test_a_plea_for_a_stranger_is_refused(tmp_path, monkeypatch):
    sentence = f"The defendant sent {_TAIL}"
    snapshot = tmp_path / "parties.json"
    snapshot.write_text(json.dumps([{
        "court": "dcd", "docket_number": "1:24-cr-1",
        "parties": [{"party_id": "p-smith", "name": "Michael Smith", "role": "defendant"}],
    }]), encoding="utf-8")
    digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    monkeypatch.setenv("CASELINKER_PARTY_SNAPSHOT", str(snapshot))
    monkeypatch.setenv("CASELINKER_PARTY_SNAPSHOT_SHA256", digest)
    docs = [("plea", "plea_agreement", [f"United States v. Robert Porter, Defendant. {sentence}"])]
    _clear(monkeypatch)
    monkeypatch.setenv("CASELINKER_EXTRACTOR", "frame-1.0")
    monkeypatch.setenv("CASELINKER_PARTY_SNAPSHOT", str(snapshot))
    monkeypatch.setenv("CASELINKER_PARTY_SNAPSHOT_SHA256", digest)
    _ask_frames(monkeypatch, [_plain_frame(sentence, "DISTRIBUTE_MATERIAL", "the defendant")])
    _store_docs(tmp_path, "stranger", docs)
    sources = json.loads((tmp_path / "stranger" / "sources.json").read_text(encoding="utf-8"))
    sources["court"] = "dcd"
    sources["docket_number"] = "1:24-cr-1"
    (tmp_path / "stranger" / "sources.json").write_text(json.dumps(sources), encoding="utf-8")
    from state_machines.coding.workflow import build_deny, case_defendants
    info = case_defendants("stranger", tmp_path)
    assert info["caption_snapshot_disagreement"] is True
    bundle, _, _log = C.code_case("stranger", "coder_A", tmp_path, deny=build_deny("stranger", tmp_path))
    assert bundle["events"] == []


def test_a_shared_surname_is_not_the_first_party(tmp_path, monkeypatch):
    sentence = f"Smith sent {_TAIL}"
    snapshot = tmp_path / "parties.json"
    snapshot.write_text(json.dumps([{
        "court": "dcd", "docket_number": "1:24-cr-2",
        "parties": [
            {"party_id": "p-def", "name": "Michael Smith", "role": "defendant"},
            {"party_id": "p-wit", "name": "Robert Smith", "role": "witness"},
        ],
    }]), encoding="utf-8")
    digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    monkeypatch.setenv("CASELINKER_PARTY_SNAPSHOT", str(snapshot))
    monkeypatch.setenv("CASELINKER_PARTY_SNAPSHOT_SHA256", digest)
    monkeypatch.setenv("CASELINKER_EXTRACTOR", "frame-1.0")
    _ask_frames(monkeypatch, [_plain_frame(sentence, "DISTRIBUTE_MATERIAL", "Smith")])
    _store_docs(tmp_path, "shared", [("sof", "statement_of_facts",
                                      [f"United States v. Michael Smith, Defendant. {sentence}"])])
    sources = json.loads((tmp_path / "shared" / "sources.json").read_text(encoding="utf-8"))
    sources["court"] = "dcd"
    sources["docket_number"] = "1:24-cr-2"
    (tmp_path / "shared" / "sources.json").write_text(json.dumps(sources), encoding="utf-8")
    from state_machines.coding.workflow import build_deny
    bundle, _, _log = C.code_case("shared", "coder_A", tmp_path, deny=build_deny("shared", tmp_path))
    assert bundle["events"] == []


def test_two_defendants_with_one_name_are_refused(tmp_path, monkeypatch):
    sentence = f"Michael Smith sent {_TAIL}"
    snapshot = tmp_path / "parties.json"
    snapshot.write_text(json.dumps([{
        "court": "dcd", "docket_number": "1:24-cr-3",
        "parties": [
            {"party_id": "p-1", "name": "Michael Smith", "role": "defendant"},
            {"party_id": "p-2", "name": "Michael Smith", "role": "defendant"},
        ],
    }]), encoding="utf-8")
    digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    monkeypatch.setenv("CASELINKER_PARTY_SNAPSHOT", str(snapshot))
    monkeypatch.setenv("CASELINKER_PARTY_SNAPSHOT_SHA256", digest)
    monkeypatch.setenv("CASELINKER_EXTRACTOR", "frame-1.0")
    _ask_frames(monkeypatch, [_plain_frame(sentence, "DISTRIBUTE_MATERIAL", "Michael Smith")])
    _store_docs(tmp_path, "twins", [("sof", "statement_of_facts",
                                     [f"United States v. Michael Smith, Defendant. {sentence}"])])
    sources = json.loads((tmp_path / "twins" / "sources.json").read_text(encoding="utf-8"))
    sources["court"] = "dcd"
    sources["docket_number"] = "1:24-cr-3"
    (tmp_path / "twins" / "sources.json").write_text(json.dumps(sources), encoding="utf-8")
    from state_machines.coding.workflow import build_deny
    bundle, _, _log = C.code_case("twins", "coder_A", tmp_path, deny=build_deny("twins", tmp_path))
    assert bundle["events"] == []
