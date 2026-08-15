"""SHACL validation adapter with deterministic report serialization."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from pyshacl import validate
from rdflib import Graph
from rdflib.compare import to_canonical_graph

from caselinker.graph.cac_legal_events import GraphProjection, _canonical_ntriples


@dataclass(frozen=True, slots=True)
class ShaclValidation:
    conforms: bool
    report_ntriples: bytes
    report_sha256: str
    projection_sha256: str
    shapes_sha256: str

    def __post_init__(self) -> None:
        if hashlib.sha256(self.report_ntriples).hexdigest() != self.report_sha256:
            raise ValueError("report_sha256 must identify report_ntriples")
        for field, value in (
            ("projection_sha256", self.projection_sha256),
            ("shapes_sha256", self.shapes_sha256),
        ):
            if re.fullmatch(r"[0-9a-f]{64}", value) is None:
                raise ValueError(f"{field} must be a lowercase SHA-256 digest")


class ShaclValidator:
    """Validate projections against an injected, pinned shapes graph."""

    def __init__(self, *, shapes: Graph) -> None:
        self._shapes = shapes
        shapes_payload = _canonical_ntriples(to_canonical_graph(shapes))
        self._shapes_sha256 = hashlib.sha256(shapes_payload).hexdigest()

    def validate(self, projection: GraphProjection) -> ShaclValidation:
        data_graph = Graph()
        data_graph.parse(data=projection.canonical_ntriples, format="nt")
        conforms, report_graph, _ = validate(
            data_graph=data_graph,
            shacl_graph=self._shapes,
            inference="none",
            advanced=False,
            meta_shacl=True,
        )
        if not isinstance(report_graph, Graph):
            raise TypeError("pySHACL did not return an RDF report graph")
        payload = _canonical_ntriples(to_canonical_graph(report_graph))
        return ShaclValidation(
            conforms=bool(conforms),
            report_ntriples=payload,
            report_sha256=hashlib.sha256(payload).hexdigest(),
            projection_sha256=projection.sha256,
            shapes_sha256=self._shapes_sha256,
        )
