"""A snapshot is current only when every build input still matches.

Regression for the 2026-11-12 snapshot: corpus count and extraction-run
fingerprint matched, but the evidence was built from a candidate list 23 days
older than the corpus.
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "run"))

from platform_affordance_evidence_freshness import (  # noqa: E402
    candidate_pool_sha256,
    code_versions,
    corpus_identity_from_groups,
    identity_matches,
    mismatched_inputs,
    platform_pairs_identity,
    read_live_identity,
    rebuild_decision,
)

EVIDENCE_DIR = ROOT / "ontology" / "platform_affordance_evidence"


def _live(pairs_rows):
    live = corpus_identity_from_groups([("run-a", len(pairs_rows))])
    live.update(platform_pairs_identity(pairs_rows))
    live["code_versions"] = {"builder.py": "v1"}
    return live


def _meta_for(live):
    return {
        "corpus_case_count": live["case_count"],
        "extraction_run_fingerprint": live["extraction_run_fingerprint"],
        "platform_pairs_sha256": live["platform_pairs_sha256"],
        "code_versions": dict(live["code_versions"]),
    }


def test_same_count_and_run_but_re_resolved_platforms_is_stale():
    built = _live([("c1", '["Kik"]'), ("c2", '["Snapchat"]')])
    meta = _meta_for(built)
    now = _live([("c1", '["Kik"]'), ("c2", "[]")])  # platform dropped in place, same run
    assert now["case_count"] == built["case_count"]
    assert now["extraction_run_fingerprint"] == built["extraction_run_fingerprint"]
    assert rebuild_decision(meta, now) == "rebuild"
    assert mismatched_inputs(meta, now) == ["platform_pairs_sha256"]
    assert rebuild_decision(meta, built) == "current"


def test_rule_change_is_stale():
    live = _live([("c1", '["Kik"]')])
    meta = _meta_for(live)
    changed = {**live, "code_versions": {"builder.py": "v2"}}
    assert not identity_matches(meta, changed)
    assert mismatched_inputs(meta, changed) == ["code:builder.py"]


def test_snapshot_without_build_inputs_is_never_current():
    live = _live([("c1", '["Kik"]')])
    legacy = {"corpus_case_count": live["case_count"],
              "extraction_run_fingerprint": live["extraction_run_fingerprint"]}
    assert rebuild_decision(legacy, live) == "rebuild"


def test_pairs_identity_ignores_order_and_accepts_jsonb_lists():
    a = platform_pairs_identity([("c2", '["Snapchat","Kik"]'), ("c1", '["Kik"]')])
    b = platform_pairs_identity([("c1", ["Kik"]), ("c2", ["Kik", "Snapchat"])])
    assert a == b and a["platform_pairs"] == 3


def test_code_versions_cover_every_builder_file():
    versions = code_versions(ROOT)
    assert len(versions) == 3 and "missing" not in versions.values()


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, EVIDENCE_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tiny_db(path: Path, rows):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE cases (id TEXT PRIMARY KEY, platforms_used TEXT, raw_data TEXT, extraction_run_id TEXT)")
    for cid, plats, text in rows:
        conn.execute("INSERT INTO cases VALUES (?,?,?,?)",
                     (cid, json.dumps(plats), json.dumps({"case_text": text}), "run-1"))
    conn.commit()
    conn.close()


def test_builder_recomputes_candidates_and_ignores_a_stale_file(tmp_path, monkeypatch):
    db = tmp_path / "corpus.db"
    _tiny_db(db, [
        ("synthetic_2024_001", ["Kik"], "The defendant used Kik to send child sexual abuse material to an undercover officer."),
        ("synthetic_2024_002", ["Snapchat"], "He contacted the minor through Snapchat and asked for images."),
    ])
    stale = tmp_path / "candidates.json"
    stale.write_text(json.dumps({"summary": {}, "flat": [
        {"platform": "Discord", "case_ids": ["synthetic_2024_099"]}]}))
    builder = _load("platform_affordance_evidence")
    monkeypatch.setattr(builder, "DB", str(db))
    monkeypatch.setattr(builder, "CANDIDATES_FILE", str(stale))
    monkeypatch.setattr(builder, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(sys, "argv", ["builder"])
    builder.main()

    evidence = json.loads((tmp_path / "platform_affordance_evidence.json").read_text())
    written = json.loads(stale.read_text())
    platforms = {r["platform"] for r in evidence["records"]}
    assert platforms == {"Kik", "Snapchat"}          # nothing from the stale file
    assert evidence["_meta"]["cases_processed"] == 2
    assert evidence["_meta"]["candidate_pool_sha256"] == candidate_pool_sha256(written)
    with sqlite3.connect(db) as conn:
        live = read_live_identity(conn, ROOT)
    assert rebuild_decision(evidence["_meta"], live) == "current"
    # Re-resolving a platform in place, same run id, makes it stale.
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE cases SET platforms_used='[]' WHERE id='synthetic_2024_002'")
    with sqlite3.connect(db) as conn:
        live = read_live_identity(conn, ROOT)
    assert rebuild_decision(evidence["_meta"], live) == "rebuild"


def test_committed_snapshot_records_its_build_inputs():
    meta = json.loads((EVIDENCE_DIR / "platform_affordance_evidence.json").read_text())["_meta"]
    candidates = json.loads((EVIDENCE_DIR / "candidates.json").read_text())
    for key in ("platform_pairs_sha256", "candidate_pool_sha256", "code_versions"):
        assert meta.get(key), key
    assert meta["candidate_pool_sha256"] == candidate_pool_sha256(candidates)
    assert meta["code_versions"] == code_versions(ROOT)
