# CaseLinker vNext Engineering Charter

**Status:** Normative for the proposal branch

**Target:** Production-grade architecture suitable for an upstream CaseLinker
3.0 decision

**Identity:** Proposal work, not an official CaseLinker release

## 1. Mission

Build the evidence-grade CSEA research substrate beneath CaseLinker's strongest
ideas. A reader must be able to move from a chart, count, relationship, or model
output to the exact evidence, method, ontology version, corpus snapshot, review
state, and limitations that produced it.

The flagship contract is:

> CaseLinker turns public enforcement records into reproducible research claims
> with source-span provenance, explicit uncertainty, immutable snapshots, and
> safe cohort-level workflows.

## 2. Authority and project identity

- Upstream remains `mrinaalr/CaseLinker`.
- This work targets a possible v3 architecture but does not assign upstream a
  version number or release date.
- Proposal maturity identifiers use `proposal-0.x`; they are not SemVer claims
  about upstream CaseLinker.
- The fork preserves upstream copyright, license, history, and attribution.
- No official-looking release, deployment, paper claim, or maintainer statement
  is published without upstream alignment.

## 3. Product boundary

| System | Responsibility | Smallest trustworthy unit |
|---|---|---|
| CaseLinker | CSEA evidence substrate and research workbench | Source-grounded assertion |
| CaseNoesis | Cross-domain formal modeling and falsification | State transition or framework test |
| CAC Ontology | Shared vocabulary and semantic constraints | Typed graph statement |

CaseLinker may expose state-machine evidence to CaseNoesis. It must not become a
second cross-domain modeling product.

## 4. Scientific invariants

### 4.1 Unit clarity

`source_document`, `source_document_version`, `matter`, `case`, `party`,
`event`, `assertion`, and `artifact` are distinct units. Counts must name their
unit. Joins must not silently turn document counts into case counts or case
counts into person counts.

### 4.2 Assertion lineage

An assertion records, at minimum:

- stable identifier;
- subject, predicate, object/value, polarity, and temporal scope;
- assertion state and creation method;
- source document version;
- exact evidence span, or a typed span-unavailable reason;
- extraction/run identity and code/rule/model version;
- confidence dimensions and review status;
- supersession or retraction lineage.

Accepted assertions are append-only. Corrections supersede or retract; they do
not erase the historical record.

### 4.3 State separation

The system must preserve these states end to end:

`observed`, `extracted`, `resolved`, `derived`, `inferred`, `authored`,
`contested`, and `retracted`.

Only policy-approved states participate in a published claim. Interfaces may
not collapse `inferred` into `observed` through styling or omission.

### 4.4 Snapshot reproducibility

Every analytical artifact binds to a manifest containing hashes for the corpus,
source versions, accepted assertions, code, extraction rules, model bundles,
ontology and SHACL shapes, query, parameters, and generated outputs.

The same manifest and supported execution environment must reproduce the same
deterministic outputs byte-for-byte, except for explicitly declared volatile
metadata.

### 4.5 Claim discipline

Public-source enforcement records are a selected corpus. Product copy and
research outputs must not infer population prevalence, platform risk, or causal
effect without appropriate denominators, comparison design, and limitations.
Headline claims become executable, snapshot-pinned specifications in Claim CI.

## 5. Safety, privacy, security, and research-ethics invariants

- Default interfaces operate on cohorts and mosaics, not sensationalized case
  narratives.
- Public responses use allowlisted fields and policy shaping; serialization of
  an internal object is never treated as access control.
- Authentication, authorization, rate limits, and audit events are durable and
  deployment-safe. In-memory counters are development fallbacks only.
- CORS and trusted-proxy configuration are explicit per environment.
- Logs contain stable internal identifiers, never source text or personal data.
- Model prompts and external services receive the minimum necessary content;
  egress is documented and disableable.
- Interfaces follow WCAG 2.2 AA and trauma-aware content design.

These controls sit inside the project's documented research-ethics bound, not
beside it:

