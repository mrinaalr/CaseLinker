"""Location ground records appear in the provenance graph."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ontology" / "pipeline"))

from provenance_export import CL, build_provenance_graph  # noqa: E402
from rdflib import URIRef  # noqa: E402
from rdflib.namespace import DCTERMS, RDFS  # noqa: E402


def test_location_grounding_triples_include_geoid_and_hint():
    g = build_provenance_graph(
        "prov_loc_001",
        [],
        {},
        run_id="run_loc",
        issued_at="2026-10-20T12:00:00.000000Z",
        location_grounds=[
            {
                "mention": "Cumberland County",
                "status": "grounded",
                "fips": "34011",
                "geoid": "34011",
                "state_hint": "NJ",
                "hint_source": "source",
                "gazetteer_version": "2024.1",
                "slug": "cumberland-county-nj",
            }
        ],
    )
    labels = {str(o) for o in g.objects(None, RDFS.label)}
    assert any("location ground · Cumberland County" in x for x in labels)
    assert {str(o) for o in g.objects(None, CL.fipsCode)} == {"34011"}
    assert {str(o) for o in g.objects(None, CL.gazetteerVersion)} == {"2024.1"}
    assert {str(o) for o in g.objects(None, CL.stateHint)} == {"NJ"}
    assert {str(o) for o in g.objects(None, CL.stateHintSource)} == {"source"}
    gs = URIRef(str(CL) + "groundStatus")
    assert {str(o) for o in g.objects(None, gs)} == {"grounded"}
    subjects = {str(o) for o in g.objects(None, DCTERMS.subject)}
    assert any(o.endswith("location/cumberland-county-nj") for o in subjects)


def test_agency_grounding_triples_include_ori():
    g = build_provenance_graph(
        "prov_ag_001",
        [],
        {},
        run_id="run_ag",
        issued_at="2026-10-20T12:00:00.000000Z",
        agency_grounds=[
            {
                "mention": "Toms River PD",
                "status": "grounded",
                "ori": "NJ0152100",
                "state_hint": "NJ",
                "hint_source": "source",
                "registry_version": "cde-2026-10-20",
                "slug": "toms-river-police-department-nj",
            }
        ],
    )
    assert {str(o) for o in g.objects(None, CL.oriCode)} == {"NJ0152100"}
    assert {str(o) for o in g.objects(None, CL.agencyRegistryVersion)} == {
        "cde-2026-10-20"
    }
