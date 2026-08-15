"""Exact, unit-explicit cohort analysis over validated legal-event projections."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from rdflib import RDF, Graph, URIRef

from caselinker.graph.cac_legal_events import CL, RESOURCE, GraphProjection
from caselinker.graph.shacl import ShaclValidation
from caselinker.snapshots.manifest import (
    SHA256_PATTERN,
    SNAPSHOT_ID_PATTERN,
    canonical_json,
    sha256_bytes,
)

QUERY_ID_PATTERN: Final = re.compile(r"^qry_[a-z0-9][a-z0-9._-]{2,127}$")
LEGAL_EVENT_TYPES: Final = frozenset(
    {
        "legal_event_arrest",
        "legal_event_charge",
        "legal_event_indictment",
        "legal_event_guilty_plea",
        "legal_event_conviction",
        "legal_event_sentencing",
    }
)
LEGAL_EVENT_UNIT: Final = "legal_event"
_EVENT_PREFIX: Final = str(RESOURCE["entity/"])
_TYPE_PREFIX: Final = str(RESOURCE["legal-event-type/"])


class CohortAnalysisError(ValueError):
    """Inputs cannot support the requested cohort claim."""


@dataclass(frozen=True, slots=True)
class SnapshotReference:
    snapshot_id: str
    manifest_sha256: str
    output_sha256s: tuple[str, ...]

    def __post_init__(self) -> None:
        if SNAPSHOT_ID_PATTERN.fullmatch(self.snapshot_id) is None:
            raise ValueError("snapshot_id must be an opaque snap_ identifier")
        if SHA256_PATTERN.fullmatch(self.manifest_sha256) is None:
            raise ValueError("manifest_sha256 must be a lowercase SHA-256 digest")
        if not self.output_sha256s:
            raise ValueError("output_sha256s must identify snapshot output artifacts")
        if tuple(sorted(set(self.output_sha256s))) != self.output_sha256s:
            raise ValueError("output_sha256s must be unique and lexically sorted")
        if any(SHA256_PATTERN.fullmatch(value) is None for value in self.output_sha256s):
            raise ValueError("output_sha256s must contain lowercase SHA-256 digests")

    @classmethod
    def from_manifest(cls, manifest: Mapping[str, object]) -> SnapshotReference:
        """Bind to a self-consistent manifest after callers verify its referenced files."""
        expected_digest = manifest.get("manifest_sha256")
        unhashed = dict(manifest)
        unhashed.pop("manifest_sha256", None)
        if not isinstance(expected_digest, str) or expected_digest != sha256_bytes(
            canonical_json(unhashed)
        ):
            raise ValueError("manifest_sha256 does not match the canonical manifest payload")
        snapshot_id = manifest.get("snapshot_id")
        components = manifest.get("components")
        if not isinstance(snapshot_id, str) or not isinstance(components, list):
            raise ValueError("manifest must contain snapshot_id and components")
        outputs = [
            component
            for component in components
            if isinstance(component, Mapping)
            and component.get("kind") == "outputs"
            and component.get("status") == "included"
        ]
        if len(outputs) != 1 or not isinstance(outputs[0].get("files"), list):
            raise ValueError("manifest must contain one included outputs component")
        digests = []
        for file_record in outputs[0]["files"]:
            if not isinstance(file_record, Mapping) or not isinstance(
                file_record.get("sha256"), str
            ):
                raise ValueError("manifest output files must contain sha256 digests")
            digests.append(file_record["sha256"])
        return cls(snapshot_id, expected_digest, tuple(sorted(set(digests))))


@dataclass(frozen=True, slots=True)
class CohortQuery:
    query_id: str
    event_type: str
    unit: str = LEGAL_EVENT_UNIT

    def __post_init__(self) -> None:
        if QUERY_ID_PATTERN.fullmatch(self.query_id) is None:
            raise ValueError("query_id must be an opaque qry_ identifier")
        if self.event_type not in LEGAL_EVENT_TYPES:
            raise ValueError("event_type must use the legal-event allowlist")
        if self.unit != LEGAL_EVENT_UNIT:
            raise ValueError("this analyzer counts legal_event units only")

    @property
    def sha256(self) -> str:
        return sha256_bytes(
            canonical_json(
                {"event_type": self.event_type, "query_id": self.query_id, "unit": self.unit}
            )
        )


@dataclass(frozen=True, slots=True)
class ValidatedProjection:
    projection: GraphProjection
    validation: ShaclValidation

    def __post_init__(self) -> None:
        if not self.validation.conforms:
            raise ValueError("only conforming SHACL projections may enter analysis")
        if self.validation.projection_sha256 != self.projection.sha256:
            raise ValueError("SHACL result does not govern this projection")


@dataclass(frozen=True, slots=True)
class CohortResult:
    snapshot: SnapshotReference
    query: CohortQuery
    numerator: int
    denominator: int
    numerator_event_ids: tuple[str, ...]
    denominator_event_ids: tuple[str, ...]
    projection_sha256s: tuple[str, ...]
    shapes_sha256: str

    def __post_init__(self) -> None:
        if self.denominator < 1:
            raise ValueError("denominator must contain at least one legal-event unit")
        if not 0 <= self.numerator <= self.denominator:
            raise ValueError("numerator must be between zero and denominator")
        if len(self.numerator_event_ids) != self.numerator:
            raise ValueError("numerator must equal the number of numerator event IDs")
        if len(self.denominator_event_ids) != self.denominator:
            raise ValueError("denominator must equal the number of denominator event IDs")
        if not set(self.numerator_event_ids) <= set(self.denominator_event_ids):
            raise ValueError("numerator events must be a subset of denominator events")
        for name, values in (
            ("numerator_event_ids", self.numerator_event_ids),
            ("denominator_event_ids", self.denominator_event_ids),
            ("projection_sha256s", self.projection_sha256s),
        ):
            if tuple(sorted(set(values))) != values:
                raise ValueError(f"{name} must be unique and lexically sorted")
        if SHA256_PATTERN.fullmatch(self.shapes_sha256) is None:
            raise ValueError("shapes_sha256 must be a lowercase SHA-256 digest")


class LegalEventCohortAnalyzer:
    """Count distinct event resources across one validated snapshot input set."""

    def analyze(
        self,
        *,
        snapshot: SnapshotReference,
        query: CohortQuery,
        projections: tuple[ValidatedProjection, ...],
    ) -> CohortResult:
        if not projections:
            raise CohortAnalysisError("cohort analysis requires at least one projection")
        shapes = {item.validation.shapes_sha256 for item in projections}
        if len(shapes) != 1:
            raise CohortAnalysisError("all projections must use the same pinned SHACL shapes")

        event_types: dict[str, str] = {}
        projection_hashes: list[str] = []
        for item in projections:
            if item.projection.sha256 not in snapshot.output_sha256s:
                raise CohortAnalysisError(
                    "every projection must be an output of the bound snapshot"
                )
            projection_hashes.append(item.projection.sha256)
            event_id, event_type = self._event_record(item.projection)
            if event_id in event_types:
                raise CohortAnalysisError(f"duplicate legal-event unit: {event_id}")
            event_types[event_id] = event_type

        denominator_ids = tuple(sorted(event_types))
        numerator_ids = tuple(
            event_id for event_id in denominator_ids if event_types[event_id] == query.event_type
        )
        return CohortResult(
            snapshot=snapshot,
            query=query,
            numerator=len(numerator_ids),
            denominator=len(denominator_ids),
            numerator_event_ids=numerator_ids,
            denominator_event_ids=denominator_ids,
            projection_sha256s=tuple(sorted(set(projection_hashes))),
            shapes_sha256=next(iter(shapes)),
        )

    @staticmethod
    def _event_record(projection: GraphProjection) -> tuple[str, str]:
        graph = Graph()
        graph.parse(data=projection.canonical_ntriples, format="nt")
        events = tuple(graph.subjects(RDF.type, CL.LegalEventProjection, unique=True))
        if len(events) != 1 or not isinstance(events[0], URIRef):
            raise CohortAnalysisError("projection must contain exactly one legal-event IRI")
        event_iri = str(events[0])
        if not event_iri.startswith(_EVENT_PREFIX):
            raise CohortAnalysisError("legal-event IRI is outside the vNext resource namespace")
        event_id = event_iri.removeprefix(_EVENT_PREFIX)
        values = tuple(graph.objects(events[0], CL.legalEventType, unique=True))
        if len(values) != 1 or not isinstance(values[0], URIRef):
            raise CohortAnalysisError("projection must contain exactly one legal-event type IRI")
        type_iri = str(values[0])
        if not type_iri.startswith(_TYPE_PREFIX):
            raise CohortAnalysisError("legal-event type is outside the allowlisted namespace")
        event_type = type_iri.removeprefix(_TYPE_PREFIX)
        if event_type not in LEGAL_EVENT_TYPES:
            raise CohortAnalysisError("projection contains an unrecognized legal-event type")
        return event_id, event_type
