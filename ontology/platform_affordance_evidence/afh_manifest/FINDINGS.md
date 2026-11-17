# AfH 2.0 Q1: final local review packet

**Scope.** Branch `research/afh-q1-reconstruction` (local, not pushed), working from frozen corpus snapshot `60f7bfaa…d06b` (10,802 cases, 78 sources). Nothing outside this repository was touched: no manuscript, database, Railway or graph store.

**Versions.**

| Component | Version |
|---|---|
| Platform registry | `platforms-2` |
| Codebook | `codebook-6` |
| Evidence tiers | `tiers-1` (baseline) and `tiers-1+linewrap-2` (primary) |

Every downstream level reads the primary tier (`Record.primary_tier`).

**Where the numbers live.** Every number is read from [outputs/](outputs/), with full tables in [TABLES.md](outputs/TABLES.md). The LaTeX tables are written to `outputs/latex/` when you run the pipeline locally; they are not committed.

**Analytic set.** The paper's set is the 1,863 named-platform cases; `affordance_coverage.json` → `classes_named_platforms_only` gives the six-class table on that set. The extended 1,984-case set adds Gen AI and ambiguous labels; generative synthesis needs it (on named platforms alone, explicit generative use is 2 cases).

**Who checked what.** All case-level validation is by blind AI reviewers on masked passages; the author agent adjudicated disagreements. No row is human-verified. The 25 platform-history claims were checked by an AI agent on fetched, dated pages.

## Hardy review corrections

**Finding 1: inconsistent tier.** The headline used the line-wrap tier, but every downstream calculation still used the baseline tier: capability-relevant conduct, inferred facilitation, explicit use, harm flags, AI material, the manifest, the temporal tables and the platform-harm tables. So 422 platform-case records in 378 cases counted as documented use in Section 3 but could never appear in Section 4.

The fix: records expose `primary_tier`, which all downstream levels now read; `tier` remains the baseline. No record lost a flag. Changes, in distinct cases:

| Class | B: before → after | I: before → after | C: before → after |
|---|---|---|---|
| Anonymity | 412 → 479 | 338 → 378 | 22 → 28 |
| Contact discovery | 454 → 529 | 30 → 38 | 9 → 10 |
| Unmonitored communication | 459 → 534 | 360 → 399 | 22 → 23 |
| Distribution infrastructure | 802 → 960 | 544 → 667 | 437 → 515 |
| Ephemerality | 322 → 363 | 177 → 181 | 0 → 0 |
| Generative synthesis | 121 → 137 | 54 → 66 | 19 → 21 |

Other effects:
- Manifest documented-use counts rose: Kik 409 → 488, Dropbox 69 → 107, Facebook 132 → 181.
- Manifest platforms: 34 → 36.
- 42 new exemplars appeared and were blind-reviewed: 22 supported, 16 partly, 4 not.

Regression tests:
- a record promoted only by the repair reaches B, C and documented harm;
- no B or documented-harm flag rests on a named-only primary tier;
- manifest documented-use counts equal the primary-tier counts.

**Finding 2: what 1,513 means.** The headline splits as follows (`inventory.json` → `headline_reconciliation`):

| Part of 1,513 | Cases | Rule | Blind review: offender use |
|---|---|---|---|
| Stated | 1,322 | Platform tied to offense conduct in one sentence | 13/15 in a random sample (9 stated in the release, 4 known via a platform report) |
| Inferred only (co-occurrence) | 191 | Platform and offense language in one sentence, with no instrumental link | 14/15 in a random sample (9 stated in the release, 5 via a platform report) |
| Named only (not counted) | 350 | Platform only named | – |

Promoted cases (45 sampled, all tiers): 39 show offender use.

**Recommended wording:** "1,513 cases document platform use: 1,322 state it, and 191 show platform and offense language co-occurring." Do not call all 1,513 "documented offender use" without the rates. Part of the use is known through platform reports, not the release narrative.

## 1. Evidence levels

