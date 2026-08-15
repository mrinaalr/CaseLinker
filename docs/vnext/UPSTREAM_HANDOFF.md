# CaseLinker vNext proposal: upstream handoff

## Decision summary

This branch is an implementation proposal for selective upstream adoption. It is
not an official CaseLinker release, does not reserve `v3.0.0`, and does not ask a
maintainer to accept one indivisible change. Upstream retains complete authority
over architecture, naming, merge order, release timing, and publication.

The proposal adds a narrow, auditable research path:

```text
immutable source version
  -> evidence-bound candidate assertions
  -> append-only human review
  -> review-aware resolution
  -> policy-gated CAC RDF projection
  -> pinned SHACL validation
  -> snapshot-scoped cohort and Claim Card
  -> Evidence Pack
  -> Claim CI
```

The exact upstream baseline is
`9da0a4ff8b45df03fed073a9af5c00d22aab0d9d`. The reviewed implementation
checkpoint is `802fb7d244e3751b42dbb20cc8d258e1b71adbc7`. Every implementation
milestone, commit, ADR, representative test, and SQLite migration is indexed in
[`traceability.v1.json`](traceability.v1.json) and validated in CI.

## What this proposal contributes

- Content-addressed snapshot manifests with deterministic build and verification.
- Immutable document identity and an append-only assertion/review ledger.
- Conservative platform-mention and reported-legal-event extraction with exact
  evidence spans, explicit subjects, and allegation-preserving predicates.
- Atomic persistence of candidate batches and immutable review lineage.
- Canonical legal-event resolution that fails closed on mixed, stale, partial, or
  incoherent evidence.
- A live research-eligibility gate that invalidates resolutions after a governing
  review changes.
- Deterministic CAC-aligned RDF, local pinned SHACL, and canonical digests.
- Explicit-unit cohort analysis, generated Claim Cards, canonical Evidence Packs,
  content-addressed expectations, and Claim CI.
- One repository-bound CLI that re-verifies the entire artifact chain instead of
  trusting previously stored pass flags.

## What it deliberately does not do

- It does not grant disclosure authorization or implement access control.
- It does not claim that public-source material is risk-free to republish.
- It does not infer guilt, identity, causation, prevalence, or platform risk.
- It does not replace the legacy CaseLinker database, graph, API, UI, or pipeline.
- It does not auto-approve review decisions or Claim CI expectations.
- It does not run migrations, deploy an environment, publish a corpus, or create a
  release tag merely by being merged.
- It does not claim complete CAC Ontology conformance; the included SHACL profile
  validates only the proposal's legal-event projection contract.

## Maintainer review order

Review the proposal as seven reversible boundaries, in the order defined in
[`ADOPTION_PLAN.md`](ADOPTION_PLAN.md). The recommended first decision is only
whether the governance, reproducibility, immutable identity, and ledger primitives
are useful. Extraction, graph, analysis, and operational adoption can each stop
without invalidating that earlier work.

For each boundary, review in this order:

1. ADR and stated non-goals.
2. Domain invariants and failure behavior.
3. Migration or artifact compatibility.
4. Adversarial and contract tests.
5. Operational activation and rollback.

[`THREAT_MODEL.md`](THREAT_MODEL.md) consolidates the trust boundaries and residual
risks. [`TRACEABILITY_MATRIX.md`](TRACEABILITY_MATRIX.md) is the human review map.
[`DRAFT_PULL_REQUEST.md`](DRAFT_PULL_REQUEST.md) contains a copy-ready draft PR.

## Acceptance posture

All new paths are additive and opt-in. Adoption should remain in fixture or shadow
mode until the maintainer has approved the relevant semantics, migration rehearsal,
privacy review, and disclosure policy. A passing test suite establishes software
contract evidence; it does not establish external validity, legal compliance, or
permission to publish.

## Reproduction

From the repository root, run:

```bash
uv sync --locked --no-extra ml
uv run --locked --no-extra ml python scripts/quality/check_repository.py
uv run --locked --no-extra ml python scripts/quality/check_traceability.py
uv run --locked --no-extra ml ruff check scripts/quality scripts/run/claim_pipeline.py scripts/run/snapshot_manifest.py src/caselinker tests
uv run --locked --no-extra ml ruff format --check scripts/quality scripts/run/claim_pipeline.py scripts/run/snapshot_manifest.py src/caselinker tests
uv run --locked --no-extra ml mypy scripts/quality/check_repository.py scripts/quality/check_traceability.py scripts/run/claim_pipeline.py src/caselinker
uv run --locked --no-extra ml pytest tests/quality tests/unit tests/integration tests/contract --cov=scripts/quality --cov=src/caselinker --cov-report=term-missing
uv run --locked pytest -m smoke tests/smoke
uv run --locked pip-audit --local --skip-editable
uv run --locked bandit -q -lll -r scripts/quality scripts/run/claim_pipeline.py scripts/run/snapshot_manifest.py src/caselinker
```

CI also rebuilds the policy-safe snapshot fixture twice, compares the bytes, and
verifies the resulting manifest.
