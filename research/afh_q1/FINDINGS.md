# AfH 2.0 Q1: author review report

Corpus snapshot `60f7bfaa…d06b` (10,802 cases, 78 sources). Rules: `platforms-2`, `codebook-3`. Outputs are regenerated from a clean clone of this branch and reproduce byte for byte (`run_all.py --export --verify` → `identical`). Every number below is read from [outputs/](outputs/); [TABLES.md](outputs/TABLES.md) has the full tables. The manuscript is unchanged.

## How to read the evidence levels

AfH argues affordance → misuse → harm conceptually. Press releases are written to report charges, not mechanisms, so the corpus is read at five levels. A low count at a strict level describes the record, not the role of the affordance. The strictest counts are not a validity test of the theory.

| Level | Meaning | What it can support |
|---|---|---|
| **A available capability** | The platform offered the feature natively in the case's publication year (dated, sourced registry) | "This capability was present wherever offenders used this platform" |
| **B capability-relevant conduct** | Documented use of the platform for conduct of the kind the feature bears on | "Documented conduct of the relevant kind occurred on platforms with the feature" |
| **I inferred facilitation** | B on a platform where the feature is on for every use by design | "The conduct passed through the feature by design" (plausibility validated per class, below) |
| **C explicit instrumental use** | The release states the feature-specific behaviour in a sentence naming the platform | "The record documents the feature being used" |
| Harm: potential / documented | Potential: an AfH ψ(a) pathway is open (class at B or I). Documented: a harm cue in the release, direct (platform sentence) or case-level. | Potential harms are conceptual; documented harms are co-occurrence, not causation |

## Section 3 findings

| Finding | Value | Basis |
|---|---|---|
| Corpus | 10,802 cases, 78 sources, publication years 2002–2026 (one 1992 date error) | verified |
| Cases naming any platform label (broad, AfH 1.0 rule) | 3,080 (4,680 platform-case observations, 57 labels) | verified |
| Cases naming a specific platform (strict) | 1,863 (2,487 observations, 52 labels) | verified |
| Strict cases documenting platform use, published rules | 1,257 (1,080 stated + 177 inferred-only) | verified; a lower bound |
| Same, corrected for measured undercount | about 1,480 (sample-weighted; bounds 1,080–1,674). Sensitivity rules give 1,577. | validated (blind 70-row tier sample) |
| Timeline | Publication year only. 2,601 cases carry an offense-typed date. Program boilerplate ("launched in May 2006") is excluded from dates. | verified |
| Coverage | 84% of cases from 2021–26; source mix changes across eras; within DOJ Safe Childhood 2021–26, 67–79% of named-platform cases document use (flat) | verified |

**Systematic undercount, confirmed.** In a blind sample of 40 named-only records, 25 document use (62.5%, Wilson 47–76%). The undercount sits in one rule: the offense-keyword gate, where 20 of 26 rows document use.

The cause is mechanical. Releases are line-wrapped, so the verb and the platform name land on different "sentences". The keyword list also lacks storage and receipt verbs (stored, saved, received, requested, purchased). Joining wrapped lines and adding those verbs (the sensitivity tier) upgrades 18 of those 25 rows, and wrongly upgrades 3 of the 15 no-use rows.

The PSA, enumeration and awareness gates were right in all 6 sampled rows. Stated is 13/15 and inferred 14/15 in the new sample; 12/12 and 10/10 after adjudication in the original one.

## Section 4: platform-level comparisons

Format per class: A / B / I / C distinct cases.

| Platform | use-documented cases | Anonymity | Ephemerality | Contact discovery | Unmonitored comm. | Distribution | Generative |
|---|---|---|---|---|---|---|---|
| Kik | 409 | 561/171/171/2 | – | 561/171/0/0 | 561/171/171/12 | 561/252/109/109 | – |
| Snapchat | 377 | 417/120/120/5 | 417/144/144/0 | 417/120/4/4 | 417/120/120/1 | 417/142/48/48 | 332/31/1/1 |
| Facebook | 132 | not native | 293/50/0/0 | 318/55/1/1 | 318/55/0/0 | 318/63/63/20 | 223/4/0/0 |
| Discord | 70 | 129/28/28/0 | – | 128/28/0/0 | 129/28/28/1 | 129/40/40/12 | – |
| Dropbox | 69 | 147/1/0/0 | – | – | – | 147/60/34/34 | – |
| Instagram | 66 | 151/29/3/3 | 151/33/0/0 | 151/29/0/0 | 151/29/1/1 | 151/27/27/6 | 113/4/1/1 |
| Gen AI | 56 | – | – | – | – | – | 91/51/51/39 |
| Telegram | 42 | 83/23/23/0 | 83/25/0/0 (opt-in) | 83/23/0/0 | 83/23/23/2 | 83/21/6/6 | – |
| WhatsApp | 41 | partial (2026) | 56/28/0/0 (opt-in, 2020+) | 49/26/0/0 | 58/27/27/0 | 58/9/4/4 | 49/1/0/0 |
| BitTorrent | 29 | 36/1/1/0 | – | 36/1/0/0 | – | 36/24/24/18 | – |
| Omegle | 12 | 19/7/7/0 | – | 19/7/7/0 | 19/7/7/0 | – | – |

