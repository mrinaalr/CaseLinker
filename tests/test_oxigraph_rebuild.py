"""Canonical TTL selection and N-Quads named-graph build."""

from __future__ import annotations

import sys

import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY = ROOT / "ontology"
if str(ONTOLOGY) not in sys.path:
    sys.path.insert(0, str(ONTOLOGY))

from oxigraph_rebuild import (  # noqa: E402
    CASE_GRAPH_BASE,
    build_nquads,
    canonical_ttl_paths,
    case_graph_iri,
    pool_label_for_path,
    provenance_graph_iri,
)


def _write_ttl(path: Path, subject: str, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
        f"<{subject}> rdfs:label \"{label}\" .\n",
        encoding="utf-8",
    )


def test_canonical_priority_universe_over_staging_big_bang_analysis(tmp_path: Path):
    shared = "case_shared"
    _write_ttl(tmp_path / "universe" / f"{shared}.ttl", "http://ex.org/u", "universe")
    _write_ttl(tmp_path / f"{shared}.ttl", "http://ex.org/s", "staging")
    _write_ttl(tmp_path / "big_bang" / f"{shared}.ttl", "http://ex.org/b", "big_bang")
    _write_ttl(tmp_path / "analysis" / f"{shared}.ttl", "http://ex.org/a", "analysis")

    _write_ttl(tmp_path / "only_staging.ttl", "http://ex.org/st", "staging-only")
    _write_ttl(tmp_path / "big_bang" / "only_bang.ttl", "http://ex.org/bb", "bang-only")
    _write_ttl(tmp_path / "analysis" / "only_analysis.ttl", "http://ex.org/an", "analysis-only")

    chosen = canonical_ttl_paths(tmp_path)
    assert chosen[shared] == tmp_path / "universe" / f"{shared}.ttl"
    assert chosen["only_staging"] == tmp_path / "only_staging.ttl"
    assert chosen["only_bang"] == tmp_path / "big_bang" / "only_bang.ttl"
    assert chosen["only_analysis"] == tmp_path / "analysis" / "only_analysis.ttl"
    assert pool_label_for_path(chosen[shared]) == "universe"
    assert pool_label_for_path(chosen["only_staging"], graph_root=tmp_path) == "staging"


def test_canonical_includes_pacer_pool_without_colliding_press_release(tmp_path: Path):
    case_id = "ky_sp_2025_038"
    _write_ttl(
        tmp_path / "universe" / f"{case_id}.ttl",
        "http://ex.org/pr",
        "press-release",
    )
    _write_ttl(
        tmp_path / "pacer" / f"pacer_{case_id}.ttl",
        "http://ex.org/pacer",
        "pacer",
    )

    chosen = canonical_ttl_paths(tmp_path)
    assert chosen[case_id] == tmp_path / "universe" / f"{case_id}.ttl"
    assert chosen[f"pacer_{case_id}"] == tmp_path / "pacer" / f"pacer_{case_id}.ttl"
    assert pool_label_for_path(chosen[f"pacer_{case_id}"]) == "pacer"


def test_build_nquads_uses_per_case_named_graph(tmp_path: Path):
    ttl = tmp_path / "universe" / "nj_ag_2017_001.ttl"
    _write_ttl(
        ttl,
        "https://w3id.org/caselinker/resource/case/nj_ag_2017_001",
        "fixture",
    )
    out = tmp_path / "out.nq"
    result = build_nquads({"nj_ag_2017_001": ttl}, out)
    assert result["cases_loaded"] == 1
    assert result["provenance_loaded"] == 0
    assert result["quads"] == 1
    text = out.read_text(encoding="utf-8")
    graph_iri = str(case_graph_iri("nj_ag_2017_001"))
    assert graph_iri == CASE_GRAPH_BASE + "nj_ag_2017_001"
    assert graph_iri in text
    # Fourth N-Quads slot is the named graph.
    assert text.strip().endswith(f"<{graph_iri}> .")


