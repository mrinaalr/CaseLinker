**Title:** Rebuild the AfH Q1 Platform-Affordance Manifest from a Pinned Corpus Snapshot

## Summary

Adds `ontology/platform_affordance_evidence/afh_manifest/`, which regenerates every AfH 2.0 Section 3–4 platform figure from a pinned, read-only snapshot of the 10,802-case corpus. Outputs reproduce byte for byte.

The PR also fixes three defects in the existing platform-evidence pipeline that let the published Q1 numbers drift, and masks person names in the public evidence file, which is served as a static file and so never passed through the API's masking.

| | Cases | Basis |
|---|---:|---|
| Reference a platform or platform category | 3,080 | any label except "online" / "internet" |
| Identify a specific named platform (paper's analytic set) | 1,863 | 52 named platforms |
| Stated platform-use evidence | 1,322 | platform tied to offense conduct in one sentence |
| Weaker co-occurrence evidence | 187 | platform and offense language in one sentence, no instrumental link |
| Both tiers | 1,509 | original rules: 1,257 |

## Need

AfH 1.0's Q1 figures could not be regenerated:
- The published evidence file was built from a 23-day-old candidate list (3,183 cases listed, 3,083 live), and the freshness check passed it.
- 51 of 118 cited harm examples used case ids that had since been renumbered.
- The six CAC affordance classes were never assigned to cases.
- Platform capability dates had no sources.

## Counts

**Cases**

| Step | Removed | Remaining |
|---|---:|---:|
| Corpus | | 10,802 |
| No platform label | 4,384 | 6,418 |
| Only "online" or "internet" | 3,334 | |
| Platform appears only in a PSA, or a Gen AI mention is page decoration | 4 | 3,080 |
| Only a generic category ("social media", "chat") | 1,096 | |
| Only "Gen AI" (a technology, not a platform) | 70 | |
| Only an ambiguous label ("Webcam platform", "Mega") | 51 | **1,863** |
| Stated platform-use evidence | | 1,322 |
| Weaker co-occurrence evidence | | 187 |
| Platform named only | | 354 |

**Distinct labels**

| Step | Removed | Remaining |
|---|---:|---:|
| Labels in `platforms_used` | | 59 |
| "online", "internet" | 2 | 57 *(labels on the map)* |
| Generic ("social media", "chat") | 2 | |
| Technology ("Gen AI") | 1 | |
| Ambiguous ("Webcam platform", "Mega") | 2 | **52 named platforms** |

**Platform-case pairs**

| Step | Removed | Remaining |
|---|---:|---:|
| Pairs in `platforms_used` | | 11,024 |
| "online", "internet" | 6,322 | 4,702 |
| Gen AI page decoration | 1 | |
| Platform only after a PSA boundary | 21 | 4,680 *(all labels)* |
| Generic, technology or ambiguous labels | 2,193 | **2,487** *(named platforms)* |

**Six affordance classes**, distinct cases on the 1,863 named-platform set:

| Class | Available | Capability-relevant conduct | Inferred facilitation | Explicit use |
|---|---:|---:|---:|---:|
| Distribution infrastructure | 1,845 | 945 | 655 | 509 |
| Unmonitored communication | 1,676 | 513 | 399 | 23 |
| Anonymity | 1,653 | 457 | 373 | 23 |
| Contact discovery | 1,691 | 508 | 38 | 10 |
| Ephemerality | 926 | 361 | 181 | 0 |
| Generative synthesis | 651 | 71 | 1 | 1 |

Generative synthesis is almost entirely recorded under the "Gen AI" technology label. On the extended 1,984-case set (named platforms + Gen AI + ambiguous labels) it is 733 / 136 / 66 / 20. The paper should footnote it from that set. Both tables are in `outputs/affordance_coverage.json`.

## Design

- **Snapshot.** Read-only export from the corpus DB. `dataset_identity` hashes every case's id, content fingerprint, text, platforms, topics, source and year. `run_all.py --verify` regenerates everything and compares against `RUN_IDENTITY.json`.
- **Evidence tiers.** The existing sentence rules, plus an additive hard-wrap repair (`tiers-1+linewrap-3`) that never demotes. It refuses a promotion earned only by agency social-media or reporting-duty boilerplate that names that platform ("In a Facebook post, the sheriff's office said…" refuses Facebook, not the Kik use in the same sentence). Every downstream level reads the same tier (`Record.primary_tier`). The original-rule result is kept as a baseline.
- **Affordance levels.** Each is a subset of the one before:
  - available (native in the case's publication year, from a dated registry);
  - capability-relevant documented conduct;
  - inferred facilitation (the feature is on for every use by design);
  - explicit instrumental use.
  - For anonymity and ephemerality, inferred facilitation is reported as "present by design", because the review did not support "facilitated" for those classes.
- **Harm.** Potential (an AfH ψ(a) pathway is open) and documented (harm stated in the release) are reported separately. Possessing AI-generated material is counted apart from synthesizing a child's likeness.
- **Registry.** 216 capability rows, each with a native/partial/no value, a by-design flag, a first-available date, a confidence level and dated sources. The 25 platform-history claims the manuscript relies on were checked on fetched pages: 23 confirmed, 2 corrected.
- **Citations.** Every exemplar is bound to its case's content fingerprint, so a renumbered id cannot redirect it silently.
- **Person names.** Every string the builder copies from a release (quote, harm, reasoning preview, PSA sample, db-gap snippet) is masked with `[PERSON]` from the case's stored person spans, as case pages do, plus a by-name pass for fragments cut from joined lines. Masking runs after classification. Spans that are exactly a platform name ("Grindr", "Skout" are sometimes stored as people) are not masked.

## Changes to existing code

| File | Change |
|---|---|
| `run/platform_affordance_evidence_freshness.py`, `run/main.py` | A snapshot is current only if corpus identity, every `(case, platform)` pair and the builder's code hashes match. The API reads the same identity. |
| `ontology/platform_affordance_evidence/platform_affordance_evidence.py`, `build_candidates.py`, `scripts/run/rebuild_platform_affordance_evidence.py` | Candidates are recomputed on every build. Records gain `stated_vs_inferred_linewrap`; `stated_vs_inferred` is unchanged for all 4,680 records. Copied release text is masked (see Design). |
| `run/main.py` | `/ontology/platform-affordance-evidence/` serves only its two public JSON files. It was a directory mount, which also served the builder, candidates and the manifest folder, including a local snapshot with full release text. |
| `scripts/verify/scan_public_surfaces_for_names.py` | Scans every per-platform evidence cohort and both static evidence files, each item against its own case's people. |
| `src/Processing Layer/Pattern Processing Layer/temporal_tags.py` | 1.1.0: program-history dates ("launched in May 2006", 2,358 cases) get role `program_boilerplate`, and event dates get `event_kind`. Applies at the next extraction. |
| `visualization/visualization.html` | The Platforms tile shows named platforms (52); the map still shows all 57 labels. |
| `tests/conftest.py` | Removes an empty `caselinker.db` left by importing `run/main.py`, so a later run skips the corpus tests instead of failing them. |

## Effect on the deployed site

- **`/visualization` and `/questions/q01`:** same layout. Counts come from the regenerated evidence file:

  | Tile | Before | After |
  |---|---:|---:|
  | Cases processed | 3,183 | 3,083 |
  | Platforms | 56 (labels) | 52 named |
  | Case–platform pairs | 5,022 | 4,680 |

  Per-platform stated counts rise (Kik 299 → 353, Snapchat 235 → 287). Instagram and Twitter / X totals fall (240 → 151, 240 → 107), because footer "follow us" links no longer count.
- **Evidence quotes** in the platform panels and `/analysis` show `[PERSON]` where a release names a person: 1,466 of 4,680 records and 2,279 of 7,250 db-gap snippets change.
- **Harm vectors panel:** unchanged; it reads `platform_affordance_evidence_harm_analysis.json`, which this PR does not touch.
- **`/api/platform-affordance-evidence`:** freshness reports `stale` if production `platforms_used` differs from the snapshot.
- **`/ontology/platform-affordance-evidence/<other file>`:** now 404.

## Test plan

| What | Command | Result |
|---|---|---|
| Regenerate from a fresh clone (Python 3.12, PyYAML 6.0.3) | `AFH_Q1_SOURCE_DB=… python ontology/platform_affordance_evidence/afh_manifest/run_all.py --export --verify` | snapshot `60f7bfaa…`, `identical` (verified) |
| Q1 and changed-module tests | `DATABASE_URL='' python -m pytest -q tests/research tests/privacy tests/api tests/extraction/test_program_boilerplate_dates.py tests/extraction/test_field_assertions.py` | 343 passed, 34 skipped (verified) |
| Full repository | every `tests/**/test_*.py` in its own process | 89 files: 775 passed, 35 skipped, 0 failed (verified) |
| Privacy gate | `scripts/verify/scan_public_surfaces_for_names.py --sqlite <copy> --cases 500` | PASS, 0 surfaces with a person name: 500 case and 500 assertion responses, 2,643 disagreement items, 4,568 per-platform evidence items, 11,703 items in the static evidence file, stats, facet, triage and index endpoints, stored entity lists for 10,452 cases. On the previous evidence file the same scan fails with 1,488 items. `automated-analysis` returned 503 locally and was not scanned. (verified) |
| No stored person name in the evidence file | `CASELINKER_DB=… pytest tests/api/test_platform_affordance_evidence_masking.py` | 0 of 4,680 records, 0 of 21 exclusions, 0 of 7,250 db-gap snippets hold a name from the case's stored spans; before: 1,412 records and 2,140 snippets. Only the 5 text fields differ from the unmasked build. (verified) |
| Outputs carry no release text | `test_outputs_hold_no_source_text` | no 25+ character output string appears in any release (verified) |
| Tests fail without their fix | revert each fix | the old tagger fails 6/8 date tests; a stale candidate pool and a changed builder are reported stale; a line-wrap-only promotion fails to reach downstream levels; the undercover guard, the historical date check and explicit-use ≠ conduct each fail their test; the old builder and file fail 13 of the 14 masking and routing tests, and the linewrap-2 guard fails 4 of the 12 line-wrap tests (verified) |

**Validation of classifications.** Blind AI reviewers read masked passages without classifier labels; the author agent adjudicated disagreements. No human adjudication.

| Sample | Rows | Result |
|---|---:|---|
| Classification | 107 | κ 0.78 (explicit use), 0.84 (tiers) between two reviewers |
| Line-wrap promoted cases | 45 of 269 | 39 offender use; about 96% after the boilerplate guard (measured under linewrap-2) |
| Random stated / co-occurrence records | 15 / 15 | 13 and 14 offender use; 4 and 5 of those known through a platform report |
| Inferred facilitation | 36 | reasonable: generative 6/6, unmonitored 5/6, contact 4/6; anonymity and ephemerality 0/6 |
| Harm cues | 74 | direct cues 67–100% precise by harm |
| Manifest exemplars | 201 | 144 supported |

## Manual review

- [ ] **Evidence tiers and denominators.** 1,509 = 1,322 stated + 187 weaker co-occurrence. Report the two separately and keep 1,257 as the original-rule baseline; the 187 are not established offender use. Validation rates rest on AI-reviewed samples of 3–45 rows per cell.
- [ ] **Analytic sets.** Paper tables use the 1,863 named-platform set. Generative synthesis is reported from the extended 1,984-case set (adds Gen AI and ambiguous labels) as a footnote. Both are in `outputs/affordance_coverage.json`.
- [ ] **Dates.** The timeline is publication year, not offense date. 38 registry rows have uncertain start dates (9 on manuscript example platforms), underlying 13–17% of anonymity, contact and unmonitored "available" counts.
- [ ] **Legacy harm-analysis file.** `platform_affordance_evidence_harm_analysis.json` holds 118 case references: 56 resolve correctly, 48 point to different records, 13 are unresolved, 1 is name-only. Case IDs shifted; the analysis was not wrong. This PR does not modify the file. Decide before deployment whether to repair it (via `outputs/legacy_afh1_exemplars.json`) or suppress the affected references.
- [ ] **API freshness.** After deployment `/api/platform-affordance-evidence` reports `stale` unless production `platforms_used` matches the snapshot. Decide whether to rebuild production first or accept the disclosure.
- [ ] **Snapshot archive.** The snapshot (`sha256 8dfc22b1…`, 43 MB, full release text) is gitignored. After the next corpus rebuild only an archived copy reproduces these figures; `--verify` needs only the file. Choose a restricted-access deposit (e.g. a restricted Zenodo record) and cite its sha256. Details: manifest README, "Snapshot archive".
- [ ] **Names on the live site and in git history.** The evidence file on `main`, which the deployed site serves today, holds stored person names in 1,184 of 5,022 records and 2,209 of 7,649 snippets. Deploying this PR removes them from the site. Earlier commits of the file still hold them; removing them from history needs a rewrite, which is a separate decision.
- [ ] **Merge order.** `build_candidates.py` imports `ai_extraction_patterns.py`, which #94 and #98 change (#99 does not). Rebuilt with both merged in, the evidence file and every Q1 output are identical; only code hashes change. Whichever lands later needs the evidence file and `RUN_IDENTITY.json` regenerated (`rebuild_platform_affordance_evidence.py`, then `run_all.py`).
- [ ] **Merge vs deploy.** Merging makes the Q1 manifest reproducible from the repository. Deploying additionally needs the legacy-file and freshness decisions; stored date assertions keep their old roles until the next extraction run.

## Residual gaps

- **Validation.** All of it is AI review on 3–45 rows per cell.
- **Coverage, not prevalence.** Counts reflect enforcement-report coverage. 84% of cases are from 2021–26, and the source mix changes by era.
- **AI cells.** 20 explicit generative-use and 20 likeness-synthesis cases on the extended set; exemplars 2/3 and 1/3 supported.
- **Platform attribution.** A sentence naming two platforms can attribute conduct to the wrong one. About a third of named-only records still describe offender use the rules miss.
- **Masking.** Two quotes over-mask a non-person word a stored span covers (an app and a newspaper name). Case pages still mask platform names that are stored as person spans ("Grindr", "Skout"); that is a `people_mask` issue outside this PR.




