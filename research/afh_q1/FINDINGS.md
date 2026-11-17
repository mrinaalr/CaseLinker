# AfH 2.0 Q1: final local review packet

Branch `research/afh-q1-reconstruction` (local, not pushed). Frozen corpus snapshot `60f7bfaa…d06b` (10,802 cases, 78 sources). Rules:
- platform registry `platforms-2`
- codebook `codebook-6`
- evidence tiers `tiers-1` (original baseline) and `tiers-1+linewrap-2` (primary)

Every number here is read from [outputs/](outputs/): [TABLES.md](outputs/TABLES.md) has the full tables, and [outputs/latex/](outputs/latex/) has booktabs versions. The manuscript is unchanged. No database, Railway or graph store was written.

**Who checked what.** All case-level validation below was done by blind AI reviewers: separate agent instances reading masked passages, with no access to the classifier's labels. Disagreements were adjudicated by the author agent. **No row has yet been checked by a human.** "Supported" therefore means "an independent AI reviewer judged it supported", not human-verified. The 25 platform-history claims were checked by an AI agent on fetched, dated pages.

## 1. Evidence levels

| Level | Meaning | Paper wording |
|---|---|---|
| A available capability | The platform offered the feature natively in the case's publication year (dated registry) | "available" |
| B capability-relevant conduct | Documented platform use for conduct of the kind the feature bears on | "documented … conduct on a platform with …" |
| I inferred facilitation | B on a platform where the feature is on for every use by design | Anonymity, Ephemerality: **"present by design"**. Unmonitored, Generative, stranger-meeting Contact: "facilitated" (reviewer judged the inference reasonable in 5/6, 6/6, 4/6). Distribution: "present by design" (1/6). |
| C explicit instrumental use | The release states the feature-specific behaviour in a sentence naming the platform | "documented use of …" |
| Harm: potential / documented | Potential: an AfH ψ(a) pathway is open (B or I). Documented: a harm cue in the release. | Potential harms are never written as outcomes. |

Levels nest: A ⊇ B ⊇ I ⊇ C. A low C reflects what press releases spell out. It is not evidence that a capability played no role, and it is not a test of the AfH argument.

## 2. Final six-affordance table

Assessed cases: 1,984. Distinct cases, with platform-case observations in brackets. Classes overlap. File: `latex/tab_affordance_coverage.tex`.

| Class | A available | B relevant conduct | I inferred facilitation | C explicit use | Platforms at C |
|---|---|---|---|---|---|
| Anonymity | 1,782 (2,306) | 412 (466) | 338 (370) | 22 (23) | 6 |
| Ephemerality | 926 (1,197) | 322 (365) | 177 (178) | 0 | 0 |
| Contact discovery | 1,798 (2,373) | 454 (522) | 30 (30) | 9 (9) | 4 |
| Unmonitored communication | 1,729 (2,314) | 459 (532) | 360 (380) | 22 (24) | 8 |
| Distribution infrastructure | 1,898 (2,525) | 802 (914) | 544 (608) | 437 (487) | 28 |
| Generative synthesis | 733 (902) | 121 (126) | 54 (54) | 19 (19) | 1 |

**Why some counts exceed 1,863.** The affordance tables use 1,984 assessed cases: the 1,863 strict cases, plus 70 whose only assessed label is "Gen AI" and 51 whose only one is an ambiguous alias ("Webcam platform", "Mega"). A case can count in several classes.

**Recurrence.** "Recurs" means at least 20 cases, 3+ platform families and 2+ publication eras, each with 2+ cases (`latex/tab_recurrence.tex`).

| Class | Recurs at | Note |
|---|---|---|
| Distribution | A, B, I, C | |
| Anonymity | A, B, I, C | C: 22 cases, 3 families, 3 eras |
| Unmonitored communication | A, B, I | |
| Contact discovery | A, B, I | |
| Ephemerality | A, B | Native ephemeral messaging starts in 2011 |
| Generative synthesis | none across eras | Public tools date from 2017 and 2022 |

## 3. Section 3: corpus and evidence-tier counts

File: `latex/tab_inventory.tex`.

