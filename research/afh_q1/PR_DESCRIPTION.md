**Title:** rebuild AfH 2.0 Q1 platform-affordance manifest from a pinned corpus snapshot

## Summary

Adds `research/afh_q1/`, which builds the AfH 2.0 Section 3–4 manifest from a pinned, read-only snapshot of the 10,802-case corpus. Results:

| Measure | Value |
|---|---|
| Cases naming a specific platform | 1,863 (2,487 platform-case observations) |
| Cases documenting platform use | **1,513** with the line-wrap repair (primary); 1,257 under the original rules (baseline) |
| Six CAC affordance classes | Counted at four nested levels: available capability, capability-relevant conduct, inferred facilitation, explicit use |
| Harm pathways | Observed and potential, reported separately |
| Platform registry | 216 capability rows with dated sources |
| Exemplars | 184 fingerprint-bound; each blind-reviewed |
| LaTeX tables | 6, booktabs |

Also fixes four defects in the existing pipeline that the Q1 audit found.

## Root cause

| Defect | Cause | Effect |
|---|---|---|
| Stale evidence snapshot | The builder read `candidates.json` from disk; freshness compared only case count and extraction-run fingerprint | The 2026-11-12 snapshot passed while built from a 23-day-old candidate list (3,183 vs 3,083 live) |
| Program boilerplate as case dates | `temporal_tags` had no rule for program-history sentences | "launched in May 2006" was an event date in 2,358 cases |
| Undercounted platform use | Press releases are hard-wrapped; verb and platform reached `classify_sentence` as separate fragments | 25 of 40 sampled named-only records document use |
| Test-order failures | Importing `run/main.py` creates an empty `caselinker.db` | Later runs fail the DB-dependent extraction tests instead of skipping them |

## Fix

- **Freshness** (`run/platform_affordance_evidence_freshness.py`, `platform_affordance_evidence.py`, `build_candidates.py`, `rebuild_platform_affordance_evidence.py`, `run/main.py`):
  - candidates are recomputed from the DB on every build;
  - a snapshot is current only if corpus identity, every `(case, platform)` pair and the builder code hashes all match;
  - the API uses the same check.
- **Tiers** (`platform_affordance_evidence.py`):
  - `repair_line_wraps` joins mid-sentence wraps;
  - `linewrap_tiers` takes the better of the original and repaired tier, and refuses promotions earned only by agency social-media boilerplate;
  - records keep `stated_vs_inferred` (`tiers-1`, unchanged) and add `stated_vs_inferred_linewrap` (`tiers-1+linewrap-2`).
- **Dates** (`temporal_tags.py` 1.1.0): adds role `program_boilerplate`, and gives event dates `extras.event_kind` (offense, investigation, arrest, prosecution, unknown).
- **Tests** (`tests/conftest.py`): at session end, removes a `caselinker.db` that the session created and that holds no cases.
- **Research package** (`research/afh_q1/`):
  - snapshot export and identity;
  - content crosswalk for June 2026 case ids;
  - fingerprint-bound citations;
  - platform registry (`platforms-2`, generated from `config/capability_sources/`);
  - codebook (`codebook-6`);
  - classification, harm, validation, LaTeX;
  - docs: `FINDINGS.md`, `DECISION_1_TIERS.md`, `README.md`.

## Test plan

Regenerate and verify every output against `RUN_IDENTITY.json` (Python 3.12 and PyYAML 6.0.3 only):

```bash
AFH_Q1_SOURCE_DB=/path/to/caselinker.db python research/afh_q1/run_all.py --export --verify
```

Run the tests:

```bash
DATABASE_URL='' python -m pytest -q tests/research tests/privacy tests/api tests/extraction/test_program_boilerplate_dates.py tests/extraction/test_field_assertions.py
```

- **Fresh clone:** snapshot `60f7bfaa…`, outputs `identical`; 322 passed, 33 skipped.
- **Tests that fail without their fix:**
  - the old tagger fails 6/8 boilerplate tests;
  - a candidate pool changed in place is reported stale;
  - removing the undercover guard, setting explicit use equal to conduct, or dropping the historical date check each fails its test;
  - the line-wrap tests fail without the repair or the guard.

| | Before | After |
|---|---|---|
| Freshness check on the 2026-11-12 snapshot | `current` | `rebuild` |
| Program-history dates | tagged as events (May 2006 in 2,358 cases) | 3,183 dates moved to `program_boilerplate` |
| Strict cases documenting use | 1,257 | 1,513 primary, 1,257 baseline |
| Manifest exemplar citations | 51 of 118 pointed at a case without that platform (bare ids) | 184 bound to content fingerprints, all resolve |
| `tests/api`, then `test_field_assertions` | 10 failed | 88 passed, 10 skipped |

**Validation.** Blind AI reviewers saw masked passages and no labels. The promoted-case sample reached about 96% estimated precision after the guard (14/16 social, 25/25 other; conservative lower bound 80%).

| Sample | Rows |
|---|---|
| Classification (κ 0.78 / 0.84 against round 1) | 107 |
| Harm | 74 |
| Evidence tiers | 70 |
| Tier variants | 120 |
| Inferred facilitation | 36 |
| Promoted cases | 45 |
| Manifest exemplars | 184 |

## Stored data

- `ontology/platform_affordance_evidence/platform_affordance_evidence.json` is regenerated. `stated_vs_inferred` is identical for all 4,680 records; it adds `stated_vs_inferred_linewrap` and rule versions in `_meta`.
- Date assertions already stored in `caselinker.db` and production keep their old roles until the next extraction run. This PR does not re-extract.

## Residual gaps

- **No human adjudication yet.** All validation is AI review; per-cell samples are 3–45 rows.
- **AI cells are small.** 19 explicit generative-use cases and 19 likeness-synthesis cases; exemplars are 2/3 and 1/2 supported.
- **Uncertain registry dates.** 38 capability rows have an uncertain start date; 9 are on platforms the manuscript uses as examples. They underlie 13–17% of Anonymity, Contact discovery and Unmonitored availability counts.
- **Remaining undercount.** About a third of named-only records still describe offender use the rules miss.
- **Platform attribution.** A sentence naming two platforms can attribute conduct to the wrong one.
- **Public API.** It still serves raw `evidence_quote` text.

Files changed: 81 (`git diff --stat origin/main`), 0 under `ontology/graph_output/`.
