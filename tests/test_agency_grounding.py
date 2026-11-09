"""Agency authority grounding (FBI CDE + federal table)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "agency_registry"
PROC = ROOT / "src" / "Processing Layer" / "agency_grounding.py"


def _load():
    spec = importlib.util.spec_from_file_location("agency_grounding", PROC)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules["agency_grounding"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ag():
    if not (REG / "MANIFEST.json").is_file():
        pytest.skip("agency registry not pinned (run scripts/run/fetch_agency_registry.sh)")
    return _load()


def test_missing_registry_raises(tmp_path, monkeypatch):
    mod = _load()
    empty = tmp_path / "empty_reg"
    empty.mkdir()
    monkeypatch.setenv("CASELINKER_AGENCY_REGISTRY_DIR", str(empty))
    with pytest.raises(mod.AgencyRegistryError):
        mod.require_agency_registry(empty)


def test_normalize_pd_expansion(ag):
    assert "Police Department" in ag.normalize_agency_name("Toms River PD")


def test_federal_fbi_grounds(ag):
    rows = ag.ground_case_agencies(["FBI"], source="NJ AG", case_id="t1")
    assert rows[0]["status"] == "grounded"
    assert rows[0]["code"] == "FBI"
    assert rows[0]["slug"] == "fbi"


def test_toms_river_pd_nj(ag):
    rows = ag.ground_case_agencies(
        ["Toms River PD"], source="NJ AG", case_id="t2"
    )
    assert rows[0]["status"] == "grounded", rows[0]
    assert rows[0]["ori"] == "NJ0150700"  # Toms River Township PD (Ocean County)
    assert rows[0]["agency_name"] == "Toms River Township Police Department"
    assert (rows[0].get("county") or "").upper() == "OCEAN"
    assert rows[0]["state_hint"] == "NJ"


def test_south_toms_river_never_collides_with_township(ag):
    rows = ag.ground_case_agencies(
        ["South Toms River Police Department"], source="NJ AG", case_id="t3"
    )
    assert rows[0]["status"] == "grounded", rows[0]
    assert rows[0]["ori"] == "NJ0152900"
    assert rows[0]["ori"] != "NJ0150700"


def test_international_out_of_scope_not_ungrounded(ag):
    for label in ("NCA", "Europol", "AFP", "Police Scotland", "Brazil Federal Police"):
        rows = ag.ground_case_agencies([label], source="NCMEC", case_id="intl")
        assert rows[0]["status"] == "out_of_scope", (label, rows[0])
        assert rows[0]["reason"] == "international_agency"


def test_generic_sheriff_ambiguous_without_county(ag):
    rows = ag.ground_case_agencies(
        ["Sheriff's Department"], source="NJ AG", case_id="gen"
    )
    assert rows[0]["status"] == "ambiguous"
    assert rows[0]["reason"] == "generic_no_place"


def test_prosecutor_is_out_of_registry_not_ungrounded(ag):
    rows = ag.ground_case_agencies(
        ["Ocean County Prosecutor's Office"], source="NJ AG", case_id="pros"
    )
    assert rows[0]["status"] == "out_of_registry"
    assert rows[0]["reason"] == "not_in_cde_registry"


def test_soft_prefix_no_longer_maps_jersey_state_to_jersey_city(ag):
    rows = ag.ground_case_agencies(
        ["Jersey State Police Department"], source="NJ AG", case_id="badsoft"
    )
    assert rows[0].get("ori") != "NJ0090600"
    assert rows[0]["status"] in {"ungrounded", "ambiguous", "out_of_registry"}


def test_mapper_mints_readable_agency_iri():
    sys.path.insert(0, str(ROOT / "ontology"))
    from features_to_cac import BASE, CaseToCAC, GRAPH_DETERMINISTIC
    from rdflib.namespace import DCTERMS, RDFS

    mapper = CaseToCAC()
    case = {
        "id": "agency_map_001",
        "source": "NJ AG",
        "agencies_involved": ["Toms River Police Department"],
        "agency_grounds": [
            {
                "mention": "Toms River Police Department",
                "status": "grounded",
                "ori": "NJ0152100",
                "agency_name": "Toms River Police Department",
                "state_hint": "NJ",
                "hint_source": "source",
                "slug": "toms-river-police-department-nj",
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
    uri = BASE["agency/toms-river-police-department-nj"]
    det = g.get_context(GRAPH_DETERMINISTIC)
    assert {str(o) for o in det.objects(uri, DCTERMS.identifier)} == {"ori:NJ0152100"}
    # How it was grounded lives in the provenance graph, not on the shared node (#57).
    assert not any("/vocab/" in str(p) for _, p, _ in det)
    assert "Toms River Police Department" in {str(x) for x in det.objects(uri, RDFS.label)}
