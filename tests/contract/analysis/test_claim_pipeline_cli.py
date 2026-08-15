from __future__ import annotations

import json
from pathlib import Path

import pytest

from caselinker.analysis import ClaimExpectation, ClaimPipeline, ClaimPipelineError
from caselinker.analysis.cli import main
from caselinker.analysis.pipeline import load_projection
from caselinker.graph import CacLegalEventProjector
from caselinker.snapshots.manifest import (
    ComponentKind,
    build_manifest,
    canonical_json,
    sha256_bytes,
    write_manifest,
)
from tests.unit.graph.test_cac_legal_events import ReviewReader, resolved_bundle


def _workspace(tmp_path: Path) -> Path:
    dummy = tmp_path / "dummy.txt"
    dummy.write_text("policy-safe fixture\n", encoding="utf-8")
    shapes = tmp_path / "shapes.ttl"
    shapes.write_text(
        Path("schemas/rdf/cac-legal-event-projection-v1.shacl.ttl").read_text(),
        encoding="utf-8",
    )
    assertions, decisions = resolved_bundle()
    projection = CacLegalEventProjector().project(
        assertions=assertions, reviews=ReviewReader(decisions)
    )
    projection_path = tmp_path / "legal-event.nt"
    projection_path.write_bytes(projection.canonical_ntriples)
    query = tmp_path / "query.json"
    query.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "query_id": "qry_cli_charge_001",
                "event_type": "legal_event_charge",
                "unit": "legal_event",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    paths = {kind: ["dummy.txt"] for kind in ComponentKind}
    paths[ComponentKind.SHAPES] = ["shapes.ttl"]
    paths[ComponentKind.QUERY] = ["query.json"]
    paths[ComponentKind.OUTPUTS] = ["legal-event.nt"]
    snapshot_spec = {
        "schema_version": "1.0",
        "snapshot_id": "snap_claim_cli_001",
        "recorded_at": "2026-08-15T00:00:00Z",
        "code_revision": "40d0392e2b004b8e4f02349322aa352e815c4b24",
        "components": [{"kind": kind.value, "paths": paths[kind]} for kind in ComponentKind],
    }
    snapshot_spec_path = tmp_path / "snapshot-spec.json"
    snapshot_spec_path.write_text(json.dumps(snapshot_spec), encoding="utf-8")
    manifest = build_manifest(root=tmp_path, spec_path=snapshot_spec_path)
    write_manifest(tmp_path / "manifest.json", manifest)

    pipeline_spec = {
        "schema_version": "1.0",
        "snapshot_manifest": "manifest.json",
        "shapes": "shapes.ttl",
        "query": "query.json",
        "projections": ["legal-event.nt"],
    }
    pipeline_spec_path = tmp_path / "pipeline.json"
    pipeline_spec_path.write_text(json.dumps(pipeline_spec), encoding="utf-8")
    return pipeline_spec_path


def _write_expectation(path: Path, expectation: ClaimExpectation) -> None:
    path.write_text(json.dumps(expectation.to_dict(), sort_keys=True), encoding="utf-8")


def test_cli_builds_exact_pack_and_passes_claim_ci(tmp_path: Path, capsys: object) -> None:
    spec = _workspace(tmp_path)
    result = ClaimPipeline().run(root=tmp_path, spec_path=spec)
    expectation = ClaimExpectation.pin(claim=result.claim, evidence_pack=result.evidence_pack)
    expectation_path = tmp_path / "expectation.json"
    _write_expectation(expectation_path, expectation)
    output = tmp_path / "evidence-pack.json"

    assert (
        main(["--root", str(tmp_path), "build", "--spec", str(spec), "--output", str(output)]) == 0
    )
    assert output.read_bytes() == result.evidence_pack.canonical_json
    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "check",
                "--spec",
                str(spec),
                "--expectation",
                str(expectation_path),
            ]
        )
        == 0
    )


