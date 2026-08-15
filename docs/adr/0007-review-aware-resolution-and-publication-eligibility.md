# ADR 0007: Preserve review lineage through resolution and evaluate publication eligibility live

- **Status:** Accepted for the proposal branch
- **Date:** 2026-08-15
- **Decision owners:** Proposal contributors; upstream adoption remains a maintainer decision

## Context

ADR 0003 separated review decisions from assertions and required resolved
assertions to cite their candidate inputs. That is necessary but insufficient:
without links to the exact review decisions, a canonical value cannot prove who
authorized its resolution or which version of an append-only review chain was
current at the time.

Review acceptance, semantic resolution, publication eligibility, disclosure
authorization, and access control answer different questions. Collapsing them
into one `accepted` flag would make later corrections unauditable and could
publish stale determinations.

## Decision

Add migration `0003_assertion_review_lineage.sql` with an immutable
`assertion_review_inputs` relation. A review edge is valid only when its decision
governs one of the resolved assertion's input assertions. Domain and repository
contracts reject duplicate, malformed, missing, and cross-input decision
lineage.

The first `LegalEventResolver` accepts one coherent candidate bundle containing:

- exactly one reported-subject relation;
- exactly one reported procedural type;
- at most one directly bound reported date.

Every candidate must be `extracted`, affirmed, from one extraction execution,
and governed by a current `accepted` review. Subject and type must share the
same exact event span. A date must identify the same event and cite that event
span plus its own exact date span. The resolver rejects partial, duplicated,
mixed-run, unknown-type, rejected, and cross-event bundles.

Resolution emits new `resolved` assertions with canonical non-reported
predicates. It never mutates or relabels candidates. Every output cites the
complete ordered candidate bundle and complete ordered review-decision bundle.
The whole canonical bundle is stored atomically.

`ResearchPublicationEligibilityPolicy` is a separate live read decision. A
resolved assertion is eligible only while every cited decision remains the
current accepted decision for its corresponding candidate. Superseding a review
does not erase the historical resolution; it makes that resolution presently
ineligible.

## Distinct decisions

| Decision | Meaning | Persistent? |
|---|---|---:|
| Review | A reviewer adjudicated one candidate | Append-only decision |
| Resolution | Accepted candidates form one canonical relation | Append-only assertion |
| Research publication eligibility | Current evidence/review state passes the research gate | Recomputed live |
| Disclosure authorization | Fields may be exposed to this audience and purpose | Separate policy, not implemented here |
| Access control | This principal may perform this operation | Separate security boundary |

Publication eligibility is necessary but not sufficient for disclosure. It is
not an authorization system and must never be used as one.

## Threats and controls

| Threat | Control |
|---|---|
| Resolution cannot identify its authorizing reviews | Immutable review-decision input edges |
| Accepted candidates from different events are spliced | Event identity and shared-span coherence checks |
| A partial event graph becomes canonical | Required subject/type cardinality and atomic batch write |
| Request ordering changes canonical identity | Semantic ordering before deterministic ID construction |
| Rejected or needs-changes candidate enters resolution | Current accepted review required for every input |
| Later rejection leaves stale output publishable | Eligibility compares cited decision with live review head |
| Research gate becomes access control | Narrow policy name, result type, and explicit non-authorization contract |

## Compatibility and migration

Migration 0003 is additive and requires migrations 0001 and 0002. Existing
assertions have empty review-decision lineage and retain their identity. No
legacy case table, API, graph, or extraction output changes. Old proposal
databases must apply 0003 before using the updated assertion repository.

## Recovery and rollback

The migration is idempotent. Production adoption requires backup and restore
testing. There is no destructive down migration: stop resolution writes and
revert application callers while preserving the review lineage for audit. The
live eligibility evaluator can be disabled without deleting assertions.

## Limitations

- Current-review checks and resolved writes are tested with the SQLite
  reference adapter. PostgreSQL adoption requires transaction-isolation and
  concurrency analysis.
- Eligibility is evaluated per assertion. Snapshot assembly must pin the
  eligible assertion set and all review heads before generating an artifact.
- This slice produces canonical internal predicates, not CAC RDF. CAC mapping,
  SHACL validation, disclosure shaping, and Evidence Pack generation remain
  separate boundaries.
