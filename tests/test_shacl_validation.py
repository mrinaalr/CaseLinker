"""SHACL shapes load + canary: invalid graphs must not conform."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from rdflib import Dataset, Namespace, RDF, URIRef

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


def test_canary_invalid_victim_role_fails_validation():
    """VictimRole without required hasRoleBeginPoint must not conform."""
    ds = Dataset()
    ctx = ds.graph(URIRef("https://example.org/graph/canary"))
    role = URIRef("https://example.org/victimRole/canary-invalid")
    ctx.add((role, RDF.type, CAC.VictimRole))

    conforms, report = CaseToCAC().validate(ds)
    assert conforms is False
    assert "Victim role must have begin point" in (report or "") or "MinCount" in (
        report or ""
    )
