# AfH 2.0 numbers

AfH 2.0 snapshot: corpus **10,802 cases** · `codebook-9` · registry `platforms-3` · PACER `pacer-v2` (hashes in SNAPSHOT.md). Values in numbers.json; run order in run_all.sh. Read-only on the DB and the PACER release.

Data caveats are marked ⚑ and collected in [Flags](#flags).

## 1. Cover and abstract

| Placeholder | Value | Definition | Source |
|---|---:|---|---|
| NCases | 10,802 | rows in `cases` | `CaseStorage.get_all_cases` |
| NFeatures | 231,988 | `/api/stats` `unique_features`: every value read from the case text and stored; each list value counts; labels count, and the quoted spans behind them are listed, not counted; place names count (their role is not stated); placeholders, program boilerplate (incl. the CyberTipline flag), provenance and copies excluded | `run/feature_count.py` |
| NSources | 76 | publishing families: distinct `source` labels after `_source_count_key` folding | `run/feature_count.py` `source_count_key` (as in `get_stats`) |
| NSourceLabels | 78 | distinct raw `source` labels | same |
| NAgencies | 4,326 | distinct agencies named in the corpus after `distinct_named_agencies` | `agency_label_normalize.distinct_named_agencies` (as in `get_stats`) |
| NAgencyVariants | 5,052 | distinct raw `agencies_involved` strings before normalization | `extracted_features.agencies_involved` |
| NTaskForces | 61 of 61 | geographic ICAC task forces whose lead agency is named in case text (agency needles on normalized text and agencies); 43 have a case from that task force's own ingest source, 59 a mention outside NCMEC/DOJ feeds | `scripts/verify/icac_tf_verify.py`, output in `task_forces/` |
| NPacerCases | 30 | cases in pacer-v2 | `<PACER release>/manifest.json` |
| NPacerDocs | 98 | source documents in pacer-v2 (dockets included) | manifest `source_documents` |
| NPacerIndictments | 25 docs / 24 cases | documents typed `indictment` or `superseding_indictment` ⚑ | bundle `doc_type` |
| NPacerSoO | 2 docs (strict) · 9 docs / 8 cases (factual family) | strict: `statement_of_offense`; family adds statement of facts, factual proffer, stipulation of facts, factual basis ⚑ | bundle `doc_type` |
| NNamedPlatforms | 52 | distinct specific (non-generic, non-alias, non-technology) platform labels in the Q1 pool | `build/inventory.json` `labels.specific` |
| (platforms analysed) | 36 | manifest platforms: ≥3 use-documented cases | `build/manifest.json` |
| YearStart | 2002 | earliest publication year after the load-time year corrections (29 records, §13); `/api/stats` reads the stored dates without them (1992). 0 case(s) before 2002 | `raw_data.year`, `afhq1/labels.year_corrections` |
| YearEnd | 2026 | latest publication year | `raw_data.year` |

PACER document types: indictment 17, judgment 14, docket 13, sentencing_memorandum 13, plea_agreement 10, superseding_indictment 8, complaint 4, trial_brief 3, statement_of_facts 3, statement_of_offense 2, factual_proffer 2, findings_of_fact 1, information 1, amended_judgment 1, opinion 1, brief 1, stipulation_of_facts 1, statement_of_reasons 1, factual_basis 1, plea_transcript 1.

## 2. Recurrence and persistence

Rule (`afhq1/harm_release.py` `build`, `_on_at`, `_recurs`): a row is a stated-tier (line-wrap) record of a platform where the class is `default_on` and its registry window covers the publication year (`since`…`ended`). A bin qualifies at **n_min = 30** distinct coded cases; a class is present at **k = 3**; recurs/persists = present in ≥2 qualifying bins and every qualifying bin after its first.

**Recurrence by launch cohort.** Qualifying: <=2003, 2004-2010, 2011-2016.

| | <=2003 | 2004-2010 | 2011-2016 | >=2017 | verdict |
|---|---:|---:|---:|---:|---|
| cases in bin | 82 | 747 | 498 | 2 ✗ | |
| Anonymity | **81** | **454** | **448** | 2 | recurs |
| Ephemerality | 0 | 0 | **318** | 0 | first appears in the last qualifying cohort; recurrence untestable |
| ContactDiscovery | **52** | **261** | **359** | 1 | recurs |
| UnmonitoredCommunication | **18** | **485** | **456** | 0 | recurs |
| DistributionInfrastructure | **52** | **272** | **109** | 0 | recurs |
| GenerativeSynthesis (descriptive) | 0 | 0 | 0 | 1 | not tested |

**Persistence by publication era.** Qualifying: <=2016, 2020-2022, 2023-2026.

| | <=2016 | 2017-2019 | 2020-2022 | 2023-2026 | verdict |
|---|---:|---:|---:|---:|---|
| cases in bin | 60 | 20 ✗ | 253 | 900 | |
| Anonymity | **28** | 6 | **179** | **722** | persists |
| Ephemerality | 0 | 1 | **65** | **254** | persists |
| ContactDiscovery | **51** | 15 | **139** | **441** | persists |
| UnmonitoredCommunication | **9** | 8 | **178** | **724** | persists |
| DistributionInfrastructure | **53** | 14 | **91** | **282** | persists |
| GenerativeSynthesis (descriptive) | 0 | 0 | 0 | 62 | not tested |

Bold = present; ✗ = bin does not qualify. Non-qualifying launch cohorts: >=2017 (2 coded cases). Verdicts: Anonymity: recurs (cohort), persists (era); Ephemerality: first appears in the last qualifying cohort; recurrence untestable (cohort), persists (era); ContactDiscovery: recurs (cohort), persists (era); UnmonitoredCommunication: recurs (cohort), persists (era); DistributionInfrastructure: recurs (cohort), persists (era). Top platform per era cell is in numbers.json (`top_platform_share`).

## 3. ContactDiscovery in the ≤2003 cohort without P2P

P2P rows = rows whose platform has registry `family: p2p` (BitTorrent, Kazaa, LimeWire). Recomputed with the same row rule as §2 (`compute_numbers.py` §3; the with-P2P count matches the committed table: True).

| | ≤2003 coded cases | qualifies | ContactDiscovery cases | present (k=3) |
|---|---:|---|---:|---|
| with p2p | 82 | True | 52 | True |
| without p2p | 47 | True | 17 | True |

Without P2P: ContactDiscovery 17 cases (present: True); cohort 47 coded cases (qualifies: True). 35 of the 52 with-P2P cases reach ContactDiscovery only through a P2P row.

## 4. Affordance × harm (rows closed at registry end dates)

A row counts a class only while the platform's registry window for it is open (`since`…`ended`, `harm_release._on_at`). `harm_open/` keeps the unclosed tables for comparison.

**Strict** (harm cue in a sentence naming the platform, and the harm in the case set). Distinct cases per cell; base: 1,291 stated-tier cases with a default-on class (1,489 mentions).

| class | h1 | h2 | h3 | h4 | h5 |
|---|---:|---:|---:|---:|---:|
| Anonymity | 7 | 11 | 544 | 8 | 2 |
| Ephemerality | 3 | 9 | 131 | 4 | 0 |
| ContactDiscovery | 12 | 14 | 292 | 23 | 1 |
| UnmonitoredCommunication | 7 | 11 | 504 | 10 | 1 |
| DistributionInfrastructure | 8 | 2 | 225 | 21 | 1 |
| GenerativeSynthesis | 0 | 20 | 12 | 0 | 0 |

**Broad** (the case-level harm set). Distinct cases per cell; base: 1,291 stated-tier cases with a default-on class (1,489 mentions).

| class | h1 | h2 | h3 | h4 | h5 |
|---|---:|---:|---:|---:|---:|
| Anonymity | 145 | 169 | 822 | 36 | 22 |
| Ephemerality | 48 | 71 | 252 | 20 | 3 |
| ContactDiscovery | 114 | 157 | 537 | 50 | 13 |
| UnmonitoredCommunication | 142 | 167 | 803 | 39 | 21 |
| DistributionInfrastructure | 84 | 100 | 380 | 41 | 10 |
| GenerativeSynthesis | 17 | 38 | 43 | 1 | 0 |

Moved by closing rows (open → closed): strict Anonymity × h3_imagery_circulated 546→544; strict Ephemerality × h3_imagery_circulated 133→131; strict ContactDiscovery × h3_imagery_circulated 293→292; strict UnmonitoredCommunication × h3_imagery_circulated 506→504; broad Anonymity × h1_contact_sexual_abuse 146→145; broad Anonymity × h2_depicted_in_abuse_imagery 172→169; broad Anonymity × h3_imagery_circulated 827→822; broad Ephemerality × h2_depicted_in_abuse_imagery 72→71; broad Ephemerality × h3_imagery_circulated 255→252; broad ContactDiscovery × h2_depicted_in_abuse_imagery 159→157; broad ContactDiscovery × h3_imagery_circulated 539→537; broad UnmonitoredCommunication × h1_contact_sexual_abuse 143→142; broad UnmonitoredCommunication × h2_depicted_in_abuse_imagery 170→167; broad UnmonitoredCommunication × h3_imagery_circulated 808→803. Stated cases with a default-on class: 1298 → 1291.

**h1_form** (cases with h1): in_person 1,674 · online 71 · both 12; no h1 9,045. Rule: `pipeline.h1_form` on line-repaired text (`harm_release.classify_release`).

**Excluded groups** (`harm_release.build`, `excluded_groups`): ai_no_identifiable_child 54 · attempted_contact 57 · sting_no_minor 4 · **union 113**. Overlaps: ai_no_identifiable_child & attempted_contact 0, ai_no_identifiable_child & sting_no_minor 0, attempted_contact & sting_no_minor 2, all_three 0. Stings kept in the base: 5 keep h2/h3, 0 keep another harm.

**Uncovered share** = 1,040 / 10,689 = **0.0973** (9.73%). Rule: Empty harm set among cases in none of ai_no_identifiable_child, attempted_contact, and sting_no_minor, over that same set.

## 5. Q1 evidence base

Q1 pool: cases whose platform labels include anything other than `online`/`internet`; generic categories (`social media`, `chat`) stay in the pool but are never named platforms. Source: `build/records.csv`, `build/inventory.json`.

| Value | Number |
|---|---:|
| NQOneCases (Q1 candidate cases) | 3,057 (28.3% of corpus) |
| PctNoPlatform (no label beyond online/internet) | 71.7% |
| NPlatformCaseRecords | 4,628 |
| stated / inferred / named-only, line-wrap (primary) | 2,335 (50.5%) / 404 (8.7%) / 1,889 (40.8%) |
| stated / inferred / named-only, tiers-1 (baseline) | 1,806 / 314 / 2,508 |
| cases with a named platform | 1,843 |
| named-platform records (line-wrap stated / inferred / named-only) | 2,441 (1,522 / 267 / 652) |
| named platforms | 52 |

Per platform (manifest table: platforms with ≥3 use-documented cases). Stated = cases whose best line-wrap tier for that platform is stated; total = all cases naming it (`afhq1/build.py` `manifest`).

| platform | stated | total |
|---|---:|---:|
| BitTorrent | 28 | 36 |
| Cash App | 8 | 20 |
| Craigslist | 9 | 15 |
| Discord | 79 | 128 |
| Dropbox | 86 | 147 |
| FaceTime | 3 | 11 |
| Facebook | 129 | 295 |
| Facebook Messenger | 35 | 45 |
| Gen AI | 62 | 86 |
| Google Drive | 27 | 53 |
| Grindr | 6 | 14 |
| IRC | 7 | 15 |
| Instagram | 77 | 149 |
| Kazaa | 5 | 6 |
| Kik | 424 | 550 |
| MeWe | 10 | 10 |
| Mega.nz | 15 | 38 |
| MySpace | 1 | 3 |
| Omegle | 11 | 19 |
| OneDrive | 3 | 3 |
| Reddit | 19 | 32 |
| Roblox | 4 | 7 |
| Skype | 20 | 30 |
| Snapchat | 318 | 411 |
| Telegram | 48 | 83 |
| TikTok | 10 | 29 |
| Tor | 8 | 10 |
| Tumblr | 12 | 20 |
| Twitch | 1 | 4 |
| Twitter / X | 39 | 105 |
| Webcam platform | 24 | 47 |
| WhatsApp | 47 | 58 |
| Whisper | 9 | 17 |
| Wickr | 10 | 11 |
| YouTube | 8 | 19 |
| iCloud | 6 | 18 |

## 6. Affordance families

Base: the 3,057 Q1 candidate cases, assigned by offense topic (or the matching codebook-9 harm); a case can sit in several families; 229 sit in none.

| family | cases | rule |
|---|---:|---|
| contact and approach | 648 | topic hands_on or sextortion, or h1 or h4 in the codebook-9 case harm set |
| production | 578 | topic production, or h2 in the case harm set |
| possession and trade | 2,625 | topic possession or distribution, or h3 in the case harm set |
| coordination | 32 | extracted multi_defendant_operation, or a §2252A(g) child exploitation enterprise charge named in the case text; naming Discord or a game platform alone does not count |

Coordination parts: multi_defendant_operation 31, §2252A(g) enterprise charge in the text 2 (1 by the charge alone). The charge has no stored field; it is matched in the case text.

## 7. PACER (pacer-v2)

Cases **30** (press-linked 30/30) · documents **98** · agreed acts **290** · chains **170** · observations **875** · derived steps with capability candidates **20 of 420**. Source: `<PACER release>/manifest.json`, `derived/`.

**Two-coder reliability** (pipeline report, `state_machines/coding/report.py` `build`, `reliability_real_cases`; model-coded acts only, docket-parser acts excluded): coder A 2,684 acts, coder B 5,904, matched 1,070, mean event F1 0.229. Action code on matched pairs: raw agreement 365/1070 = 0.341; mean per-case Cohen's κ 0.296. This is agreement conditional on both coders coding the act; it has no negatives.

| case | acts | chains | obs | docs | A | B | matched | F1 | action exact | κ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| anchorage_pd_2022_004 | 9 | 7 | 16 | 3 | 130 | 211 | 58 | 0.34 | 11/58 | 0.147 |
| anchorage_pd_2022_006 | 15 | 4 | 4 | 4 | 163 | 397 | 59 | 0.211 | 18/59 | 0.28 |
| anchorage_pd_2022_007 | 25 | 19 | 175 | 2 | 290 | 338 | 91 | 0.29 | 33/91 | 0.322 |
| doj_ceos_2025_004 | 1 | 0 | 5 | 3 | 14 | 107 | 3 | 0.05 | 1/3 | 0.25 |
| doj_ceos_2025_007 | 5 | 1 | 13 | 2 | 81 | 170 | 26 | 0.207 | 10/26 | 0.321 |
| doj_ceos_2025_014 | 6 | 0 | 32 | 3 | 49 | 186 | 19 | 0.162 | 5/19 | 0.238 |
| doj_ceos_2025_023 | 9 | 8 | 10 | 3 | 41 | 163 | 27 | 0.265 | 10/27 | 0.336 |
| doj_ceos_2025_025 | 19 | 10 | 225 | 5 | 432 | 671 | 205 | 0.372 | 65/205 | 0.252 |
| doj_ceos_2025_026 | 15 | 9 | 3 | 3 | 33 | 27 | 21 | 0.7 | 10/21 | 0.439 |
| doj_ceos_2025_031 | 14 | 4 | 72 | 6 | 178 | 285 | 66 | 0.285 | 21/66 | 0.255 |
| doj_ceos_2026_001 | 32 | 27 | 93 | 2 | 147 | 106 | 57 | 0.451 | 27/57 | 0.437 |
| doj_ceos_2026_003 | 2 | 1 | 2 | 3 | 109 | 421 | 21 | 0.079 | 8/21 | 0.352 |
| doj_ceos_2026_006 | 14 | 9 | 18 | 4 | 180 | 348 | 90 | 0.341 | 23/90 | 0.216 |
| doj_ceos_2026_007 | 4 | 1 | 3 | 6 | 52 | 375 | 17 | 0.08 | 7/17 | 0.375 |
| doj_ceos_2026_008 | 6 | 5 | 8 | 4 | 44 | 233 | 17 | 0.123 | 7/17 | 0.354 |
| doj_ceos_2026_012 | 9 | 3 | 2 | 4 | 16 | 135 | 10 | 0.132 | 5/10 | 0.462 |
| doj_safe_childhood_2023_420 | 5 | 4 | 16 | 3 | 51 | 123 | 20 | 0.23 | 6/20 | 0.257 |
| ky_sp_2025_038 | 2 | 2 | 5 | 3 | 61 | 120 | 28 | 0.309 | 5/28 | 0.155 |
| ncis_2022_002 | 4 | 3 | 5 | 3 | 21 | 142 | 15 | 0.184 | 4/15 | 0.207 |
| ncis_2023_001 | 4 | 3 | 5 | 3 | 60 | 84 | 16 | 0.222 | 4/16 | 0.19 |
| ncmec_2022_575 | 21 | 24 | 38 | 3 | 96 | 182 | 45 | 0.324 | 25/45 | 0.46 |
| ncmec_2023_222 | 1 | 0 | 0 | 2 | 14 | 63 | 1 | 0.026 | 1/1 |  |
| ncmec_2025_1026 | 0 | 0 | 6 | 2 | 11 | 99 | 0 | 0.0 | 0/0 |  |
| svicac_2022_009 | 17 | 5 | 27 | 3 | 57 | 96 | 15 | 0.196 | 7/15 | 0.4 |
| texas_ag_2019_013 | 19 | 4 | 26 | 6 | 96 | 232 | 45 | 0.274 | 17/45 | 0.344 |
| usss_2017_006 | 14 | 5 | 49 | 2 | 106 | 85 | 37 | 0.387 | 13/37 | 0.269 |
| usss_2021_017 | 7 | 7 | 10 | 3 | 88 | 175 | 32 | 0.243 | 13/32 | 0.354 |
| usss_2023_004 | 3 | 3 | 0 | 3 | 42 | 127 | 21 | 0.249 | 6/21 | 0.255 |
| ut_ag_2026_006 | 2 | 2 | 7 | 2 | 15 | 82 | 5 | 0.103 | 2/5 | 0.211 |
| wy_dci_2023_005 | 6 | 0 | 0 | 3 | 7 | 121 | 3 | 0.047 | 1/3 | 0.143 |

## 8. Limitations

CSAM-related (rule: topic csam, ai_csam, possession, distribution or production): **NCSAM 9,676** (PctCSAM 89.6%). Of those, **1,762** (18.2%) have a named platform, and NCSAMQOne **2,879** (29.8%) are Q1 candidates (generic categories included). NQOneCases 3,057 (PctQOneCases 28.3%).

## 9. doj_safe_childhood_2023_103 vs 2024_461

**Two releases about one prosecution, not one release ingested twice.**

| | 2023_103 | 2024_461 |
|---|---|---|
| source URL | https://www.justice.gov/usao-sdwv/pr/missouri-man-pleads-guilty-child-pornography-crime | https://www.justice.gov/usao-sdwv/pr/missouri-man-sentenced-10-years-prison-child-pornography-crime |
| release date in text | October 18, 2023 | February 06, 2024 |
| shared conduct date in text | November 27, 2022 | November 27, 2022 |
| text length | 2,968 | 2,820 |
| fingerprint (fp-1) | 735b8410e519a70d… | bda3ff387e7fcfd2… |

Different URLs (plea, then sentencing), different release dates, different fingerprints; text similarity 0.857 with 17 sentences shared and 7/6 unique (the plea and the sentence). The corpus counts one prosecution twice.

## 10. Platform co-occurrence (BiCM)

Q1 cases × named platforms; an edge is dropped when the case was published after the platform's registry `until`. Bipartite Configuration Model (Saracco et al. 2015) fitted with `bicm` 3.5.0 in an isolated venv; for each platform pair, observed co-occurrence, BiCM expectation, and the exact Poisson-binomial upper-tail p-value; Benjamini–Hochberg at q = 0.05 over every pair. Fit: max degree error 2.5e-10; exact vs package `poibin` p-values differ by at most 1.6e-13. Code: [cooc/](cooc/).

| run | cases | platforms | edges | pairs tested | pairs co-occurring | significant | of those flagged (<5 cases or one source) |
|---|---:|---:|---:|---:|---:|---:|---:|
| stated: stated tier, rows closed at `until` | 1,300 | 45 | 1,510 | 990 | 93 | 1 | 0 |
| all: all tiers | 1,833 | 51 | 2,423 | 1,275 | 212 | 51 | 45 |
| stated_clean: stated tier without the 0 boilerplate-only edges (cooc-boilerplate-1) | 1,300 | 45 | 1,510 | 990 | 93 | 1 | 0 |
| all_clean: all tiers without the 106 boilerplate-only edges (cooc-boilerplate-1) | 1,823 | 49 | 2,317 | 1,176 | 162 | 0 | 0 |

Platform labels carry the Facebook-in-Messenger correction (§12). Boilerplate: an edge is dropped when every sentence naming the platform matches an app-list pattern (`config/cooc_boilerplate_sentences.yaml`).

**Summary.** Stated tier: 990 pairs tested, 1 significant; Facebook + Facebook Messenger 18 cases against 4.288 expected. All tiers: 51 significant, 45 flagged (<5 cases or one source); without boilerplate edges, stated **1**, all tiers **0**. Significant on both boilerplate-free runs: none. Most Q1 cases name one platform (§11), so the test has little power.

Affordance classes on each significant pair are in numbers.json (`significant[].classes`). Same-platform class pairs (registry bundling) are listed per platform under `mechanical_same_platform_class_pairs` and not tested.

## 11. Prevalence by class, tier and level

Over the 4,628 Q1 platform–case records (line-wrap tiers: stated 2,335, inferred 404, named-only 1,889). Levels: A the class is registry default_on on the platform with its window open at publication; A_any the platform offered it at all; B capability-relevant conduct; I inferred facilitation; C instrumental, stated in the platform sentence. Cells: records (share of all Q1 records); then stated / inferred / named-only. Source: `build/records.csv` (`<Class>.<level>` columns).

| class | A | B | I | C |
|---|---|---|---|---|
| Anonymity | 1,463 (31.6%): 1,022 / 167 / 274 | 532 (11.5%): 482 / 50 / 0 | 407 (8.8%): 367 / 40 / 0 | 32 (0.7%): 29 / 3 / 0 |
| Ephemerality | 415 (9.0%): 321 / 63 / 31 | 402 (8.7%): 371 / 31 / 0 | 177 (3.8%): 162 / 15 / 0 | 0 (0.0%): 0 / 0 / 0 |
| ContactDiscovery | 1,245 (26.9%): 717 / 147 / 381 | 596 (12.9%): 544 / 52 / 0 | 323 (7.0%): 299 / 24 / 0 | 10 (0.2%): 10 / 0 / 0 |
| UnmonitoredCommunication | 1,353 (29.2%): 990 / 155 / 208 | 605 (13.1%): 553 / 52 / 0 | 416 (9.0%): 379 / 37 / 0 | 24 (0.5%): 23 / 1 / 0 |
| DistributionInfrastructure | 938 (20.3%): 469 / 101 / 368 | 1,094 (23.6%): 951 / 143 / 0 | 742 (16.0%): 656 / 86 / 0 | 571 (12.3%): 521 / 50 / 0 |
| GenerativeSynthesis | 87 (1.9%): 63 / 5 / 19 | 138 (3.0%): 124 / 14 / 0 | 63 (1.4%): 59 / 4 / 0 | 21 (0.4%): 21 / 0 / 0 |

Named platforms per case: stated tier 1,127 cases name exactly 1, 173 name 2+ (of 1,300); all tiers 1,456 vs 377 (of 1,833). B, I and C are zero on named-only records by construction. C, I and B nest within A_any (C ⊆ I ⊆ B ⊆ A_any); A counts only capabilities on by default, so a C on an opt-in feature is not in A. I is B on a default_on platform with its window open, or C. A_any (every capability the platform had shipped): Anonymity 2,256, Ephemerality 1,157, ContactDiscovery 2,300, UnmonitoredCommunication 2,233, DistributionInfrastructure 2,462, GenerativeSynthesis 876 (`A_any` in numbers.json).

## 12. Data checks

**Boilerplate app lists.** Rule: every sentence naming the platform is awareness/list framing (is_awareness_or_list_framing), or names 3+ of the case's platforms and is a bare enumeration (is_enumeration_only). Flagged: 240 records (225 named-only, 12 inferred, 3 stated); 27 Q1 cases carry only flagged tags, 43 carry only flagged named-platform tags. Named-only totals may be inflated by up to the flagged named-only records. This is an upper bound.

**Facebook double tag.** the platform matcher tags 'Facebook' inside the phrase 'Facebook Messenger'. Corpus: 321 cases tagged Facebook in the DB, 23 only from 'Facebook Messenger' (23 in Q1) → **298**. Applied at load, in every AfH output (snapshot cases, Q1 records, manifest, harm tables, co-occurrence); the DB is unchanged. Manifest Facebook after the correction: 295 total, 129 stated.

**Yahoo Chat end year.** both capability years are right for their product (public chat rooms closed Dec 14, 2012; Yahoo! Messenger private messages until Jul 17, 2018). The platform-level end was wrong: the label also matches 'Yahoo! Messenger' (pattern_processing.py, the 'Yahoo Chat' platform pattern). Fix: capability_sources/messaging.yaml Yahoo Chat ended 2012 -> 2018; platforms.yaml regenerated (until 2012 -> 2018).

**Feature count.** `/api/stats` gives 231,988 on the frozen corpus under the rule in §1. Span-checked field assertions: 132,956 rows over 10,698 cases, 132,956 span-ok, 7 fields. Excluded by rule (`run/feature_count.py` EXCLUDED; stored items): agency_grounds 40,492, location_grounds 41,965, person_spans 98,470, comparison_values 10,802, ml_features 10,802, date_range 10,802, document_version_id 329, extraction_run_id 10,802, press_digest_pollution 26, organizations 35,666, pathway_agencies_federal 17,436, pathway_agencies_state_local 23,104, severity_phrases 4,955, perpetrator_admissions 1,974, investigation_technology 1,810. Counted case attributes: platforms_used 10,971, case_topics 31,532, severity_indicators 7,386, agencies_involved 40,492, perpetrator_admission_themes 1,676, anonymization_network 112, p2p_clients 3, locations 41,965, relationship_to_victim 796, perpetrator_gender 308, multi_defendant_operation 125, victim_count 161, prosecution_outcome 27,711, evidence_volume 1,988, case_demographics 288; span-checked assertions: age 16,271, date 25,530, sentence 18,187, investigation_type 2,636, legal_context 2,437, prior_history 1,212, cybertip_reporter 201. The two sum to NFeatures.

## 13. Publication year

Rule: a stored publication year is corrected when >= 2 of the record's publication evidence fields (case-id year, compilation-file year, stated publication dates) agree on another year and none supports the stored one; an event date supports the stored year only when no publication date is stated. **29 stored years corrected** at load (table below); the DB is unchanged. **50 records flagged** because their stored year conflicts with their own fields (39 of them not corrected; list in `year_evidence.json`).

| case | stored | corrected | agreeing evidence |
|---|---:|---:|---|
| ncmec_2022_056 | 2021 | 2022 | id, file, publication |
| ncmec_2022_146 | 2021 | 2022 | id, file, publication |
| ncmec_2022_167 | 2021 | 2022 | id, file, publication |
| ncmec_2022_173 | 2021 | 2022 | id, file, publication |
| ncmec_2022_222 | 2021 | 2022 | id, file, publication |
| ncmec_2022_309 | 2021 | 2022 | id, file, publication |
| ncmec_2022_314 | 2021 | 2022 | id, file, publication |
| ncmec_2022_415 | 2021 | 2022 | id, file, publication |
| ncmec_2022_506 | 1992 | 2022 | id, file |
| ncmec_2022_512 | 2019 | 2022 | id, file, publication |
| ncmec_2022_543 | 2021 | 2022 | id, file, publication |
| ncmec_2023_013 | 2022 | 2023 | id, file, publication |
| ncmec_2023_080 | 2022 | 2023 | id, file, publication |
| ncmec_2023_175 | 2020 | 2023 | id, file |
| ncmec_2023_178 | 2022 | 2023 | id, file, publication |
| ncmec_2023_245 | 2020 | 2023 | id, file, publication |
| ncmec_2023_275 | 2017 | 2023 | id, file, publication |
| ncmec_2023_301 | 2022 | 2023 | id, file, publication |
| ncmec_2023_400 | 2022 | 2023 | id, file, publication |
| ncmec_2023_405 | 2022 | 2023 | id, file, publication |
| ncmec_2023_510 | 2022 | 2023 | id, file, publication |
| ncmec_2023_582 | 2019 | 2023 | id, file, publication |
| ncmec_2023_597 | 2007 | 2023 | id, file, publication |
| ncmec_2024_1203 | 2025 | 2024 | id, file |
| ncmec_2024_609 | 2023 | 2024 | id, file, publication |
| ncmec_2024_905 | 2002 | 2024 | id, file |
| ncmec_2025_299 | 2022 | 2025 | id, file, publication |
| ncmec_2025_559 | 2022 | 2025 | id, file, publication |
| ncmec_2025_843 | 2022 | 2025 | id, file |

**Sensitivity.** Every year-dependent result (launch cohorts, publication eras, affordance × harm tables, prevalence, Q1) recomputed without the 50 flagged records (15 of them in Q1): **no verdict changes**. Values side by side in `year_sensitivity.json`.

## Flags

- ⚑ **NAgencies** is 4,326 after normalization; 5,052 raw labels remain distinct before it.
- ⚑ **NTaskForces**: 61 of 61 task forces are mentioned in corpus text, 43 have a case from their own feed; stored agency labels cannot count them (ingest collapses every ICAC task force to `ICAC`).
- ⚑ **Publication year**: 29 stored years corrected at load and 50 records flagged (§13); the DB is unchanged.
- ⚑ **Launch cohorts** that do not qualify: >=2017 (2 coded cases).
- ⚑ **PACER doc types**: 25 indictment documents in 24 cases; 2 typed `statement_of_offense`; 8 cases have a factual-statement document of some type.
- ⚑ **Record tiers**: two rules (line-wrap, primary; tiers-1, baseline). Line-wrap moves 529 records into stated.
- ⚑ **PACER reliability** is conditional (matched pairs only): mean κ 0.296, mean event F1 0.229; lowest F1 `ncmec_2025_1026` (0.0: 0 agreed acts from 11 vs 99 coded).
- ⚑ **Facebook double tag**: 23 DB Facebook tags exist only inside 'Facebook Messenger'; corrected at analysis time, the DB still holds them.
- ⚑ **Duplicate prosecution**: 2023_103 and 2024_461 are one prosecution counted twice; other such pairs are not measured here.
