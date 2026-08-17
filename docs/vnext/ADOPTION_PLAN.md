# Staged upstream adoption and rollback plan

## Strategy

Do not merge a multi-stage proposal as a single feature release. Review each
boundary independently. Every later stage is additive, defaults to inactive, and
has an explicit stop point.

This branch implements **Stage 1 only**.

| Stage | Proposed PR | Included boundary | Activation gate | Rollback |
|---|---|---|---|---|
| 1 | Governance and reproducible quality | M01 | maintainer approves proposal conventions and CI cost | revert proposal-only files; no data state |
| 2 | Immutable provenance kernel | parked | migration review, after Stage 1 disposition | not in this branch |
| 3 | Evidence-bound extraction | parked | adversarial fixture review | not in this branch |
| 4 | Reviewed resolution | parked | reviewer workflow and lineage review | not in this branch |
| 5 | CAC graph projection | parked | dedicated ontology compatibility discussion | not in this branch |
| 6 | Claims, Evidence Packs, Claim CI | parked | unit/denominator and expectation governance | not in this branch |
| 7 | Repository-bound CLI | parked | end-to-end fixture and operational runbook | not in this branch |

## Stage 1 gate

Stage 1 asks only whether the following are useful and affordable:

1. Proposal identity: `0.0.0` workspace metadata, `proposal/` branches, no
   official version claim.
2. A dependency-free repository checker and locked quality environment.
3. CI cost for integrity, smoke, audit, CodeQL, and dependency review.
4. A security policy and threat model written against the Scaling paper and
   the current HRPO determination.

Stage 1 does not ask the maintainer to accept a data model, extraction
semantics, graph projection, or claim pipeline.

## Later stages

Stages 2–7 remain parked on the prior architectural-review draft
([PR #4](https://github.com/mrinaalr/CaseLinker/pull/4)) until the maintainer
disposes of each ADR. They are not reviewed, merged, or implied by this
branch.

Each later stage must still satisfy, before the next begins:

1. The relevant ADR has an explicit maintainer disposition: accept, amend,
   defer, or reject.
2. Contract, adversarial, integration, and regression tests pass on the target
   branch.
3. Compatibility is demonstrated against current legacy application smoke tests.
4. Any persistent-state change has backup, restore, idempotency, and
   forward-only rollback rehearsal.
5. Privacy, disclosure, and access-control responsibilities are not delegated
   to a research-eligibility result.
6. Observability identifies failures without logging sensitive source text.
7. Any change in stored fields, extraction dimensions, or data scope is
   reviewed against HRPO Determination #7668 before adoption.

## Branch and release sovereignty

The proposal branch name and its checkpoint commits are review coordinates, not
a release train. The upstream maintainer may squash, reorder, rewrite, or adopt
only a subset. No fork tag should imply that upstream has approved an official
version.
