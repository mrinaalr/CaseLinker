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
    manifest = json.loads((ROOT / "state_machines/data/pacer-v1/manifest.json").read_text())
    empty = {(c["case_id"], k) for c in manifest["cases"] for k, v in c["graphs"].items()
             if 0 in (v.get("chains"), v.get("observations"))}
    assert empty   # pacer-v1 has cases with no trajectory or no observation graph
    body = TestClient(_app()).get("/api/ontology/pacer").json()
    listed = {(c["case_id"], k) for c in body["cases"] for k in c["graphs"]}
    assert not listed & empty
    assert all("evidence" in c["graphs"] for c in body["cases"])
    assert body["release_graph"] == "urn:caselinker:pacer-release:pacer-v1" and body["review_mode"] == "machine"
