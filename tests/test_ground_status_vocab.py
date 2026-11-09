"""Neutral caselinker:groundStatus for locations and agencies."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_vocab_defines_ground_status_not_location_ground_status():
    ttl = (ROOT / "ontology" / "caselinker-provenance.ttl").read_text(encoding="utf-8")
    assert "caselinker:groundStatus" in ttl
    assert "locationGroundStatus" not in ttl


def test_shapes_cover_ground_status():
    shapes = (ROOT / "ontology" / "caselinker-provenance-shapes.ttl").read_text(
        encoding="utf-8"
    )
    assert "caselinker:groundStatus" in shapes or "groundStatus" in shapes


def test_ground_status_is_written_once_in_the_provenance_namespace():
    """The case graph no longer repeats grounding facts under resource/vocab/ (#57)."""
    sys.path.insert(0, str(ROOT / "ontology"))
    import features_to_cac as F

    assert not hasattr(F, "CASELINKER_GROUND_STATUS")
    assert "resource/vocab" not in (ROOT / "ontology" / "features_to_cac.py").read_text(encoding="utf-8")


def test_provenance_export_uses_ground_status():
    sys.path.insert(0, str(ROOT / "ontology"))
    from provenance_export import CL, build_provenance_graph
    from rdflib import URIRef

    g = build_provenance_graph(
        "gs_001",
        [],
        {},
        run_id="r",
        issued_at="2026-10-20T12:00:00.000000Z",
        location_grounds=[
            {
                "mention": "X",
                "status": "grounded",
                "fips": "34",
                "state_hint": "NJ",
                "hint_source": "source",
                "gazetteer_version": "2024.1",
                "slug": "new-jersey-nj",
            }
        ],
        agency_grounds=[
            {
                "mention": "FBI",
                "status": "grounded",
                "code": "FBI",
                "slug": "federal-bureau-of-investigation",
                "registry_version": "cde-2026-10-20",
            }
        ],
    )
    prop = URIRef(str(CL) + "groundStatus")
    vals = {str(o) for o in g.objects(None, prop)}
    assert "grounded" in vals
    old = URIRef(str(CL) + "locationGroundStatus")
    assert not list(g.objects(None, old))