def test_provenance_sidecar_loads_beside_the_chosen_case_only(tmp_path: Path):
    case_id = "nj_ag_2017_001"
    _write_ttl(
        tmp_path / "universe" / f"{case_id}.ttl",
        f"https://w3id.org/caselinker/resource/case/{case_id}",
        "case",
    )
    _write_ttl(
        tmp_path / "universe" / f"{case_id}.provenance.ttl",
        f"https://w3id.org/caselinker/resource/case/{case_id}/assertion/1",
        "provenance",
    )
    _write_ttl(tmp_path / f"{case_id}.provenance.ttl", "http://ex.org/stale", "stale")
    _write_ttl(tmp_path / "orphan.provenance.ttl", "http://ex.org/orphan", "orphan")

    chosen = canonical_ttl_paths(tmp_path)
    assert list(chosen) == [case_id]
    out = tmp_path / "out.nq"
    result = build_nquads(chosen, out)
    assert result["cases_loaded"] == 1
    assert result["provenance_loaded"] == 1
    assert result["provenance_failed"] == []
    text = out.read_text(encoding="utf-8")
    case_iri = str(case_graph_iri(case_id))
    prov_iri = str(provenance_graph_iri(case_id))
    assert prov_iri == case_iri + "/provenance"
    assert f"<{prov_iri}>" in text
    assert "stale" not in text
    assert "orphan" not in text
    case_lines = [line for line in text.splitlines() if line.endswith(f"<{case_iri}> .")]
    prov_lines = [line for line in text.splitlines() if line.endswith(f"<{prov_iri}> .")]
    assert len(case_lines) == 1
    assert len(prov_lines) == 1
    assert "assertion/1" in prov_lines[0]
    assert "assertion/1" not in case_lines[0]


def test_broken_provenance_sidecar_does_not_drop_the_case(tmp_path: Path):
    case_id = "nj_ag_2017_001"
    _write_ttl(
        tmp_path / f"{case_id}.ttl",
        f"https://w3id.org/caselinker/resource/case/{case_id}",
        "case",
    )
    (tmp_path / f"{case_id}.provenance.ttl").write_text("this is not turtle {\n", encoding="utf-8")
    out = tmp_path / "out.nq"
    result = build_nquads({case_id: tmp_path / f"{case_id}.ttl"}, out)
    assert result["cases_loaded"] == 1
    assert result["provenance_loaded"] == 0
    assert result["provenance_failed"][0]["case_id"] == case_id
    assert str(case_graph_iri(case_id)) in out.read_text(encoding="utf-8")


def test_rebuild_lock_round_trip(monkeypatch, tmp_path: Path):
    run = ROOT / "run"
    if str(run) not in sys.path:
        sys.path.insert(0, str(run))
    import sparql_rebuild_lock as lock

    path = tmp_path / "rebuild.lock"
    monkeypatch.setenv("SPARQL_REBUILD_LOCK", str(path))
    assert lock.rebuild_in_progress() is False
    lock.acquire_rebuild_lock()
    assert path.is_file()
    assert lock.rebuild_in_progress() is True
    lock.release_rebuild_lock()
    assert lock.rebuild_in_progress() is False
    assert not path.exists()


class _FakeOxigraph:
    """Answers COUNT queries and bulk POSTs the way ``oxigraph serve`` does."""

    def __init__(self, start=0, fail_first_posts=0, drop_lines=0):
        self.quads = start
        self.posts = []
        self.fail_first_posts = fail_first_posts
        self.drop_lines = drop_lines

    def handler(self, request):
        import json

        import httpx

        if request.url.path == "/query":
            body = {"results": {"bindings": [{"n": {"value": str(self.quads)}}]}}
            return httpx.Response(200, text=json.dumps(body))
        self.posts.append((str(request.url), request.content))
        if self.fail_first_posts:
            self.fail_first_posts -= 1
            return httpx.Response(500, text="IO error")
        lines = [l for l in request.content.splitlines() if l.strip()]
        self.quads += max(0, len(lines) - self.drop_lines)
        return httpx.Response(204)

    def client(self):
        import httpx

        return httpx.Client(transport=httpx.MockTransport(self.handler))