| Level | Meaning | Paper wording |
|---|---|---|
| A available capability | The platform offered the feature natively in the case's publication year | "available" |
| B capability-relevant conduct | Documented use (primary tier) for conduct of the kind the feature bears on | "documented … conduct on a platform with …" |
| I inferred facilitation | B on a platform where the feature is on for every use by design | See below |
| C explicit instrumental use | The release states the feature-specific behaviour in a platform sentence | "documented use of …" |
| Harm | Potential: an AfH ψ(a) pathway is open (B or I). Documented: a harm cue in the release. | Potential harms are never written as outcomes. |

Wording at I depends on the class, based on how often the blind reviewer judged the inference reasonable:

| Class | Reasonable | Wording |
|---|---|---|
| Generative synthesis | 6/6 | "facilitated" |
| Unmonitored communication | 5/6 | "facilitated" |
| Contact discovery (stranger-meeting platforms) | 4/6 | "facilitated" |
| Distribution | 1/6 | "present by design" |
| Anonymity | 0/6 | "present by design" |
| Ephemerality | 0/6 | "present by design" |

Levels nest: A ⊇ B ⊇ I ⊇ C. A low C reflects what press releases state. It is not a test of the AfH argument.

## 2. Final six-affordance table

Assessed cases: 1,984. Distinct cases, with platform-case observations in brackets; classes overlap.

| Class | A available | B relevant conduct | I inferred facilitation | C explicit use | Platforms at C |
|---|---|---|---|---|---|
| Anonymity | 1,782 (2,306) | 479 (545) | 378 (418) | 28 (32) | 7 |
| Ephemerality | 926 (1,197) | 363 (420) | 181 (182) | 0 | 0 |
| Contact discovery | 1,798 (2,373) | 529 (616) | 38 (39) | 10 (10) | 4 |
| Unmonitored communication | 1,729 (2,314) | 534 (628) | 399 (427) | 23 (25) | 9 |
| Distribution infrastructure | 1,898 (2,525) | 960 (1,120) | 667 (758) | 515 (581) | 29 |
| Generative synthesis | 733 (902) | 137 (145) | 66 (68) | 21 (22) | 3 |

**Why some counts exceed 1,863.** The assessed cases are the 1,863 strict cases plus 70 whose only assessed label is "Gen AI" and 51 whose only one is an ambiguous alias. A case can count in several classes.

**AI material.** 48 cases document AI-generated material; 36 of them don't attribute its creation to anyone in the case, so they are not counted as synthesis.

**Recurrence.** "Recurs" means at least 20 cases, 3+ families and 2+ eras, each with 2+ cases.

| Class | Recurs at | Note |
|---|---|---|
| Distribution | A, B, I, C | |
| Anonymity | A, B, I, C | C: 28 cases, 3 families, 3 eras |
| Unmonitored communication | A, B, I | |
| Contact discovery | A, B, I | |
| Ephemerality | A, B | Native ephemeral messaging starts in 2011 |
| Generative synthesis | none across eras | Public tools date from 2017 and 2022 |

## 3. Section 3: corpus and evidence tiers

| Measure | Cases | Platform-case observations |
|---|---|---|
| Corpus | 10,802 | – |
| Any platform label (broad; includes generic categories) | 3,080 | 4,680 (57 labels) |
| Specific named platform (strict) | 1,863 | 2,487 (52 labels) |
| **Documented use, stated or co-occurring (primary)** | **1,513** (stated 1,322 + co-occurring 191) | 1,834 |
| Documented use, original-rule baseline | 1,257 (stated 1,080 + co-occurring 177) | 1,477 |
| Named only (primary / baseline) | 350 / 606 | 653 / 1,010 |
| Generic category only | 1,096 | – |

How the repair was validated:
- Precision of the 256 promoted cases is about 96% (strata 14/16 and 25/25; conservative lower bound about 80%).
- The repair is additive and never demotes.
- About a third of named-only records still hide offender use, so 1,513 is still a lower bound.
- Within DOJ Safe Childhood, 2021–25, 85–90% of named-platform cases document use.

The tier-rule comparison is in `DECISION_1_TIERS.md`:

| Rule | Cases |
|---|---|
| Original | 1,257 |
| Plain repair | 1,486 |
| Additive repair, no guard | 1,526 |
| **Additive repair with guard (primary)** | **1,513** |
| Extra verbs only | 1,398 |
| Repair + verbs | 1,577 |

