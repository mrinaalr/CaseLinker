# Stage 1 threat model

**Status:** Normative for `proposal/stage-1-m01`. Proposal language only; not
an official CaseLinker release.

**Purpose:** State the risk argument this proposal is willing to be reviewed
against, including residual risk, before any later data-model stage is
considered.

**Primary sources:**

- Ramachandran, M. (2026). *CaseLinker: 5 Sources, 500 Cases, and Scaling
  Considerations* (Report #3), §6
  ([Scaling.pdf](https://mrinaalr.github.io/website/Scaling.pdf)).
- Ramachandran, M. (2026). *A Framework for Retrospective Analysis and Case
  Studies…* (Report #4), §§3.4 and 5 (HRPO determination, restricted-first
  dissemination, explicit non-goals).
- UMass Amherst HRPO Determination #7668 (Not Human Subjects Research,
  45 CFR 46.102(f)(1)–(2)), as cited by the maintainer.

This is a rewrite, not a restatement of a generic application threat model.
The previous draft treated “fail closed on missing evidence bindings” as the
center of gravity. That is necessary later. It is not the project's actual
risk argument. The project's actual argument is: **public success narratives
give defenders compounding analytical utility and give adversaries almost
nothing they could not already read in the source press releases — provided
the system never raises the identification ceiling, never invents
unpublished operational signal, and never leaves the documented data
scope.**

Stage 1 implements none of the later provenance pipeline. It still has to
get this argument right, because the maintainer asked to start here, and
because later stages are not allowed to silently invalidate it.

## 1. Safety objective

The objective is not “safe to publish” and not “zero residual risk.”

The objective is:

1. Preserve what a source agency already chose to publish and redact.
2. Do not create identifying, operational, or demographic signal that the
   source set did not contain.
3. Keep defender utility able to grow with corpus size, while keeping
   adversary utility approximately constant.
4. Fail closed when a proposed change would leave the HRPO-documented
   scope, raise the identification ceiling, or present a selected
   success-only corpus as prevalence, platform danger, or evasion advice.
5. Make residual risk explicit enough that a later stage cannot claim it
   was already accepted.

## 2. What is in scope for this branch

| In this PR | Not in this PR |
|---|---|
| Governance, DCO, proposal identity (`0.0.0`) | Immutable document store |
| Repository checker, lockfile, quality CI | Extraction, resolution, review ledger |
| Smoke test of the existing application boot | CAC graph projection |
| This threat model and `SECURITY.md` | Claim Cards, Evidence Packs, Claim CI |
| Dependency audit / CodeQL / Dependabot | Repository-bound research CLI |
| | Production access-control redesign |
| | Any change to stored case fields |

The existing CaseLinker application and its live deployment remain upstream
assets. Stage 1 must not break them and must not pretend to have replaced
their controls.

## 3. Protected assets

- The **source-bounded identification ceiling**: nothing CaseLinker stores
  or emits may be easier to use for re-identification than the originating
  public document.
- The **operational-signal floor**: failure modes, undercover methodology,
  tip routing, and forensic tooling that agencies did not publish.
- The **HRPO data-scope bound**: public, already-redacted,
  closed/adjudicated records only.
- Distinctions among reported, reviewed, resolved, eligible, and disclosed
  state. Stage 1 does not implement those states; it forbids collapsing
  them in documentation or later design.
- Maintainer release authority and human review authority.
- The integrity of the locked quality environment and CI, because a
  compromised lockfile or workflow is a path into every later stage.

## 4. Trust boundaries

1. **World → source document.** Remote content is untrusted. Public
   availability is not truth, consent, or disclosure authorization.
2. **Source document → CaseLinker record.** Feature extraction may not add
   identifiers, recover redactions, or import outside identity data.
3. **Record → aggregate / facet / chart.** Aggregation changes
   *discoverability* of already-public facts. It must not change the
   *identification ceiling* or be labeled as population prevalence.
4. **Aggregate → audience.** Research usefulness is not permission to
   republish source text, names, or elevated-severity narratives.
5. **Documented HRPO scope → any new field or source.** Crossing this
   boundary is a research-ethics change, not an engineering optimization.
6. **Repository / CI → later code.** Dependencies, Actions, and reviewed
   lockfiles are supply-chain inputs. Stage 1 adds this surface.
7. **Proposal language → official release.** Naming, tags, and README
   banners must not imply maintainer adoption.

## 5. The Scaling-paper argument, restated as reviewable claims

Report #3 §6 defines a dataset `D = {c_1, …, c_n}` of public ICAC success
narratives and three quantities:

- `U_D(D)`: utility to defenders (investigators, researchers, journalists)
- `U_A(D)`: utility to adversaries
- `R(c_i)`: re-identification risk of case `c_i`
- `S(c_i)`: operational signal in case `c_i` (tactics, tools, failure
  modes)

This proposal accepts those definitions and the following claims as
**design constraints**, not as marketing.

### 5.1 Proposition 1 — re-identification is source-bounded

**Claim.** `R(c_i) ≤ R(source(c_i))` for every `c_i` in `D`.

**Why the paper thinks this holds.** CaseLinker does not process victim
names, perpetrator personal identifiers, addresses, or case numbers beyond
structural metadata already in the source. The nine (later ten) extraction
dimensions introduce no new identifying information. Aggregating redacted
summaries surfaces distributional patterns; it does not reconstruct the
underlying case file.

**What Stage 1 must not break.** No later stage may add a field, join, or
UI path that raises `R(c_i)` above the source document. That includes
cross-source identity resolution, “same offender?” hints, geolocation finer
than the source, and any reconstruction of redacted spans.

**Residual risk.** The inequality is a ceiling, not a zero. Mosaic risk
already exists in the source set: a distinctive platform + jurisdiction +
year + severity phrase can be unique. CaseLinker can make that mosaic
*cheaper to query*. The honest bound is: we will not make a mosaic that the
source documents themselves do not already support, and we will not present
the cheaper query as a reason to publish more source text.

**IRB implication.** HRPO #7668 depends on the corpus containing no private
or identifiable information beyond the public record. A feature that
creates new identifiability is not a small product change. It is a
determination-breaking change.

### 5.2 Proposition 2 — operational signal is absent by construction

**Claim.** `S(c_i) ≈ 0` for all `c_i` in `D`, independent of `n`.

**Why the paper thinks this holds.** Each `c_i` is a redacted success
narrative. Agencies do not publish communication-interception methods,
undercover persona construction, tip-source routing, or forensic tooling.
An adversary who reads 500 cases therefore learns approximately as much
operational detail as an adversary who reads 10. Aggregation cannot recover
what was never published. Because `D` contains only successes, it also
cannot reveal the conditions under which enforcement fails.

**What Stage 1 must not break.** Later stages must not scrape, store, or
infer unpublished methodology “for completeness.” They must not treat
investigation-type labels (`undercover`, `proactive`, `reactive`) as a
how-to. They must not backfill gaps in terse sources (the Michigan vs
AZICAC reporting disparity in Report #3 §3.2) with speculation.

**Residual risk.** Some public narratives still mention platforms, charge
categories, and coarse investigation type. That is not tradecraft, but it
is not nothing. The paper's own bounded-misuse section exists because
`S(c_i) ≈ 0` is an approximation. We keep the approximation only by
refusing to enrich those fields.

### 5.3 Proposition 3 — utility asymmetry

**Claim.** `U_D(D) ≫ U_A(D)` for any practically relevant `n` (the paper
uses `n ≥ 50`), because

```text
∂U_A / ∂n ≈ 0    while    ∂U_D / ∂n > 0
```

**Why the paper thinks this holds.** Defender utility is superlinear in
`n`: cross-jurisdictional success patterns, platform evolution, agency
networks, and offense-type distributions are invisible in any single
source. Adversary utility is approximately constant: no failure modes or
evasion tactics accumulate with scale.

**What Stage 1 must not break.** Product copy, charts, and later Claim
Cards must not invert the asymmetry — for example by publishing “platforms
that do not appear,” “jurisdictions with low prosecution counts,” or
“age bands with fewer successful cases” as if those were enforcement
holes. Report #3 §6.4 is explicit that those gaps are reporting artifacts
of a success-only corpus.

**Residual risk.** The derivatives are an argument about *this* corpus
construction, not a law of nature. They fail if the corpus starts to
include unsuccessful operations, non-public files, or extracted operational
detail. They also fail, more softly, if a UI invites an adversarial reading
that the underlying data cannot support.

## 6. Bounded misuse cases

Report #3 §6.4 names three misuse vectors and a practical ceiling for each.
This model keeps all three, and adds the residual-risk statement the earlier
draft omitted.

| Vector | Why it looks tempting | Why the paper bounds it | Residual risk we still accept |
|---|---|---|---|
| Platform avoidance | Repeated Facebook / Discord / Snapchat hits look like a “do not use” list | The same signal is in the original press releases; CyberTipline / device correlation binds offenders to devices, not platforms | We may still make the already-public list faster to compile. That is a discoverability cost, not new operational intelligence. |
| Geographic / agency avoidance | High-prosecution task forces look like places to avoid | Internet offenses are not geographically bounded the way physical crimes are; tips route to the offender's location | Counts can still be misread as local “heat maps.” Interfaces must not rank jurisdictions by punitiveness. |
| Victim-demographic targeting | Age or severity distributions look like under-policed groups | `D` is prosecuted CSAM, not a sourcing gap; there is no demographic hole that reflects a true blind spot | A success-only histogram can still be quoted out of context. Denominators and limitations are mandatory on any public statistic. |

A later stage that makes any of these vectors *cheaper than reading the
sources*, *more precise than the sources*, or *easier to export as a
targeting list* has left this threat model.

## 7. Access-control and scope boundary conditions

Report #3 §6.6 states two conditions under which the propositions hold.

### 7.1 Access control (existing system, not added here)

For elevated-sensitivity indicators (infant victims, hands-on severity
phrases), the live system restricts **direct case retrieval** to access-key
holders. Facet navigation and aggregate statistics remain public. The
intent is to stop the system functioning as a targeted lookup tool for the
most sensitive already-public details.

Stage 1 does not implement, replace, or weaken that gate. A later stage
that adds new retrieval paths — exports, MCP tools, evidence packs, “open
this case” links — must re-apply the same or a stricter rule. Research
eligibility is not that rule.

Known limitation of the current application, recorded so Stage 1 does not
paper over it: optional `API_KEY` authentication fails open when the
variable is unset. That is a deployment control, not a property of this
PR.

### 7.2 Scope boundary (HRPO and the Scaling paper agree)

The propositions hold only for **public, redacted, closed/adjudicated**
summaries. They do not generalize to:

- non-public case data;
- active investigation records;
- unpublished operational details;
- qualitatively new extracted features outside the current dimensional
  schema;
- joins to commercial, court-sealed, or identity-resolution sources.

Report #4 §5.1 adds the ethics restatement: HRPO #7668 reflects the nature
of the source material, “not a judgment that the subject matter is without
sensitivity.” Restricted-first dissemination of case studies is a
professional choice, not a legal requirement. Stage 1 adopts that posture
for any future research output.

**If a later stage wants any of the out-of-scope data, the threat model is
withdrawn and a new HRPO review is a precondition, not a follow-up.**

## 8. Stage 1 surface — threats this PR actually adds

| Threat | Control in this PR | Residual risk / owner |
|---|---|---|
| Unsigned or recycled commits obscure provenance | DCO (`Signed-off-by`) required on every new commit; old Codex-authored commits are not reused | Maintainer still decides whether to require a DCO bot |
| Proposal represented as an official v3 release | `0.0.0` workspace metadata; `proposal/` branch; README and ADR 0000 | Communication remains a maintainer control |
| Corrupt or non-UTF-8 source silently enters the tree | repository checker; `.gitattributes` working-tree-encoding | Generated RDF pools remain excluded and must be hashed later |
| Known-vulnerable dependencies | locked `uv.lock`; `pip-audit`; Dependabot; dependency-review on PRs | Optional ML extra is locked but **not** installed or audited in CI |
| CI supply-chain substitution | pinned `astral-sh/setup-uv@v10.0.1`; Actions on `pull_request`/`push` of `proposal/**` and `main` | GitHub-hosted runners and action maintainers remain trusted third parties |
| Quality workflow becomes an unbounded cost | Stage-1-scoped jobs only: integrity on `scripts/quality` + `tests`, smoke of existing app, no snapshot rebuild | CodeQL (Python + JS) and weekly Dependabot are new recurring cost — see PR body |
| Tests that reproduce harmful case text | CONTRIBUTING and SECURITY forbid real case material in fixtures | Historical fixtures already in the tree are an upstream inheritance, not expanded here |
| Later-stage code lands “because CI is here” | adoption plan parks Stages 2–7; quality.yml does not reference them | Social / review discipline; this file is the stop sign |

## 9. Residual risk register

These risks remain after Stage 1. Accepting this PR accepts them as
**open**, not solved.

1. **Cheaper mosaics.** Faceted search over already-public fields lowers the
   time to assemble a unique tuple. Ceiling still equals the source
   documents; discoverability is higher.
2. **Success-only bias read as truth.** Terse sources (Michigan-style) look
   like empty phenomena. Report #3 §3.2 refuses to normalize this away.
   Downstream statistics that ignore the warning will overfit reporting
   style.
3. **Utility-asymmetry is an argument.** It is not an empirical measurement
   of adversary behavior, and it dies if the corpus composition changes.
4. **HRPO is scoped.** Determination #7668 does not travel automatically to
   a new data model, a new institution, or a new class of record.
5. **Access control is not redesigned here.** Elevated-severity lookup
   restrictions remain an upstream production concern. Stage 1 does not
   audit them.
6. **ML extra is unaudited.** Torch / transformers / stanza stay out of
   core CI on purpose. A later stage that turns them on needs its own
   supply-chain review.
7. **No disclosure authority is granted.** A technically correct aggregate
   can still be the wrong thing to put on the public internet. Restricted-
   first review (Report #4 §5.2) remains a human process.
8. **Vicarious trauma is a safety issue.** Report #4 §4.3 records secondary
   traumatic stress rates of 40–60% in this domain. Interfaces and
   documentation should keep default paths on cohorts, not on graphic
   narrative. Stage 1 does not implement a new UI.

## 10. Fail-closed adoption rules

1. If a change cannot show that it preserves `R(c_i) ≤ R(source(c_i))`, it
   does not ship.
2. If a change would add unpublished operational signal, it does not ship.
3. If a change would leave the HRPO-documented data scope, work stops for
   maintainer and HRPO review. Engineering convenience is not a reason to
   proceed.
4. If a statistic has no explicit unit, denominator, membership rule, and
   limitations, it is not a public claim.
5. If disclosure authorization is absent, a technically eligible artifact
   remains non-public. Research eligibility is not that authorization.
6. If a later stage needs a different threat model, it must replace this
   document in public, not footnote it.

## 11. What later stages must re-evaluate

When — and only when — the maintainer opens a later stage, that PR must
re-answer:

- Does the stored schema still match HRPO #7668, or has a new field
  created identifiability?
- Do extraction dimensions stay inside the source document?
- Does any graph edge imply a person-identity or guilt finding the source
  did not state?
- Do Evidence Packs exclude source text and display names by default?
- Does Claim CI refuse to auto-approve an expectation?
- Is the elevated-sensitivity retrieval gate still in front of every new
  export path?

Those questions are out of scope for Stage 1 on purpose. Opening them here
would recreate the review-unit problem of PR #4.
