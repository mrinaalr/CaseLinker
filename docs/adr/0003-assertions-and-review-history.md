# ADR 0003: Immutable assertions and append-only review history

**Status:** Accepted for the proposal branch

**Date:** 2026-08-15

## Context

The v2 case record stores extracted values in mutable dictionaries. That makes
it difficult to distinguish a source statement, deterministic extraction,
resolution decision, derived result, model inference, and researcher synthesis
after the value reaches an API or graph.

The vNext evidence core needs a representation that makes those differences
structural and preserves later review or correction without rewriting history.

## Decision

Introduce an immutable assertion kernel with these contracts:

- Assertion state is one of `observed`, `extracted`, `resolved`, `derived`,
  `inferred`, `authored`, `contested`, or `retracted`.
- Polarity is independent of state; negation and uncertainty cannot be encoded
  as absence.
- Values are typed and canonicalized as entity IDs, bounded text, integers,
  booleans, dates, or absolute IRIs.
- Exact evidence includes a document-version ID, the full normalized-text hash,
  offsets, the selected-span hash, and an optional one-based page number.
- If exact offsets are unavailable, a typed reason is mandatory. Missing span
  data can never look like an exact citation.
- Source assertions require document evidence. Resolution, derivation,
  contestation, and retraction require explicit input assertion IDs.
- Retraction is a new assertion that identifies and depends on its target. It
  does not mutate or delete the historical assertion.
- Method family, method name/version, run ID, and code revision travel with the
  assertion.
- Quantified confidence uses integer millionths and requires a calibration ID.
  Unquantified confidence is represented as unquantified, not as an invented
  probability.
- Review acceptance or rejection is a separate immutable `ReviewDecision`.
  There is no mutable `accepted` flag on an assertion.

## State and evidence requirements

| State | Required direct evidence | Required assertion lineage |
|---|---:|---:|
| Observed | Yes | No |
| Extracted | Yes | No |
| Resolved | Optional | Yes |
| Derived | Optional | Yes |
| Inferred | Evidence or lineage | Evidence or lineage |
| Authored | Evidence or lineage | Evidence or lineage |
| Contested | Optional | Yes |
| Retracted | Optional | Yes, including target |

These requirements establish minimum provenance, not publication eligibility.
A later policy service decides which state/review combinations may contribute
to a claim.

## Consequences

Interfaces and semantic exports can no longer collapse inferred values into
observations without explicitly violating a typed contract. Corrections remain
auditable. Evidence-span verification can detect both changed source text and
changed offsets.

The kernel is deliberately storage-independent. The repository port defines
append-only operations, but the SQLite schema and adapter are a separate change
so the domain contract can be reviewed before persistence freezes it.

## Security and privacy

Evidence references store hashes and offsets, not quoted source text. Assertion
text values are bounded to prevent the assertion ledger from becoming a second
raw-narrative store. Reviewer IDs are opaque internal identifiers. Review
rationales are bounded and must not contain control characters, but policy and
interface layers must still prevent sensitive narrative from being entered.

## Compatibility, recovery, and rollback

This change does not alter a database, API, graph, or v2 extraction output.
Rollback removes the additive domain module. No legacy value is automatically
promoted to an observed or accepted assertion.

## Limitations

- Current confidence fields record a calibrated scalar for one named
  dimension; multidimensional uncertainty can be added without changing value
  or evidence identity.
- Temporal scope currently uses inclusive dates rather than uncertain or
  interval-valued time.
- Publication policy, review-chain enforcement, persistence, and graph mapping
  remain subsequent layers.