- The current research posture, as documented by the maintainer, is UMass
  Amherst HRPO Determination #7668: Not Human Subjects Research under
  45 CFR 46.102(f)(1)–(2), because the corpus is public, already-redacted,
  closed/adjudicated enforcement material. That determination is a statement
  about the present data scope. It is not a finding that the subject matter
  lacks sensitivity, and it is not a standing authorization to add non-public,
  identifiable, or operationally live records.
- Public availability is not disclosure authorization, republication
  permission, or proof that aggregation is harmless.
- Feature extraction must not introduce identifying information that the
  source document did not publish. Mosaic re-identification risk is
  source-bounded: CaseLinker must not raise the identification ceiling above
  what the originating agency chose to publish.
- The corpus is a selected set of successful public outcomes. It contains no
  failure modes, unpublished tradecraft, or enforcement blind spots. Outputs
  must not be readable as prevalence, platform danger, demographic targeting
  guidance, or a map of where not to offend.
- Adversarial risk is analyzed in the terms of the Scaling paper: defender
  utility is expected to grow with corpus size, while adversary utility from
  these public success narratives remains approximately constant. That
  argument is a bound, not a proof of zero residual risk.
- Any later stage that changes the data model, extraction dimensions, or
  stored fields must be reviewed against the HRPO determination before
  adoption. Stage 1 does not implement that data model.

## 6. Architecture rules

1. Domain logic does not import FastAPI, storage drivers, or rendering code.
2. I/O occurs behind typed ports; adapters own PostgreSQL, RDF, filesystem, MCP,
   HTTP, and model-provider behavior.
3. Domain values are immutable where practical and validated at construction.
4. Identifiers are opaque and stable; display labels are never identifiers.
5. Time is timezone-aware UTC at boundaries and injectable in tests.
6. Serialization schemas are versioned and reject unknown security-sensitive
   fields unless a compatibility policy says otherwise.
7. Migrations are forward-only in production and include tested rollback or
   recovery procedures.
8. Generated artifacts include provenance manifests and are never the sole
   source of truth.

## 7. Change protocol

For each material change, record:

1. **Outcome:** What user or research capability becomes possible?
2. **Invariant:** What must remain true?
3. **Threats:** How could the change leak data, misstate evidence, or corrupt
   reproducibility?
4. **Acceptance:** What executable evidence proves success?
5. **Compatibility:** What existing API, artifact, or workflow may change?
6. **Migration:** How is existing data transformed and verified?
7. **Rollback:** How is the change safely disabled or reversed?

Architectural decisions go in `docs/adr/`. Experimental findings go in
`docs/research/`; they do not silently become product claims.

## 8. Quality gates

Every merge candidate must satisfy:

- tracked authored text is valid UTF-8 and free of unresolved merge markers;
- every tracked Python file parses and compiles;
- formatter and linter checks pass for the touched/new strict surface;
- fast unit and contract tests pass deterministically;
- dependency resolution is locked and CI uses the lock;
- secrets and high-risk dependency findings are reviewed;
- new public endpoints include authorization, policy-shaping, abuse, and
  observability tests;
- migrations are tested against a representative fixture and verify row counts,
  hashes, constraints, and idempotency;
- evidence-semantic changes include golden fixtures and provenance assertions;
- documentation states limitations and operational recovery steps.

Strictness expands monotonically. Legacy exceptions require an owner, reason,
and deletion condition; new vNext modules receive no blanket exclusions.

## 9. Definition of done

A feature is done only when code, tests, documentation, migrations, telemetry,
security controls, provenance, and limitations agree. A passing demonstration
without reproducible evidence is a prototype, not a completed CaseLinker
capability.

## 10. First vertical milestone

Take a representative, policy-safe subset from immutable source documents
through evidence spans, assertion resolution, accepted assertions, CAC graph
generation, cohort analysis, one claim card, and a reproducible Evidence Pack.

Scale only if this slice is materially easier to audit, reproduce, and cite than
the current implementation. That vertical is not part of Stage 1.
