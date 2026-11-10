"""SHACL shapes load + canary: invalid graphs must not conform."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from decimal import Decimal

from rdflib import Dataset, Literal, Namespace, RDF, URIRef

REPO = Path(__file__).resolve().parents[1]
ONTOLOGY = REPO / "ontology"
if str(ONTOLOGY) not in sys.path:
    sys.path.insert(0, str(ONTOLOGY))

from features_to_cac import (  # noqa: E402
    CaseToCAC,
    get_core_shapes_path,
    load_core_shapes_graph,
)

CAC = Namespace("https://cacontology.projectvic.org#")
pytest.importorskip("pyshacl")


def test_core_shapes_path_defaults_to_pinned_ontology_dir():
    path = get_core_shapes_path()
    assert path == (ONTOLOGY / "vendor" / "cac-3.1.0" / "cacontology-core-shapes.ttl").resolve()
    assert path.is_file()


def test_load_core_shapes_graph_has_shapes():
    shapes_graph, shape_count = load_core_shapes_graph()
    assert shape_count > 0
    assert len(shapes_graph) > 0


def test_load_core_shapes_missing_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("CAC_ONTOLOGY_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError, match="SHACL shapes file not found"):
        load_core_shapes_graph()


def test_load_core_shapes_empty_raises(tmp_path, monkeypatch):
    empty = tmp_path / "cacontology-core-shapes.ttl"
    empty.write_text(
        "@prefix sh: <http://www.w3.org/ns/shacl#> .\n"
        "@prefix ex: <https://example.org/> .\n"
        "ex:notAShape ex:comment \"no shapes here\" .\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CAC_ONTOLOGY_DIR", str(tmp_path))
    with pytest.raises(RuntimeError, match="0 NodeShape/PropertyShape"):
        load_core_shapes_graph()


def test_canary_wrong_value_fails_validation():
    """A value CaseLinker got wrong fails, even when other gaps are only unstated."""
    TEMPORAL = Namespace("https://cacontology.projectvic.org/temporal#")
    ds = Dataset()
    ctx = ds.graph(URIRef("https://example.org/graph/canary"))
    age = URIRef("https://example.org/age/canary-invalid")
    person = URIRef("https://example.org/person/canary")
    ctx.add((person, RDF.type, URIRef("https://ontology.unifiedcyberontology.org/uco/identity/Person")))
    ctx.add((age, RDF.type, TEMPORAL.AgeAtTimeSituation))
    ctx.add((age, TEMPORAL.ageSubject, person))
    ctx.add((age, TEMPORAL.hasAgeInYears, Literal(Decimal(14))))
    ctx.add((age, TEMPORAL.concernsAgeQuality, URIRef("https://example.org/not-age")))

    conforms, report = CaseToCAC().validate(ds)
    assert conforms is False
    assert report.startswith("caselinker: 1 AgeAtTimeSituation, when specifying a quality type")


def test_unstated_values_are_reported_not_invented():
    """A victim role with no begin point passes (the release never states one) and is reported."""
    ds = Dataset()
    ctx = ds.graph(URIRef("https://example.org/graph/canary"))
    role = URIRef("https://example.org/victimRole/no-begin-point")
    ctx.add((role, RDF.type, CAC.VictimRole))

    conforms, report = CaseToCAC().validate(ds)
    assert conforms is True
    assert "unstated: 1 Victim role must have begin point" in report
