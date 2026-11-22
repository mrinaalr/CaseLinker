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


def code_events(tmp, monkeypatch, case, docs, sentence, actor="the defendant", *, means="encrypted",
                object_text="the files", env=None):
    _clear(monkeypatch)
    monkeypatch.setenv("CASELINKER_EXTRACTOR", "frame-1.0")
    for key, value in (env or {}).items():
        monkeypatch.setenv(key, value)
    _ask_frames(monkeypatch, [_plain_frame(sentence, "DISTRIBUTE_MATERIAL", actor, means=means, object_text=object_text)])
    _store_docs(tmp, case, docs)
    from state_machines.coding.workflow import build_deny
    bundle, _, log = C.code_case(case, "coder_A", tmp, deny=build_deny(case, tmp))
    return [event["action"] for event in bundle["events"]], log


def _reasons(tmp, case):
    path = tmp / case / "v2_refusals.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line)["reason"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _one(name, sentence, actor="the defendant"):
    return [("sof", "statement_of_facts", [f"United States v. {name}, Defendant. {sentence}"])]


@pytest.mark.parametrize("sentence,actor,means,object_text,extra", [
    ("The defendant sent the files to Agent Porter.", "the defendant", "", "the files", None),
    ("Michael Smith distributed the images.", "Michael Smith", "", "the images", None),
    ("The files were sent by the defendant.", "the defendant", "", "The files", None),
    ("The defendant downloaded and sent the files.", "the defendant", "", "the files", None),
    ("He sent the files.", "He", "", "the files", {"CASELINKER_COREFERENCE": "1"}),
])
def test_plain_positive_clauses_publish(tmp_path, monkeypatch, sentence, actor, means, object_text, extra):
    events, _log = code_events(
        tmp_path, monkeypatch, "plain", _one("Michael Smith", sentence), sentence, actor,
        means=means, object_text=object_text, env=extra)
    assert events == ["DISTRIBUTE_MATERIAL"]


@pytest.mark.parametrize("sentence,actor,reason,env", [
    ("After the defendant logged in, Agent Porter sent the files.", "the defendant", "subordinate_clause", None),
    ("The defendant said that the victim sent the files.", "the defendant", "reported_speech", None),
    ("The defendant did not send the files.", "the defendant", "negated", None),
    ("The defendant would have sent the files.", "the defendant", "modal_conditional", None),
    ("The defendant and Agent Porter sent the files.", "the defendant", "coordinated_subject", None),
    ("Smith, his sister, sent the files.", "Smith", "appositive_relation", None),
    ("Agent Porter sent him the files.", "him", "pronoun_object", {"CASELINKER_COREFERENCE": "1"}),
])
def test_each_refusal_reason_is_counted(tmp_path, monkeypatch, sentence, actor, reason, env):
    events, _log = code_events(
        tmp_path, monkeypatch, "why", _one("Michael Smith", sentence), sentence, actor,
        means="", env=env)
    assert events == []
    assert reason in _reasons(tmp_path, "why")


