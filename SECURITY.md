# Security Policy

CaseLinker aggregates **public, already-redacted** enforcement records about
internet crimes against children. That data-scope statement is the beginning of
the security problem, not the end of it.

Even when every source document is already public, aggregation, search, facet
navigation, and careless disclosure can still cause harm: they can make already
public details easier to find, easier to mosaic, or easier to misread as
operational guidance. Security reports, therefore, must minimize reproduction
and redistribution of case content. Synthetic fixtures are the default.

This document is the reporting and response policy for the **Stage 1 (M01)
proposal**. The risk analysis that this policy assumes is in
[`docs/vnext/THREAT_MODEL.md`](docs/vnext/THREAT_MODEL.md). Both documents are
written against the maintainer's prior analysis in
[CaseLinker Report #3 (Scaling)](https://mrinaalr.github.io/website/Scaling.pdf)
and the current UMass Amherst HRPO determination.

## Supported work

This branch is pre-release proposal software. It is not an official CaseLinker
release and does not claim `v3.0.0` or any other upstream version.

- Security fixes on this branch target the latest commit on
  `proposal/stage-1-m01`.
- Issues that also affect the live deployment or the upstream default branch
  must be coordinated with the upstream maintainer before public discussion.
- Stage 1 does not add a new data model, extractor, graph projector, or
  research CLI. A report against those later-stage designs belongs on the
  parked architectural draft
  ([PR #4](https://github.com/mrinaalr/CaseLinker/pull/4)), not as a request
  to expand this PR.

## Research-ethics bound (HRPO #7668)

The project's documented research posture is UMass Amherst Human Research
Protection Office **Determination #7668**: the current work is **Not Human
Subjects Research** under 45 CFR 46.102(f)(1)–(2) because it analyzes public,
already-redacted, closed/adjudicated enforcement material and does not
process private or identifiable information beyond what the source agencies
published.

That determination is a statement about **present data scope**. It is not:

- a finding that the subject matter lacks sensitivity;
- a standing authorization to ingest non-public, identifiable, sealed, or
  operationally live records;
- permission to re-identify anyone, reconstruct unpublished methodology, or
  republish source text;
- a substitute for access control, disclosure review, or incident response.

Any change that would store new identifying fields, join public records to
non-public sources, or process active-investigation material requires a fresh
HRPO/IRB review **before** implementation. Stage 1 does not make that change.

## Reporting a vulnerability

Use GitHub's private vulnerability-reporting or Security Advisory workflow for
the affected repository. If private reporting is unavailable, contact the
repository owner without opening a public issue that contains exploit details
or case excerpts.

Include:

- the affected commit, component, and whether the live upstream deployment is
  implicated;
- a **minimal reproduction on synthetic data**;
- impact and the likely abuse path, stated without reproducing case text;
- suggested mitigation, if known;
- whether the issue depends on a later-stage design that is not in this
  branch.

Do **not** include:

- source PDFs or other original case records;
- illegal material, including any child sexual abuse material;
- victim-identifying details, even if they already appear in a public source;
- credentials, production tokens, or CaseLinker-Key values;
- unpublished law-enforcement methodology;
- unnecessary excerpts from case records.

If a finding cannot be demonstrated without real case text, describe the
class of defect and wait for maintainer guidance. Do not paste the text.

## What “public” does not authorize

Report #3 and Report #4 are explicit on this point, and this policy adopts it:

1. Public availability is not a truth guarantee, a disclosure authorization,
   or a republication license.
2. CaseLinker must not raise the identification ceiling above
   `R(source(c_i))` — the risk already created by the originating agency's
   publication and redaction choices.
3. Extraction and aggregation must not invent identifiers, recover redacted
   spans, or join a public record to an outside identity source.
4. Success-only public narratives are not a map of enforcement gaps, safe
   platforms, safe jurisdictions, or undertargeted victim groups.
5. Restricted-first review remains a professional obligation even when an
   HRPO determination says the work is not human-subjects research.

A vulnerability that lets a caller cross any of those lines is in scope, even
if the underlying record was already on the public internet.

## High-priority classes

### Harm to people and research-ethics scope

- any path that returns, logs, caches, or exports source text, notes, or
  victim-adjacent fields to an unauthorized caller;
- any path that reconstructs or infers identity beyond the source document;
- any join of CaseLinker records to external identity, commercial, or
  non-public data;
- any change that would silently move the project outside HRPO #7668's
  documented scope.

### Misuse of the public corpus (Scaling paper §6)

The Scaling paper names three bounded misuse vectors. Reports that enlarge
those vectors, or that make them cheaper than reading the original press
releases, are in scope:

- **platform avoidance** presented as actionable guidance rather than a
  restatement of already-public success narratives;
- **geographic or agency avoidance** inferred from prosecution counts;
- **victim-demographic targeting** inferred from severity or age
  distributions.

These are not “the system is doing research, therefore it is fine.” They are
residual risks with a documented ceiling. A defect that punches through that
ceiling — for example by exposing unpublished failure modes, operational
tradecraft, or non-public case detail — is a security issue.

### Access and policy bypass on the existing application

The live system, as documented in Report #3 §6.6, restricts direct retrieval
of elevated-sensitivity cases (infant-victim and hands-on severity
indicators) to access-key holders, while leaving facet navigation and
aggregate statistics public. Stage 1 does not reimplement that gate, but
reports against the existing application remain in scope for coordination
with upstream:

- unauthorized access to source text, notes, exports, or administrative
  routes;
- bypass of cohort, field-level, bulk-export, or trusted-key controls;
- cache-key, tenant, or snapshot confusion that returns another policy
  context;
- disabling authentication by omitting `API_KEY` in a deployment that
  intended to require it.

### Integrity of evidence and claims

- provenance tampering or a claim linked to the wrong evidence;
- silent collapse of allegation, reported speech, or procedural status into
  a finding of guilt;
- a count that changes unit or denominator without saying so.

Stage 1 does not add the later assertion/claim pipeline. If a report is
about that pipeline, say so and keep the reproduction on the parked draft.

### Supply chain and the Stage 1 surface

This branch does add a lockfile, quality CI, CodeQL, dependency review, and
Dependabot. The following are in scope here:

- secret exposure, unsafe deserialization, path traversal;
- dependency compromise or a lockfile substitution that reintroduces a
  known-vulnerable component;
- CI workflow injection, cache poisoning, or unpinned action substitution;
- denial of service against ingestion, graph generation, cohort queries, or
  model endpoints on the existing application;
- prompt injection or model egress that exposes restricted content, if a
  deployment has model access enabled.

## Disclosure expectations

Please allow maintainers time to reproduce, contain, fix, and coordinate
before public disclosure. Preferred order:

1. private report with a synthetic reproduction;
2. maintainer confirmation of scope (proposal branch, upstream `main`, live
   deployment, or parked later-stage design);
3. fix or documented residual-risk acceptance;
4. coordinated public advisory, if one is warranted.

This policy does not authorize access to systems or data beyond what the
reporter already has permission to use. It does not authorize the collection
of real case material, the circumvention of trusted-key controls, or the
publication of exploit details that reproduce case content.

## What this branch does not claim

- It does not make CaseLinker “safe,” “IRB complete,” or “cleared for
  republication.”
- It does not replace the maintainer's Scaling-paper risk argument with a
  new one. It implements that argument as policy.
- It does not move disclosure, access control, or HRPO review into CI.
- It does not authorize production deployment, live-source ingestion, or an
  official version tag.
