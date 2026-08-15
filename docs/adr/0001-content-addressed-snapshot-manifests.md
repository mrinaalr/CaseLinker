# ADR 0001: Content-addressed snapshot manifests

**Status:** Accepted for the proposal branch

**Date:** 2026-08-15

## Context

CaseLinker's current analytical outputs can name corpus size and implementation
version, but they do not bind every result to the exact source versions,
accepted assertions, code, extraction rules, ontology, shapes, query,
parameters, model inputs, and outputs that produced it. A result can therefore
remain plausible while its reproducibility boundary has drifted.

The vNext charter requires snapshot-scoped claims and byte-for-byte
deterministic outputs. The first implementation must be useful before a new
database schema, API, or UI exists.

## Decision

Introduce a versioned JSON snapshot manifest with these properties:

- Every required component kind appears exactly once.
- A component is either `included` with explicit repository-relative inputs or
  `not_applicable` with a non-empty reason.
- Files and components are SHA-256 content-addressed.
- The complete canonical manifest payload is SHA-256 content-addressed.
- Directories expand recursively into sorted file records.
- Absolute paths, traversal, non-normalized paths, symlinks, missing inputs,
  duplicate component kinds, and unknown specification fields fail closed.
- `recorded_at` is supplied as UTC data rather than generated at build time, so
  rebuilding the same specification and files is deterministic.
- Writes are atomic. Verification re-hashes both the manifest and every
  referenced file.

The operational implementation is a typed, dependency-free module under
`src/caselinker/snapshots`. A small script adapter makes it runnable without
requiring the legacy application or database to boot.

## Consequences

Every future claim card, Evidence Pack, graph release, or Claim CI result can
bind to one immutable manifest hash. Silent omissions become visible review
decisions. A changed source, assertion set, query, or output invalidates
verification.

The manifest establishes integrity and identity; it does not establish that an
input is scientifically correct, authorized for publication, free of sensitive
content, or semantically conformant. Those remain separate review, policy, and
SHACL gates.

## Compatibility and migration

This capability is additive. It does not modify the v2 database, APIs, corpus,
or generated graphs. Existing analytical artifacts can be adopted
incrementally by writing a specification that names their actual inputs.

## Security and privacy

The manifest stores paths, sizes, and hashes—not source text. Specifications
must still avoid filenames that expose personal information. Symlinks are
rejected to prevent a repository-local specification from hashing files outside
the declared root.

## Rollback

Remove the snapshot module, schema, example fixture, and documentation. No
persistent state or existing artifact format depends on this decision yet.
