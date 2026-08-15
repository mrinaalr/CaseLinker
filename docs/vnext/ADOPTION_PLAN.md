# Staged upstream adoption and rollback plan

## Strategy

Do not merge the proposal as a single feature release. Rebase the seven boundaries
below onto the maintainer's chosen baseline, preserving each ADR with its code and
tests. Every stage is additive, defaults to inactive, and has an explicit stop point.

| Stage | Proposed PR | Included boundary | Activation gate | Rollback |
|---|---|---|---|---|
| 1 | Governance and reproducible quality | M01 | maintainer approves proposal conventions and CI cost | revert proposal-only files; no data state |
| 2 | Immutable provenance kernel | M02 | migration review, SQLite backup/restore rehearsal, deterministic snapshot fixture | stop new writes; preserve additive tables for audit; revert callers |
| 3 | Evidence-bound extraction | M03 | adversarial fixture review and shadow comparison against representative sources | disable extractor; retain candidate assertions and run records |
| 4 | Reviewed resolution | M04 | reviewer workflow, lineage checks, stale-review drills, transaction review | stop resolution writes; retain immutable decisions and assertions |
| 5 | CAC graph projection | M05 | mapping review with ontology maintainer and pinned SHACL approval | disable projector; regenerate disposable RDF later |
| 6 | Claims, Evidence Packs, Claim CI | M06 | approve unit/denominator semantics, limitations, and expectation governance | disable analyzer/check; discard regenerated artifacts |
| 7 | Repository-bound CLI | M07 | end-to-end fixture, operational runbook, disclosure gate outside the CLI | remove CI invocation; retain all authoritative inputs |

## Stage gates

Each stage must satisfy all of the following before the next begins:

1. The relevant ADR has an explicit maintainer disposition: accept, amend, defer, or
   reject.
2. Contract, adversarial, integration, and regression tests pass on the target branch.
3. Compatibility is demonstrated against current legacy application smoke tests.
4. Any persistent-state change has backup, restore, idempotency, and forward-only
   rollback rehearsal.
5. Privacy, disclosure, and access-control responsibilities are not delegated to a
   research-eligibility result.
6. Observability identifies failures without logging sensitive source text.

## Shadow-mode sequence

- Start with policy-safe fixtures only.
- Replay a maintainer-approved, non-sensitive historical sample without writing to
  legacy tables or publishing results.
- Compare extraction candidates and resolutions with independent human review; record
  error classes rather than tuning against hidden test answers.
- Generate RDF and claims in an isolated artifact namespace. Verify byte stability on
  repeat runs and after clean environment setup.
- Exercise review supersession and confirm all dependent resolutions become ineligible.
- Exercise snapshot, shape, query, projection, and expectation tampering and confirm
  fail-closed behavior.
- Only then consider a limited operational pilot, with separate authorization for any
  audience-facing disclosure.

## Branch and release sovereignty

The proposal branch name and its checkpoint commits are review coordinates, not a
release train. The upstream maintainer may squash, reorder, rewrite, or adopt only a
subset. No fork tag should imply that upstream has approved an official version.
