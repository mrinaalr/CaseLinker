# AfH 2.0 Q1: platform-affordance manifest (review checkpoint)

Snapshot `60f7bfaa…d06b` (10,802 cases, 78 sources). Rules: `platforms-2`, `codebook-5`, evidence tiers `tiers-1` (published) and `tiers-1+linewrap-1` (alternative). Every number below is read from [outputs/](outputs/). [TABLES.md](outputs/TABLES.md) has every table, and [outputs/latex/](outputs/latex/) has booktabs versions for `\input{}`. A fresh clone with only Python 3.12 and PyYAML regenerates all outputs byte for byte. The manuscript is unchanged.

## Evidence levels and denominators

| Term | Definition | Denominator |
|---|---|---|
| Specific platform presence | Case names a registered specific platform (not "social media", "chat", "online") | distinct cases; platform-case observations |
| Documented use: stated / inferred / named only | Published `tiers-1` rules on the platform sentence; case tier = best record tier, exclusive per case | strict cases |
| Documented use, line-wrap repair | The better of `tiers-1` on stored text and on text with mid-sentence hard wraps joined (Decision 1) | strict cases; reported beside, not instead of, `tiers-1` |
| A available capability | Platform offered the class natively in the case's publication year (dated registry) | cases on assessed platforms (1,984) |
| B capability-relevant conduct | A, plus documented use for conduct of the kind the class bears on | same |
| I inferred facilitation | B, on a platform where the feature is on for every use by design | same |
| C explicit instrumental use | B, plus the class-specific behaviour stated in a sentence naming the platform | same |
| Potential vs documented harm | Potential: AfH ψ(a) pathway open (B or I). Documented: harm cue in a platform sentence (direct) or anywhere in the release (case level). | cases at that level |

Levels nest: A ⊇ B ⊇ I ⊇ C. A low C describes how press releases are written. It is not evidence that a capability played no role, and it is not a test of the AfH theory.

## 1–2. Platform presence and documented use

| Measure | Cases | Platform-case observations |
|---|---|---|
| Corpus | 10,802 | – |
| Any platform label (broad, AfH 1.0 rule) | 3,080 | 4,680 (57 labels) |
| **Specific named platform (strict)** | **1,863** | **2,487** (52 labels) |
| stated | 1,080 | 1,228 |
| inferred only | 177 | 249 |
| named only | 606 | 1,010 |
| **Documented use, original rules** | **1,257** | 1,477 |
| **Documented use, line-wrap repair** | **1,526** | 1,850 |
| Generic-category-only cases | 1,096 | – |

The corpus also has 4,384 cases with no platform label, 3,334 with only "online" or "internet", and 4 lost to PSA or Gen-AI filters. All partitions reconcile (`inventory.json` → `reconciliation`).

Tier precision, from a blind, offender-use-coded sample:
- stated 13/15, inferred 14/15;
- named-only rows document offender use in 26/40;
- line-wrap promotions are 11/15 precise. The repair recovers 14/26 hidden uses for 2/14 false promotions.

Decision 1 has the full comparison: `DECISION_1_TIERS.md`, `outputs/tier_variants.json`.

## 3. Six-affordance coverage

Distinct cases, with platform-case observations in brackets; last column is distinct platforms at C.

| Class | A available | B relevant conduct | I inferred facilitation | C explicit use | C platforms |
|---|---|---|---|---|---|
| Anonymity | 1,782 (2,306) | 412 (466) | 338 (370) | 22 (23) | 6 |
| Ephemerality | 926 (1,197) | 322 (365) | 177 (178) | 0 | 0 |
| Contact discovery | 1,798 (2,373) | 454 (522) | 30 (30) | 9 (9) | 4 |
| Unmonitored communication | 1,729 (2,314) | 459 (532) | 360 (380) | 22 (24) | 8 |
| Distribution infrastructure | 1,898 (2,525) | 802 (914) | 544 (608) | 437 (487) | 28 |
| Generative synthesis | 733 (902) | 121 (126) | 54 (54) | 19 (19) | 1 |

43 cases document AI-generated material. 31 of them don't attribute creation to anyone in the case, so they count as "AI material", not synthesis.

**Validation (blind reviewers).**
- **Explicit use, exemplar review:** Anonymity 12/14 supported, Contact 5/7, Unmonitored 13/15, Distribution 54/67, Generative 2/3.
- **Inferred facilitation judged reasonable:** Generative 6/6, Unmonitored 5/6, Contact 4/6, Distribution 1/6.
- **Anonymity and Ephemerality:** 0/6 each judged reasonable; all were "weak". The conduct passes through the feature by design, but the passage doesn't show it depended on it. Call this "present by design", not "facilitated".

## Historically supported recurrence

Recurrence means at least 20 cases, 3+ families with 2+ cases each, and 2+ publication eras with 2+ cases each.

| Class | B: cases / families / eras | I | C | Recurs at |
|---|---|---|---|---|
| Distribution | 802 / 9 / 4 | 544 / 9 / 4 | 437 / 6 / 4 | A, B, I, C |
| Anonymity | 412 / 9 / 4 | 338 / 8 / 4 | 22 / 3 / 3 | A, B, I, C |
| Unmonitored communication | 459 / 9 / 4 | 360 / 4 / 4 | 22 / 2 / 2 | A, B, I |
| Contact discovery | 454 / 7 / 4 | 30 / 6 / 3 | 9 / 2 / 1 | A, B, I |
| Ephemerality | 322 / 3 / 3 | 177 / 1 / 2 | 0 | A, B. Native ephemeral messaging begins in 2011, so earlier absence is historical. |
| Generative synthesis | 121 / 3 / 1 | 54 / 1 / 1 | 19 / 1 / 1 | none across eras. Public tools date from 2017 (face-swap) and 2022 (diffusion). |

