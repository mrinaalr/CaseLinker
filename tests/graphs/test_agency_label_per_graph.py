"""Agency singletons must carry rdfs:label in every mapped case graph."""

from __future__ import annotations

import sys
from pathlib import Path

from rdflib import Literal
from rdflib.namespace import RDFS

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ontology" / "pipeline"))

from features_to_cac import (  # noqa: E402
    AZICAC_2011_006_FIXTURE,
    BASE,
    GRAPH_DETERMINISTIC,
    CaseToCAC,
)


def test_agency_label_written_into_every_case_graph():
    mapper = CaseToCAC()
    shared = ["FBI", "NCMEC"]
    g1, _ = mapper.map_case(
        {
            **AZICAC_2011_006_FIXTURE,
            "id": "agency_label_a",
            "agencies_involved": shared + ["Arizona ICAC"],
        }
    )
    g2, _ = mapper.map_case(
        {
            **AZICAC_2011_006_FIXTURE,
            "id": "agency_label_b",
            "agencies_involved": shared + ["Maricopa County Sheriff's Office"],
        }
    )

    fbi = BASE["agency/fbi"]
    ncmec = BASE["agency/ncmec"]
    assert mapper._agency_registry["fbi"] == fbi
    assert mapper._agency_registry["ncmec"] == ncmec

    for graph in (g1, g2):
        det = graph.get_context(GRAPH_DETERMINISTIC)
        # Grounded federals use registry canonical as rdfs:label; mention → skos:altLabel
        assert (fbi, RDFS.label, Literal("Federal Bureau of Investigation")) in det
        assert (
            ncmec,
            RDFS.label,
            Literal("National Center for Missing and Exploited Children"),
        ) in det


def test_second_case_keeps_label_after_registry_hit():
    """Regression: registry hit used to skip rdfs:label on later graphs."""
    mapper = CaseToCAC()
    g1, _ = mapper.map_case(
        {
            **AZICAC_2011_006_FIXTURE,
            "id": "first_hit",
            "agencies_involved": ["FBI"],
        }
    )
    g2, _ = mapper.map_case(
        {
            **AZICAC_2011_006_FIXTURE,
            "id": "second_hit",
            "agencies_involved": ["FBI"],
        }
    )
    fbi = BASE["agency/fbi"]
    label = Literal("Federal Bureau of Investigation")
    assert (fbi, RDFS.label, label) in g1.get_context(GRAPH_DETERMINISTIC)
    assert (fbi, RDFS.label, label) in g2.get_context(GRAPH_DETERMINISTIC)
