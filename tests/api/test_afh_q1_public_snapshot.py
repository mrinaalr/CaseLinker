"""AfH 2.0 Q1 public snapshot and frozen-era snapshots. Synthetic data only."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "ontology" / "platform_affordance_evidence" / "afh_manifest"
sys.path.insert(0, str(MANIFEST))

from afhq1 import build, pipeline as pl, snapshot  # noqa: E402

CASES = [
    {"id": "c1", "source": "SRC", "source_url": "https://example.org/1", "pub_year": 2021,
     "platforms": ["Kik"], "topics": ["t"], "text": "release text that must not ship", "person_spans": [[0, 7]]},
    {"id": "c2", "source": "SRC", "source_url": "https://example.org/2", "pub_year": None,
     "platforms": [], "topics": [], "text": "another release", "person_spans": None},
]
RECORDS = [pl.Record("c1", "fp1", "SRC", 2021, "Kik", "specific", "messaging", "stated", True,
                     tier_linewrap="stated", conduct=["contact"], sentence_spans=[(3, 9)],
                     instrumental={"Anonymity": True}, instrumental_span={"Anonymity": (3, 9)},
                     review={"Anonymity": "candidate"}, harm_direct={"h1": True})]
EXCLUDED = [{"case_id": "c2", "platform": "online", "reason": "generic_excluded"}]
DATES = {"c1": {"roles": {"publication": 1}, "first_year": {"publication": 2021}, "version": "1.1.0"},
         "c2": {"roles": {}, "first_year": {}, "version": "1.1.0"}}
META = {"dataset_identity": "abc", "case_count": "2"}


def _write(tmp_path):
    snapshot.write_public(tmp_path, META, CASES, {"c1": "fp1", "c2": "fp2"}, RECORDS, EXCLUDED, DATES)
    return tmp_path


def test_public_snapshot_round_trips(tmp_path):
    meta, cases, fps, records, excluded, dates = snapshot.load_public(_write(tmp_path))
    assert meta == META
    assert records == RECORDS
    assert excluded == EXCLUDED and dates == DATES
    assert fps == {"c1": "fp1", "c2": "fp2"}
    assert [c["id"] for c in cases] == ["c1", "c2"] and cases[0]["platforms"] == ["Kik"]


def test_public_snapshot_holds_no_text_or_spans(tmp_path):
    blob = "".join(p.read_text() for p in _write(tmp_path).iterdir())
    assert "release text" not in blob and "another release" not in blob
    assert "person_spans" not in blob and '"text"' not in blob
    _, cases, *_ = snapshot.load_public(tmp_path)
    assert all(c["text"] is None and c["person_spans"] is None for c in cases)


def test_load_public_without_snapshot_says_how_to_make_it(tmp_path):
    with pytest.raises(FileNotFoundError, match="public snapshot"):
        snapshot.load_public(tmp_path)


def test_text_only_outputs_are_the_ones_that_read_release_text():
    assert build.TEXT_ONLY_OUTPUTS == ("legacy_afh1_exemplars.json",)


@pytest.mark.skipif(not snapshot.SNAPSHOT.is_file(), reason="full snapshot not exported")
def test_public_build_equals_full_build(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "OUT", tmp_path / "full")
    monkeypatch.setattr(build, "PUBLIC", tmp_path / "public")
    full = build.build(log=lambda *_: None)
    monkeypatch.setattr(build, "OUT", tmp_path / "pub")
    pub = build.build(log=lambda *_: None, public=True)
    assert pub["dataset_identity"] == full["dataset_identity"]
    assert set(full["outputs_sha256"]) - set(pub["outputs_sha256"]) == set(build.TEXT_ONLY_OUTPUTS)
    assert {k: v for k, v in full["outputs_sha256"].items() if k not in build.TEXT_ONLY_OUTPUTS} == pub["outputs_sha256"]


# --- run_all ---------------------------------------------------------------------------------

def _run_all():
    spec = importlib.util.spec_from_file_location("afh_run_all", MANIFEST / "run_all.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_verify_without_committed_outputs_exits_cleanly(tmp_path, monkeypatch, capsys):
    ra = _run_all()
    monkeypatch.setattr(ra, "HERE", tmp_path)
    assert ra.main(["--verify", "--public"]) == 2
    assert "no committed outputs" in capsys.readouterr().err


def test_fetch_era_rejects_unregistered_era(tmp_path, monkeypatch):
    ra = _run_all()
    reg = tmp_path / "snapshots.json"
    reg.write_text(json.dumps({"eras": {}}))
    monkeypatch.setattr(ra, "ERAS", reg)
    with pytest.raises(SystemExit, match="unknown era"):
        ra.fetch_era("afh-2.0")


def test_fetch_era_rejects_sha_mismatch_and_keeps_no_file(tmp_path, monkeypatch):
    ra = _run_all()
    reg = tmp_path / "snapshots.json"
    reg.write_text(json.dumps({"eras": {"afh-2.0": {"sha256": hashlib.sha256(b"real").hexdigest()}}}))
    monkeypatch.setattr(ra, "ERAS", reg)
    monkeypatch.setattr(ra.snapshot, "DATA", tmp_path / "data")
    monkeypatch.setattr(ra.snapshot, "SNAPSHOT", tmp_path / "data" / "snapshot.sqlite")
    monkeypatch.setenv("CASELINKER_API_URL", "https://example.invalid")
    monkeypatch.setenv("CASELINKER_KEY", "k")

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(ra.urllib.request, "urlopen", lambda req: Resp(b"tampered"))
    with pytest.raises(SystemExit, match="sha256"):
        ra.fetch_era("afh-2.0")
    assert not any((tmp_path / "data").iterdir())


def test_fetch_era_installs_matching_file(tmp_path, monkeypatch):
    ra = _run_all()
    reg = tmp_path / "snapshots.json"
    reg.write_text(json.dumps({"eras": {"afh-2.0": {"sha256": hashlib.sha256(b"real").hexdigest()}}}))
    monkeypatch.setattr(ra, "ERAS", reg)
    monkeypatch.setattr(ra.snapshot, "DATA", tmp_path / "data")
    monkeypatch.setattr(ra.snapshot, "SNAPSHOT", tmp_path / "data" / "snapshot.sqlite")
    monkeypatch.setenv("CASELINKER_API_URL", "https://example.invalid")
    monkeypatch.setenv("CASELINKER_KEY", "k")

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    seen = {}

    def urlopen(req):
        seen["key"] = req.get_header("Caselinker-key")
        return Resp(b"real")

    monkeypatch.setattr(ra.urllib.request, "urlopen", urlopen)
    ra.fetch_era("afh-2.0")
    assert (tmp_path / "data" / "snapshot.sqlite").read_bytes() == b"real"
    assert seen["key"] == "k"


# --- GET /api/snapshots/<era> ------------------------------------------------------------------

@pytest.fixture
def main(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("caselinker_run_main_snapshots", ROOT / "run" / "main.py")
    mod = sys.modules.get("caselinker_run_main_snapshots")
    if mod is None:
        mod = importlib.util.module_from_spec(spec)
        sys.modules["caselinker_run_main_snapshots"] = mod
        spec.loader.exec_module(mod)
    reg = tmp_path / "snapshots.json"
    reg.write_text(json.dumps({"eras": {"afh-2.0": {"sha256": "f" * 64}}}))
    monkeypatch.setattr(mod, "_SNAPSHOT_ERAS", reg)
    monkeypatch.setattr(mod, "CASELINKER_TRUSTED_KEYS", {"k-test"})
    (tmp_path / "store").mkdir()
    monkeypatch.setenv("CASELINKER_SNAPSHOT_DIR", str(tmp_path / "store"))
    mod.limiter.reset()
    return mod, tmp_path / "store"


def _remote(mod):
    return TestClient(mod.app, client=("203.0.113.9", 50000))


def test_snapshot_needs_a_trusted_key(main):
    mod, _ = main
    assert _remote(mod).get("/api/snapshots/afh-2.0").status_code == 403
    assert _remote(mod).get("/api/snapshots/afh-2.0", headers={"CaseLinker-Key": "wrong"}).status_code == 403


def test_snapshot_serves_only_registered_eras(main):
    mod, store = main
    (store / "other.sqlite").write_bytes(b"x")
    r = _remote(mod).get("/api/snapshots/other", headers={"CaseLinker-Key": "k-test"})
    assert r.status_code == 404 and "unknown" in r.json()["detail"]
    r = _remote(mod).get("/api/snapshots/..%2Fsnapshots", headers={"CaseLinker-Key": "k-test"})
    assert r.status_code == 404


def test_registered_era_not_hosted_is_404(main):
    mod, _ = main
    r = _remote(mod).get("/api/snapshots/afh-2.0", headers={"CaseLinker-Key": "k-test"})
    assert r.status_code == 404 and "not hosted" in r.json()["detail"]


def test_registered_hosted_era_is_served_with_its_sha(main):
    mod, store = main
    (store / "afh-2.0.sqlite").write_bytes(b"frozen")
    r = _remote(mod).get("/api/snapshots/afh-2.0", headers={"CaseLinker-Key": "k-test"})
    assert r.status_code == 200 and r.content == b"frozen"
    assert r.headers["X-Snapshot-SHA256"] == "f" * 64


def test_committed_registry_is_well_formed():
    eras = json.loads((MANIFEST / "snapshots.json").read_text())["eras"]
    for era, e in eras.items():
        assert set(e) >= {"sha256", "dataset_identity", "case_count", "frozen"}, era
        assert len(e["sha256"]) == 64
