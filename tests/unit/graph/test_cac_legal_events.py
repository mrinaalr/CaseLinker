from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from caselinker.assertions.models import (
    Assertion,
    AssertionValue,
    ReviewDecision,
    ReviewerRole,
    ReviewOutcome,
    ValueKind,
)
from caselinker.documents.models import SourceDocumentVersion
from caselinker.extraction import AttributedSubject, ExtractionRun, LegalEventExtractor
from caselinker.graph import (
    CacLegalEventProjector,
    GraphProjection,
    IneligibleProjectionError,
    ProjectionBundleError,
)
from caselinker.resolution import CandidateReview, LegalEventResolver, ResolutionRun

NOW = datetime(2026, 8, 15, 19, 0, tzinfo=UTC)
TEXT = "Example Defendant was charged on January 4, 2026."


class ReviewReader:
    def __init__(self, decisions: tuple[ReviewDecision, ...]) -> None:
        self.decisions = {item.assertion_id: item for item in decisions}

    def current_review_decision(self, assertion_id: str) -> ReviewDecision | None:
        return self.decisions.get(assertion_id)


def resolved_bundle() -> tuple[tuple[Assertion, ...], tuple[ReviewDecision, ...]]:
    version = SourceDocumentVersion.capture(
        version_id="docv_graph_fixture_001",
        document_id="doc_graph_fixture_001",
        content=TEXT.encode(),
        retrieved_at=NOW,
        published_at=None,
        recorded_at=NOW,
        mime_type="text/plain",
        http_status=200,
        http_etag=None,
        http_last_modified=None,
        parser_name="fixture_parser",
        parser_version="1.0.0",
        normalized_text=TEXT,
    )
    candidates = LegalEventExtractor().extract(
        subject=AttributedSubject("party_graph_fixture_001", ("Example Defendant",)),
        document_version=version,
        normalized_text=TEXT,
        run=ExtractionRun("run_graph_extract_001", "extract-revision", NOW),
    )
    decisions = tuple(
        ReviewDecision(
            decision_id=f"rvw_graph_fixture_{index:03d}",
            assertion_id=assertion.assertion_id,
            outcome=ReviewOutcome.ACCEPTED,
            reviewer_id="reviewer_graph_fixture_001",
            reviewer_role=ReviewerRole.DOMAIN_REVIEWER,
            rationale="Synthetic fixture accepted.",
            decided_at=NOW + timedelta(minutes=index),
            supersedes_decision_id=None,
        )
        for index, assertion in enumerate(candidates, start=1)
    )
    resolved = LegalEventResolver().resolve(
        reviewed_candidates=tuple(
            CandidateReview(assertion, decision)
            for assertion, decision in zip(candidates, decisions, strict=True)
        ),
        run=ResolutionRun("run_graph_resolve_001", "resolve-revision", NOW),
    )
    return resolved, decisions


def test_projection_is_order_independent_and_byte_reproducible() -> None:
    assertions, decisions = resolved_bundle()
    projector = CacLegalEventProjector()
    reviews = ReviewReader(decisions)

    first = projector.project(assertions=assertions, reviews=reviews)
    second = projector.project(assertions=tuple(reversed(assertions)), reviews=reviews)

    assert first.canonical_ntriples == second.canonical_ntriples
    assert first.sha256 == second.sha256
    assert first.assertion_ids == tuple(sorted(item.assertion_id for item in assertions))
    text = first.canonical_ntriples.decode()
    assert "cacontology.projectvic.org/legal-outcomes#CriminalCharge" in text
    assert '"2026-01-04"^^<http://www.w3.org/2001/XMLSchema#date>' in text
    assert text.count("ResolvedProjectionStatement") == 3