def test_caption_layouts_and_labels(tmp_path, monkeypatch):
    from state_machines.coding.workflow import case_defendants, defendant_records_in
    assert [r["surname"] for r in defendant_records_in(
        "UNITED STATES v.\nMICHAEL SMITH,\nROBERT BROWN,\nDefendants.")] == ["SMITH", "BROWN"]
    assert [r["surname"] for r in defendant_records_in(
        "UNITED STATES v.\nMICHAEL SMITH,\n\nROBERT BROWN,\nDefendants.")] == ["SMITH", "BROWN"]
    kite = defendant_records_in('UNITED STATES v.\n(1) SMITH, a/k/a "Kite"\n(2) PORTER\nDefendants.')
    assert [r["surname"] for r in kite] == ["SMITH", "PORTER"]
    assert kite[0]["aliases"] == ["Kite"]
    assert [r["surname"] for r in defendant_records_in(
        "UNITED STATES v.\n1. SMITH\n2. PORTER\nDefendants.")] == ["SMITH", "PORTER"]
    assert "Assigned" not in [r["full"] for r in defendant_records_in(
        "UNITED STATES v. Quill Assigned to Magistrate")]
    assert [r["full"] for r in defendant_records_in("UNITED STATES v. ALAN QUILL USM Number")] == ["ALAN QUILL"]
    assert [r["full"] for r in defendant_records_in(
        "UNITED STATES v. MICHAEL SMITH CASE Number: 1:24-cr-1")] == ["MICHAEL SMITH"]
    assert [r["surname"] for r in defendant_records_in(
        "UNITED STATES v. MICHAEL SMITH\nCriminal No. 24-123 (ABC)\nDefendant.")] == ["SMITH"]
    assert [r["surname"] for r in defendant_records_in(
        "UNITED STATES v. MICHAEL SMITH\n18 U.S.C. 2252\nDefendant.")] == ["SMITH"]
    assert defendant_records_in("See United States v. Booker, 123 Fed. Appx. 456.") == []
    _store_docs(tmp_path, "cover", [("indictment", "indictment", [
        "COVER SHEET",
        "UNITED STATES v. MICHAEL SMITH and ROBERT BROWN, Defendants.",
    ])])
    assert [r["surname"] for r in case_defendants("cover", tmp_path)["records"]] == ["SMITH", "BROWN"]
    sentence = "The defendant sent the files."
    events, _log = code_events(tmp_path, monkeypatch, "memo", [
        ("complaint", "complaint", ["United States v. Michael Smith, Defendant."]),
        ("memo", "memorandum", [f"United States v. Robert Porter, Defendant. {sentence}"]),
    ], sentence, means="")
    assert events == []
    assert "caption_mismatch" in _reasons(tmp_path, "memo")


def test_multi_defendant_and_shared_surname_are_counted(tmp_path, monkeypatch):
    generic = "The defendant sent the files."
    events, _log = code_events(
        tmp_path, monkeypatch, "multi",
        [("sof", "statement_of_facts", [f"United States v. Michael Smith and Robert Porter, Defendants. {generic}"])],
        generic, means="")
    assert events == []
    assert "multi_defendant_caption" in _reasons(tmp_path, "multi")
    shared = "Smith sent the files."
    events, _log = code_events(
        tmp_path, monkeypatch, "same",
        [("sof", "statement_of_facts", [f"United States v. Michael Smith and Robert Smith, Defendants. {shared}"])],
        shared, actor="Smith", means="")
    assert events == []
    assert "ambiguous_surname" in _reasons(tmp_path, "same")


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


def test_recovery_uses_the_same_document_defendant(tmp_path, monkeypatch):
    sentence = f"The defendant sent {_TAIL}"
    docs = [
        ("complaint", "complaint", ["United States v. Michael Smith, Defendant."]),
        ("plea", "plea_agreement", [f"United States v. Robert Porter, Defendant. {sentence}"]),
    ]
    events, _log = code_events(tmp_path, monkeypatch, "agree", docs, sentence)
    assert events == ["DISTRIBUTE_MATERIAL"]
    from state_machines.coding import pipeline as P
    out = tmp_path / "coded"
    for coder in ("coder_A", "coder_B"):
        (out / coder).mkdir(parents=True)
        (out / coder / "agree.json").write_text(json.dumps({
            "case_id": "agree", "documents": [], "passages": [], "participants": [],
            "events": [], "relations": [], "tracks": [], "coding": {"coder_id": coder},
        }), encoding="utf-8")
    monkeypatch.setenv("CASELINKER_ACT_POLICY", "propose-verify-1.0")
    P.resolve_cases(["agree"], out, tmp_path)
    recovered = json.loads((out / "resolved" / "agree.json").read_text(encoding="utf-8"))["recovered"]
    assert recovered
    assert all("Porter" in frame["actor"]["text"] for frame in recovered)
    assert all("Smith" not in frame["actor"]["text"] for frame in recovered)


