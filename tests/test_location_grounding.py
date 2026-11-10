"""Location authority grounding (post-extract linker, not a witness)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GAZ = ROOT / "data" / "gazetteer"
PROC = ROOT / "src" / "Processing Layer" / "location_grounding.py"


def _load_mod():
    spec = importlib.util.spec_from_file_location("location_grounding", PROC)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules["location_grounding"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def lg():
    if not (GAZ / "2024_Gaz_counties_national.txt").is_file():
        pytest.skip("Census gazetteer not present (run scripts/run/fetch_gazetteer.sh)")
    return _load_mod()


def test_cumberland_county_nj_grounds_to_fips(lg):
    rows = lg.ground_case_locations(
        ["Cumberland County"],
        source="NJ AG",
        case_text="The New Jersey Attorney General announced arrests in Cumberland County.",
        case_id="nj_ag_test_001",
    )
    assert len(rows) == 1
    assert rows[0]["status"] == "grounded"
    assert rows[0]["fips"] == "34011"
    assert rows[0]["entity_kind"] == "county"


def test_sc_abbrev_grounds_as_state(lg):
    # Pure state abbrev must ground even when the "string" hint source is demoted.
    rows = lg.ground_case_locations(["S.C."], source="SCAG ICAC", case_text="")
    assert rows[0]["status"] == "grounded", rows[0]
    assert rows[0]["entity_kind"] == "state"
    assert rows[0]["fips"] == "45"
    assert rows[0].get("slug") in {None, "south-carolina-sc", "south-carolina"} or (
        "south-carolina" in (rows[0].get("slug") or "")
    )


def test_possessive_stripped(lg):
    rows = lg.ground_case_locations(
        ["New Jersey's"],
        source="NCMEC",
        case_text="A New Jersey's task force operation.",
    )
    assert rows[0]["status"] == "grounded"
    assert rows[0]["fips"] == "34"


def test_international_source_not_ungrounded_failure(lg):
    rows = lg.ground_case_locations(
        ["Auckland"],
        source="NZ DIA",
        case_text="Police in Auckland charged the offender.",
    )
    assert rows[0]["status"] == "international"


def test_mapper_mints_readable_state_iri_when_grounds_present():
    sys.path.insert(0, str(ROOT / "ontology"))
    from features_to_cac import BASE, CaseToCAC, GRAPH_DETERMINISTIC
    from rdflib.namespace import DCTERMS, RDFS

    mapper = CaseToCAC()
    case = {
        "id": "ground_map_001",
        "source": "NJ AG",
        "locations": ["Cumberland County"],
        "location_grounds": [
            {
                "mention": "Cumberland County",
                "status": "grounded",
                "fips": "34011",
                "geoid": "34011",
                "entity_name": "Cumberland County",
                "entity_kind": "county",
                "reason": "county_in_state",
                "state_hint": "NJ",
                "hint_source": "source",
                "slug": "cumberland-county-nj",
                "gazetteer_version": "2024.1",
            }
        ],
        # Explicit empty agency_grounds so remap does not require CDE registry.
        "agencies_involved": [],
        "agency_grounds": [],
        "case_topics": [],
        "platforms_used": [],
        "severity_indicators": [],
    }
    g, _ = mapper.map_case(case)
    uri = BASE["location/cumberland-county-nj"]
    det = g.get_context(GRAPH_DETERMINISTIC)
    assert {str(o) for o in det.objects(uri, DCTERMS.identifier)} == {"fips:34011"}
    assert not any("/vocab/" in str(p) for _, p, _ in det)
    assert "Cumberland County" in {str(x) for x in det.objects(uri, RDFS.label)}
    assert "cumberland-county-nj" in mapper._location_registry
    assert uri in list(det.subjects())


def test_readable_slug_appends_geoid_on_collision(lg):
    used = {"springfield-ma"}
    slug = lg.readable_location_slug(
        entity_name="Springfield",
        mention="Springfield",
        state_hint="MA",
        fips="250670",
        entity_kind="place",
        collision_slugs=used,
    )
    assert slug == "springfield-ma-250670"


def test_svicac_releases_default_to_california():
    # Silicon Valley ICAC: 49 of its 84 releases name San Jose or California, 1 names Virginia.
    from location_grounding import source_default_state

    assert source_default_state("SVICAC") == "CA"
