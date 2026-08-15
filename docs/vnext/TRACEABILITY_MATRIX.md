# vNext proposal traceability matrix

The authoritative machine-readable index is
[`traceability.v1.json`](traceability.v1.json). Its canonical SHA-256 is stored
inside the file after excluding the digest field itself. The quality checker rejects
an invalid digest, missing or unsafe paths, duplicate commits, noncontiguous
milestones, or incomplete ADR and SQLite-migration coverage.

| Milestone | Review boundary | Decisions | Primary implementation | Primary evidence |
|---|---|---|---|---|
| M01 | Governance and engineering baseline | ADR 0000 | CI, repository checker, locked environment | quality and smoke tests |
| M02 | Immutable records and provenance | ADRs 0001-0004 | snapshots, documents, assertion ledger | unit, integration, and CLI contract tests |
| M03 | Evidence-bound extraction | ADRs 0005-0006 | platform mentions, legal events, atomic extraction service | adversarial extraction fixtures and integration tests |
| M04 | Human review and canonical resolution | ADR 0007 | review lineage, resolver, live eligibility policy | stale-review, mixed-bundle, and publication-policy tests |
| M05 | CAC graph projection | ADR 0008 | deterministic projection and pinned SHACL | permutation, golden digest, and SHACL failure tests |
| M06 | Research claims and regression control | ADRs 0009-0010 | cohorts, Claim Cards, Evidence Packs, Claim CI | exact-member, unit, digest, and expectation tests |
| M07 | Operational adapter | ADR 0011 | repository-bound claim pipeline CLI | CLI contract and failure-exit tests |

## Cross-boundary invariants

| Invariant | Established | Rechecked downstream |
|---|---|---|
| Source versions are immutable and content-addressed | M02 | M03, M06, M07 |
| Assertions retain exact evidence and method provenance | M02 | M03-M05 |
| Reported claims remain distinct from canonical resolved relations | M03 | M04-M06 |
| Review decisions are append-only and currentness is evaluated live | M04 | M05 |
| Research eligibility is not disclosure authorization | M04 | M05-M07 |
| Projection bytes and validation shapes are pinned | M05 | M06-M07 |
| The counted unit and complete numerator/denominator membership are explicit | M06 | M07 |
| CI expectations are reviewed inputs, never automatically blessed | M06 | M07 |
| Repository paths cannot escape or traverse symlinks | M07 | CLI contract tests |

## Evidence interpretation

Tests establish conformance to these authored contracts. They do not independently
validate source accuracy, reviewer judgment, ontology completeness, population-level
inference, disclosure safety, or fitness for a particular deployment. Those remain
explicit maintainer and governance decisions.