## Platform registry and operational definitions

| Item | Value |
|---|---|
| Platforms | 59 labels, each with a status (specific / technology / generic / ambiguous alias / excluded) and a family (`config/platforms.yaml`) |
| Capability rows | 216 across the 55 corpus labels that have capabilities (56 platforms researched, including VRChat, which is not in the corpus): 87 documented, 91 approximate, 38 uncertain. Each row has native, `default_on`, first year and confidence; dated evidence per cell is in `config/capability_sources/*.yaml`. |
| Source reachability | 217 cited URLs: 185 resolve, 30 return 4xx (mostly bot blocking; 1 404, 1 410), 2 time out (`url_check.json`) |
| Manuscript-relevant claims | 25 checked on fetched dated pages: 23 confirmed, 2 corrected (`manuscript_claims_verified.csv`) |
| Coding rules | Ephemerality and Generative synthesis count only fully native features. Contact discovery is on by design only for stranger-meeting platforms. Snapchat's generative capability is dated to Dreams (2023-08), not AR Lenses. |
| Definitions | `config/codebook.yaml`: class definitions, conduct categories, instrumental cues and guards (undercover, app descriptions, AI detection, passive or possession AI wording), harm cues |

The two corrections:
- **Kik:** discoverable hashtag groups date from 2014-12.
- **Dropbox:** a Public folder and shared folders at the 2008 launch; per-file share links from 2012-04.

## Platform comparisons (Section 4)

34 platforms have at least 3 use-documented cases. Each manifest entry gives the capability profile with dates, cases by tier, conduct mix, A/B/I/C per class, harm counts and fingerprint-bound exemplars (`outputs/manifest.json`; top 15 in `latex/tab_platform_manifest.tex`). All 185 cited exemplars resolve to the same content (`citation_check: ok`).

## Verified exemplar inventory

Every manifest exemplar was blind-reviewed (`outputs/exemplar_inventory.json`, `latex/tab_verified_exemplars.tex`). Cite only `supported`.

| Cited for | Supported | Partly | Not |
|---|---|---|---|
| Distribution (explicit use) | 54 | 10 | 3 |
| Unmonitored communication | 13 | 1 | 1 |
| Anonymity | 12 | 1 | 1 |
| Contact discovery | 5 | 0 | 2 |
| Generative synthesis | 2 | 0 | 1 |
| h3 material distributed | 37 | 11 | 9 |
| h4 sextorted | 7 | 3 | 2 |
| h2 coerced self-generated | 3 | 0 | 0 |
| h1 groomed toward in-person | 2 | 2 | 0 |
| h6 likeness synthesized | 1 | 0 | 2 |

The main failure patterns:
- the harm or conduct happened on a different platform named in the same sentence (e.g. first contact on Grindr, material sent over Kik);
- an upload to cloud storage with no sharing shown;
- headline-only passages;
- an undercover target.

## Misuse → harm: observed vs potential

| Pathway | Observed (direct cases at C / I) | Label |
|---|---|---|
| Distribution → material distributed | 431 / 497 | Observed. The class and harm share verbs, so count it once. |
| Anonymity → sextortion | 6 / 13 | Observed examples |
| Unmonitored → sextortion, coerced imagery | 1 / 10; 0 / 8 | Observed at I, with examples |
| Ephemerality → coerced imagery, sextortion | 0 / 10; 0 / 4 | Potential: pathway open in 322 cases; no release describes disappearing content |
| Contact discovery → grooming | 0 / 0 (103 case-level) | Potential; illustrate with stranger-meeting platforms |
| Generative → likeness synthesized | 19 / 19 | Observed but small. Exemplars 1/3 supported, so adjudicate before citing. |

## Limitations

- Enforcement-report coverage, not prevalence: 84% of cases are from 2021–26 and the source mix changes by era.
- Publication year is the timeline; it is an upper bound on conduct time.
- Text is capped at 6,000 characters. Cues are sentence-local, so a sentence naming two platforms can attribute conduct to the wrong one.
- Rules are deterministic regexes with small validation samples (n = 3–40 per cell; wide intervals).
- All reviewers were AI agents working blind; no human adjudicator has checked the disagreement rows.
- 38 registry rows are uncertain; most citations were checked for reachability, not read in full. The 25 manuscript claims were read in full.

## Remaining author decisions

1. Adopt the line-wrap repair (1,526) as the Section 3 count, or report 1,257 with the repair alongside.
2. Wording for inferred facilitation: "facilitated" for Generative, Unmonitored and stranger-meeting Contact; "present by design" for Anonymity and Ephemerality.
3. Resolve the 38 uncertain registry rows that appear in the manuscript, and the 2 claim corrections.
4. Human adjudication of the Generative and h6 cells before citing AI examples.
5. A Facebook/YouTube boilerplate filter: 7 of 8 false line-wrap promotions.
6. Whether Gen AI is listed as a manifest platform (it is a technology label).
7. Re-extraction to store the fixed date roles (`temporal_tags` 1.1.0) in the databases.
8. Raw `evidence_quote` text in the public evidence API.
