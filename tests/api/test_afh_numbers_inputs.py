"""AfH numbers runs on any corpus: the AfH 2.0 snapshot is recognised, other inputs are labelled, never refused."""
import hashlib
import importlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

NUMBERS = Path(__file__).resolve().parents[2] / "ontology" / "platform_affordance_evidence" / "afh_manifest" / "numbers"


@pytest.fixture()
def ai(monkeypatch):
    monkeypatch.syspath_prepend(str(NUMBERS))
    monkeypatch.delenv("AFH_OUT", raising=False)
    import afh_inputs
    return importlib.reload(afh_inputs)


def _db(path: Path, n: int) -> Path:
    con = sqlite3.connect(path)
    con.execute("create table cases (id text)")
    con.executemany("insert into cases values (?)", [(f"c{i}",) for i in range(n)])
    con.commit()
    con.close()
    return path


def _pacer(root: Path) -> Path:
    (root / "cases").mkdir(parents=True)
    (root / "manifest.json").write_text(json.dumps({"release_id": "pacer-test"}))
    (root / "cases" / "a.json").write_text("{}")
    return root


def _snapshot(path: Path, ai, db: Path, pacer: Path) -> Path:
    path.write_text(json.dumps({"db_sha256": ai.sha256_file(db), "db_cases": 3,
                                "pacer_release": "pacer-test", "pacer_sha256": ai.sha256_tree(pacer)}))
    return path


def test_tree_hash_matches_snapshot_md_command(ai, tmp_path):
    """sha256_tree is the value of SNAPSHOT.md's `find . -type f | sort | xargs shasum -a 256 | shasum -a 256`."""
    root = _pacer(tmp_path / "p")
    (root / "B.json").write_text("x")
    listing = subprocess.run("find . -type f -print0 | LC_ALL=C sort -z | xargs -0 shasum -a 256",
                             shell=True, cwd=root, capture_output=True, text=True, check=True).stdout
    assert ai.sha256_tree(root) == hashlib.sha256(listing.encode()).hexdigest()


def test_snapshot_inputs_are_recognised(ai, tmp_path):
    db, pacer = _db(tmp_path / "c.db", 3), _pacer(tmp_path / "p")
    ident = ai.identity(db, pacer, _snapshot(tmp_path / "s.json", ai, db, pacer))
    assert ident["afh_2_0_snapshot"] is True
    assert ai.default_out(ident) == ai.HERE


def test_new_corpus_runs_and_is_labelled(ai, tmp_path):
    """Three months on, 100 more cases: identity() still answers, flags the DB, keeps the PACER match."""
    db, pacer = _db(tmp_path / "c.db", 3), _pacer(tmp_path / "p")
    snap = _snapshot(tmp_path / "s.json", ai, db, pacer)
    grown = _db(tmp_path / "grown.db", 103)
    ident = ai.identity(grown, pacer, snap)
    assert ident["db_cases"] == 103
    assert (ident["afh_2_0_snapshot"], ident["db_matches_afh_2_0"], ident["pacer_matches_afh_2_0"]) == (False, False, True)
    out = ai.default_out(ident)
    assert out != ai.HERE, "a new corpus must never overwrite the published AfH 2.0 outputs"
    assert out == ai.REPO / "local" / "afh-runs" / ident["db_sha256"][:12]


def test_changed_pacer_release_is_labelled(ai, tmp_path):
    db, pacer = _db(tmp_path / "c.db", 3), _pacer(tmp_path / "p")
    snap = _snapshot(tmp_path / "s.json", ai, db, pacer)
    (pacer / "cases" / "b.json").write_text("{}")
    ident = ai.identity(db, pacer, snap)
    assert (ident["afh_2_0_snapshot"], ident["db_matches_afh_2_0"], ident["pacer_matches_afh_2_0"]) == (False, True, False)


def test_afh_out_overrides(ai, tmp_path, monkeypatch):
    monkeypatch.setenv("AFH_OUT", str(tmp_path / "mine"))
    assert ai.out_dir({"afh_2_0_snapshot": True, "db_sha256": "0" * 64}) == (tmp_path / "mine").resolve()


def test_committed_reference_is_the_snapshot_md_values(ai):
    ref = json.loads(ai.SNAPSHOT_FILE.read_text())
    md = (ai.AFH / "SNAPSHOT.md").read_text()
    assert ref["db_sha256"] in md and ref["pacer_sha256"] in md


def test_other_run_never_replaces_the_afh_2_0_full_snapshot(ai, tmp_path):
    """A non-AfH 2.0 run once overwrote afh_manifest/data/snapshot.sqlite; it keeps its own copy now."""
    assert ai.full_snapshot_path(ai.HERE) == ai.AFH / "data" / "snapshot.sqlite"
    other = tmp_path / "local" / "afh-runs" / "abc"
    assert ai.full_snapshot_path(other) == other / "data" / "snapshot.sqlite"


def _cli(env_extra, tmp_path):
    import os
    env = {**os.environ, "AFH_OUT": str(tmp_path / "out"), **env_extra}
    env.pop("AFH_ALLOW_OTHER_INPUTS", None) if "AFH_ALLOW_OTHER_INPUTS" not in env_extra else None
    return subprocess.run([sys.executable, str(NUMBERS / "afh_inputs.py")], env=env, capture_output=True, text=True)


def test_cli_refuses_other_inputs_without_the_flag(tmp_path):
    db = _db(tmp_path / "grown.db", 103)
    r = _cli({"AFH_DB": str(db)}, tmp_path)
    assert r.returncode == 3 and "--other-inputs" in r.stderr
    assert not (tmp_path / "out" / "RUN_INPUTS.json").exists()


