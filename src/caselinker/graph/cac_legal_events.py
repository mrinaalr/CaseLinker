"""Project eligible resolved legal-event assertions into deterministic CAC RDF."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final

from rdflib import DCTERMS, PROV, RDF, XSD, Graph, Literal, Namespace, URIRef

from caselinker.assertions.models import Assertion, AssertionState, Polarity, ValueKind
from caselinker.resolution.legal_events import (
    EVENT_DATE_PREDICATE,
    EVENT_TYPE_PREDICATE,
    SUBJECT_OF_EVENT_PREDICATE,
)
from caselinker.resolution.publication import (
    CurrentReviewReader,
    ResearchPublicationEligibilityPolicy,
)

RESOURCE: Final = Namespace("https://caselinker.up.railway.app/resource/vnext/")
CL: Final = Namespace("https://caselinker.up.railway.app/vocab/vnext#")
CAC: Final = Namespace("https://cacontology.projectvic.org#")
CAC_LEGAL: Final = Namespace("https://cacontology.projectvic.org/legal-outcomes#")
PROFILE_VERSION: Final = "cac-legal-event-projection-v1"

# These are intentionally conservative CAC classes already used by CaseLinker's legacy mapper.
# The exact procedural distinction remains explicit in cl:legalEventType.
_CAC_EVENT_CLASSES: Final[dict[str, URIRef]] = {
    "legal_event_arrest": CAC.LegalProcessPhase,
    "legal_event_charge": CAC_LEGAL.CriminalCharge,
    "legal_event_indictment": CAC.LegalProcessPhase,
    "legal_event_guilty_plea": CAC_LEGAL.PleaBargaining,
    "legal_event_conviction": CAC_LEGAL.LegalProceeding,
    "legal_event_sentencing": CAC_LEGAL.SentencingHearing,
}


class ProjectionBundleError(ValueError):
    """Resolved assertions do not form one coherent legal-event bundle."""


class IneligibleProjectionError(ProjectionBundleError):
    """At least one assertion fails the live research-publication gate."""


def _iri(kind: str, opaque_id: str) -> URIRef:
    return RESOURCE[f"{kind}/{opaque_id}"]


def _canonical_ntriples(graph: Graph) -> bytes:
    lines = sorted(
        f"{subject.n3()} {predicate.n3()} {value.n3()} ." for subject, predicate, value in graph
    )
    return ("\n".join(lines) + "\n").encode("utf-8")


@dataclass(frozen=True, slots=True)
class GraphProjection:
    canonical_ntriples: bytes
    sha256: str
    assertion_ids: tuple[str, ...]
    profile_version: str = PROFILE_VERSION

    def __post_init__(self) -> None:
        if hashlib.sha256(self.canonical_ntriples).hexdigest() != self.sha256:
            raise ValueError("sha256 must identify canonical_ntriples")
        if len(set(self.assertion_ids)) != len(self.assertion_ids):
            raise ValueError("assertion_ids must not repeat")


class CacLegalEventProjector:
    """Pure projection over resolved assertions; performs no storage or network I/O."""

    def __init__(self, *, eligibility: ResearchPublicationEligibilityPolicy | None = None) -> None:
        self._eligibility = eligibility or ResearchPublicationEligibilityPolicy()

    def project(
        self,
        *,
        assertions: tuple[Assertion, ...],
        reviews: CurrentReviewReader,
    ) -> GraphProjection:
        if len(assertions) not in {2, 3}:
            raise ProjectionBundleError("projection requires two or three resolved assertions")
        if len({item.assertion_id for item in assertions}) != len(assertions):
            raise ProjectionBundleError("projection assertions must not repeat")

        by_predicate: dict[str, list[Assertion]] = {}
        for assertion in assertions:
            eligibility = self._eligibility.evaluate(assertion=assertion, reviews=reviews)
            if not eligibility.eligible:
                reasons = ", ".join(reason.value for reason in eligibility.reasons)
                raise IneligibleProjectionError(
                    f"assertion {assertion.assertion_id} is not eligible: {reasons}"
                )
            if assertion.state is not AssertionState.RESOLVED:
                raise ProjectionBundleError("only resolved assertions may be projected")
            if assertion.polarity is not Polarity.AFFIRMED:
                raise ProjectionBundleError("only affirmed assertions may be projected")
            by_predicate.setdefault(assertion.predicate, []).append(assertion)

        relation = self._one(by_predicate, SUBJECT_OF_EVENT_PREDICATE, required=True)
        event_type = self._one(by_predicate, EVENT_TYPE_PREDICATE, required=True)
        event_date = self._one(by_predicate, EVENT_DATE_PREDICATE, required=False)
        assert relation is not None and event_type is not None

        lineage = {(item.input_assertion_ids, item.review_decision_ids) for item in assertions}
        methods = {
            (
                item.method.family,
                item.method.name,
                item.method.version,
                item.method.run_id,
                item.method.code_revision,
            )
            for item in assertions
        }
        if len(lineage) != 1 or len(methods) != 1:
            raise ProjectionBundleError("resolved assertions must share exact lineage and method")
        if relation.value.kind is not ValueKind.ENTITY:
            raise ProjectionBundleError("subject relation must identify an event entity")
        event_id = relation.value.value
        if event_type.subject_id != event_id or event_type.value.kind is not ValueKind.ENTITY:
            raise ProjectionBundleError("event type must describe the related event entity")
        cac_class = _CAC_EVENT_CLASSES.get(event_type.value.value)
        if cac_class is None:
            raise ProjectionBundleError("event type has no approved CAC projection mapping")
        if event_date is not None and (
            event_date.subject_id != event_id or event_date.value.kind is not ValueKind.DATE
        ):
            raise ProjectionBundleError("event date must be a canonical date on the same event")

        graph = Graph()
        graph.bind("cac", CAC)
        graph.bind("cac-legal", CAC_LEGAL)
        graph.bind("cl", CL)
        graph.bind("dcterms", DCTERMS)
        graph.bind("prov", PROV)
        subject_iri = _iri("entity", relation.subject_id)
        event_iri = _iri("entity", event_id)
        type_iri = _iri("legal-event-type", event_type.value.value)
        graph.add((subject_iri, RDF.type, CL.AttributedLegalSubject))
        graph.add((event_iri, RDF.type, CL.LegalEventProjection))
        graph.add((event_iri, RDF.type, cac_class))
        graph.add((event_iri, CL.projectionProfile, Literal(PROFILE_VERSION)))
        graph.add((subject_iri, CL.subjectOfLegalEvent, event_iri))
        graph.add((event_iri, CL.legalEventType, type_iri))
        if event_date is not None:
            graph.add((event_iri, DCTERMS.date, Literal(event_date.value.value, datatype=XSD.date)))

        for assertion in assertions:
            assertion_iri = _iri("assertion", assertion.assertion_id)
            graph.add((event_iri, PROV.wasDerivedFrom, assertion_iri))
            graph.add((assertion_iri, RDF.type, CL.ResolvedProjectionStatement))
            graph.add((assertion_iri, CL.assertionState, Literal("resolved")))
            graph.add(
                (assertion_iri, CL.inputAssertionCount, Literal(len(assertion.input_assertion_ids)))
            )
            graph.add(
                (assertion_iri, CL.reviewDecisionCount, Literal(len(assertion.review_decision_ids)))
            )
            graph.add((assertion_iri, PROV.wasGeneratedBy, _iri("run", assertion.method.run_id)))

        payload = _canonical_ntriples(graph)
        return GraphProjection(
            canonical_ntriples=payload,
            sha256=hashlib.sha256(payload).hexdigest(),
            assertion_ids=tuple(sorted(item.assertion_id for item in assertions)),
        )

    @staticmethod
    def _one(
        by_predicate: dict[str, list[Assertion]], predicate: str, *, required: bool
    ) -> Assertion | None:
        values = by_predicate.get(predicate, [])
        if len(values) > 1 or (required and not values):
            expectation = "exactly one" if required else "at most one"
            raise ProjectionBundleError(f"projection requires {expectation} {predicate}")
        return values[0] if values else None