def test_citation_lines_are_not_defendants(tmp_path, monkeypatch):
    from state_machines.coding.workflow import defendant_records_in, eyecite_version
    assert eyecite_version()
    page = (
        "See United States v. Booker, 543 F.4th 100.\n"
        "As held in United States v. Booker, the guidelines changed.\n"
        "United States v. Gall, 552 F. App'x 1.\n"
        "United States v. Gall, 128 S. Ct. 586, 169 L. Ed. 2d 445.\n"
        "United States v. Booker, id. at 220.\n"
        "Fed. Appx. 12 says the same.\n"
        f"United States v. Michael Smith, Defendant. The defendant sent {_TAIL}"
    )
    assert [r["surname"] for r in defendant_records_in(page)] == ["Smith"]
    events, _log = code_events(
        tmp_path, monkeypatch, "cites",
        [("sof", "statement_of_facts", [page])],
        f"The defendant sent {_TAIL}",
    )
    assert events == ["DISTRIBUTE_MATERIAL"]
    numbered = "UNITED STATES v. Case No. 1:24-cr-1\n(1) JOHN DOE\n(2) JANE ROE\n"
    assert [r["surname"] for r in defendant_records_in(numbered)] == ["DOE", "ROE"]


def test_extract_records_court_case_number_and_document_hash(tmp_path, monkeypatch):
    import pymupdf
    from state_machines.coding.workflow import extract
    source = tmp_path / "src" / "BULK_FOLDER"
    source.mkdir(parents=True)
    pdf = source / "pacer -- sample_2024_001 -- complaint.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "IN THE UNITED STATES DISTRICT COURT FOR THE DISTRICT OF COLUMBIA")
    page.insert_text((72, 100), "Case No. 1:24-cr-4")
    page.insert_text((72, 130), "United States v. Michael Smith, Defendant. " + ("The defendant sent the files to other users via an encrypted channel. " * 8))
    document.save(pdf)
    document.close()
    monkeypatch.setattr("state_machines.coding.workflow.MIN_TEXT_CHARS", 1)
    monkeypatch.setenv("CASELINKER_PACER_SOURCE", str(tmp_path / "src"))
    monkeypatch.setenv("CASELINKER_PACER_TEXT", str(tmp_path / "text"))
    manifest = extract("sample_2024_001")
    assert "court" not in manifest and "docket_number" not in manifest["documents"][0]
    assert manifest["documents"][0]["sha256"]
    key = json.loads((tmp_path / "text" / "sample_2024_001" / "case_key.json").read_text(encoding="utf-8"))
    assert key["court"] == "DISTRICT OF COLUMBIA"
    assert key["docket_number"].startswith("1:24-cr-4")
    from state_machines.coding.workflow import court_and_docket
    maryland = court_and_docket("UNITED STATES DISTRICT COURT FOR THE DISTRICT OF MARYLAND")[0]
    new_york = court_and_docket("UNITED STATES DISTRICT COURT FOR THE SOUTHERN DISTRICT OF NEW YORK")[0]
    assert maryland == "DISTRICT OF MARYLAND"
    assert new_york == "SOUTHERN DISTRICT OF NEW YORK"
    assert maryland != new_york


