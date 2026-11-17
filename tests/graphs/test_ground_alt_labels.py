"""Grounded location/agency nodes keep article wording as skos:altLabel."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ontology" / "pipeline"))

from features_to_cac import BASE, CaseToCAC, GRAPH_DETERMINISTIC  # noqa: E402
from rdflib.namespace import RDFS, SKOS  # noqa: E402


def test_agency_alt_label_is_article_wording_not_canonical():
    mapper = CaseToCAC()
    case = {
        "id": "alt_ag_001",
        "source": "NJ AG",
        "agencies_involved": ["Toms River PD"],
        "agency_grounds": [
            {
                "mention": "Toms River PD",
                "status": "grounded",
                "ori": "NJ0150700",
                "agency_name": "Toms River Township Police Department",
                "state_hint": "NJ",
                "hint_source": "source",
                "slug": "toms-river-township-police-department-nj",
                "registry_version": "cde-2026-10-20",
            }
        ],
        "locations": [],
        "location_grounds": [],
        "case_topics": [],
        "platforms_used": [],
        "severity_indicators": [],
    }
    g, _ = mapper.map_case(case)
    uri = BASE["agency/toms-river-township-police-department-nj"]
    det = g.get_context(GRAPH_DETERMINISTIC)
    assert {str(o) for o in det.objects(uri, RDFS.label)} == {
        "Toms River Township Police Department"
    }
    assert {str(o) for o in det.objects(uri, SKOS.altLabel)} == {"Toms River PD"}


def test_location_alt_label_is_article_wording():
    mapper = CaseToCAC()
    case = {
        "id": "alt_loc_001",
        "source": "NJ AG",
        "locations": ["Cumberland Co."],
        "location_grounds": [
            {
                "mention": "Cumberland Co.",
                "status": "grounded",
                "fips": "34011",
                "entity_name": "Cumberland County",
                "entity_kind": "county",
                "state_hint": "NJ",
                "hint_source": "source",
                "slug": "cumberland-county-nj",
                "gazetteer_version": "2024.1",
            }
        ],
        "agencies_involved": [],
        "agency_grounds": [],
        "case_topics": [],
        "platforms_used": [],
        "severity_indicators": [],
    }
    g, _ = mapper.map_case(case)
    uri = BASE["location/cumberland-county-nj"]
    det = g.get_context(GRAPH_DETERMINISTIC)
    assert {str(o) for o in det.objects(uri, RDFS.label)} == {"Cumberland County"}
    assert {str(o) for o in det.objects(uri, SKOS.altLabel)} == {"Cumberland Co."}


def test_alt_label_deduped_when_same_as_canonical():
    mapper = CaseToCAC()
    case = {
        "id": "alt_same_001",
        "source": "NJ AG",
        "locations": ["Cumberland County"],
        "location_grounds": [
            {
                "mention": "Cumberland County",
                "status": "grounded",
                "fips": "34011",
                "entity_name": "Cumberland County",
                "entity_kind": "county",
                "state_hint": "NJ",
                "hint_source": "source",
                "slug": "cumberland-county-nj",
                "gazetteer_version": "2024.1",
            }
        ],
        "agencies_involved": [],
        "agency_grounds": [],
        "case_topics": [],
        "platforms_used": [],
        "severity_indicators": [],
    }
    g, _ = mapper.map_case(case)
    uri = BASE["location/cumberland-county-nj"]
    det = g.get_context(GRAPH_DETERMINISTIC)
    assert list(det.objects(uri, SKOS.altLabel)) == []