All 34 manifest platforms are in `outputs/manifest.json`, with capability profile, dates, confidence, conduct mix and fingerprint-verified exemplars (all 146 citations `ok`).

Comparisons that hold:
- Kik's record is dominated by distribution and pseudonymous contact.
- Snapchat is the only platform where ephemerality is on by design for every capability-relevant interaction (144 cases).
- File hosting and P2P appear almost only as distribution.
- Facebook has no native anonymity (real-name policy) yet carries comparable contact conduct.
- Omegle and the dating and game platforms are the stranger-meeting cases.

## Historically supported recurrence

Every capability year now comes from dated research: 216 capability rows across 56 platforms, 87 documented, 91 approximate, 38 uncertain. Recurrence means at least 20 cases, 3+ platform families with 2+ cases each, and 2+ eras with 2+ cases each.

| Class | B: families / eras | I: families / eras | C: families / eras | Strongest level that recurs |
|---|---|---|---|---|
| UnmonitoredCommunication | 7 / 4 | 4 / 4 | 2 / 2 | I |
| Anonymity | 7 / 4 | 5 / 4 | 2 / 2 | I |
| ContactDiscovery | 7 / 4 | 6 / 3 | 2 / 1 | I (28 cases) |
| DistributionInfrastructure | 8 / 4 | 8 / 4 | 7 / 4 | **C** |
| Ephemerality | 3 / 3 | 1 / 2 | 0 / 0 | B; native ephemeral messaging only exists from 2011 (Snapchat), so pre-2011 absence is historical, not a gap |
| GenerativeSynthesis | 3 / 1 | 1 / 1 | 1 / 1 | none across eras; consistent with public tools dating from 2017 (face-swap) and 2022 (diffusion) |

Two kinds of recurrence are supported:
- **Distribution** recurs as documented misuse (C) from IRC and early P2P to Telegram and cloud links.
- **Private communication, pseudonymity and stranger contact** recur as capability-relevant conduct across every era and seven platform families.

## Defensible affordance → misuse → harm examples

These come from cells with documented harm at C or I, whose harm cue passed the blind harm review.

| Pathway | Evidence | Status |
|---|---|---|
| Distribution infrastructure → material distributed / re-victimization | 290 C cases; harm direct in 280; reviewer confirmed 6/6 shared-trigger rows and 5/6 direct rows | Defensible. State that the conduct and harm cues share verbs, so this is one observation. |
| Generative synthesis → likeness synthesized | 41 C cases; harm direct in 37 | Defensible for creation. 3 of 4 shared-trigger rows were possession of AI material, not synthesis of a child's likeness, so phrase it as "AI-generated material", and as likeness synthesis only where the release says so. |
| Unmonitored communication → coerced self-generated imagery / sextortion | I in 391 cases; harm direct 3 (h2) and 3 (h4); inference judged reasonable in 5/6 | Defensible as qualitative examples with case ids, not as a rate |
| Contact discovery (stranger-meeting platforms) → grooming | I in 28 cases; inference reasonable in 4/6; h1 case-level only | Use as illustration (Omegle, dating, game platforms) |
| Anonymity (persona) → sextortion | C 10; h4 direct 3 | Thin; usable as named examples |

Pick the exemplars from `outputs/manifest.json`. Each carries a case id and content fingerprint.

## Conceptual examples that need labelling as such

