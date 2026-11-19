"""PACER graph releases: build, manifest, N-Quads with stable graph IRIs, store verification."""
from __future__ import annotations

import copy
import json
import shutil

from pathlib import Path

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
    b["coding"]["note"] = "machine resolution (resolve-1.2.0) of two independent codings; not adjudicated"
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
    del e["affordances"][0]["platform_surface"]
    bundle["documents"][0]["source_path"] = f"BULK_FOLDER/pacer -- {F.CASE} -- Smithson Factual Proffer.pdf"   # a file name as collected
    path.write_text(json.dumps(bundle), encoding="utf-8")
    assert [h["kind"] for h in privacy_scan("test-v1", tmp_path / "text", data_root=root)["hits"]] == ["open_text"]
    tail = bundle["documents"][0]["doc_type"].replace("_", " ")
    bundle["documents"][0]["source_path"] = f"BULK_FOLDER/pacer -- Smithson -- {tail}.pdf"                     # a valid tail, a name where the case id belongs
    path.write_text(json.dumps(bundle), encoding="utf-8")
    assert [h["kind"] for h in privacy_scan("test-v1", tmp_path / "text", data_root=root)["hits"]] == ["open_text"]
    bundle["documents"][0]["source_path"] = f"FICTIONAL/{F.CASE} -- {bundle['documents'][0]['doc_type']}.pdf"
    bundle["events"][0]["platform_interactions"] = [dict(platform_surface="Some Username", platform_key="Some Username", mode="through")]
    path.write_text(json.dumps(bundle), encoding="utf-8")
    assert [h["kind"] for h in privacy_scan("test-v1", tmp_path / "text", data_root=root)["hits"]] == ["open_text"]   # every platform surface is checked
    bundle["events"][0]["platform_interactions"] = []
    path.write_text(json.dumps(bundle), encoding="utf-8")
    # the committed observation files are held to the same lists and forms
    obs = root / "test-v1" / "observations"
    obs.mkdir(exist_ok=True)
    row = {"observation_id": "o0001", "kind": "platform", "platform": "Some Username", "named_as": "Some Username"}
    (obs / f"{F.CASE}.json").write_text(json.dumps({"case_id": F.CASE, "observations": [row]}), encoding="utf-8")
    assert [(h["kind"], h["file"]) for h in privacy_scan("test-v1", tmp_path / "text", data_root=root)["hits"]] == [("open_text", f"observations/{F.CASE}.json")]
    row = {"observation_id": "o0001", "kind": "service_description", "service_term": "somebody's private site"}
    (obs / f"{F.CASE}.json").write_text(json.dumps({"case_id": F.CASE, "observations": [row]}), encoding="utf-8")
    assert [h["kind"] for h in privacy_scan("test-v1", tmp_path / "text", data_root=root)["hits"]] == ["open_text"]


