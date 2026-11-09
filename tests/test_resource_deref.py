"""GET /resource and /ns/provenance describe a local Oxigraph-shaped store.

Store-backed tests build one case through the real grounders and mapper.
They do not read ontology/graph_output/, whose slugs change when graphs
are regenerated.
"""

from __future__ import annotations

import importlib.util
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import rdflib
from fastapi.testclient import TestClient
from rdflib import URIRef
from rdflib.namespace import DCTERMS, RDF

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "run"
ONTOLOGY = ROOT / "ontology"
PROC = ROOT / "src" / "Processing Layer"
CASE_ID = "doj_archives_2003_011"
CASE_IRI = f"https://w3id.org/caselinker/resource/case/{CASE_ID}"
PROV_IRI = CASE_IRI + "/provenance"

FIXTURE_ID = "deref_fixture_001"
FIXTURE_CASE_IRI = f"https://w3id.org/caselinker/resource/case/{FIXTURE_ID}"
FIXTURE_PROV_IRI = FIXTURE_CASE_IRI + "/provenance"
FIXTURE_TEXT = "The FBI announced charges in Indiana."


def _load_py(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_main():
    return _load_py("caselinker_run_main_deref", RUN / "main.py")


def _fixture_case() -> dict:
    """Mentions only. Slugs come from the pinned gazetteer and agency registry."""
    return {
        "id": FIXTURE_ID,
        "source": "DOJ",
        "locations": ["Indiana"],
        "agencies_involved": ["FBI"],
        "case_topics": [],
        "platforms_used": [],
        "severity_indicators": [],
        "raw_data": {"case_text": FIXTURE_TEXT},
    }


def _build_fixture() -> dict:
    """Ground, map, and write provenance the way a reload does."""
    if str(ONTOLOGY) not in sys.path:
        sys.path.insert(0, str(ONTOLOGY))
    from features_to_cac import CAC_MULTI, CaseToCAC, flatten_dataset
    from provenance_export import build_provenance_graph

    locations = _load_py("location_grounding", PROC / "location_grounding.py")
    agencies = _load_py("agency_grounding", PROC / "agency_grounding.py")
    case = _fixture_case()
    location_grounds = locations.ground_case_locations(
        case["locations"],
        source=case["source"],
        case_text=FIXTURE_TEXT,
        case_id=FIXTURE_ID,
    )
    agency_grounds = agencies.ground_case_agencies(
        case["agencies_involved"],
        source=case["source"],
        case_id=FIXTURE_ID,
    )
    assert len(location_grounds) == 1
    loc = location_grounds[0]
    assert loc["status"] == "grounded", loc
    assert loc.get("fips")
    assert loc.get("slug")
    assert loc.get("gazetteer_version")
    assert len(agency_grounds) == 1
    ag = agency_grounds[0]
    assert ag["status"] == "grounded", ag
    assert ag.get("slug")
    assert ag.get("registry_version")

    case["location_grounds"] = location_grounds
    case["agency_grounds"] = agency_grounds
    dataset, warnings = CaseToCAC().map_case(case)
    assert warnings == []
    case_graph = flatten_dataset(dataset)
    inv = URIRef(FIXTURE_CASE_IRI)
    location_iri = f"https://w3id.org/caselinker/resource/location/{loc['slug']}"
    agency_iri = f"https://w3id.org/caselinker/resource/agency/{ag['slug']}"
    assert {str(o) for o in case_graph.objects(inv, DCTERMS.spatial)} == {location_iri}
    assert {str(o) for o in case_graph.objects(inv, CAC_MULTI.involvesAgency)} == {agency_iri}
    assert any(case_graph.triples((inv, RDF.type, None)))
    assert (inv, DCTERMS.provenance, URIRef(FIXTURE_PROV_IRI)) in case_graph

    mention_at = FIXTURE_TEXT.index("Indiana")
    provenance = build_provenance_graph(
        FIXTURE_ID,
        [
            {
                "field": "locations",
                "method": "gazetteer",
                "family": "authority",
                "value": "Indiana",
                "span_start": mention_at,
                "span_end": mention_at + len("Indiana"),
                "span_text": "Indiana",
                "confidence": 0.9,
            }
        ],
        {"locations": {"status": "resolved", "rule_set_version": "resolve_v3.0"}},
        location_grounds=location_grounds,
        agency_grounds=agency_grounds,
        run_id="run_deref_fixture",
        issued_at="2026-10-20T12:00:00.000000Z",
    )
    return {
        "case_graph": case_graph,
        "provenance": provenance,
        "location_iri": location_iri,
        "agency_iri": agency_iri,
        "location_slug": loc["slug"],
        "agency_slug": ag["slug"],
    }


_FIXTURE = None


def _fixture() -> dict:
    global _FIXTURE
    if _FIXTURE is None:
        _FIXTURE = _build_fixture()
    return _FIXTURE


def _store() -> rdflib.Dataset:
    """Case triples in the case named graph; provenance sidecar beside it."""
    built = _fixture()
    dataset = rdflib.Dataset()
    case_ng = dataset.graph(URIRef(FIXTURE_CASE_IRI))
    for triple in built["case_graph"]:
        case_ng.add(triple)
    prov_ng = dataset.graph(URIRef(FIXTURE_PROV_IRI))
    for triple in built["provenance"]:
        prov_ng.add(triple)
    return dataset


def _serve(dataset: rdflib.Dataset) -> str:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            query = self.rfile.read(length).decode("utf-8")
            accept = (self.headers.get("Accept") or "text/turtle").split(",")[0].strip()
            result = dataset.query(query)
            if "sparql-results+json" in accept or result.type == "SELECT":
                body = result.serialize(format="json")
                content_type = "application/sparql-results+json"
            else:
                body = result.serialize(format="turtle")
                content_type = "text/turtle"
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}"