| Claim | Why it is conceptual here |
|---|---|
| Ephemerality → coerced imagery / sextortion | Ephemerality is on by design in 147 Snapchat cases with capability-relevant conduct. In 6/6 sampled rows the reviewer judged the facilitation possible but not shown ("weak inference"). No release states disappearing content facilitated the conduct; one generic-platform case documents a five-second-view image. |
| Anonymity → grooming / coerced imagery | 364 cases pass through by-design pseudonymity (I), but 6/6 sampled rows were "weak inference". Only 10 releases describe a persona on a named platform. |
| Contact discovery on feed platforms (People You May Know, Quick Add) | Shown by default, but the record rarely says where first contact began. Coded as available, not inferred. |
| ψ(a) links rated "documented in cases where the pathway is open" (`harm.json`) | Harm is documented in the case, not tied to the feature |

## Claims to remove or revise

| AfH 1.0 claim | Revision |
|---|---|
| 1,875 / 3,128 / 54 / 858 / 136 / 881 | Report broad 3,080 and strict 1,863 with both denominators, tiers as a lower bound, and the corrected estimate. 858/136 appear in no committed output; the June outputs say 856/134. |
| Platform signatures written as offender use ("Ephemerality … evidence destruction by design" for Snapchat; Kik "anonymity") | Write as capability (A, with dates) plus inferred facilitation (I), and cite explicit examples where they exist |
| "The same chat affordance, on a platform from 2008 or 2025, produces the same offense pattern" | Supported as recurrence of capability-relevant conduct (B) across eras, and of documented misuse (C) for distribution only. Drop "produces". |
| "A platform's affordance profile predicts its harm profile" | Not tested; call it a hypothesis |
| Snapchat generative synthesis, or any "AI on every platform" reading | Meta, Snapchat, X and TikTok AI image tools date from 2023–25. Availability (A) is not misuse. |
| Contact-discovery claims for 2002–2014 releases on Kik | Kik's searchable public groups date from 2014 (approximate); username search earlier |

## Unresolved author decisions

1. **Registry confidence.** 38 capability rows are `uncertain` and 91 `approximate`. of 217 cited URLs, 185 resolve, 28 block automated checks (403/429), 2 are dead (404/410) and 2 timed out (`config/capability_sources/url_check.json`). Cells to resolve first: Chat Avenue launch year, Wickr signup identity, Snapchat Quick Add date, Kik public-groups year, Instagram/TikTok/Tumblr discovery dates.
2. **Tier rules.** Adopt the sensitivity tier (unwrap + verbs) as the published rule, or report published counts with the corrected estimate. The choice changes Section 3 numbers.
3. **What "inferred facilitation" may be called in the paper.** It validates for GenerativeSynthesis, UnmonitoredCommunication and stranger-meeting ContactDiscovery. For Anonymity and Ephemerality it means "passed through the feature by design", not "was facilitated by it".
4. **Class boundaries.** Closed-group trading (Unmonitored vs Distribution), and screenshots or screen recordings of live or ephemeral content (capture; CAC CoercionLeverage is outside the six).
5. **Gen AI as a manifest row.** It is a technology label, not a platform.
6. **Release boundaries in compilations.** One reviewed Anonymity hit came from a different release on the same compilation page. Splitting NCMEC and state compilations more finely would remove such cases.
7. **Re-extraction.** Storing the fixed date roles (`temporal_tags` 1.1.0) in `caselinker.db` and production needs your approval.
8. **Raw `evidence_quote` text in the public evidence API.**

## Validation summary

| Check | Result |
|---|---|
| 107-row classification sample, second blind reviewer | Agreement: instrumental rows 47/49 (κ 0.78), tier rows 31/32 (κ 0.84). 7 disagreements adjudicated (`config/validation_adjudication.csv`). |
| Explicit-use precision after adjudication | Anonymity 5/7, ContactDiscovery 7/7, Distribution 14/15, Generative 9/10, Unmonitored 8/10 |
| Harm cues (74 rows) | Direct cue tied to platform: h1 2/3, h2 3/3, h3 5/6, h4 5/6, h6 5/6. Case-level-only rows are weak (0–75%). Negatives: h3 2/4 missed, others 0/4. |
| Inferred facilitation (36 rows) | Reasonable: Generative 6/6, Unmonitored 5/6, Contact 4/6, Distribution 1/6, Anonymity 0/6, Ephemerality 0/6 (the remainder "weak", 1 not reasonable) |
| Determinism and clean checkout | `--verify` identical in a fresh clone after `--export`; 47 Q1 tests pass there |
| Privacy | Outputs hold ids, hashes, offsets and counts. A test asserts no 25+ character output string appears in any release. Review sheets with masked passages stay in gitignored `data/`. |

Reviewers: one agent reviewer (round 1) and four independent blind agent reviewers (round 2), each with only the masked passages and definitions. Human adjudication of the disagreement rows is still pending.
