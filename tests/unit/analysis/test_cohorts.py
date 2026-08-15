from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest
from rdflib import RDF, Graph, URIRef

from caselinker.analysis import (
    CohortAnalysisError,
    CohortQuery,
    LegalEventCohortAnalyzer,
    SnapshotReference,
    ValidatedProjection,
)
from caselinker.graph import GraphProjection, ShaclValidation
from caselinker.graph.cac_legal_events import CL, RESOURCE, _canonical_ntriples
from caselinker.snapshots.manifest import canonical_json, sha256_bytes

SHAPES_DIGEST = "a" * 64


def validated_projection(
    event_id: str,
    event_type: str,
    *,
    assertion_suffix: str,
    shapes_sha256: str = SHAPES_DIGEST,
) -> ValidatedProjection:
    graph = Graph()
    event = RESOURCE[f"entity/{event_id}"]
    graph.add((event, RDF.type, CL.LegalEventProjection))
    graph.add((event, CL.legalEventType, RESOURCE[f"legal-event-type/{event_type}"]))
    payload = _canonical_ntriples(graph)
    projection = GraphProjection(
        payload,
        hashlib.sha256(payload).hexdigest(),
        (f"asrt_analysis_{assertion_suffix}",),
    )
    report = b"conforming-report\n"
    validation = ShaclValidation(
        True,
        report,
        hashlib.sha256(report).hexdigest(),
        projection.sha256,
        shapes_sha256,
    )
    return ValidatedProjection(projection, validation)


def snapshot(projections: tuple[ValidatedProjection, ...] = ()) -> SnapshotReference:
    output_hashes = tuple(sorted(item.projection.sha256 for item in projections))
    return SnapshotReference("snap_analysis_fixture_001", "b" * 64, output_hashes or ("f" * 64,))


def query() -> CohortQuery:
    return CohortQuery("qry_charge_events_001", "legal_event_charge")


def test_exact_cohort_counts_name_unit_and_denominator_members() -> None:
    projections = (
        validated_projection("event_analysis_001", "legal_event_charge", assertion_suffix="001"),
        validated_projection("event_analysis_002", "legal_event_arrest", assertion_suffix="002"),
        validated_projection("event_analysis_003", "legal_event_charge", assertion_suffix="003"),
    )

    result = LegalEventCohortAnalyzer().analyze(
        snapshot=snapshot(projections), query=query(), projections=tuple(reversed(projections))
    )

    assert result.query.unit == "legal_event"
    assert (result.numerator, result.denominator) == (2, 3)
    assert result.numerator_event_ids == ("event_analysis_001", "event_analysis_003")
    assert result.denominator_event_ids == (
        "event_analysis_001",
        "event_analysis_002",
        "event_analysis_003",
    )
    assert result.projection_sha256s == tuple(
        sorted(item.projection.sha256 for item in projections)
    )


def test_zero_numerator_remains_an_exact_supported_result() -> None:
    projections = (
        validated_projection("event_analysis_001", "legal_event_charge", assertion_suffix="001"),
    )
    result = LegalEventCohortAnalyzer().analyze(
        snapshot=snapshot(projections),
        query=CohortQuery("qry_sentencing_events_001", "legal_event_sentencing"),
        projections=projections,
    )

    assert (result.numerator, result.denominator) == (0, 1)
    assert result.numerator_event_ids == ()


def test_empty_cohort_and_duplicate_event_units_are_rejected() -> None:
    analyzer = LegalEventCohortAnalyzer()
    with pytest.raises(CohortAnalysisError, match="at least one"):
        analyzer.analyze(snapshot=snapshot(), query=query(), projections=())

    duplicate = (
        validated_projection("event_analysis_001", "legal_event_charge", assertion_suffix="001"),
        validated_projection("event_analysis_001", "legal_event_arrest", assertion_suffix="002"),
    )
    with pytest.raises(CohortAnalysisError, match="duplicate legal-event"):
        analyzer.analyze(snapshot=snapshot(duplicate), query=query(), projections=duplicate)


def test_mixed_shapes_are_rejected() -> None:
    projections = (
        validated_projection("event_analysis_001", "legal_event_charge", assertion_suffix="001"),
        validated_projection(
            "event_analysis_002",
            "legal_event_charge",
            assertion_suffix="002",
            shapes_sha256="c" * 64,
        ),
    )

    with pytest.raises(CohortAnalysisError, match="same pinned SHACL"):
        LegalEventCohortAnalyzer().analyze(
            snapshot=snapshot(projections), query=query(), projections=projections
        )


