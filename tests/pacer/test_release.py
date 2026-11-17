"""PACER graph releases: build, manifest, N-Quads with stable graph IRIs, store verification."""
from __future__ import annotations

import copy
import json

import pytest
import rdflib

from tests.pacer import fixtures as F

pytest.importorskip("case_uco")

from state_machines.graphs.release import GRAPH_PREFIX, build, graph_iri, nquads, verify_store  # noqa: E402


def _adjudicated(bundle):
    b = copy.deepcopy(bundle)
    for e in b["events"]:
        e["review"] = {"status": "adjudicated", "coders": ["coder_A", "coder_B"], "adjudicator": "author"}
    return b


def _release(tmp_path, bundle, release="test-v1"):
    cases = tmp_path / "data" / release / "cases"
    cases.mkdir(parents=True)
    (cases / f"{bundle['case_id']}.json").write_text(json.dumps(bundle), encoding="utf-8")
    F.write_pages(tmp_path / "text")
    return tmp_path / "data"


def _query(ds):
    def run(q):
        out = []
        for row in ds.query(q):
            out.append({str(k): str(v) for k, v in row.asdict().items()})
        return out
    return run


def test_unadjudicated_bundles_are_refused_unless_building_a_preview(tmp_path):
    b, _ = F.build()
    root = _release(tmp_path, b)
    with pytest.raises(SystemExit, match="not adjudicated"):
        build("test-v1", data_root=root, text_root=tmp_path / "text")
    m = build("test-v1", data_root=root, text_root=tmp_path / "text", allow_unreviewed=True)
    assert m["adjudicated"] is False


def test_invalid_bundles_are_refused(tmp_path):
    b = _adjudicated(F.build()[0])
    b["events"][0]["time"]["assertions"][0]["basis"] = "enclosing_window"   # a DIRECT window: T13
    root = _release(tmp_path, b)
    with pytest.raises(SystemExit, match="T13"):
        build("test-v1", data_root=root, text_root=tmp_path / "text")


def test_release_manifest_nquads_and_store_verification(tmp_path):
    b = _adjudicated(F.build()[0])
    root = _release(tmp_path, b)
    m = build("test-v1", data_root=root, text_root=tmp_path / "text")
    case = m["cases"][0]
    assert m["adjudicated"] is True and m["schema_version"] == "2.0.0"
    assert case["graphs"]["evidence"]["iri"] == graph_iri(b["case_id"], "evidence") == f"{GRAPH_PREFIX}{b['case_id']}:evidence"
    assert case["shacl"]["violations"] == 0
    assert set(case["source_documents"]) == {d["sha256"] for d in b["documents"]}

    nq = nquads("test-v1", data_root=root)
    ds = rdflib.Dataset()
    ds.parse(nq, format="nquads")
    ds.graph(rdflib.URIRef("https://w3id.org/caselinker/resource/case/press_001")).add(
        (rdflib.URIRef("urn:s"), rdflib.URIRef("urn:p"), rdflib.Literal("o")))
    assert verify_store(m, _query(ds), min_case_graphs=1) == []

    # a superseded graph, a stray PACER graph and a missing graph are all reported
    ds.graph(rdflib.URIRef("urn:pacer:kg:BULK_FOLDER/old.jsonld")).add((rdflib.URIRef("urn:s"), rdflib.URIRef("urn:p"), rdflib.Literal("o")))
    ds.graph(rdflib.URIRef(f"{GRAPH_PREFIX}other_case:evidence")).add((rdflib.URIRef("urn:s"), rdflib.URIRef("urn:p"), rdflib.Literal("o")))
    ds.remove_graph(ds.graph(rdflib.URIRef(case["graphs"]["trajectories"]["iri"])))
    problems = verify_store(m, _query(ds), min_case_graphs=2)
    assert any("superseded urn:pacer:kg" in p for p in problems)
    assert any("not in this release" in p for p in problems)
    assert any("missing PACER graph" in p and "trajectories" in p for p in problems)
    assert any("press-release case graphs" in p for p in problems)


def test_nquads_refuses_graph_files_that_drifted_from_the_manifest(tmp_path):
    b = _adjudicated(F.build()[0])
    root = _release(tmp_path, b)
    build("test-v1", data_root=root, text_root=tmp_path / "text")
    g = root / "test-v1" / "graphs" / f"{b['case_id']}.evidence.jsonld"
    g.write_text(g.read_text() + " ", encoding="utf-8")
    with pytest.raises(SystemExit, match="does not match the manifest"):
        nquads("test-v1", data_root=root)


def test_release_graphs_hold_no_quotes_or_names(tmp_path):
    b = _adjudicated(F.build()[0])
    root = _release(tmp_path, b)
    build("test-v1", data_root=root, text_root=tmp_path / "text")
    _, quotes = F.build()
    for p in (root / "test-v1" / "graphs").glob("*.jsonld"):
        text = p.read_text()
        assert not [q for q in quotes.values() if len(q.split()) > 4 and q in text]
