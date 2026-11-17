<!-- Proposed PR, for review before anyone opens it. Branch: research/afh-q1-reconstruction -->

**Title:** rebuild AfH 2.0 Q1 platform-affordance manifest from a pinned corpus snapshot

## Summary

- Adds `research/afh_q1/`: a reproducible pipeline from a pinned, read-only snapshot of the 10,802-case corpus to the AfH 2.0 Section 3–4 manifest. It covers:
  - platform presence: 1,863 strict cases / 2,487 platform-case observations;
  - documented use: 1,257 under the original rules, 1,526 with line-wrap repair;
  - six-class coverage at four nested evidence levels;
  - recurrence, observed vs potential harm pathways;
  - a blind-verified exemplar inventory;
  - booktabs LaTeX tables.
- Replaces hand-entered platform capability years with dated, sourced research: 216 capability rows, and 25 manuscript claims checked on fetched pages.
- Fixes three upstream defects the audit found:
  - the Q1 freshness gate missed a stale candidate list;
  - program-launch boilerplate was tagged as case event dates;
  - hard-wrapped releases hid documented platform use from the tier rules.

## Root cause

1. **Stale snapshot.** `platform_affordance_evidence.py` read `candidates.json` from disk. Freshness compared only the corpus case count and extraction-run fingerprint, so the 2026-11-12 snapshot passed while built from a 23-day-old candidate list (3,183 listed vs 3,083 live).
2. **Case ids.** Ids before #38 were positional. 924 of 976 content-matched June NCMEC ids now name different releases, and 919 more ids moved between the 2026-10-20 backup and now. Citations by bare id broke: 51 of 118 manifest exemplars.
3. **Dates.** `temporal_tags` tagged "Project Safe Childhood, a nationwide initiative launched in May 2006" as an event date in 2,358 cases.
4. **Tiers.** Press-release PDFs are hard-wrapped. "Communicated with a 15-year-old\nvia Discord" reached `classify_sentence` as two fragments. 25 of 40 sampled named-only records document use.
5. **Capabilities.** Platform affordance years were compiled without sources, and the six classes were assigned per case only in hand-coded PACER graphs.

## Fix

| Area | Change |
|---|---|
| Freshness | The builder recomputes candidates from the DB on every run. `_meta` records `platform_pairs_sha256`, `candidate_pool_sha256` and `code_versions`. `identity_matches` requires all of them; `read_live_identity` is portable to Postgres and used by the API. |
| Tiers | `repair_line_wraps` and `linewrap_tiers` (additive). Records carry `stated_vs_inferred_linewrap` beside the unchanged `stated_vs_inferred` (`tier_rules_version: tiers-1`). |
| Dates | `temporal_tags` 1.1.0: role `program_boilerplate`, and `extras.event_kind` (offense, investigation, arrest, prosecution, unknown) for events |
| Research | `afhq1/` snapshot export and identity, content crosswalk for June ids, fingerprint-bound citations, platform registry (`platforms-2`), six-class codebook (`codebook-5`), A/B/I/C levels, harm pathways, validation, LaTeX |

## Test plan

```bash
python research/afh_q1/run_all.py --export --verify
```

```bash
DATABASE_URL='' python -m pytest -q tests/research tests/privacy tests/extraction/test_program_boilerplate_dates.py tests/api/test_platform_affordance_evidence_build_inputs.py tests/api/test_platform_affordance_evidence_linewrap.py tests/api/test_platform_affordance_evidence_freshness.py
```

- **Reproduction:** a fresh clone with Python 3.12 + PyYAML 6.0.3 only exports snapshot `60f7bfaa…` and gives `identical` outputs.
- **Tests:** 138 passed in the clean clone. Extraction: `test_field_assertions` + `test_date_and_sentence_extraction` give 96 passed, 10 skipped.
- **Each new test fails without its fix:**
  - the old tagger fails 6 of 8 boilerplate-date tests;
  - removing the undercover guard, setting C to B, or dropping the historical date check each fails its test;
  - an old-style snapshot is reported as stale.
- **Before and after:**

| | Before | After |
|---|---|---|
| Freshness check on the 2026-11-12 snapshot | `current` | `rebuild` (mismatch: platform pairs, code) |
| May-2006 boilerplate tagged as event | 2,358 cases | moved to `program_boilerplate`: 3,183 dates |
| Documented-use strict cases | 1,257 | 1,257 published; 1,526 with line-wrap repair |
| Manifest exemplar citations | 51 of 118 pointed at a case without that platform (bare ids) | 185 bound to content fingerprints, all `ok`; each blind-reviewed |

- **Validation:** blind reviewers (masked passages, no labels) covered:
  - the 107-row classification sample: κ 0.78 / 0.84 against round 1;
  - a 74-row harm sample;
  - a 70-row tier sample;
  - a 120-row tier-variant sample;
  - a 36-row inferred-facilitation sample;
  - all 185 manifest exemplars.
- **Privacy:** outputs hold ids, hashes, offsets and counts. A test asserts no 25+ character output string appears in any release. Masked review sheets stay in gitignored `research/afh_q1/data/`.

## Stored data

- `ontology/platform_affordance_evidence/platform_affordance_evidence.json` is regenerated. Its published tier is identical for all 4,680 records; it adds the line-wrap field and rule versions.
- Stored date assertions in `caselinker.db` and production keep the old roles until the next extraction run. This PR does not re-extract.

## Residual gaps

- 38 registry rows are `uncertain`. Most cited URLs were checked for reachability only; the 25 manuscript claims were read in full, and 2 were corrected.
- Explicit use is precise but sentence-local. A sentence naming two platforms can attribute conduct to the wrong one (Grindr first contact, Kik distribution).
- Generative synthesis and likeness-synthesis cells are small (19 cases). Exemplars are 2/3 and 1/3 supported, so they need human adjudication before citing.
- Line-wrap false promotions are mostly Facebook/YouTube boilerplate (7 of 8); no filter is added here.
- `tests/privacy` and `tests/api` create an empty `caselinker.db` in a checkout without one. The DB-dependent extraction tests then fail instead of skipping. This predates the branch.
- Reviewers were AI agents; no human adjudication yet.
- The public API serves raw `evidence_quote` text from the evidence file; unchanged here.

No linked issue. Decisions for the authors are listed in `research/afh_q1/FINDINGS.md`.
