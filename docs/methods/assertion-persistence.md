# Assertion persistence

The SQLite assertion adapter is a reference implementation of the domain
repository port. It exists to make evidence and review invariants executable
before integration with the legacy extraction pipeline.

## Migration order

Apply the additive migrations in order:

1. `migrations/sqlite/0001_source_documents.sql`
2. `migrations/sqlite/0002_assertion_ledger.sql`
3. `migrations/sqlite/0003_assertion_review_lineage.sql`

All migrations are idempotent. Back up any persistent database first. None
modifies or populates the legacy `cases` table.

## Write ordering

1. Persist the immutable source document.
2. Persist the immutable retrieved document version and normalized-text hash.
3. Construct evidence spans against exactly that normalized text.
4. Insert the assertion. The adapter verifies document and assertion lineage,
   then atomically writes the assertion and ordered edges.
5. Append a review decision. A later decision must supersede the current head
   and have a strictly later UTC timestamp.
6. When resolution is review-authorized, insert the resolved assertion with
   ordered candidate inputs and ordered review-decision inputs. Each decision
   must govern one of the assertion inputs.

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
inputs, review-decision lineage, migration idempotency, legacy-table
preservation, review forks, cross-assertion supersession, monotonic review time,
and direct mutation or deletion attempts.

## Operational boundary

This adapter is not wired to public APIs or the existing ingestion command.
There is no silent dual write. Proposal extractors and the first reviewed
legal-event resolver use it behind typed services; no broader corpus backfill
or public-response integration occurs implicitly.
