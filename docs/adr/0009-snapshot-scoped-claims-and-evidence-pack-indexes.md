# ADR 0009: Snapshot-scoped claims and Evidence Pack indexes

- **Status:** Accepted for the proposal branch
- **Date:** 2026-08-15
- **Decision owners:** Proposal contributors; upstream retains publication authority

## Outcome

Produce a reproducible numerical research claim from SHACL-conforming legal-event
projections while making the counted unit, complete denominator, snapshot identity,
query, inputs, and limitations inseparable from the claim.

## Invariant

A count cannot silently change units. A claim over a selected public-enforcement corpus
cannot be presented as population prevalence, platform risk, causal effect, or a count
of people, cases, or documents. Research eligibility is not disclosure authorization.

## Decision

1. The first cohort analyzer supports exactly one unit: a distinct eligible
   `legal_event` resource.
2. The denominator is every distinct validated legal-event projection supplied for the
   bound snapshot. The numerator is the allowlisted event type selected by the query.
3. Results preserve the complete, sorted numerator and denominator membership lists.
   Duplicate event identifiers are errors rather than silently deduplicated counts.
4. Every projection must have a conforming SHACL result bound to its exact digest, and
   every result must use the same shapes digest. Every projection digest must also be
   present in the bound snapshot's output inventory.
5. No floating-point percentage is stored. Numerator and denominator are the canonical
   result; presentation layers may derive a labeled display value without changing the
   claim.
6. Claim text is generated from the typed result, not accepted as arbitrary prose.
   Mandatory limitations are part of the content-addressed claim identity.
7. An Evidence Pack is a canonical JSON audit index binding the claim, snapshot
   manifest, query, projections, and shapes. It intentionally excludes source text,
   personal display labels, and disclosure authorization.

## Threats and controls

| Threat | Control |
|---|---|
| Case counts are confused with event counts | One explicit `legal_event` unit and full membership lists |
| A selected corpus is described as prevalence | Mandatory limitations embedded in every claim identity |
| Invalid graphs enter a denominator | Exact projection/SHACL digest binding and conformance requirement |
| An artifact from another run is inserted | Projection digest must appear in the bound snapshot outputs |
| Multiple shape profiles make a cohort incomparable | One shapes digest required across the cohort |
| Duplicate graph inputs inflate a count | Duplicate event resources are rejected |
| A claim changes without its identifier changing | Query, counts, members, inputs, and limitations are content-addressed |
| An audit package leaks source text or names | Evidence Pack is a digest index with explicit exclusions |

## Acceptance evidence

- Input ordering cannot change result membership, claim identity, or Evidence Pack
  bytes.
- Golden identifiers pin a two-event, one-match fixture.
- Zero-match results remain valid when the denominator is nonzero.
- Zero denominators, inconsistent counts, duplicate units, mixed shapes, foreign IRIs,
  unknown event types, and mismatched validation reports fail closed.
- An end-to-end test runs reviewed assertions through projection, SHACL, analysis,
  claim generation, and Evidence Pack assembly.

## Compatibility and migration

This is an additive vNext package. It does not call, replace, or reinterpret the legacy
facet tree, dashboards, graph cache, or research-question scripts. No database migration
is required. Existing snapshot manifests remain the authority for immutable component
files.

## Recovery and rollback

Disable analysis callers and discard generated claim/Evidence Pack artifacts. All
documents, assertions, reviews, resolutions, projections, and snapshot manifests remain
unchanged and can be reprocessed by a corrected analyzer.

## Limitations

- The pack is an index, not a self-contained archive; referenced content remains under
  the snapshot manifest and applicable access controls.
- File-level verification of the manifest must occur before analysis.
- The first query supports event-type composition only. Statistical inference,
  comparison groups, case-level joins, temporal rates, and causal claims are out of
  scope.
- Claim generation does not grant permission to disclose or publish an artifact.