def test_cli_returns_one_for_valid_but_different_expectation(
    tmp_path: Path, capsys: object
) -> None:
    spec = _workspace(tmp_path)
    result = ClaimPipeline().run(root=tmp_path, spec_path=spec)
    expectation = ClaimExpectation.pin(claim=result.claim, evidence_pack=result.evidence_pack)
    values = expectation.to_dict(include_expectation_id=False)
    values["query_sha256"] = "9" * 64
    expectation_id = "expect_" + sha256_bytes(canonical_json(values))
    changed = ClaimExpectation.from_dict({**values, "expectation_id": expectation_id})
    path = tmp_path / "changed-expectation.json"
    _write_expectation(path, changed)

    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "check",
                "--spec",
                str(spec),
                "--expectation",
                str(path),
            ]
        )
        == 1
    )


def test_cli_rejects_path_escape(tmp_path: Path, capsys: object) -> None:
    spec = _workspace(tmp_path)
    value = json.loads(spec.read_text())
    value["shapes"] = "../shapes.ttl"
    spec.write_text(json.dumps(value), encoding="utf-8")

    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "build",
                "--spec",
                str(spec),
                "--output",
                str(tmp_path / "out"),
            ]
        )
        == 2
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.pop("query"), "v1 contract"),
        (lambda value: value.update({"shapes": "dummy.txt"}), "shapes file is not bound"),
        (lambda value: value.update({"query": "dummy.txt"}), "query file is not bound"),
        (lambda value: value.update({"projections": []}), "non-empty"),
        (
            lambda value: value.update({"projections": ["legal-event.nt", "legal-event.nt"]}),
            "must not repeat",
        ),
    ],
)
def test_pipeline_spec_failures_are_typed(tmp_path: Path, mutation: object, message: str) -> None:
    spec = _workspace(tmp_path)
    value = json.loads(spec.read_text())
    mutation(value)  # type: ignore[operator]
    spec.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ClaimPipelineError, match=message):
        ClaimPipeline().run(root=tmp_path, spec_path=spec)


def test_stale_manifest_and_unbound_projection_are_rejected(tmp_path: Path) -> None:
    spec = _workspace(tmp_path)
    (tmp_path / "dummy.txt").write_text("changed\n", encoding="utf-8")
    with pytest.raises(ClaimPipelineError, match="verification failed"):
        ClaimPipeline().run(root=tmp_path, spec_path=spec)

    spec = _workspace(tmp_path)
    original = (tmp_path / "legal-event.nt").read_text()
    changed = original.replace("asrt_5620", "asrt_5621")
    (tmp_path / "unbound.nt").write_text(changed, encoding="utf-8")
    value = json.loads(spec.read_text())
    value["projections"] = ["unbound.nt"]
    spec.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ClaimPipelineError, match="not bound to the snapshot outputs"):
        ClaimPipeline().run(root=tmp_path, spec_path=spec)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"\xff", "valid UTF-8"),
        (b"not rdf\n", "N-Triples"),
        (
            b"<https://caselinker.up.railway.app/resource/vnext/entity/event_test_001> "
            b"<http://www.w3.org/1999/02/22-rdf-syntax-ns#type> "
            b"<https://caselinker.up.railway.app/vocab/vnext#LegalEventProjection> .\n",
            "no resolved assertion provenance",
        ),
    ],
)
def test_projection_loader_rejects_invalid_or_unprovenanced_rdf(
    tmp_path: Path, payload: bytes, message: str
) -> None:
    path = tmp_path / "projection.nt"
    path.write_bytes(payload)

    with pytest.raises(ClaimPipelineError, match=message):
        load_projection(path)


def test_projection_loader_rejects_noncanonical_bytes(tmp_path: Path) -> None:
    _workspace(tmp_path)
    path = tmp_path / "legal-event.nt"
    path.write_bytes(path.read_bytes() + b"\n")

    with pytest.raises(ClaimPipelineError, match="not canonical"):
        load_projection(path)


def test_cli_rejects_malformed_expectation(tmp_path: Path, capsys: object) -> None:
    spec = _workspace(tmp_path)
    expectation = tmp_path / "bad-expectation.json"
    expectation.write_text("{}", encoding="utf-8")

    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "check",
                "--spec",
                str(spec),
                "--expectation",
                str(expectation),
            ]
        )
        == 2
    )
