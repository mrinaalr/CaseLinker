"""Anyone without caselinker.db can rebuild the AfH 2.0 Q1 build from the shipped text-free snapshot."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

AFH = Path(__file__).resolve().parents[2] / "ontology" / "platform_affordance_evidence" / "afh_manifest"
sys.path.insert(0, str(AFH))

from afhq1 import build, snapshot  # noqa: E402

PUBLIC = AFH / "numbers" / "public"


def _run_all():
    spec = importlib.util.spec_from_file_location("afh_run_all_public", AFH / "run_all.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def no_database(monkeypatch, tmp_path):
    """No full-text snapshot and no corpus DB: any attempt to open one fails the test."""
    def refuse(*_a, **_k):
        raise AssertionError("the public rebuild opened a database")
    monkeypatch.setattr(snapshot, "SNAPSHOT", tmp_path / "absent.sqlite")
    monkeypatch.setattr(snapshot, "connect", refuse)
    monkeypatch.setattr(build, "connect", refuse)
    monkeypatch.setenv("AFH_Q1_SOURCE_DB", str(tmp_path / "absent.db"))
    monkeypatch.setenv("CASELINKER_DB", str(tmp_path / "absent.db"))


def test_public_snapshot_rebuilds_the_shipped_build_byte_for_byte(no_database, capsys):
    assert snapshot.PUBLIC == PUBLIC
    assert _run_all().main(["--verify", "--public"]) == 0
    # run_all prints one verdict line last; background threads from other tests may print before it
    assert capsys.readouterr().out.strip().splitlines()[-1] == "identical"


def test_public_snapshot_names_the_shipped_corpus():
    meta = json.loads((PUBLIC / "meta.json").read_text())
    ident = json.loads((AFH / "numbers" / "build" / "RUN_IDENTITY.json").read_text())
    assert meta["dataset_identity"] == ident["dataset_identity"] and meta["case_count"] == 10802


def test_public_cases_carry_no_source_url():
    """No computation reads source_url, so the minimal public snapshot leaves it out."""
    with (PUBLIC / "cases.jsonl").open() as f:
        first = json.loads(f.readline())
    assert set(first) == {"id", "fingerprint", "source", "pub_year", "platforms", "topics", "dates"}


# --- the verifier checks the shipped bytes (Codex: a manifest replaced by {} still printed "identical") ---

def _shipped_copy(tmp_path):
    import shutil
    dst = tmp_path / "build"
    shutil.copytree(AFH / "numbers" / "build", dst, ignore=shutil.ignore_patterns("latex"))
    recorded = json.loads((dst / "RUN_IDENTITY.json").read_text())["outputs_sha256"]
    return dst, dict(recorded)


def test_verifier_passes_an_intact_release(tmp_path):
    dst, rebuilt = _shipped_copy(tmp_path)
    assert _run_all().verify_against_shipped(dst, rebuilt) == []


def test_verifier_fails_a_changed_shipped_file(tmp_path):
    dst, rebuilt = _shipped_copy(tmp_path)
    (dst / "manifest.json").write_text("{}")
    assert any(p.startswith("manifest.json") for p in _run_all().verify_against_shipped(dst, rebuilt))


def test_verifier_fails_a_missing_or_extra_file(tmp_path):
    dst, rebuilt = _shipped_copy(tmp_path)
    (dst / "inventory.json").unlink()
    (dst / "surprise.json").write_text("{}")
    got = _run_all().verify_against_shipped(dst, rebuilt)
    assert any(p.startswith("inventory.json: missing") for p in got)
    assert any(p.startswith("surprise.json") for p in got)


def test_outputs_never_claim_paper_numbers_without_afh_2_0_inputs(monkeypatch):
    from afhq1 import harm_release as hr
    monkeypatch.setattr(hr, "INPUTS", None)
    assert hr._paper_numbers() is False
    monkeypatch.setattr(hr, "INPUTS", {"afh_2_0_snapshot": False, "db_sha256": "x"})
    assert hr._paper_numbers() is False and hr._snapshot_label()["afh_2_0_snapshot"] is False
    monkeypatch.setattr(hr, "INPUTS", {"afh_2_0_snapshot": True})
    assert hr._paper_numbers() is True


def test_shipped_outputs_record_afh_2_0_inputs():
    num = AFH / "numbers"
    assert json.loads((num / "build" / "RUN_IDENTITY.json").read_text())["afh_inputs"]["afh_2_0_snapshot"] is True
    for f in ("harm_closed/affordance_harm_strict.json", "prevalence.json", "data_checks.json", "cooc/cooccurrence.json"):
        doc = json.loads((num / f).read_text())
        label = doc.get("afh_inputs") or doc.get("snapshot")
        assert isinstance(label, dict) and label["afh_2_0_snapshot"] is True, f


def test_every_shipped_build_json_carries_the_input_label():
    """Codex round 2: citations.json and validation_sample.json were arrays and carried no label."""
    for f in sorted((AFH / "numbers" / "build").glob("*.json")):
        doc = json.loads(f.read_text())
        assert isinstance(doc, dict), f.name
        label = doc.get("afh_inputs")
        assert isinstance(label, dict) and label["afh_2_0_snapshot"] is True, f.name


def test_no_shipped_numbers_file_carries_an_absolute_machine_path():
    """The task-force log once printed /Users/<name>/... into a shipped file."""
    import re
    rx = re.compile(r"/(?:Users|home)/[^/\s]+/")
    hits = [str(f.relative_to(AFH)) for f in (AFH / "numbers").rglob("*")
            if f.is_file() and f.suffix in (".json", ".md", ".csv", ".jsonl", ".out") and rx.search(f.read_text(errors="ignore"))]
    assert hits == [], hits