def test_extraction_keeps_file_names_local_and_adds_new_filings_without_touching_old_ones(tmp_path, monkeypatch):
    pymupdf = pytest.importorskip("pymupdf")
    from state_machines.coding import workflow as W
    src, text = tmp_path / "src", tmp_path / "text"
    (src / "BULK_FOLDER").mkdir(parents=True)

    def pdf(name, words):
        d = pymupdf.open()
        d.new_page().insert_textbox(pymupdf.Rect(40, 40, 560, 780), (words + " ") * 40)
        d.save(str(src / "BULK_FOLDER" / name))
    monkeypatch.setenv("CASELINKER_PACER_SOURCE", str(src))
    monkeypatch.setitem(W.COLLECTED_AS, "agency_2024_002", "agency_2024_009")      # the press release was renumbered after collection
    pdf("pacer -- agency_2024_009 -- Smithson Factual Proffer.pdf", "The defendant admits the facts set out here.")
    first = W.extract("agency_2024_002", text)
    (doc,) = first["documents"]
    assert doc["doc_id"] == "factual_proffer" and doc["source_path"] == "BULK_FOLDER/pacer -- agency_2024_002 -- factual proffer.pdf"
    assert "Smithson" not in json.dumps(first)                                        # the name on disk stays in the local store
    assert W.local_file("agency_2024_002", "factual_proffer", text).name == "pacer -- agency_2024_009 -- Smithson Factual Proffer.pdf"
    (text / "agency_2024_002" / "sources.json").write_text(json.dumps(first), encoding="utf-8")
    page = text / "agency_2024_002" / "factual_proffer" / "p0001.txt"
    stamp = page.stat().st_mtime_ns
    pdf("pacer -- agency_2024_009 -- Avery Factual Proffer.pdf", "A second defendant admits other facts in this one.")   # sorts before the first
    pdf("pacer -- agency_2024_009 -- criminal complaint.pdf", "The affiant states the following on oath to the court.")
    second = W.extract("agency_2024_002", text)
    assert [d["doc_id"] for d in second["documents"]] == ["factual_proffer_2", "factual_proffer", "complaint"]     # file-name order
    assert next(d for d in second["documents"] if d["doc_id"] == "factual_proffer")["sha256"] == doc["sha256"]   # the old filing keeps its id
    assert page.stat().st_mtime_ns == stamp                                           # and its page text is not rewritten
    # a rerun recodes a case whose documents changed, and a build refuses a bundle that does not cover them
    from state_machines.coding.pipeline import _same_documents
    coded = tmp_path / "coded.json"
    coded.write_text(json.dumps({"documents": first["documents"]}), encoding="utf-8")
    assert _same_documents(coded, text, "agency_2024_002")                         # sources.json still lists the one document
    (text / "agency_2024_002" / "sources.json").write_text(json.dumps(second), encoding="utf-8")
    assert not _same_documents(coded, text, "agency_2024_002")                     # two filings were added: code the case again
    shutil.copy(src / "BULK_FOLDER" / "pacer -- agency_2024_009 -- criminal complaint.pdf",
                src / "BULK_FOLDER" / "pacer -- agency_2024_009 -- copy of complaint.pdf")                     # the same file under two names
    assert len(W.extract("agency_2024_002", text)["documents"]) == 3
    with pytest.raises(FileNotFoundError):                                          # a mistyped id is an error, not an empty case
        W.extract("agency_2024_999", text)
    assert not (text / "agency_2024_999" / "sources.json").exists()
    assert W.doc_type_of(Path("pacer -- x -- response in opposition.pdf")) == "brief" and W.doc_type_of(Path("pacer -- x -- memorandum opinion and order.pdf")) == "opinion"


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
    assert set(page["observed"]["features"]) == set(case["observations"]["feature_classes"]) and "mentions, not use" in page["observed"]["meaning"]
    # the research table is rebuilt from the committed files alone and keeps the three kinds of evidence apart
    from state_machines.observations import table as T
    stored = json.loads((root / "test-v1" / "research_table.json").read_text())
    assert stored == json.loads(json.dumps(T.build(root / "test-v1"), sort_keys=True))
    row = stored["cases"][0]
    assert {"platform_named", "feature_stated", "used_in_act"} <= set(row) and row["counts"]["feature_statements"] == case["observations"]["feature_observations"]
    assert (root / "test-v1" / "research_table.csv").read_text().splitlines()[0].split(",")[:3] == ["case_id", "documents", "agreed_acts"]
    # the affordance evidence matrix: every class present, kinds of evidence apart, rebuilt from committed files alone
    from state_machines.observations import affordance_matrix as AM
    from state_machines.evidence import vocab as V
    matrix = json.loads((root / "test-v1" / "affordance_matrix.json").read_text())
    assert [c["affordance_class"] for c in matrix["classes"]] == list(V.AFFORDANCE_CLASSES) and matrix["cases_read"] == 1
    stated = {c["affordance_class"]: c["phrase_stated"]["statements"] for c in matrix["classes"]}
    assert sum(stated.values()) == case["observations"]["feature_observations"]
    for c in matrix["classes"]:
        assert not (c["needs_researcher_interpretation"] and c["no_evidence_in_these_records"])
        assert c["no_evidence_in_these_records"] == (not c["phrase_stated"]["statements"] and not c["means_stated_in_act_sentence"]["acts"])
        assert set(c["in_agreed_act_sentence"]["cases"]) <= set(c["phrase_stated"]["cases"])       # co-occurrence needs a statement
        assert set(c["means_stated_act_disputed"]["cases"]) <= set(c["phrase_stated"]["cases"])   # a disputed-act sentence is a statement too
        assert c["means_stated_act_disputed"]["sentences"] == 0                                    # no coder bundles in this build: no tier
    import re
    assert re.fullmatch(r"v\d+\.\d+\.\d+ [0-9a-f]{40}", m["sdk"])                               # the SDK that wrote the graphs, not a comment line
    import hashlib
    assert case["bundle_sha256"] == hashlib.sha256((root / "test-v1" / "cases" / f"{F.CASE}.json").read_bytes()).hexdigest()   # the bundle's own hash
    # with the two coders' bundles at hand the build is the same release plus the disputed tier, and the manifest still names the agreed bundle
    coders = tmp_path / "coders"
    for name in ("coder_A", "coder_B"):
        (coders / name).mkdir(parents=True)
        (coders / name / f"{F.CASE}.json").write_text(json.dumps(b), encoding="utf-8")
    m2 = build("test-v1", data_root=root, text_root=tmp_path / "text", observations=True, coders_root=coders)
    assert m2["cases"][0]["bundle_sha256"] == case["bundle_sha256"]
    assert {k: v["sha256"] for k, v in m2["cases"][0]["graphs"].items() if k != "observations"} == before
    assert {n: (root / "test-v1" / n).read_text() for n in AM.FILES} == AM.rendered(root / "test-v1")
    assert len((root / "test-v1" / "affordance_case_grid.csv").read_text().splitlines()) == 2
    shutil.rmtree(root / "test-v1" / "cases")                       # no local bundle is needed
    assert json.loads(json.dumps(T.build(root / "test-v1"), sort_keys=True)) == stored
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


