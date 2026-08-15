# Document identity and versioning

The document layer separates the identity of a public source document from the
immutable bytes observed during a retrieval. It is intentionally independent
of FastAPI, the legacy storage classes, and any object-storage provider.
Canonical URLs must be produced by a versioned source-specific canonicalizer;
the document record preserves that canonicalization version.

## Domain contract

`SourceDocumentVersion.capture(...)` derives the byte length, SHA-256 digest,
normalized-text digest, and content-addressed storage key from supplied bytes.
Callers do not provide those values independently.

The repository contract distinguishes:

- `created`: the immutable record was inserted;
- `existing`: an exact retry found the same immutable record;
- `ImmutableConflictError`: an ID or canonical URL was reused inconsistently;
- `MissingDocumentError`: a version arrived before its document identity.

## Apply the SQLite reference migration

The migration is forward-only and idempotent:

```python
import sqlite3
from pathlib import Path

from caselinker.documents.sqlite_repository import apply_migration

connection = sqlite3.connect("caselinker.db")
sql = Path("migrations/sqlite/0001_source_documents.sql").read_text(encoding="utf-8")
apply_migration(connection, sql)
```

Back up a persistent database before applying any proposal migration. The
migration does not populate records or alter legacy tables.

## Verification

```bash
uv run --locked pytest tests/unit/documents tests/integration/documents
```

The integration suite applies the real migration twice, exercises exact retry
and conflict behavior, round-trips every version field, checks deterministic
ordering, verifies foreign keys and content-address constraints, and attempts
forbidden updates and deletes.

## Operational limitations

Do not deploy the SQLite migration to PostgreSQL. Production adoption requires
a dialect-specific migration and equivalent tests against the supported
PostgreSQL version. This layer also assumes the acquisition service writes and
verifies bytes at the derived storage key before publishing a version record;
that object-storage transaction is not implemented yet.
