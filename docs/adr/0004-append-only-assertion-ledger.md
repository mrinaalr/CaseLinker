# ADR 0004: Append-only assertion ledger persistence

**Status:** Accepted for the proposal branch

**Date:** 2026-08-15

## Context

ADR 0003 established immutable assertion, evidence, lineage, and review domain
contracts. Those guarantees are incomplete if persistence can update a fact,
detach its source, fork a review history, or accept offsets created against a
different normalized document version.

The first adapter must prove the complete storage behavior without changing the
legacy `cases` table or claiming production PostgreSQL readiness.

## Decision

Add an idempotent SQLite migration and repository adapter with four append-only
tables:

- `assertions` stores typed value, epistemic state, polarity, method,
  confidence, temporal scope, supersession, and creation identity;
- `assertion_evidence` stores ordered document-version anchors or typed
  span-unavailable reasons;
- `assertion_inputs` stores ordered assertion-to-assertion lineage;
- `review_decisions` stores the ordered append-only review chain.

One repository transaction inserts an assertion and all of its evidence and
input edges. Before insertion it verifies that:

- every referenced document version exists;
- every evidence basis hash equals that version's normalized-text hash;
- every input or superseded assertion exists;
- an exact retry is identical, otherwise ID reuse is a conflict.

Review history is linear at both service and database boundaries:

- one root review is allowed per assertion;
- each review decision can have at most one successor;
- a successor must reference a decision for the same assertion;
- decision time must strictly advance;
- exact retries are idempotent and conflicting ID reuse fails.

Database triggers reject update and delete operations on all four tables.
Foreign keys use `RESTRICT`; historical evidence cannot disappear through a
cascade.

## Threats and controls

| Threat | Control |
|---|---|
| Assertion saved without all evidence edges | Single transaction |
| Stale offsets attached to changed parsed text | Basis hash compared with document version |
| Derived assertion cites nonexistent inputs | Foreign keys plus repository preflight |
| Concurrent reviewers fork history | Partial unique indexes and validation trigger |
| Review is backdated ahead of current state | Monotonic-time checks in service and database |
| Accepted fact or citation is edited in place | Update/delete denial triggers |
| Retry creates duplicate facts | Exact immutable equality returns `existing` |

## Compatibility and migration

Migration `0002_assertion_ledger.sql` requires the additive document tables from
migration `0001_source_documents.sql`. It does not alter or backfill legacy
tables. Existing case dictionaries, API routes, and graph generators remain
unchanged.

Legacy fields must later pass through extractor adapters and review policy.
They are not accepted assertions merely because they currently appear in a
case record.

## Recovery and rollback

The migration is idempotent. Production adoption requires a backup and tested
restore. There is intentionally no destructive down migration: rollback means
stopping proposal writes and reverting application use while preserving the
ledger for diagnosis. At the current proposal stage, the tables are additive
and unused by v2 behavior.

## Limitations

- SQLite is the tested reference adapter, not the production deployment
  target. PostgreSQL requires an equivalent migration, locking analysis, and
  concurrency tests.
- The repository compares basis hashes but does not load source text from
  object storage to recompute the selected span; acquisition and evidence-pack
  verification will perform that end-to-end check.
- Publication eligibility and disclosure policy are separate services. A
  current `accepted` review does not by itself authorize public output.