def test_validation_must_conform_and_bind_exact_projection() -> None:
    item = validated_projection("event_analysis_001", "legal_event_charge", assertion_suffix="001")
    nonconforming = ShaclValidation(
        False,
        item.validation.report_ntriples,
        item.validation.report_sha256,
        item.projection.sha256,
        SHAPES_DIGEST,
    )
    with pytest.raises(ValueError, match="conforming"):
        ValidatedProjection(item.projection, nonconforming)

    mismatched = ShaclValidation(
        True,
        item.validation.report_ntriples,
        item.validation.report_sha256,
        "d" * 64,
        SHAPES_DIGEST,
    )
    with pytest.raises(ValueError, match="does not govern"):
        ValidatedProjection(item.projection, mismatched)


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: SnapshotReference("bad", "b" * 64, ("f" * 64,)), "snapshot_id"),
        (lambda: SnapshotReference("snap_valid_001", "bad", ("f" * 64,)), "manifest_sha256"),
        (lambda: SnapshotReference("snap_valid_001", "b" * 64, ()), "output_sha256s"),
        (lambda: SnapshotReference("snap_valid_001", "b" * 64, ("bad",)), "output_sha256s"),
        (
            lambda: SnapshotReference("snap_valid_001", "b" * 64, ("f" * 64, "f" * 64)),
            "unique",
        ),
        (lambda: CohortQuery("bad", "legal_event_charge"), "query_id"),
        (lambda: CohortQuery("qry_valid_001", "legal_event_unknown"), "allowlist"),
        (lambda: CohortQuery("qry_valid_001", "legal_event_charge", "case"), "counts"),
    ],
)
def test_boundary_values_are_strict(factory: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        factory()  # type: ignore[operator]


def test_query_digest_is_stable_and_content_sensitive() -> None:
    assert query().sha256 == query().sha256
    assert query().sha256 != CohortQuery("qry_arrest_events_001", "legal_event_arrest").sha256


def test_snapshot_reference_is_derived_from_canonical_manifest_outputs() -> None:
    payload: dict[str, object] = {
        "snapshot_id": "snap_manifest_fixture_001",
        "components": [
            {
                "kind": "outputs",
                "status": "included",
                "files": [{"path": "one.nt", "bytes": 1, "sha256": "1" * 64}],
                "sha256": "2" * 64,
            }
        ],
    }
    manifest = {**payload, "manifest_sha256": sha256_bytes(canonical_json(payload))}

    reference = SnapshotReference.from_manifest(manifest)

    assert reference.snapshot_id == "snap_manifest_fixture_001"
    assert reference.output_sha256s == ("1" * 64,)

    manifest["snapshot_id"] = "snap_tampered_001"
    with pytest.raises(ValueError, match="does not match"):
        SnapshotReference.from_manifest(manifest)


def test_projection_must_be_an_output_of_bound_snapshot() -> None:
    item = validated_projection("event_analysis_001", "legal_event_charge", assertion_suffix="001")

    with pytest.raises(CohortAnalysisError, match="output of the bound snapshot"):
        LegalEventCohortAnalyzer().analyze(snapshot=snapshot(), query=query(), projections=(item,))


def test_projection_with_foreign_event_namespace_is_rejected() -> None:
    graph = Graph()
    foreign = URIRef("https://example.invalid/event/001")
    graph.add((foreign, RDF.type, CL.LegalEventProjection))
    graph.add((foreign, CL.legalEventType, RESOURCE["legal-event-type/legal_event_charge"]))
    payload = _canonical_ntriples(graph)
    projection = GraphProjection(
        payload, hashlib.sha256(payload).hexdigest(), ("asrt_foreign_001",)
    )
    report = b"ok\n"
    item = ValidatedProjection(
        projection,
        ShaclValidation(
            True,
            report,
            hashlib.sha256(report).hexdigest(),
            projection.sha256,
            SHAPES_DIGEST,
        ),
    )

    with pytest.raises(CohortAnalysisError, match="resource namespace"):
        LegalEventCohortAnalyzer().analyze(
            snapshot=snapshot((item,)), query=query(), projections=(item,)
        )


def test_result_rejects_inconsistent_counts_membership_order_and_shapes() -> None:
    projections = (
        validated_projection("event_analysis_001", "legal_event_charge", assertion_suffix="001"),
        validated_projection("event_analysis_002", "legal_event_arrest", assertion_suffix="002"),
    )
    valid = LegalEventCohortAnalyzer().analyze(
        snapshot=snapshot(projections),
        query=query(),
        projections=projections,
    )
    mutations = (
        ({"denominator": 0}, "at least one"),
        ({"numerator": 3}, "between zero"),
        ({"numerator_event_ids": ()}, "number of numerator"),
        ({"denominator_event_ids": ("event_analysis_001",)}, "number of denominator"),
        ({"numerator_event_ids": ("event_other_001",)}, "subset"),
        (
            {"denominator_event_ids": tuple(reversed(valid.denominator_event_ids))},
            "lexically sorted",
        ),
        ({"projection_sha256s": (valid.projection_sha256s[0],) * 2}, "lexically sorted"),
        ({"shapes_sha256": "bad"}, "shapes_sha256"),
    )
    for changes, message in mutations:
        with pytest.raises(ValueError, match=message):
            replace(valid, **changes)


def test_projection_with_foreign_or_unknown_type_namespace_is_rejected() -> None:
    for type_iri, message in (
        (URIRef("https://example.invalid/type/charge"), "allowlisted namespace"),
        (RESOURCE["legal-event-type/legal_event_unknown"], "unrecognized"),
    ):
        graph = Graph()
        event = RESOURCE["entity/event_analysis_001"]
        graph.add((event, RDF.type, CL.LegalEventProjection))
        graph.add((event, CL.legalEventType, type_iri))
        payload = _canonical_ntriples(graph)
        projection = GraphProjection(
            payload, hashlib.sha256(payload).hexdigest(), ("asrt_type_001",)
        )
        report = b"ok\n"
        item = ValidatedProjection(
            projection,
            ShaclValidation(
                True,
                report,
                hashlib.sha256(report).hexdigest(),
                projection.sha256,
                SHAPES_DIGEST,
            ),
        )
        with pytest.raises(CohortAnalysisError, match=message):
            LegalEventCohortAnalyzer().analyze(
                snapshot=snapshot((item,)), query=query(), projections=(item,)
            )