| Measure | Cases | Platform-case observations |
|---|---|---|
| Corpus | 10,802 | – |
| Any platform label (broad; includes "social media", "chat") | 3,080 | 4,680 (57 labels) |
| Specific named platform (strict) | 1,863 | 2,487 (52 labels) |
| **Documented use, primary (line-wrap repair)**: stated 1,322 + inferred-only 191 | **1,513** | 1,834 |
| Documented use, original-rule baseline: stated 1,080 + inferred-only 177 | 1,257 | 1,477 |
| Named only (primary / baseline) | 350 / 606 | 653 / 1,010 |
| Generic category only | 1,096 | – |

**How the primary count was validated.**
- **Before the guard:** a blind review of 45 of the 269 cases the repair promoted, oversampling social platforms, found 39 with offender use. All 6 misses were agency social-media boilerplate.
- **The guard (`linewrap-2`)** refuses a promotion earned only by an agency's page, post, footer links or post URL. It blocked 4 of those 6 and none of the 39 true promotions.
- **After the guard:** 256 cases are promoted, giving 1,513. Estimated precision is about 96% (strata 14/16 social, 25/25 other; conservative lower bound about 80%).
- **Never demotes:** the repair is additive, so no record loses the tier the original rules gave it.
- **Remaining undercount:** in an earlier random sample, the rules still miss offender use in about a third of named-only records, so 1,513 is still a lower bound.

The full comparison is in `DECISION_1_TIERS.md` and `outputs/tier_variants.json`:

| Rule | Documented-use cases |
|---|---|
| A original | 1,257 |
| B plain repair | 1,486 |
| B+ additive, no guard | 1,526 |
| **B+ additive, guarded (primary)** | **1,513** |
| C extra verbs only | 1,398 |
| D repair + verbs | 1,577 |

## 4. Section 4: manifest and LaTeX

- **Manifest:** 34 platforms with at least 3 documented-use cases (`outputs/manifest.json`). Each entry has its dated capability profile, cases by tier, conduct mix, A/B/I/C per class, harm counts and fingerprint-bound exemplars. Citation check: 184/184 resolve to the same content.
- **LaTeX tables:** `tab_inventory`, `tab_affordance_coverage`, `tab_recurrence`, `tab_platform_manifest` (top 15), `tab_tier_variants`, `tab_verified_exemplars`. They compile with pdflatex, and a test checks this. Each carries its denominator in a comment. The "How to read each table" section of `TABLES.md` gives, for every table, the denominator, unit, whether generic labels and overlaps are included, and whether it describes availability or use.

**Misuse → harm, observed vs potential.** Counts are cases with the harm cue in a platform sentence, at the I and C levels.

| Pathway | At I | At C | Label |
|---|---|---|---|
| Distribution → material distributed | 497 | 431 | Observed. Class and harm share verbs, so count once. |
| Anonymity → sextortion | 13 | 6 | Observed examples |
| Unmonitored → sextortion | 10 | 1 | Observed examples at I |
| Unmonitored → coerced imagery | 8 | 0 | Observed examples at I |
| Ephemerality → coerced imagery / sextortion | 10 / 4 | 0 | Potential: present by design; no release describes disappearing content |
| Contact discovery → grooming | 0 | 0 | Potential (103 case-level co-occurrences) |
| Generative → likeness synthesized | 19 | 19 | Small; see section 8 |

## 5. Source-verified exemplar inventory

184 exemplars, each with its blind-review verdict (`outputs/exemplar_inventory.json`; supported ones in `latex/tab_verified_exemplars.tex`). **136 were judged supported by an AI reviewer. None are human-verified.**

| Cited for | Supported | Partly | Not |
|---|---|---|---|
| Distribution (explicit use) | 54 | 10 | 3 |
| Unmonitored communication | 13 | 1 | 1 |
| Anonymity | 12 | 1 | 1 |
| Contact discovery | 5 | 0 | 2 |
| Generative synthesis | 2 | 0 | 1 |
| Harm: material distributed | 37 | 11 | 9 |
| Harm: sextorted | 7 | 3 | 2 |
| Harm: coerced self-generated | 3 | 0 | 0 |
| Harm: groomed toward in-person | 2 | 2 | 0 |
| Harm: likeness synthesized | 1 | 0 | 1 |

Cite only "supported" rows, after a human read.

## 6. Codebook and platform registry