def _nq(path: Path, n: int, graph: str = "urn:g") -> Path:
    import gzip

    text = "".join(f"<urn:s{i}> <urn:p> \"{i}\" <{graph}> .\n" for i in range(n))
    if path.suffix == ".gz":
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.write(text)
    else:
        path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def lock_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SPARQL_REBUILD_LOCK", str(tmp_path / "rebuild.lock"))
    monkeypatch.delenv("REDIS_URL", raising=False)
    return tmp_path / "rebuild.lock"


def test_bulk_load_uses_the_no_transaction_bulk_path_in_slices(tmp_path, lock_env):
    from oxigraph_rebuild import bulk_load_nquads

    store = _FakeOxigraph()
    cases = _nq(tmp_path / "cases.nq.gz", 25)
    pacer = _nq(tmp_path / "pacer.nq", 4, "urn:pacer:kg:1")
    out = bulk_load_nquads([cases, pacer], "http://oxigraph:7878", chunk_lines=10,
                           retry_wait_s=0, client=store.client())
    assert out == {"quads_sent": 29, "store_quads": 29}
    assert [url for url, _ in store.posts] == ["http://oxigraph:7878/store?no_transaction"] * 4
    assert [len(body.splitlines()) for _, body in store.posts] == [10, 10, 5, 4]
    assert not lock_env.exists()          # lock released


def test_bulk_load_refuses_a_store_that_is_not_empty(tmp_path, lock_env):
    from oxigraph_rebuild import bulk_load_nquads

    store = _FakeOxigraph(start=7)
    with pytest.raises(RuntimeError, match="already holds 7 quads"):
        bulk_load_nquads([_nq(tmp_path / "c.nq", 3)], "http://ox", client=store.client())
    assert store.posts == []


def test_bulk_load_reposts_a_failed_slice(tmp_path, lock_env):
    from oxigraph_rebuild import bulk_load_nquads

    store = _FakeOxigraph(fail_first_posts=1)
    out = bulk_load_nquads([_nq(tmp_path / "c.nq", 3)], "http://ox", retry_wait_s=0, client=store.client())
    assert out["store_quads"] == 3 and len(store.posts) == 2


def test_bulk_load_fails_loudly_when_the_store_count_does_not_match(tmp_path, lock_env):
    from oxigraph_rebuild import bulk_load_nquads

    store = _FakeOxigraph(drop_lines=1)
    with pytest.raises(RuntimeError, match="holds 2 quads after loading 3 lines"):
        bulk_load_nquads([_nq(tmp_path / "c.nq", 3)], "http://ox", client=store.client())
    assert not lock_env.exists()


def test_build_nquads_writes_gzip_when_asked(tmp_path: Path):
    import gzip

    _write_ttl(tmp_path / "graphs" / "case_a.ttl", "http://ex.org/a", "a")
    dest = tmp_path / "out.nq.gz"
    result = build_nquads(canonical_ttl_paths(tmp_path / "graphs"), dest)
    lines = gzip.open(dest, "rt", encoding="utf-8").read().splitlines()
    assert result["quads"] == len(lines) == 1
    assert lines[0].endswith(f"<{CASE_GRAPH_BASE}case_a> .")


def test_cli_skip_build_needs_an_existing_file_and_load_needs_a_url(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "scripts"))
    import rebuild_oxigraph

    monkeypatch.delenv("OXIGRAPH_URL", raising=False)
    assert rebuild_oxigraph.main(["--skip-build", "--output", str(tmp_path / "none.nq")]) == 1
    nq = _nq(tmp_path / "c.nq", 2)
    assert rebuild_oxigraph.main(["--skip-build", "--output", str(nq)]) == 1          # no URL
    assert rebuild_oxigraph.main(["--skip-build", "--output", str(nq), "--no-load"]) == 0
