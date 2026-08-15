# Assertion persistence

The SQLite assertion adapter is a reference implementation of the domain
repository port. It exists to make evidence and review invariants executable
before integration with the legacy extraction pipeline.

## Migration order

Apply the additive migrations in order:

1. `migrations/sqlite/0001_source_documents.sql`
2. `migrations/sqlite/0002_assertion_ledger.sql`

Both migrations are idempotent. Back up any persistent database first. Neither
migration modifies or populates the legacy `cases` table.

## Write ordering

1. Persist the immutable source document.
2. Persist the immutable retrieved document version and normalized-text hash.
3. Construct evidence spans against exactly that normalized text.
4. Insert the assertion. The adapter verifies document and assertion lineage,
   then atomically writes the assertion and ordered edges.
5. Append a review decision. A later decision must supersede the current head
   and have a strictly later UTC timestamp.

Do not interpret `InsertOutcome.EXISTING` as a merge. It means the complete
immutable object was already identical. Any difference raises a conflict.

## Verification

```bash
uv run --locked pytest \
  tests/unit/assertions \
  tests/integration/assertions
```

The integration suite uses the real migrations and tests exact retry,
conflicting identity, missing lineage, evidence-basis mismatch, ordered derived
inputs, migration idempotency, legacy-table preservation, review forks,
cross-assertion supersession, monotonic review time, and direct mutation or
deletion attempts.

## Operational boundary

This adapter is not wired to public APIs or the existing ingestion command.
There is no silent dual write. The next extractor adapter will emit a
policy-safe predicate subset into this ledger and compare its outputs against
adjudicated golden fixtures before any broader backfill.
