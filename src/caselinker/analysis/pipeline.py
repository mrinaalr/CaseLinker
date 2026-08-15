"""Strict filesystem adapter for the reproducible claim pipeline."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

from rdflib import RDF, Graph, URIRef

from caselinker.analysis.claims import ClaimCard, ClaimCardBuilder
from caselinker.analysis.cohorts import (
    CohortQuery,
    LegalEventCohortAnalyzer,
    SnapshotReference,
    ValidatedProjection,
)
from caselinker.analysis.evidence_pack import EvidencePack, EvidencePackAssembler
from caselinker.graph.cac_legal_events import CL, RESOURCE, GraphProjection, _canonical_ntriples
from caselinker.graph.shacl import ShaclValidation, ShaclValidator
from caselinker.snapshots.manifest import verify_manifest

PIPELINE_SCHEMA_VERSION: Final = "1.0"
SPEC_FIELDS: Final = frozenset(
    {"schema_version", "snapshot_manifest", "shapes", "query", "projections"}
)
QUERY_FIELDS: Final = frozenset({"schema_version", "query_id", "event_type", "unit"})
_ASSERTION_PREFIX: Final = str(RESOURCE["assertion/"])


class ClaimPipelineError(ValueError):
    """A pipeline input fails its strict reproducibility contract."""


@dataclass(frozen=True, slots=True)
class PipelineResult:
    claim: ClaimCard
    evidence_pack: EvidencePack
    validations: tuple[ShaclValidation, ...]

    def __post_init__(self) -> None:
        if not self.validations or not all(item.conforms for item in self.validations):
            raise ValueError("pipeline results require conforming SHACL validations")


def _load_json(path: Path, *, label: str) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClaimPipelineError(f"{label} is not valid UTF-8 JSON: {path}") from exc
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ClaimPipelineError(f"{label} must be a JSON object")
    return value


def _resolve_input(root: Path, raw: object, *, field: str) -> Path:
    if not isinstance(raw, str) or not raw or "\\" in raw:
        raise ClaimPipelineError(f"{field} must be a non-empty repository-relative POSIX path")
    relative = PurePosixPath(raw)
    if relative.is_absolute() or ".." in relative.parts or relative.as_posix() != raw:
        raise ClaimPipelineError(f"{field} must be a normalized repository-relative path")
    candidate = root.joinpath(*relative.parts)
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ClaimPipelineError(f"{field} must not traverse a symbolic link")
    if not candidate.is_file():
        raise ClaimPipelineError(f"{field} does not identify a regular file")
    return candidate


def resolve_repository_input(root: Path, path: Path, *, field: str) -> Path:
    """Resolve an explicit CLI path while forbidding escape and symlink traversal."""
    root = root.resolve(strict=True)
    lexical = Path(os.path.abspath(path))
    try:
        relative = lexical.relative_to(root)
    except ValueError as exc:
        raise ClaimPipelineError(f"{field} must be inside the repository root") from exc
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ClaimPipelineError(f"{field} must not traverse a symbolic link")
    if not lexical.is_file():
        raise ClaimPipelineError(f"{field} does not identify a regular file")
    return lexical


def _component_hashes(manifest: Mapping[str, object], kind: str) -> frozenset[str]:
    components = manifest.get("components")
    if not isinstance(components, list):
        raise ClaimPipelineError("snapshot manifest components are malformed")
    matches = [
        component
        for component in components
        if isinstance(component, Mapping)
        and component.get("kind") == kind
        and component.get("status") == "included"
    ]
    if len(matches) != 1 or not isinstance(matches[0].get("files"), list):
        raise ClaimPipelineError(f"snapshot manifest requires one included {kind} component")
    result: set[str] = set()
    for record in matches[0]["files"]:
        if not isinstance(record, Mapping) or not isinstance(record.get("sha256"), str):
            raise ClaimPipelineError(f"snapshot {kind} file inventory is malformed")
        result.add(record["sha256"])
    return frozenset(result)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_projection(path: Path) -> GraphProjection:
    try:
        payload = path.read_bytes()
        payload.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ClaimPipelineError(f"projection is not valid UTF-8: {path}") from exc
    try:
        graph = Graph()
        graph.parse(data=payload, format="nt")
    except Exception as exc:
        raise ClaimPipelineError(f"projection is not valid UTF-8 N-Triples: {path}") from exc
    canonical = _canonical_ntriples(graph)
    if payload != canonical:
        raise ClaimPipelineError(f"projection is not canonical N-Triples: {path}")
    assertion_ids = []
    for node in graph.subjects(RDF.type, CL.ResolvedProjectionStatement, unique=True):
        if not isinstance(node, URIRef) or not str(node).startswith(_ASSERTION_PREFIX):
            raise ClaimPipelineError("projection contains an invalid resolved-assertion IRI")
        assertion_ids.append(str(node).removeprefix(_ASSERTION_PREFIX))
    if not assertion_ids:
        raise ClaimPipelineError("projection contains no resolved assertion provenance")
    return GraphProjection(
        canonical_ntriples=payload,
        sha256=hashlib.sha256(payload).hexdigest(),
        assertion_ids=tuple(sorted(assertion_ids)),
    )


class ClaimPipeline:
    def run(self, *, root: Path, spec_path: Path) -> PipelineResult:
        root = root.resolve(strict=True)
        spec_path = resolve_repository_input(root, spec_path, field="pipeline specification")
        spec = _load_json(spec_path, label="pipeline specification")
        if set(spec) != SPEC_FIELDS or spec.get("schema_version") != PIPELINE_SCHEMA_VERSION:
            raise ClaimPipelineError("pipeline specification does not match the v1 contract")

        manifest_path = _resolve_input(root, spec["snapshot_manifest"], field="snapshot_manifest")
        findings = verify_manifest(root=root, manifest_path=manifest_path)
        if findings:
            raise ClaimPipelineError(
                f"snapshot manifest verification failed with {len(findings)} finding(s)"
            )
        manifest = _load_json(manifest_path, label="snapshot manifest")
        snapshot = SnapshotReference.from_manifest(manifest)

        shapes_path = _resolve_input(root, spec["shapes"], field="shapes")
        if _file_sha256(shapes_path) not in _component_hashes(manifest, "shapes"):
            raise ClaimPipelineError("shapes file is not bound to the snapshot manifest")
        shapes = Graph()
        try:
            shapes.parse(shapes_path, format="turtle")
        except Exception as exc:
            raise ClaimPipelineError("shapes file is not valid Turtle") from exc

        query_path = _resolve_input(root, spec["query"], field="query")
        if _file_sha256(query_path) not in _component_hashes(manifest, "query"):
            raise ClaimPipelineError("query file is not bound to the snapshot manifest")
        query_value = _load_json(query_path, label="query")
        if set(query_value) != QUERY_FIELDS or query_value.get("schema_version") != "1.0":
            raise ClaimPipelineError("query does not match the v1 contract")
        query_id = query_value["query_id"]
        event_type = query_value["event_type"]
        unit = query_value["unit"]
        if not all(isinstance(value, str) for value in (query_id, event_type, unit)):
            raise ClaimPipelineError("query identifiers and values must be strings")
        assert isinstance(query_id, str)
        assert isinstance(event_type, str)
        assert isinstance(unit, str)
        try:
            query = CohortQuery(
                query_id=query_id,
                event_type=event_type,
                unit=unit,
            )
        except ValueError as exc:
            raise ClaimPipelineError(f"query is invalid: {exc}") from exc

        raw_projections = spec["projections"]
        if not isinstance(raw_projections, list) or not raw_projections:
            raise ClaimPipelineError("projections must be a non-empty path array")
        if len(set(str(value) for value in raw_projections)) != len(raw_projections):
            raise ClaimPipelineError("projection paths must not repeat")
        output_hashes = _component_hashes(manifest, "outputs")
        projections = []
        validations = []
        validator = ShaclValidator(shapes=shapes)
        for index, raw_path in enumerate(raw_projections):
            path = _resolve_input(root, raw_path, field=f"projections[{index}]")
            projection = load_projection(path)
            if projection.sha256 not in output_hashes:
                raise ClaimPipelineError("projection is not bound to the snapshot outputs")
            validation = validator.validate(projection)
            if not validation.conforms:
                raise ClaimPipelineError("projection failed the pinned SHACL profile")
            projections.append(ValidatedProjection(projection, validation))
            validations.append(validation)

        result = LegalEventCohortAnalyzer().analyze(
            snapshot=snapshot,
            query=query,
            projections=tuple(projections),
        )
        claim = ClaimCardBuilder().build(result)
        pack = EvidencePackAssembler().assemble(claim)
        return PipelineResult(claim, pack, tuple(validations))
