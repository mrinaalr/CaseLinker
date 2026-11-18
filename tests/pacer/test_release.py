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

    ev_iri, tr_iri = case["graphs"]["evidence"]["iri"], case["graphs"]["trajectories"]["iri"]
    press = rdflib.URIRef("https://w3id.org/caselinker/resource/case/press_001")
    triple = (rdflib.URIRef("urn:s"), rdflib.URIRef("urn:p"), rdflib.Literal("o"))

    def load(select):
        ds = rdflib.Dataset()
        ds.parse(nquads("test-v1", data_root=root, select=select, out=tmp_path / f"{select}.nq"), format="nquads")
        ds.graph(press).add(triple)
        return ds

    # all: both kinds, each of its kind
    ds = load("all")
    assert {str(g.identifier) for g in ds.graphs() if str(g.identifier).startswith(GRAPH_PREFIX)} == {ev_iri, tr_iri}
    assert verify_store(m, _query(ds), min_case_graphs=1) == []
    # evidence only: the trajectory graph must be absent, and is reported if loaded anyway
    ds = load("evidence")
    assert {str(g.identifier) for g in ds.graphs() if str(g.identifier).startswith(GRAPH_PREFIX)} == {ev_iri}
    assert verify_store(m, _query(ds), min_case_graphs=1, select="evidence") == []
    assert any("missing PACER graph" in p and "trajectories" in p for p in verify_store(m, _query(ds), min_case_graphs=1))

    # a superseded graph, a stray PACER graph, a missing graph and a mixed-up graph are all reported
    ds = load("all")
    ds.graph(rdflib.URIRef("urn:pacer:kg:BULK_FOLDER/old.jsonld")).add(triple)
    ds.graph(rdflib.URIRef(f"{GRAPH_PREFIX}other_case:evidence")).add(triple)
    ds.graph(rdflib.URIRef(tr_iri)).add((rdflib.URIRef("urn:x"), rdflib.RDF.type,
                                         rdflib.URIRef("https://ontology.caseontology.org/case/investigation/Investigation")))
    ds.remove_graph(ds.graph(rdflib.URIRef(ev_iri)))
    problems = verify_store(m, _query(ds), min_case_graphs=2)
    assert any("superseded urn:pacer:kg" in p for p in problems)
    assert any("not in this release" in p and "other_case" in p for p in problems)
    assert any("missing PACER graph" in p and "evidence" in p for p in problems)
    assert any(tr_iri in p and "investigation" in p for p in problems)
    assert any("press-release case graphs" in p for p in problems)


def test_trajectory_graphs_name_rule_and_threshold_on_every_lifecycle(tmp_path):
    b = _adjudicated(F.build()[0])
    root = _release(tmp_path, b)
    m = build("test-v1", data_root=root, text_root=tmp_path / "text")
    ds = rdflib.Dataset()
    ds.parse(nquads("test-v1", data_root=root, out=tmp_path / "all.nq"), format="nquads")
    tr = ds.graph(rdflib.URIRef(m["cases"][0]["graphs"]["trajectories"]["iri"]))
    tr.remove((None, rdflib.URIRef("https://w3id.org/caselinker/trajectory#derivationRule"), None))
    problems = verify_store(m, _query(ds))
    assert any("without derivation rule and threshold" in p for p in problems)


def test_nquads_refuses_graph_files_that_drifted_from_the_manifest(tmp_path):
    b = _adjudicated(F.build()[0])
    root = _release(tmp_path, b)
    build("test-v1", data_root=root, text_root=tmp_path / "text")
    g = root / "test-v1" / "graphs" / f"{b['case_id']}.evidence.jsonld"
    g.write_text(g.read_text() + " ", encoding="utf-8")
    with pytest.raises(SystemExit, match="does not match the manifest"):
        nquads("test-v1", data_root=root)


def test_release_outputs_hold_no_coder_text(tmp_path):
    """Graphs, derived views and the page snapshot carry codes only: no act descriptions or notes."""
    b = _adjudicated(F.build()[0])
    root = _release(tmp_path, b)
    build("test-v1", data_root=root, text_root=tmp_path / "text")
    rel = root / "test-v1"
    out = "".join(p.read_text(encoding="utf-8") for p in [*rel.glob("graphs/*"), *rel.glob("derived/*"), rel / "lifecycle.json"])
    for e in b["events"]:
        assert e["description"] not in out