**Codebook** (`config/codebook.yaml`, `codebook-6`). Each class has a definition, conduct categories, explicit-use cues and guards. The guards cover undercover-officer personas, app descriptions, AI used for detection, passive or possession AI wording, statute and capability statements, and "undress" alone. Harm cues: h1, h2, h3, h4 and h6.
- **AI rule:** possession or sharing of AI-generated material is counted separately as "AI material" (43 cases, 31 without creation). It is never counted as synthesis.
- **Synthesis rule:** synthesis needs creation or alteration language, an AI instrument, and an actor in the case. A test checks the possession case directly.

**Registry** (`config/platforms.yaml`, generated from `config/capability_sources/`):
- 59 labels.
- 216 capability rows: 87 documented, 91 approximate, 38 uncertain.
- 217 cited URLs: 185 resolve, 28 are bot-blocked, 2 dead, 2 timed out.
- Coding rules: ephemerality and generative synthesis count only fully native features; contact discovery is "by design" only on stranger-meeting platforms.

**25 manuscript-relevant claims** (`config/capability_sources/manuscript_claims_verified.csv`) were checked on fetched, dated pages: 23 confirmed, 2 corrected.
- Kik discoverable hashtag groups date from 2014-12.
- Dropbox had a Public folder and shared folders in 2008; per-file links came in 2012-04.

## 7. Reproducibility and test results

Run from the repository root.

1. Fresh clone of the local branch:

```bash
git clone --branch research/afh-q1-reconstruction /path/to/CaseLinker CaseLinker-q1
```

2. Minimal environment:

```bash
python3.12 -m venv .venv-q1 && .venv-q1/bin/pip install PyYAML==6.0.3
```

3. Regenerate and verify every output against `RUN_IDENTITY.json` (needs read access to the frozen corpus DB):

```bash
AFH_Q1_SOURCE_DB=/path/to/caselinker.db .venv-q1/bin/python research/afh_q1/run_all.py --export --verify
```

4. Tests, which need pytest and the repo requirements:

```bash
DATABASE_URL='' python -m pytest -q tests/research tests/privacy tests/api tests/extraction/test_program_boilerplate_dates.py tests/extraction/test_field_assertions.py
```

Results:
- **Clean clone:** snapshot `60f7bfaa…` and `identical`. That covers the frozen corpus identity, inventory, registry, six-affordance table, temporal tables, exemplars, LaTeX and every output hash.
- **Tests:** 226 passed, 23 skipped in the worktree.
- **Privacy:**
  - no output string of 25 or more characters appears in any release;
  - reviewer notes stay in `config/` CSVs only;
  - masked review sheets stay in the gitignored `research/afh_q1/data/`.
- **Test-order interference (fixed):** importing `run/main.py` creates an empty `caselinker.db`. `tests/conftest.py` now removes it at session end, but only if it didn't exist at start and holds zero cases. The corpus-dependent tests then skip correctly on the next run.

## 8. Remaining uncertainties

- **No human adjudication yet.** All case-level checks are AI-reviewed; sample sizes per cell are 3–45, so intervals are wide.
- **AI cells are small.** Explicit generative use is 19 cases with 2/3 exemplars supported; likeness synthesis is 19 cases with 1/2 supported. Read before citing. Do not claim identity-based likeness synthesis beyond the supported example.
- **Uncertain registry rows.** 38 rows have uncertain start dates (the feature is native; the date falls back to the launch year). They underlie 17% of Anonymity, 13% of Contact and 17% of Unmonitored A cases, but no Ephemerality or Generative cases.
  - 9 concern manuscript example platforms: Instagram and TikTok contact discovery; TikTok, Reddit and Roblox messaging; Whisper discovery; Dropbox anonymity; both Webcam rows.
  - Since 84% of cases are from 2021–26, a wrong start year affects few cases (`registry_checks.json` → `uncertain_impact`).
- **Attribution errors.** A sentence naming two platforms can attribute conduct to the wrong one (Grindr first contact, Kik distribution). Uploads to cloud storage can count as distribution without sharing shown.
- **Remaining undercount.** About a third of named-only records still hide offender use.
- **Coverage, not prevalence.** Enforcement reports, a publication-year timeline and a changing source mix.
- **Outside this branch.** The public API still serves raw `evidence_quote` text, and stored date roles in the databases are unchanged (no re-extraction).

## 9 and 10. Diff summary and PR description

See `PR_DESCRIPTION.md`: the proposed title, body and exact list of files changed against `origin/main`.
