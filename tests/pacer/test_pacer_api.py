"""GET /api/ontology/pacer lists only the graphs a store holds, and names the release graph."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]


def _app():
    spec = importlib.util.spec_from_file_location("caselinker_run_main_pacer_api", ROOT / "run" / "main.py")
    mod = sys.modules.get("caselinker_run_main_pacer_api")
    if mod is None:
        mod = importlib.util.module_from_spec(spec)
        sys.modules["caselinker_run_main_pacer_api"] = mod
        spec.loader.exec_module(mod)
    return mod.app


def test_only_loaded_graphs_are_listed():
    from state_machines.trajectories.payload import release_dir
    manifest = json.loads((release_dir() / "manifest.json").read_text())     # the release the API serves (newest)
    empty = {(c["case_id"], k) for c in manifest["cases"] for k, v in c["graphs"].items()
             if 0 in (v.get("chains"), v.get("observations"))}
    assert empty   # the release has cases with no trajectory or no observation graph
    body = TestClient(_app()).get("/api/ontology/pacer").json()
    listed = {(c["case_id"], k) for c in body["cases"] for k in c["graphs"]}
    assert not listed & empty
    assert all("evidence" in c["graphs"] for c in body["cases"])
    assert body["release_graph"] == f"urn:caselinker:pacer-release:{manifest['release_id']}" and body["review_mode"] == "machine"
    assert manifest["release_id"] == "pacer-v2"


def test_evidence_graphs_load_on_the_canvas():
    """The graph page opens the evidence graph, the same way it used to open an investigation file."""
    client = TestClient(_app())
    body = client.get("/api/ontology/pacer").json()
    investigations = body["investigations"]
    assert len(investigations) == body["n"]
    one = next(row for row in investigations if row["id"] == "doj_ceos_2026_001")
    assert one["path"].endswith("/doj_ceos_2026_001.evidence.jsonld")
    assert "Action" in one["classes"]
    doc = client.get(one["path"]).json()
    assert isinstance(doc.get("@graph"), list) and doc["@graph"]
    assert any("Investigation" in str(node.get("@type")) for node in doc["@graph"])
    missing = client.get("/api/ontology/pacer/not_a_case.evidence.jsonld")
    assert missing.status_code == 404
    slipped = client.get("/api/ontology/pacer/..%2Fmanifest.evidence.jsonld")
    assert slipped.status_code == 404