def test_cli_runs_other_inputs_with_the_flag_and_labels_them(tmp_path):
    db = _db(tmp_path / "grown.db", 103)
    r = _cli({"AFH_DB": str(db), "AFH_ALLOW_OTHER_INPUTS": "1"}, tmp_path)
    assert r.returncode == 0 and "WARNING" in r.stderr and "will not match AfH 2.0" in r.stderr
    got = json.loads((tmp_path / "out" / "RUN_INPUTS.json").read_text())
    assert got["afh_2_0_snapshot"] is False and got["db_cases"] == 103


# --- read-only inputs (Codex blocker: compute_numbers recreated a missing index) -----------

def _index_missing_db(path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "Storage Layer"))
    from storage import CaseStorage
    CaseStorage(str(path))                                   # full schema, then drop one index
    con = sqlite3.connect(path)
    idx = [n for (n,) in con.execute("select name from sqlite_master where type='index' and name like 'idx_%'")]
    con.execute(f"drop index {idx[0]}")
    con.execute("insert into cases (id, source) values ('c1', 'S')")
    con.commit()
    con.close()
    return path


def test_numbers_storage_reads_without_writing_an_index_missing_db(ai, tmp_path):
    from storage import CaseStorage
    db = _index_missing_db(tmp_path / "canary.db")
    before = ai.sha256_file(db)
    store = CaseStorage.read_only(str(db))
    assert len(store.get_all_cases(include_raw_data=False)) == 1
    store.count_assertion_feature_values(set())
    assert ai.sha256_file(db) == before


def test_read_only_storage_refuses_any_write(tmp_path):
    from storage import CaseStorage, get_connection
    db = _index_missing_db(tmp_path / "canary.db")
    con = get_connection(CaseStorage.read_only(str(db)).db_path)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        con.execute("create index idx_probe on cases(source)")


def test_compute_numbers_never_imports_the_api():
    """run/main.py builds a writable CaseStorage at import; the numbers path must not load it."""
    src = (NUMBERS / "compute_numbers.py").read_text()
    assert "run\" / \"main.py" not in src and "CaseStorage(str(" not in src


def test_run_fails_when_an_input_changed(ai, tmp_path, monkeypatch):
    db, pacer = _db(tmp_path / "c.db", 3), _pacer(tmp_path / "p")
    out = tmp_path / "out"
    out.mkdir()
    ident = ai.identity(db, pacer, _snapshot(tmp_path / "s.json", ai, db, pacer))
    (out / "RUN_INPUTS.json").write_text(json.dumps(ident))
    assert ai.check_unchanged(out, db, pacer) == []
    con = sqlite3.connect(db)
    con.execute("create index idx_late on cases(id)")
    con.commit()
    con.close()
    assert ai.check_unchanged(out, db, pacer) == ["db"]


def test_cli_refuses_to_write_other_inputs_into_shipped_numbers(tmp_path):
    db = _db(tmp_path / "grown.db", 103)
    r = _cli({"AFH_DB": str(db), "AFH_ALLOW_OTHER_INPUTS": "1", "AFH_OUT": str(NUMBERS)}, tmp_path)
    assert r.returncode == 3 and "shipped numbers/" in r.stderr


# --- two pacer-v2 pins (Codex: the git tree failed the full-release hash gate) ---------------

def test_snapshot_md_pins_full_release_public_subset_and_zenodo_files(ai):
    ref = json.loads(ai.SNAPSHOT_FILE.read_text())
    md = (ai.AFH / "SNAPSHOT.md").read_text()
    for h in (ref["pacer_sha256"], ref["pacer_public_sha256"], *ref["zenodo_files_sha256"].values()):
        assert h in md
    assert ref["data_doi"] in md


def test_git_shipped_pacer_subset_hashes_to_the_public_pin(ai, tmp_path):
    """Copy exactly the files git would ship and hash them like SNAPSHOT.md says."""
    import shutil
    root = ai.REPO / "state_machines" / "data" / "pacer-v2"
    shipped = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", "--", "."], cwd=root,
                             capture_output=True, text=True, check=True).stdout.split()
    dst = tmp_path / "pacer-v2"
    for rel in shipped:
        (dst / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, dst / rel)
    assert not (dst / "cases").exists()
    assert ai.sha256_tree(dst) == json.loads(ai.SNAPSHOT_FILE.read_text())["pacer_public_sha256"]


def test_public_subset_is_named_and_points_to_the_full_release(tmp_path):
    db, root = _db(tmp_path / "c.db", 3), tmp_path / "p"
    _pacer(root)
    ref = tmp_path / "s.json"
    import afh_inputs as ai_mod
    ref.write_text(json.dumps({"db_sha256": ai_mod.sha256_file(db), "pacer_sha256": "full",
                               "pacer_public_sha256": ai_mod.sha256_tree(root), "data_doi": "10.5281/zenodo.24520066"}))
    ident = ai_mod.identity(db, root, ref)
    assert ident["pacer_is_public_subset"] and not ident["afh_2_0_snapshot"]


def test_shipped_doc_type_inventory_reproduces_the_document_counts():
    num = NUMBERS
    inv = json.loads((num / "pacer_doc_types.json").read_text())["cases"]
    cover = json.loads((num / "numbers.json").read_text())["1_cover"]
    from collections import Counter
    total = Counter()
    for kinds in inv.values():
        total.update(kinds)
    assert len(inv) == cover["NPacerCases"] and sum(total.values()) == cover["NPacerDocs"]
    assert dict(total) == cover["NPacerDocs_by_type"]
