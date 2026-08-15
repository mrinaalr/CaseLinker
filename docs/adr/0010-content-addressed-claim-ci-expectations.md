# ADR 0010: Content-addressed Claim CI expectations

- **Status:** Accepted for the proposal branch
- **Date:** 2026-08-15
- **Decision owners:** Proposal contributors; upstream retains claim-approval authority

## Outcome

Make an explicitly reviewed research claim executable as a regression contract. A
regenerated claim passes only when its scientific scope, membership, inputs,
limitations, and content identities still match the pinned expectation.

## Invariant

Claim CI detects change; it does not decide whether a changed claim is scientifically
acceptable. A contributor must never update an expectation merely to make CI green.
Review and a new content identity are required. Passing Claim CI is neither disclosure
authorization nor publication approval.

## Decision

Pin these dimensions in a versioned, content-addressed expectation:

- snapshot manifest digest;
- query digest and analytical unit;
- numerator and denominator;
- separate numerator and denominator membership digests;
- projection-set digest and SHACL-shapes digest;
- mandatory-limitations digest;
- claim-card identity and Evidence Pack identity.

The evaluator also independently recomputes the claim content identity and rebuilds the
Evidence Pack from the observed claim. Findings use a closed drift taxonomy so CI and
review interfaces can distinguish numerical drift from membership or provenance drift.

## Threats and controls

| Threat | Control |
|---|---|
| A denominator changes while the count stays equal | Membership digest fails independently of counts |
| A snapshot or query is silently replaced | Dedicated snapshot and query findings |
| Limitations disappear but numbers stay equal | Limitations are hashed into expectation and claim identity |
| An old pack is paired with a new claim | Pack is deterministically rebuilt and exact bytes are compared |
| Expected values are edited under an old approval ID | Expectation ID is the canonical content digest |
| CI is treated as scientific or disclosure approval | Governance language keeps detection separate from approval |

## Acceptance evidence

- The pinned fixture passes with no findings and matches a golden expectation identity.
- Snapshot, query, counts, numerator membership, denominator membership, projections,
  shapes, limitations, claim identity, and Evidence Pack drift are detected.
- Invalid expectation identities, digests, namespaces, units, ratios, and duplicate
  report findings fail at construction.
- The full reviewed-evidence integration path ends in a passing Claim CI report.

## Compatibility and migration

Claim CI is additive. Existing claims and packs remain valid artifacts but are not
regression-protected until an expectation is deliberately reviewed and pinned. There is
no database migration and no change to legacy tests or dashboards.

## Recovery and rollback

Disable the Claim CI job or revert this evaluator; do not rewrite generated evidence to
fit an old expectation. Preserve both old and proposed expectations during review so
the semantic difference remains auditable.

## Limitations

- Claim CI proves exact agreement with a reviewed contract, not truth, representativeness,
  statistical significance, fairness, privacy, or permission to publish.
- Expectation approval workflow and reviewer signatures remain future work.
- The first contract supports the `legal_event` unit only.