def test_release_graphs_hold_no_quotes_or_names(tmp_path):
    b = _adjudicated(F.build()[0])
    root = _release(tmp_path, b)
    build("test-v1", data_root=root, text_root=tmp_path / "text")
    _, quotes = F.build()
    for p in (root / "test-v1" / "graphs").glob("*.jsonld"):
        text = p.read_text()
        assert not [q for q in quotes.values() if len(q.split()) > 4 and q in text]


def test_bundle_folders_are_ignored_on_case_sensitive_filesystems():
    """cases/ must be ignored by its own rule, not by the case-insensitive match of Cases/."""
    import subprocess
    from pathlib import Path
    repo = Path(__file__).resolve().parents[2]

    def ignored(path):
        return subprocess.run(["git", "-c", "core.ignorecase=false", "check-ignore", "-q", path], cwd=repo).returncode == 0

    assert ignored("state_machines/data/any-release/cases/case.json")
    assert not ignored("state_machines/data/any-release/manifest.json")
    assert not ignored("state_machines/data/any-release/graphs/case.evidence.jsonld")
    assert not ignored("state_machines/data/any-release/derived/case.direct.json")
    # files the pipeline needs from a clean checkout
    assert not ignored("state_machines/coding/models.json")
    assert not ignored("state_machines/benchmark/data/synth_001/gold.json")
    assert not ignored("state_machines/benchmark/data/MANIFEST.json")
    assert ignored("local/coder_cache.db") and ignored("local/auto/coder_A/case.json")


def test_privacy_scan_finds_a_name_or_quote_in_committed_files(tmp_path):
    from state_machines.graphs.release import privacy_scan
    b = _adjudicated(F.build()[0])
    root = _release(tmp_path, b)
    build("test-v1", data_root=root, text_root=tmp_path / "text")
    (tmp_path / "text" / F.CASE / "deny.json").write_text(json.dumps(["Jordan Example"]), encoding="utf-8")
    _, quotes = F.build()
    (tmp_path / "text" / F.CASE / "quotes.json").write_text(json.dumps({f"coder_A:{k}": v for k, v in quotes.items()}), encoding="utf-8")
    clean = privacy_scan("test-v1", tmp_path / "text", data_root=root)
    assert clean["hits"] == [] and clean["files"] > 0 and clean["quotes"] > 0
    g = root / "test-v1" / "graphs" / f"{F.CASE}.evidence.jsonld"
    g.write_text(g.read_text() + "\n// Jordan Example " + next(iter(quotes.values())), encoding="utf-8")
    kinds = {h["kind"] for h in privacy_scan("test-v1", tmp_path / "text", data_root=root)["hits"]}
    assert kinds == {"deny", "quote"}


def test_privacy_scan_refuses_an_unlisted_platform_name_in_a_machine_coded_bundle(tmp_path):
    from state_machines.graphs.release import privacy_scan
    b = _adjudicated(F.build()[0])
    b["coding"]["note"] = "machine resolution (resolve-1.1.0) of two independent codings; not adjudicated"
    root = _release(tmp_path, b)
    build("test-v1", data_root=root, text_root=tmp_path / "text")
    path = root / "test-v1" / "cases" / f"{F.CASE}.json"
    bundle = json.loads(path.read_text())
    for a in bundle["events"]:                              # as the automated coder writes them: listed words only
        a["affordances"] = [{k: v for k, v in dict(o, feature_term="public group").items() if k != "platform_surface"} for o in a["affordances"]]
        a["platform_interactions"], a["platform_mentions"] = [], []
    path.write_text(json.dumps(bundle), encoding="utf-8")
    assert [h for h in privacy_scan("test-v1", tmp_path / "text", data_root=root)["hits"] if h["kind"] == "open_text"] == []
    e = next(x for x in bundle["events"] if x["affordances"])
    e["affordances"][0]["platform_surface"] = "Some Username"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    assert [h["kind"] for h in privacy_scan("test-v1", tmp_path / "text", data_root=root)["hits"]] == ["open_text"]


