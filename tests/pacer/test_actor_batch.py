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


