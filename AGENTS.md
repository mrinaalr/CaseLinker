# CaseLinker vNext Engineering Contract

This branch is a **proposal for a future CaseLinker architecture**. It is not an
official CaseLinker release. Mrinaal Ramachandran, as the upstream creator and
maintainer, retains authority over upstream naming, roadmap, and release tags.

Read [`docs/vnext/ENGINEERING_CHARTER.md`](docs/vnext/ENGINEERING_CHARTER.md)
before changing code. That charter is normative for all work on this branch.

## Non-negotiable operating rules

1. Preserve evidence lineage. No accepted fact may exist without a source
   document version and either an exact evidence span or an explicit reason a
   span is unavailable.
2. Keep observation, extraction, resolution, derivation, model inference, and
   human authorship distinguishable in data, APIs, graphs, and interfaces.
3. Models produce review candidates, never canonical facts.
4. Treat every corpus statistic as snapshot-scoped. Never imply population
   prevalence from a public-enforcement corpus without an explicit denominator
   and limitations statement.
5. Keep CaseLinker focused on the CSEA evidence substrate. Do not duplicate the
   cross-domain formal-modeling role of CaseNoesis.
6. Preserve upstream behavior unless a documented migration or compatibility
   decision authorizes a break.
7. Never commit source PDFs, secrets, access tokens, victim-identifying data,
   user-submitted notes, or generated model artifacts not explicitly allowlisted.
8. Prefer small, reversible, independently valuable commits. Record durable
   architectural decisions in `docs/adr/`.
9. Add tests before or with behavior changes. A change is not complete until
   its failure modes, security implications, and evidence semantics are tested.
10. Do not create an official-looking `v3.0.0` tag or release. Development
    maturity uses `proposal-*`; upstream alone decides official versioning.

## Required workflow

1. State the user or research outcome and the invariant it must preserve.
2. Inspect current behavior and write the smallest falsifiable acceptance test.
3. Implement through a narrow interface; avoid new global state and hidden I/O.
4. Run `uv run --locked --no-extra ml python scripts/quality/check_repository.py`.
5. Run focused tests, then the complete fast suite.
6. Document migrations, limitations, and rollback behavior.
7. Summarize evidence for correctness in the commit or pull-request description.

Generated RDF, JSON-LD, corpus snapshots, and analytical outputs are build
artifacts. Change their generators and manifests first; never hand-edit an
artifact as the sole implementation of a fix.