def test_provenance_html_title_names_the_case_not_first_assertion():
    sys.path.insert(0, str(RUN))
    sys.path.insert(0, str(ROOT / "ontology"))
    import deref
    from provenance_export import build_provenance_graph

    # Fresh graph so labels/order match the exporter under test (not a stale TTL).
    graph = build_provenance_graph(
        CASE_ID,
        [
            {
                "field": "age",
                "method": "regex",
                "family": "surface_pattern",
                "value": 30,
                "role": "perpetrator",
                "span_start": 10,
                "span_end": 12,
                "span_text": "30",
                "confidence": 0.9,
            },
            {
                "field": "age",
                "method": "regex",
                "family": "surface_pattern",
                "value": 14,
                "role": "decoy",
                "span_start": 40,
                "span_end": 42,
                "span_text": "14",
                "confidence": 0.9,
            },
        ],
        {"age": {"status": "partial", "rule_set_version": "resolve_v3.0"}},
        run_id="run_deref_order",
        issued_at="2026-10-17T18:00:00.000000Z",
    )
    page = deref.render_html(graph, focus=PROV_IRI)
    assert f"<h1>Provenance · {CASE_ID}</h1>" in page
    assert page.count(f"<h1>Provenance · {CASE_ID}</h1>") == 1
    assert "<h2>age 30 · perpetrator</h2>" in page
    assert "<h2>passage · age 30 · perpetrator</h2>" in page
    assert "target ·" not in page
    assert "assertionRole" in page
    # Assertion section appears before its passage and selectors.
    a = page.find("<h2>age 30 · perpetrator</h2>")
    p = page.find("<h2>passage · age 30 · perpetrator</h2>")
    pos = page.find("<h2>position 10–12</h2>")
    assert a != -1 and p != -1 and pos != -1
    assert a < p < pos


def test_case_html_title_is_case_id_with_classic_section_layout():
    sys.path.insert(0, str(RUN))
    import deref

    built = _fixture()
    page = deref.render_html(built["case_graph"], focus=FIXTURE_CASE_IRI)
    assert f"<h1>{FIXTURE_ID}</h1>" in page
    # Classic layout: focus node is a section with h2 + self IRI link (not a top-level .iri strip).
    assert "<h2>" in page
    assert f'href="{FIXTURE_CASE_IRI}"' in page
    assert 'class="iri"' not in page
    assert ">provenance</th>" in page
    assert ">type</th>" in page


