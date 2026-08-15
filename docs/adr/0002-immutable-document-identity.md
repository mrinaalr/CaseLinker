# ADR 0002: Immutable document identity and retrieved versions

**Status:** Accepted for the proposal branch

**Date:** 2026-08-15

## Context

The inherited `cases` table combines a research case, source label, source URL,
raw ingestion batch, extracted fields, and replacement-oriented update
behavior. That representation was effective for rapid corpus growth, but it
cannot prove which retrieved bytes support an assertion or distinguish an
updated web page from an overwritten record.

Assertion-level evidence spans require stable document identity and immutable
versions first. This must be introduced without modifying production tables or
pretending that every legacy row can already be traced to authoritative source
bytes.

## Decision

Add a storage-independent domain and repository contract with two units:

- `SourceDocument` is the stable identity of one public document. Its opaque ID
  does not encode a publisher, URL, date, case, or mutable label. The identity
  records the source connector's canonicalization version rather than implying
  that URL normalization is universal.
- `SourceDocumentVersion` records one successful retrieval, its byte hash,
  byte length, content-addressed storage key, retrieval/publication/recording
  times, constrained HTTP metadata, parser identity, and optional normalized
  text hash.

The first executable adapter is SQLite and its migration is additive:

- exact insertion retries return `existing`;
- reuse of an ID with different values fails as an immutable conflict;
- one canonical URL cannot silently identify two documents;
- a version cannot exist before its document identity;
- update and delete triggers enforce append-only behavior below the
  application layer;
- content keys are derived as `sha256/<prefix>/<digest>` and checked by the
  database;
- timestamps serialize as timezone-aware UTC with a canonical `Z` suffix;
- arbitrary HTTP headers and source text are not stored in these metadata
  tables.

## Threats and controls

| Threat | Control |
|---|---|
| Existing row is overwritten by a retry | Exact retry is idempotent; differing values fail |
| File bytes move or are substituted | Digest-derived storage key plus recorded byte hash |
| Source URL exposes credentials | Domain rejects userinfo and sensitive query parameters |
| Local-time ambiguity changes ordering | UTC-aware values and canonical serialization |
| Deletion removes assertion evidence | Database triggers reject update and delete |
| Legacy data is treated as verified provenance | No automatic backfill in this migration |

## Compatibility and migration

The migration does not alter `cases` or any v2 API. It creates new tables and
indexes only. A later, separately reviewed backfill must classify legacy rows
as grounded, partially grounded, or quarantined; a `source_url` string alone is
not sufficient evidence of the retrieved bytes.

SQLite is the reference adapter used to falsify domain and migration behavior.
A production PostgreSQL migration and adapter must reproduce these constraints
and pass equivalent integration tests before deployment.

## Recovery and rollback

The forward migration is idempotent. Before production adoption, recovery is a
database backup/restore operation, not a destructive down migration. At the
current proposal stage, rollback consists of ceasing writes to the additive
tables and reverting this commit; existing v2 behavior remains unchanged.

## Limitations

- This change records metadata and content addresses; it does not implement an
  object-storage adapter or commit source bytes to Git.
- It does not yet model retrieval attempts, redirects, failed acquisitions,
  robots/terms review, or parser derivatives as separate units.
- It does not establish assertion spans, case resolution, review decisions, or
  publication authorization.
