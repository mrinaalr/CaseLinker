<!-- Proposed PR, for review before anyone opens it. Branch: research/afh-q1-reconstruction. Do not open until authorised. -->

**Title:** rebuild AfH 2.0 Q1 platform-affordance manifest from a pinned corpus snapshot

## Summary

- Adds `research/afh_q1/`: a reproducible pipeline from a pinned, read-only snapshot of the 10,802-case corpus to the AfH 2.0 Section 3–4 manifest. It produces:
  - platform presence: 1,863 strict cases / 2,487 platform-case observations;
  - documented use: **1,513 primary** (line-wrap repair) and 1,257 original-rule baseline;
  - six-class coverage at four nested evidence levels;
  - recurrence, and observed vs potential harm pathways;
  - an exemplar inventory blind-reviewed by AI reviewers;
  - booktabs LaTeX tables.
- Replaces hand-entered platform capability years with dated, sourced research: 216 capability rows, and 25 manuscript claims checked on fetched pages (23 confirmed, 2 corrected).
- Fixes upstream defects found by the audit:
  - the Q1 freshness gate missed a stale candidate list;
  - program-launch boilerplate was tagged as case event dates;
  - hard-wrapped releases hid documented platform use from the tier rules;
  - importing `run/main.py` in tests left an empty `caselinker.db`, which broke later test runs.

## Root cause

1. **Stale snapshot.** `platform_affordance_evidence.py` read `candidates.json` from disk. Freshness compared only the corpus count and the extraction-run fingerprint, so the 2026-11-12 snapshot passed while built from a 23-day-old candidate list (3,183 listed vs 3,083 live).
2. **Case ids.** Ids before #38 were positional: 924 of 976 content-matched June NCMEC ids now name different releases. Manifest citations by bare id broke (51 of 118).
3. **Dates.** `temporal_tags` tagged "Project Safe Childhood, a nationwide initiative launched in May 2006" as an event in 2,358 cases.
4. **Tiers.** Press-release PDFs are hard-wrapped, so verb and platform reached `classify_sentence` as separate fragments.
5. **Capabilities.** Platform affordance years were unsourced, and classes were assigned per case only in hand-coded PACER graphs.
6. **Tests.** `run/main.py` builds `CaseStorage()` on the default relative path at import.

## Fix

| Area | Change |
|---|---|
| Freshness | The builder recomputes candidates on every run. `_meta` records platform-pair, candidate-pool and code hashes; `identity_matches` requires all of them (portable to Postgres; used by the API). |
| Tiers | `repair_line_wraps` and `linewrap_tiers`: additive (never demotes), refusing promotions earned only by agency social-media boilerplate. Records carry `stated_vs_inferred_linewrap` (`tiers-1+linewrap-2`) beside the unchanged `stated_vs_inferred` (`tiers-1`). |
| Dates | `temporal_tags` 1.1.0: role `program_boilerplate`, and `extras.event_kind` for events |
| Tests | `tests/conftest.py` removes an empty `caselinker.db` at session end, only if the session created it and it has no cases |
| Research | `afhq1/`: snapshot export and identity, June-id content crosswalk, fingerprint-bound citations, registry (`platforms-2`), codebook (`codebook-6`), A/B/I/C levels, harm pathways, validation, LaTeX |

## Test plan

```bash
AFH_Q1_SOURCE_DB=/path/to/caselinker.db python research/afh_q1/run_all.py --export --verify
```

```bash
DATABASE_URL='' python -m pytest -q tests/research tests/privacy tests/api tests/extraction/test_program_boilerplate_dates.py tests/extraction/test_field_assertions.py
```

- **Clean clone + Python 3.12 + PyYAML 6.0.3:** snapshot `60f7bfaa…`, outputs `identical`.
- **Tests:** see `FINDINGS.md` section 7 for the run on this commit.
- **New tests fail without their fixes:**
  - the old tagger fails 6/8 boilerplate tests;
  - removing the undercover guard, setting C to B, dropping the historical date check, or allowing a stale candidate pool each fails its test;
  - the line-wrap tests fail without the repair or the guard.

| | Before | After |
|---|---|---|
| Freshness check on the 2026-11-12 snapshot | `current` | `rebuild` (platform pairs, code) |
| May-2006 boilerplate as event dates | 2,358 cases | moved to `program_boilerplate` (3,183 dates) |
| Documented-use strict cases | 1,257 | 1,513 primary; 1,257 baseline |
| Manifest exemplar citations | 51/118 pointed at a case without that platform | 184 fingerprint-bound, all resolve; each AI-reviewed blind (136 supported) |
| Running `tests/api` then `test_field_assertions` | 10 failed | 88 passed, 10 skipped |

**Validation.** Blind AI reviewers saw masked passages and no labels. No human adjudication yet. They covered:
- 107 classification rows (κ 0.78 / 0.84 against round 1);
- 74 harm rows;
- 70 tier rows;
- 120 tier-variant rows;
- 36 inferred-facilitation rows;
- 45 promoted cases;
- all 184 manifest exemplars.

## Stored data

- `ontology/platform_affordance_evidence/platform_affordance_evidence.json` is regenerated. Its published tier is identical for all 4,680 records; it adds the line-wrap field and rule versions.
- Stored date assertions in `caselinker.db` and production keep the old roles until a re-extraction, which this PR does not run.

## Residual gaps

- No human adjudication of AI-reviewed rows.
- AI cells are small: 19 explicit generative cases (2/3 exemplars supported) and 19 likeness-synthesis cases (1/2).
- 38 registry rows have uncertain start dates. 9 concern manuscript example platforms.
- About a third of named-only records still hide offender use.
- A sentence naming two platforms can attribute conduct to the wrong one.
- The public API serves raw `evidence_quote` text (unchanged).