def test_a_build_refuses_a_bundle_that_does_not_cover_the_stored_documents(tmp_path):
    b = _adjudicated(F.build()[0])
    root = _release(tmp_path, b)
    extra = dict(b["documents"][0], doc_id="complaint", doc_type="complaint", sha256="f" * 64)       # a filing added after coding
    (tmp_path / "text" / F.CASE / "sources.json").write_text(json.dumps({"case_id": F.CASE, "documents": b["documents"] + [extra]}), encoding="utf-8")
    with pytest.raises(SystemExit, match="recode the case"):
        build("test-v1", data_root=root, text_root=tmp_path / "text", observations=True)


def test_a_rebuild_without_observations_leaves_none_behind(tmp_path):
    b = _adjudicated(F.build()[0])
    root = _release(tmp_path, b)
    (tmp_path / "text" / F.CASE / "sources.json").write_text(json.dumps({"case_id": F.CASE, "documents": b["documents"]}), encoding="utf-8")
    build("test-v1", data_root=root, text_root=tmp_path / "text", observations=True)
    rel = root / "test-v1"
    assert (rel / "research_table.json").is_file() and "observed" in (rel / "lifecycle.json").read_text()
    m = build("test-v1", data_root=root, text_root=tmp_path / "text")
    assert set(m["cases"][0]["graphs"]) == {"evidence", "trajectories"}
    assert "observed" not in (rel / "lifecycle.json").read_text()
    left = [p.name for p in rel.rglob("*") if "observations" in p.name or p.name.startswith(("research_table", "affordance_"))]
    assert left in ([], ["observations"]) and not list((rel / "observations").glob("*"))