def test_deny_list_is_built_from_the_case_captions(tmp_path):
    from state_machines.coding.workflow import build_deny
    from state_machines.evidence import evidence as E
    E.write_page("case_x", "ind", 1, "UNITED STATES OF AMERICA ) ) v. ) Case No. 1:24-cr-1 JORDAN Q. EXAMPLE, ) Defendant.", tmp_path)
    E.write_page("case_x", "jdg", 1, "JUDGMENT IN A CRIMINAL CASE V. Jordan Example a/k/a Jay Sample Case Number 3", tmp_path)
    assert build_deny("case_x", tmp_path) == ["example", "jay", "jordan", "sample"]
    assert json.loads((tmp_path / "case_x" / "deny.json").read_text()) == ["example", "jay", "jordan", "sample"]


def test_a_case_without_offender_chains_has_no_trajectory_graph_to_load(tmp_path):
    b = _adjudicated(F.build()[0])
    keep = {e["event_id"] for e in b["events"] if e["action"].startswith(("LE_", "RESP_"))}
    b["events"] = [e for e in b["events"] if e["event_id"] in keep]
    b["relations"] = [r for r in b["relations"] if r["from_event"] in keep and r["to_event"] in keep]
    b["tracks"] = [dict(t, event_ids=[x for x in t["event_ids"] if x in keep]) for t in b["tracks"]]
    root = _release(tmp_path, b)
    m = build("test-v1", data_root=root, text_root=tmp_path / "text")
    assert m["cases"][0]["graphs"]["trajectories"]["chains"] == 0
    ds = rdflib.Dataset()
    ds.parse(nquads("test-v1", data_root=root, out=tmp_path / "all.nq"), format="nquads")
    assert verify_store(m, _query(ds)) == []


def test_a_release_with_observations_adds_a_third_graph_and_leaves_the_other_two_as_they_were(tmp_path):
    b = _adjudicated(F.build()[0])
    root = _release(tmp_path, b)
    (tmp_path / "text" / F.CASE / "sources.json").write_text(json.dumps({"case_id": F.CASE, "documents": b["documents"]}), encoding="utf-8")
    plain = build("test-v1", data_root=root, text_root=tmp_path / "text")
    before = {k: v["sha256"] for k, v in plain["cases"][0]["graphs"].items()}
    assert set(before) == {"evidence", "trajectories"} and not (root / "test-v1" / "observations").exists()
    m = build("test-v1", data_root=root, text_root=tmp_path / "text", observations=True)
    case = m["cases"][0]
    assert {k: v["sha256"] for k, v in case["graphs"].items() if k != "observations"} == before
    assert case["graphs"]["observations"]["iri"] == graph_iri(F.CASE, "observations") and case["observations"]["observations"] > 0
    assert case["shacl"]["violations"] == 0
    page = json.loads((root / "test-v1" / "lifecycle.json").read_text())["cases"][0]
    assert page["observed"]["feature_classes"] == case["observations"]["feature_classes"] and "observed" not in json.dumps(plain)
    stored = json.loads((root / "test-v1" / "observations" / f"{F.CASE}.json").read_text())
    assert "quote" not in json.dumps(stored).replace("quote_sha256", "").replace("quote_word_count", "")   # hashes and offsets, no text
    ds = rdflib.Dataset()
    ds.parse(nquads("test-v1", data_root=root, out=tmp_path / "all.nq"), format="nquads")
    assert verify_store(m, _query(ds)) == []
    ob = ds.graph(rdflib.URIRef(case["graphs"]["observations"]["iri"]))
    ob.remove((None, rdflib.URIRef("https://w3id.org/caselinker/trajectory#derivationRule"), None))
    assert any("without a derivation rule" in p for p in verify_store(m, _query(ds)))
    only = rdflib.Dataset()
    only.parse(nquads("test-v1", data_root=root, out=tmp_path / "ev.nq", select="evidence"), format="nquads")
    assert verify_store(m, _query(only), select="evidence") == [] and len(list(only.graphs())) <= 2
