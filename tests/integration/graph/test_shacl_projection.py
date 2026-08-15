from __future__ import annotations

from pathlib import Path

import pytest
from rdflib import Graph

from caselinker.graph import (
    CacLegalEventProjector,
    GraphProjection,
    ShaclValidation,
    ShaclValidator,
)
from tests.unit.graph.test_cac_legal_events import ReviewReader, resolved_bundle

SHAPES = Path("schemas/rdf/cac-legal-event-projection-v1.shacl.ttl")


def validator() -> ShaclValidator:
    shapes = Graph()
    shapes.parse(SHAPES, format="turtle")
    return ShaclValidator(shapes=shapes)


def test_eligible_projection_conforms_and_report_is_reproducible() -> None:
    assertions, decisions = resolved_bundle()
    projection = CacLegalEventProjector().project(
        assertions=assertions, reviews=ReviewReader(decisions)
    )

    first = validator().validate(projection)
    second = validator().validate(projection)

    assert first.conforms
    assert first.report_ntriples == second.report_ntriples
    assert first.report_sha256 == second.report_sha256
    assert first.projection_sha256 == projection.sha256
    assert first.shapes_sha256 == second.shapes_sha256


def test_shape_gate_rejects_projection_with_missing_subject_link() -> None:
    assertions, decisions = resolved_bundle()
    projection = CacLegalEventProjector().project(
        assertions=assertions, reviews=ReviewReader(decisions)
    )
    lines = projection.canonical_ntriples.decode().splitlines()
    broken_payload = (
        "\n".join(line for line in lines if "subjectOfLegalEvent" not in line) + "\n"
    ).encode()
    import hashlib

    broken = GraphProjection(
        canonical_ntriples=broken_payload,
        sha256=hashlib.sha256(broken_payload).hexdigest(),
        assertion_ids=projection.assertion_ids,
    )

    result = validator().validate(broken)

    assert not result.conforms
    assert b"ValidationResult" in result.report_ntriples


def test_validation_value_rejects_wrong_report_digest() -> None:
    with pytest.raises(ValueError, match="report_sha256"):
        ShaclValidation(True, b"report\n", "0" * 64, "1" * 64, "2" * 64)


@pytest.mark.parametrize("field", ["projection_sha256", "shapes_sha256"])
def test_validation_value_rejects_invalid_bound_digest(field: str) -> None:
    import hashlib

    values = {
        "conforms": True,
        "report_ntriples": b"report\n",
        "report_sha256": hashlib.sha256(b"report\n").hexdigest(),
        "projection_sha256": "1" * 64,
        "shapes_sha256": "2" * 64,
    }
    values[field] = "not-a-digest"

    with pytest.raises(ValueError, match=field):
        ShaclValidation(**values)
