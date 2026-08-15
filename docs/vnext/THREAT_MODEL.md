# vNext proposal threat model

## Scope and safety objective

This model covers the additive vNext path from a public-source document version to a
research Claim Card and Evidence Pack. Its safety objective is narrower than “safe to
publish”: preserve what a source reported, prevent unsupported transformations from
silently becoming canonical, make every derived artifact reproducible, and fail closed
when evidence, review, validation, or snapshot bindings no longer agree.

## Protected assets

- Exact source bytes, source-version identity, and evidence spans.
- The distinction among reported, reviewed, resolved, eligible, and disclosed state.
- Append-only assertions, reviews, and their lineage.
- Snapshot membership, projection bytes, SHACL shapes, query semantics, cohort unit,
  numerator and denominator membership, and expected claims.
- Maintainer release authority and human review authority.
- Confidential or identifying information that could exist despite a source being
  public.

## Trust boundaries

1. **External source to immutable document.** Remote content is untrusted; public
   availability is not a truth or disclosure guarantee.
2. **Document to extracted candidate.** Rules are deterministic but fallible and may
   misbind a subject, event, date, or negation.
3. **Candidate to human review.** Reviewer identity, competence, independence, and
   currentness are governance inputs outside the extractor.
4. **Reviewed candidates to resolution.** Only coherent, current, complete bundles may
   become canonical internal relations.
5. **Resolution to graph.** Mapping may be broader than the exact procedural term;
   projection must preserve the exact type and lineage.
6. **Graph to claim.** Validation, snapshot membership, units, and all members must be
   pinned before aggregation.
7. **Research artifact to an audience.** Eligibility is never sufficient disclosure
   authorization; audience, purpose, minimization, and access policy are separate.
8. **Repository and CI environment.** Paths, dependencies, build runners, and reviewed
   expectations are supply-chain and operational inputs.

## Threats, controls, and residual risk

| Threat | Implemented control | Residual risk / required owner |
|---|---|---|
| Mutable or substituted source | content-addressed versions and snapshot inventories | source authenticity and retention policy require governance |
| Extraction assigns an event to the wrong person | exact spans, explicit subject relation, conservative patterns, human review | ambiguous prose still requires qualified review |
| Allegation becomes an assertion of guilt | reported predicates before review; procedural types; generated bounded claim text | UI and downstream prose must preserve status and context |
| Date is attached to the wrong event | event/date span binding and coherent-bundle checks | complex cross-sentence references remain out of scope |
| Review history is overwritten or stale | append-only decisions, immutable lineage, live current-review checks | reviewer authentication and authorization are not implemented here |
| Partial or cross-run facts are resolved together | exact cardinality, extraction-run, subject, method, and span checks; atomic writes | database concurrency beyond SQLite needs deployment analysis |
| Invalid or altered graph enters analysis | canonical bytes, digest binding, pinned local SHACL rerun | profile validates the proposal contract, not all CAC semantics |
| Count silently changes unit or denominator | one explicit unit, complete sorted memberships, duplicate rejection | statistical validity and generalizability require separate review |
| CI blesses a changed claim automatically | expectation is separate and content-addressed; CLI never updates it | expectation approval/signing is a human governance process |
| Path traversal or symlink substitution reads unintended files | normalized root-contained paths and symlink rejection | hostile runner or repository write access remains a broader control |
| Atomic output is mistaken for a distributed transaction | local temp-write, fsync, atomic replace | shared/distributed storage needs an operational design |
| Public-source evidence is over-disclosed | Evidence Pack excludes source text and display names; repeated non-authorization contracts | de-identification, audience policy, and legal/privacy review remain mandatory |
| A proposal is represented as an official release | proposal namespace, no official version claim, explicit upstream authority | communication and release controls remain with maintainers |

## Required deployment controls not supplied by this branch

- Authenticated principals, least-privilege authorization, and reviewer role policy.
- Secrets management, encryption policy, audit-log operations, backup/restore drills,
  retention, incident response, and environment hardening.
- A disclosure review that considers audience, purpose, data minimization, vulnerable
  persons, sealed/updated records, source terms, and applicable law or policy.
- PostgreSQL transaction-isolation and concurrent-review testing if SQLite is replaced.
- Source authenticity monitoring, takedown/correction handling, and retraction policy.
- Signed or otherwise governed approval of Claim CI expectations.

## Fail-safe adoption rule

If a boundary cannot prove its input identity, current review state, exact unit, or
required validation, it must produce no downstream research artifact. If disclosure
authorization is absent, a technically eligible artifact remains non-public.