No linked issue. Author decisions and full results are in `research/afh_q1/FINDINGS.md`.

## Files changed against origin/main

81 files changed, 49657 insertions(+), 19744 deletions(-)

**Upstream code (CaseLinker pipeline, API)** (6)

- `M` ontology/platform_affordance_evidence/build_candidates.py
- `M` ontology/platform_affordance_evidence/platform_affordance_evidence.py
- `M` run/main.py
- `M` run/platform_affordance_evidence_freshness.py
- `M` scripts/run/rebuild_platform_affordance_evidence.py
- `M` src/Processing Layer/Pattern Processing Layer/temporal_tags.py

**Upstream derived data (regenerated)** (3)

- `M` ontology/platform_affordance_evidence/candidates.json
- `M` ontology/platform_affordance_evidence/platform_affordance_evidence.json
- `M` ontology/platform_affordance_evidence/platform_affordance_evidence_table.md

**Tests** (7)

- `A` tests/api/test_platform_affordance_evidence_build_inputs.py
- `M` tests/api/test_platform_affordance_evidence_freshness.py
- `A` tests/api/test_platform_affordance_evidence_linewrap.py
- `M` tests/conftest.py
- `A` tests/extraction/test_program_boilerplate_dates.py
- `A` tests/research/test_afh_q1_identity.py
- `A` tests/research/test_afh_q1_pipeline.py

**Research package code** (13)

- `A` research/afh_q1/afhq1/__init__.py
- `A` research/afh_q1/afhq1/build.py
- `A` research/afh_q1/afhq1/citations.py
- `A` research/afh_q1/afhq1/identity.py
- `A` research/afh_q1/afhq1/latex.py
- `A` research/afh_q1/afhq1/pipeline.py
- `A` research/afh_q1/afhq1/registry.py
- `A` research/afh_q1/afhq1/report.py
- `A` research/afh_q1/afhq1/review.py
- `A` research/afh_q1/afhq1/snapshot.py
- `A` research/afh_q1/afhq1/temporal.py
- `A` research/afh_q1/afhq1/tier_variants.py
- `A` research/afh_q1/run_all.py

**Research config (registry, codebook, reviews, sources)** (17)

- `A` research/afh_q1/config/capability_sources/games.yaml
- `A` research/afh_q1/config/capability_sources/manuscript_claims_verified.csv
- `A` research/afh_q1/config/capability_sources/messaging.yaml
- `A` research/afh_q1/config/capability_sources/social.yaml
- `A` research/afh_q1/config/capability_sources/storage_video_ai.yaml
- `A` research/afh_q1/config/capability_sources/url_check.json
- `A` research/afh_q1/config/codebook.yaml
- `A` research/afh_q1/config/platforms.yaml
- `A` research/afh_q1/config/review_exemplars.csv
- `A` research/afh_q1/config/review_round2_classification.csv
- `A` research/afh_q1/config/review_round2_harm.csv
- `A` research/afh_q1/config/review_round2_inferred.csv
- `A` research/afh_q1/config/review_round2_tiers.csv
- `A` research/afh_q1/config/review_round3_tier_variants.csv
- `A` research/afh_q1/config/review_round4_promoted_cases.csv
- `A` research/afh_q1/config/validation_adjudication.csv
- `A` research/afh_q1/config/validation_reviews.csv

**Research outputs (generated)** (24)

- `A` research/afh_q1/outputs/RUN_IDENTITY.json
- `A` research/afh_q1/outputs/TABLES.md
- `A` research/afh_q1/outputs/affordance_coverage.json
- `A` research/afh_q1/outputs/citations.json
- `A` research/afh_q1/outputs/exemplar_inventory.json
- `A` research/afh_q1/outputs/harm.json
- `A` research/afh_q1/outputs/inventory.json
- `A` research/afh_q1/outputs/june_2026_reconciliation.json
- `A` research/afh_q1/outputs/latex/tab_affordance_coverage.tex
- `A` research/afh_q1/outputs/latex/tab_inventory.tex
- `A` research/afh_q1/outputs/latex/tab_platform_manifest.tex
- `A` research/afh_q1/outputs/latex/tab_recurrence.tex
- `A` research/afh_q1/outputs/latex/tab_tier_variants.tex
- `A` research/afh_q1/outputs/latex/tab_verified_exemplars.tex
- `A` research/afh_q1/outputs/legacy_afh1_exemplars.json
- `A` research/afh_q1/outputs/manifest.json
- `A` research/afh_q1/outputs/records.csv
- `A` research/afh_q1/outputs/recurrence.json
- `A` research/afh_q1/outputs/registry_checks.json
- `A` research/afh_q1/outputs/temporal.json
- `A` research/afh_q1/outputs/tier_variants.json
- `A` research/afh_q1/outputs/validation.json
- `A` research/afh_q1/outputs/validation_round2.json
- `A` research/afh_q1/outputs/validation_sample.json

**Research docs** (10)

- `A` research/afh_q1/.gitignore
- `A` research/afh_q1/DECISION_1_TIERS.md
- `A` research/afh_q1/FINDINGS.md
- `A` research/afh_q1/PR_DESCRIPTION.md
- `A` research/afh_q1/README.md
- `A` research/afh_q1/audit_2026-11-16/README.md
- `A` research/afh_q1/audit_2026-11-16/afh-q1-audit.html
- `A` research/afh_q1/audit_2026-11-16/analyze.py
- `A` research/afh_q1/audit_2026-11-16/compare.py
- `A` research/afh_q1/audit_2026-11-16/rebuild.py

**Other** (1)

- `M` .gitignore