def test_provenance_vocabulary_is_html_for_browsers_and_turtle_for_clients(monkeypatch):
    monkeypatch.setenv("OXIGRAPH_URL", "http://127.0.0.1:9")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    main = _load_main()
    # No lifespan: startup would open the configured database.
    client = TestClient(main.app)
    page = client.get("/ns/provenance", headers={"Accept": "text/html"})
    turtle = client.get("/ns/provenance", headers={"Accept": "text/turtle"})
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "evidence family" in page.text
    assert "resolution status" in page.text
    assert "rule set version" in page.text
    assert turtle.status_code == 200
    assert "text/turtle" in turtle.headers["content-type"]
    assert "owl:Ontology" in turtle.text
    assert 'owl:versionInfo "3.1"' in turtle.text
    assert "caselinker:evidenceFamily" in turtle.text


def test_resource_route_negotiates_a_local_store_and_links_cac_classes(monkeypatch):
    built = _fixture()
    base = _serve(_store())
    monkeypatch.setenv("OXIGRAPH_URL", base)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    main = _load_main()
    client = TestClient(main.app)
    turtle = client.get(f"/resource/case/{FIXTURE_ID}", headers={"Accept": "text/turtle"})
    page = client.get(f"/resource/case/{FIXTURE_ID}", headers={"Accept": "text/html"})
    data = client.get(f"/resource/case/{FIXTURE_ID}", headers={"Accept": "application/ld+json"})
    place = client.get(
        f"/resource/location/{built['location_slug']}",
        headers={"Accept": "text/turtle"},
    )
    agency = client.get(
        f"/resource/agency/{built['agency_slug']}",
        headers={"Accept": "text/turtle"},
    )
    prov = client.get(
        f"/resource/case/{FIXTURE_ID}/provenance",
        headers={"Accept": "text/turtle"},
    )
    missing = client.get("/resource/case/no_such_case", headers={"Accept": "text/turtle"})
    assert turtle.status_code == 200
    assert FIXTURE_CASE_IRI in turtle.text
    assert built["location_iri"] in turtle.text
    assert built["agency_iri"] in turtle.text
    assert "text/html" in page.headers["content-type"]
    assert 'href="https://cacontology.projectvic.org' in page.text
    assert data.status_code == 200 and "application/ld+json" in data.headers["content-type"]
    assert FIXTURE_CASE_IRI in data.text
    assert place.status_code == 200
    assert built["location_iri"] in place.text
    assert "cacontology.projectvic.org" in place.text
    assert agency.status_code == 200
    assert built["agency_iri"] in agency.text
    assert "cacontology.projectvic.org" in agency.text
    assert prov.status_code == 200
    assert "resolve_v3.0" in prov.text
    assert built["location_iri"] in prov.text
    assert missing.status_code == 404


def test_hub_page_lists_cases_referencing_this(monkeypatch):
    """Agency/platform/location HTML includes a reverse case list from SPARQL."""
    built = _fixture()
    base = _serve(_store())
    monkeypatch.setenv("OXIGRAPH_URL", base)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    main = _load_main()
    client = TestClient(main.app)
    place = client.get(
        f"/resource/location/{built['location_slug']}",
        headers={"Accept": "text/html"},
    )
    agency = client.get(
        f"/resource/agency/{built['agency_slug']}",
        headers={"Accept": "text/html"},
    )
    assert place.status_code == 200
    assert "Cases referencing this" in place.text
    assert FIXTURE_ID in place.text
    assert f'href="/resource/case/{FIXTURE_ID}"' in place.text
    assert agency.status_code == 200
    assert "Cases referencing this" in agency.text
    assert f'href="/resource/case/{FIXTURE_ID}"' in agency.text


def test_referencing_cases_query_targets_press_release_graphs_only():
    sys.path.insert(0, str(RUN))
    import deref

    iri = "https://w3id.org/caselinker/resource/location/cumberland-county"
    q = deref.referencing_cases_query(iri)
    assert iri in q
    assert 'STRSTARTS(STR(?g), "https://w3id.org/caselinker/resource/case/")' in q
    assert '!STRENDS(STR(?g), "/provenance")' in q
    assert deref.is_hub_resource(iri)
    assert not deref.is_hub_resource(CASE_IRI)
