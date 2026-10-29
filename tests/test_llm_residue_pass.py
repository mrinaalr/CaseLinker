"""The residue pass appends LLM assertions and reports added finals and vetoes."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for sub in ("src", "src/Processing Layer", "src/Storage Layer", "src/Processing Layer/ML Processing Layer"):
    sys.path.insert(0, str(REPO / sub))

import processing  # noqa: E402
from storage import CaseStorage  # noqa: E402

_SPEC = importlib.util.spec_from_file_location(
    "llm_residue_pass", REPO / "scripts/run/llm_residue_pass.py"
)
residue = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader
_SPEC.loader.exec_module(residue)


def _store(tmp_path, case_id: str, text: str):
    amod = processing.assertions_module
    raw = [amod.gate_assertion(text, a) for a in amod.patterns.age_assertions(text)]
    assertions = [a for a in raw if a.get("span_ok")]
    resolutions = amod.resolve(assertions)
    storage = CaseStorage(str(tmp_path / "t.db"))
    storage.store_case({
        "id": case_id,
        "source": "TEST",
        "case_text": text,
        "raw_data": {"case_text": text, "case_id": case_id, "source_file": "test.pdf"},
        "assertions": assertions,
        "resolutions": resolutions,
        "date_range": {"start": "2024-01-02", "end": "2024-01-02"},
    })
    return storage, assertions, resolutions


def test_pass_adds_a_weak_victim_and_vetoes_a_defendant(tmp_path, monkeypatch):
    text = "Police described an 11-year-old female. Emerson Kingsmere, 40, of Phoenix, was arrested."
    storage, assertions, before = _store(tmp_path, "residue_case", text)
    assert 40 in (before["age"]["final_value"]["perpetrators"])
    assert 11 not in (before["age"]["final_value"]["victims"])

    def fake_generate(_cfg, prompt: str):
        # Candidate lines look like: 1. field=age window=W1 text="11"
        items = []
        for line in prompt.splitlines():
            if not line[:1].isdigit() or "text=" not in line:
                continue
            cid = int(line.split(".", 1)[0])
            quoted = line.split('text="', 1)[1].split('"', 1)[0]
            if quoted == "11":
                items.append({"id": cid, "role": "victim", "quote": "an 11-year-old female"})
            elif quoted == "40":
                items.append({"id": cid, "role": "decoy", "quote": "Emerson Kingsmere, 40, of Phoenix"})
        import json
        return json.dumps({"items": items}), 12, "ok"

    monkeypatch.setattr(residue.LLM, "_generate", fake_generate)
    cfg = {**residue.LLM.llm_config(), "provider": "ollama", "model": "test-model",
           "cache_path": str(tmp_path / "cache.db")}
    cache = residue.LLM.LLMCache(cfg["cache_path"])
    first = residue.pass_case(storage, "residue_case", cfg=cfg, cache=cache, digest="sha256:test")
    assert first["status"] == "called"
    # 11 was weak (0.6). The LLM agrees, so two families settle it. 40 was already
    # resolved, so it was not sent and is not vetoed.
    assert first["added"] == 1
    assert first["vetoed"] == 0
    again = residue.pass_case(storage, "residue_case", cfg=cfg, cache=cache, digest="sha256:test")
    assert again["status"] == "skipped_done"


def test_compare_finals_counts_a_value_that_disappears():
    before = {"age": {"final_value": {"victims": [14], "perpetrators": [40], "contested": {}}},
              "sentence": {"final_value": {"imposed": ["10 years"]}, "disagreement": {}}}
    after = {"age": {"final_value": {"victims": [], "perpetrators": [40], "contested": {"14": {"value": 14}}}},
             "sentence": {"final_value": {"imposed": ["10 years"]}, "disagreement": {}}}
    added, vetoed, added_pairs, vetoed_pairs = residue.compare_finals(before, after)
    assert added == 0
    assert vetoed == 1
    assert vetoed_pairs == [("victims", "14")]
    assert added_pairs == []


def test_lvmpd_repeated_23_is_accepted_inside_its_window(monkeypatch, tmp_path):
    """lvmpd_2026_001 has two '23's in one sentence. Each mention's own span is the quote."""
    text = (
        "Sawyer Avery Hartwell, 35; Rowan Quinn Juniperton, 23; "
        "Harper Jordan Ivorydale, 23; Jordan Reese Finley Lindqvast, 29. "
        "A later paragraph mentions 23 only as a count in a different section."
    )
    spans = []
    start = 0
    while True:
        found = text.find("23", start)
        if found < 0:
            break
        spans.append(found)
        start = found + 2
    assert len(spans) == 3
    arrest = spans[:2]
    import llm_extraction as LLM
    resolutions = {
        "age": {"final_value": {
            "contested": {},
            "unresolved": [{"span": [s, s + 2], "value": 23} for s in arrest],
            "victims": [], "perpetrators": [],
        }},
        "sentence": {"disagreement": {}},
        "investigation_type": {"final_value": ["cybertip"]},
    }

    def fake_generate(_cfg, prompt: str):
        import json
        items = []
        for line in prompt.splitlines():
            if not line[:1].isdigit() or 'text="' not in line:
                continue
            cid = int(line.split(".", 1)[0])
            quoted = line.split('text="', 1)[1].split('"', 1)[0]
            if quoted == "23":
                items.append({"id": cid, "role": "perpetrator", "quote": "23"})
        return json.dumps({"items": items}), 4, "ok"

    monkeypatch.setattr(LLM, "_generate", fake_generate)
    cfg = {**LLM.llm_config(), "provider": "ollama", "model": "test-model",
           "cache_path": str(tmp_path / "cache.db")}
    out, meta = LLM.run_llm(
        text, resolutions, [], processing.assertions_module.gate_assertion,
        cfg=cfg, cache=LLM.LLMCache(cfg["cache_path"]), digest="sha256:test",
    )
    assert meta["status"] == "ok"
    grounded = [a for a in out if a["span_ok"]]
    assert sorted(a["span_start"] for a in grounded) == arrest
    assert all(a["extras"]["quote_status"] == "ok" for a in grounded)


def test_already_done_matches_the_model_digest():
    assertions = [{"method": "llm", "extras": {"model_digest": "sha256:a"}}]
    assert residue.already_done(assertions, "sha256:a") is True
    assert residue.already_done(assertions, "sha256:b") is False