def test_a_snapshot_without_its_hash_or_file_is_an_error(tmp_path, monkeypatch):
    from state_machines.coding import parties as parties_mod
    parties_mod._CACHE.clear()
    monkeypatch.setenv("CASELINKER_PARTY_SNAPSHOT_SHA256", "ab" * 32)
    monkeypatch.delenv("CASELINKER_PARTY_SNAPSHOT", raising=False)
    with pytest.raises(SystemExit, match="no snapshot file"):
        parties_mod.load()
    parties_mod._CACHE.clear()
    snapshot = tmp_path / "parties.json"
    monkeypatch.setenv("CASELINKER_PARTY_SNAPSHOT", str(snapshot))
    monkeypatch.delenv("CASELINKER_PARTY_SNAPSHOT_SHA256", raising=False)
    with pytest.raises(SystemExit, match="requires CASELINKER_PARTY_SNAPSHOT_SHA256"):
        parties_mod.load()
    monkeypatch.setenv("CASELINKER_PARTY_SNAPSHOT_SHA256", "cd" * 32)
    with pytest.raises(SystemExit, match="not available"):
        parties_mod.load()
    snapshot.write_text(json.dumps([{"parties": [{"party_id": "p", "name": "Michael Smith", "role": "defendant"}]}]),
                        encoding="utf-8")
    monkeypatch.setenv("CASELINKER_PARTY_SNAPSHOT_SHA256", hashlib.sha256(snapshot.read_bytes()).hexdigest())
    with pytest.raises(SystemExit, match="missing a court"):
        parties_mod.load()


def test_a_changed_snapshot_is_read_again(tmp_path, monkeypatch):
    from state_machines.coding.parties import defendants_for, load
    from state_machines.coding import parties as parties_mod
    parties_mod._CACHE.clear()
    snapshot = tmp_path / "parties.json"

    def _write(name):
        snapshot.write_text(json.dumps([{
            "court": "dcd", "docket_number": "1:24-cr-8",
            "parties": [{"party_id": "p", "name": name, "role": "defendant"}],
        }]), encoding="utf-8")
        monkeypatch.setenv("CASELINKER_PARTY_SNAPSHOT", str(snapshot))
        monkeypatch.setenv("CASELINKER_PARTY_SNAPSHOT_SHA256", hashlib.sha256(snapshot.read_bytes()).hexdigest())

    _write("Michael Smith")
    assert load()["index"][("dcd", "1:24-cr-8")][0]["surname"] == "Smith"
    _write("Robert Porter")
    assert defendants_for("dcd", "1:24-cr-8")[0]["surname"] == "Porter"


def test_one_snapshot_defendant_and_two_caption_defendants_refuse(tmp_path, monkeypatch):
    sentence = f"The defendant sent {_TAIL}"
    snapshot = tmp_path / "parties.json"
    snapshot.write_text(json.dumps([{
        "court": "dcd", "docket_number": "1:24-cr-7",
        "parties": [{"party_id": "p-smith", "name": "Michael Smith", "role": "defendant"}],
    }]), encoding="utf-8")
    digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    monkeypatch.setenv("CASELINKER_PARTY_SNAPSHOT", str(snapshot))
    monkeypatch.setenv("CASELINKER_PARTY_SNAPSHOT_SHA256", digest)
    events, _log = code_events(
        tmp_path, monkeypatch, "both",
        [("sof", "statement_of_facts",
          [f"United States v. Michael Smith and Robert Porter, Defendants. {sentence}"])],
        sentence,
    )
    # code_events stores sources without court. Write them, then code again.
    sources = json.loads((tmp_path / "both" / "sources.json").read_text(encoding="utf-8"))
    sources["court"] = "dcd"
    sources["docket_number"] = "1:24-cr-7"
    (tmp_path / "both" / "sources.json").write_text(json.dumps(sources), encoding="utf-8")
    from state_machines.coding.workflow import build_deny
    bundle, _, _log = C.code_case("both", "coder_A", tmp_path, deny=build_deny("both", tmp_path))
    assert bundle["events"] == []


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
    company = "UNITED STATES v. MICHAEL SMITH and ACME WIDGETS, INC., Defendants. The defendant sent the files."
    events, _log = code_events(
        tmp_path, monkeypatch, "company",
        [("sof", "statement_of_facts", [company])],
        "The defendant sent the files.", means="")
    assert events == []
    assert "other_caption" in _reasons(tmp_path, "company")
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