def test_projection_matches_pinned_golden_identity() -> None:
    assertions, decisions = resolved_bundle()
    expected = json.loads(
        Path("data/fixtures/vnext/graph/legal_event_projection_v1.golden.json").read_text()
    )

    projection = CacLegalEventProjector().project(
        assertions=assertions, reviews=ReviewReader(decisions)
    )

    assert projection.profile_version == expected["profile_version"]
    assert projection.sha256 == expected["sha256"]
    assert len(projection.canonical_ntriples.decode().splitlines()) == expected["triple_count"]
    assert list(projection.assertion_ids) == expected["assertion_ids"]


def test_superseded_review_blocks_projection() -> None:
    assertions, decisions = resolved_bundle()
    stale = replace(
        decisions[0],
        decision_id="rvw_graph_replacement_001",
        supersedes_decision_id=decisions[0].decision_id,
        decided_at=decisions[0].decided_at + timedelta(hours=1),
    )

    with pytest.raises(IneligibleProjectionError, match="review_not_current"):
        CacLegalEventProjector().project(
            assertions=assertions,
            reviews=ReviewReader((stale, *decisions[1:])),
        )


def test_mixed_resolution_lineage_is_rejected() -> None:
    assertions, decisions = resolved_bundle()
    mixed = (
        assertions[0],
        replace(
            assertions[1],
            method=assertions[1].method.__class__(
                family=assertions[1].method.family,
                name=assertions[1].method.name,
                version=assertions[1].method.version,
                run_id=assertions[1].method.run_id,
                code_revision="different-revision",
            ),
        ),
    )

    with pytest.raises(ProjectionBundleError, match="exact lineage"):
        CacLegalEventProjector().project(assertions=mixed, reviews=ReviewReader(decisions))


@pytest.mark.parametrize("size", [0, 1, 4])
def test_partial_or_oversized_bundle_is_rejected(size: int) -> None:
    assertions, decisions = resolved_bundle()

    with pytest.raises(ProjectionBundleError, match="two or three"):
        CacLegalEventProjector().project(
            assertions=(assertions * 2)[:size], reviews=ReviewReader(decisions)
        )


def test_projection_value_rejects_wrong_digest() -> None:
    with pytest.raises(ValueError, match="sha256"):
        GraphProjection(b"payload\n", "0" * 64, ("asrt_graph_001",))


def test_projection_value_rejects_duplicate_assertion_ids() -> None:
    payload = b"payload\n"
    import hashlib

    with pytest.raises(ValueError, match="must not repeat"):
        GraphProjection(
            payload,
            hashlib.sha256(payload).hexdigest(),
            ("asrt_graph_001", "asrt_graph_001"),
        )


def test_duplicate_projection_assertion_is_rejected() -> None:
    assertions, decisions = resolved_bundle()

    with pytest.raises(ProjectionBundleError, match="must not repeat"):
        CacLegalEventProjector().project(
            assertions=(assertions[0], assertions[0]), reviews=ReviewReader(decisions)
        )


@pytest.mark.parametrize(
    ("index", "changes", "message"),
    [
        (0, {"value": AssertionValue(ValueKind.TEXT, "not-an-event")}, "event entity"),
        (1, {"subject_id": "event_other_001"}, "related event"),
        (
            1,
            {"value": AssertionValue(ValueKind.ENTITY, "legal_event_unmapped")},
            "approved CAC",
        ),
        (2, {"subject_id": "event_other_001"}, "canonical date"),
    ],
)
def test_semantically_invalid_values_are_rejected(
    index: int, changes: dict[str, object], message: str
) -> None:
    assertions, decisions = resolved_bundle()
    altered = list(assertions)
    altered[index] = replace(altered[index], **changes)

    with pytest.raises(ProjectionBundleError, match=message):
        CacLegalEventProjector().project(assertions=tuple(altered), reviews=ReviewReader(decisions))


def test_duplicate_required_predicate_is_rejected() -> None:
    assertions, decisions = resolved_bundle()
    duplicate = replace(assertions[1], predicate=assertions[0].predicate)

    with pytest.raises(ProjectionBundleError, match="exactly one"):
        CacLegalEventProjector().project(
            assertions=(assertions[0], duplicate), reviews=ReviewReader(decisions)
        )
