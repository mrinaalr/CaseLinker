# ADR 0011: Repository-bound claim pipeline CLI

- **Status:** Accepted for the proposal branch
- **Date:** 2026-08-15
- **Decision owners:** Proposal contributors; upstream retains operational authority

## Outcome

Provide one reproducible operational path from repository-pinned snapshot artifacts to
an Evidence Pack and Claim CI exit status, without requiring callers to assemble domain
objects manually.

## Invariant

The CLI is an adapter over existing scientific gates, not a shortcut around them. It
must verify the snapshot and all bound files, re-run SHACL, preserve exact units and
memberships, and regenerate claim artifacts before Claim CI. It never pins or approves
an expectation automatically.

## Decision

The versioned pipeline specification references one snapshot manifest, SHACL shapes,
query file, and one or more graph projections using normalized repository-relative
POSIX paths. The pipeline:

1. rejects unknown specification and query fields;
2. forbids absolute paths, parent traversal, symlinks, duplicates, and non-files;
3. verifies the snapshot manifest and every referenced component file;
4. requires shapes, query, and projection digests to appear in their respective
   snapshot component inventories;
5. requires projection bytes to already be canonical N-Triples with resolved-assertion
   provenance;
6. re-runs the pinned SHACL profile rather than trusting a stored pass flag;
7. regenerates the cohort, Claim Card, and canonical Evidence Pack atomically;
8. returns exit `0` for success, `1` for semantic Claim CI drift, and `2` for invalid
   inputs or operational failure.

`build` writes the exact Evidence Pack bytes atomically. `check` regenerates the same
pipeline and compares it with a separately reviewed, content-addressed expectation.

## Threats and controls

| Threat | Control |
|---|---|
| Path traversal reads unreviewed files | Repository-relative normalized paths and root containment |
| A symlink swaps a governed input | Symlink traversal rejected for specs, expectations, and component paths |
| Valid RDF from another snapshot enters analysis | Projection digest must be in snapshot outputs |
| A query or shape changes outside the snapshot | Exact file digest must be in its snapshot component |
| Stored validation is stale | SHACL is executed during every run |
| A partial output replaces the destination | Temp-file write, fsync, and atomic replace |
| CI treats invalid input as ordinary claim drift | Separate exit code `2` from semantic drift code `1` |

## Acceptance evidence

- A contract fixture builds byte-identical Evidence Pack output and passes Claim CI.
- A different but valid expectation returns exit `1`.
- Invalid specs, stale manifests, path escapes, unbound inputs, duplicate projections,
  malformed expectations, invalid RDF, noncanonical RDF, and missing provenance return
  typed failures.

## Compatibility and migration

This adapter is additive and does not expose an HTTP endpoint. Existing Python APIs and
legacy scripts are unchanged. No database migration is required.

## Recovery and rollback

Remove the new CI command or revert the adapter. Generated Evidence Packs are disposable;
all authoritative documents, assertions, reviews, snapshots, projections, expectations,
and prior reports remain unchanged.

## Limitations

- Expectation approval and signing remain human/governance processes outside this CLI.
- The CLI currently accepts legal-event composition queries only.
- Atomic replacement protects local file integrity but is not a distributed transaction.
- A passing command is not disclosure authorization or release approval.