## 4. Section 4: manifest and harm pathways

The manifest covers 36 platforms with at least 3 documented-use cases (`outputs/manifest.json`). All 203 exemplar citations resolve by content fingerprint.

Harm pathways, counted as cases with a direct harm cue at the I and C levels:

| Pathway | At I | At C | Label |
|---|---|---|---|
| Distribution → material distributed | 586 | 506 | Observed. Class and harm share verbs, so count once. |
| Anonymity → sextortion | 16 | 8 | Observed examples |
| Unmonitored → sextortion | 11 | 1 | Observed examples at I |
| Unmonitored → coerced imagery | 10 | 0 | Observed examples at I |
| Ephemerality → coerced imagery / sextortion | 10 / 4 | 0 | Potential: present by design; no release describes disappearing content |
| Contact discovery → grooming | 0 | 0 | Potential (120 case-level co-occurrences) |
| Generative → likeness synthesized | 21 | 21 | Small; adjudicate before citing |

## 5. Exemplar inventory

203 exemplars, each with a blind AI verdict. **144 supported. None are human-verified.**

| Cited for | Supported | Partly | Not |
|---|---|---|---|
| Distribution (explicit use) | 56 | 12 | 3 |
| Unmonitored communication | 13 | 2 | 1 |
| Anonymity | 10 | 4 | 1 |
| Contact discovery | 6 | 0 | 2 |
| Generative synthesis | 2 | 0 | 2 |
| Harm: material distributed | 39 | 13 | 7 |
| Harm: sextorted | 10 | 4 | 1 |
| Harm: coerced self-generated | 5 | 0 | 2 |
| Harm: groomed toward in-person | 2 | 2 | 0 |
| Harm: likeness synthesized | 1 | 1 | 2 |

Cite only "supported" rows, after a human read.

## 6. Codebook and registry

**Codebook** (`config/codebook.yaml`, `codebook-6`). Class definitions; conduct categories; explicit-use cues; and guards for undercover personas, app descriptions, AI detection, passive or possession AI wording, statute and capability statements, and "undress" alone. Synthesis needs creation or alteration language, an AI instrument, and an actor in the case.

**Registry** (`config/platforms.yaml`, generated from dated sources in `config/capability_sources/`):
- 59 labels.
- 216 capability rows: 87 documented, 91 approximate, 38 uncertain.
- 25 manuscript claims checked on fetched pages: 23 confirmed, 2 corrected.
  - Kik discoverable hashtag groups date from 2014-12.
  - Dropbox per-file share links date from 2012-04.

## 7. Reproduction

Fresh clone, Python 3.12 with PyYAML 6.0.3 only:

```bash
AFH_Q1_SOURCE_DB=/path/to/caselinker.db python ontology/platform_affordance_evidence/afh_manifest/run_all.py --export --verify
```

Tests:

```bash
DATABASE_URL='' python -m pytest -q tests/api tests/privacy tests/extraction/test_program_boilerplate_dates.py tests/extraction/test_field_assertions.py
```

The expected output hashes are in `outputs/RUN_IDENTITY.json`. Results from the run on this commit are in `HARDY_REVIEW_2.md`.

## 8. Remaining uncertainties

- **No human adjudication.** Per-cell samples are 3–45 rows.
- **AI cells are small.** Explicit generative use is 21 cases (2/4 exemplars supported) and likeness synthesis 21 cases (1/4). Do not claim identity-based likeness synthesis beyond the supported example.
- **Uncertain registry dates.** 38 capability rows have uncertain start dates; 9 are on manuscript example platforms. They underlie 13–17% of Anonymity, Contact and Unmonitored availability counts; 84% of cases are from 2021–26, which limits the effect.
- **Attribution errors.** A sentence naming two platforms can attribute conduct to the wrong one. Uploads to cloud storage can count as distribution without sharing being shown.
- **Coverage, not prevalence.** Enforcement-report coverage, a publication-year timeline, and a changing source mix.
- **Visualization.** The `/visualization` Platforms tile now shows 52 *named* platforms; the map still lists all 57 labels.
- **Not changed here.** The public API serves raw `evidence_quote` text; stored date roles are unchanged until a re-extraction.
