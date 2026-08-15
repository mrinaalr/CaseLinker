# Assertion semantics

The assertion kernel makes provenance and epistemic state explicit before data
reaches storage, APIs, graphs, or visualizations.

## Exact evidence

Build a span from the exact normalized text associated with a document version:

```python
from caselinker.assertions.models import EvidenceReference

evidence = EvidenceReference.from_text(
    document_version_id="docv_example_001",
    normalized_text=normalized_text,
    start_char=start,
    end_char=end,
    page_number=2,
)
assert evidence.matches(normalized_text)
```

`matches` verifies both the complete normalized-text hash and the selected-span
hash. A coincidentally identical phrase in changed text therefore does not
validate against stale offsets.

When offsets genuinely cannot be produced, construct an evidence reference
with one `SpanUnavailableReason`. Do not use empty strings, zero offsets, or a
generic `None` to imply provenance.

## Review is not mutation

An extractor emits an `extracted` assertion. A reviewer emits a separate
`ReviewDecision`. Acceptance does not change the assertion to `observed` or
erase its extraction method. If resolution creates a canonical value, it emits
a new `resolved` assertion linked to its input assertions.

Likewise, correction emits a superseding or retraction assertion. Historical
records remain addressable so a snapshot can reproduce what was accepted at a
particular boundary.

## Confidence

Floating-point confidence is not stored. Quantified scores are integer
millionths from `0` through `1_000_000` and require a stable calibration ID.
Deterministic or uncalibrated methods may record an unquantified confidence
dimension; they must not manufacture a probability for display convenience.

## Current boundary

The domain models, SQLite migration, and repository adapter are implemented and
strictly tested. They are not yet wired into legacy extraction or public
responses. See `assertion-persistence.md` for write ordering and operational
limitations.
