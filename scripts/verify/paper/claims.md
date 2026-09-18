# Paper claims catalog

_Generated 2026-06-24 07:16 UTC_

Source: [Affordance, Misuse, Harm, Kill Chain](https://mrinaalr.github.io/website/Affordance%2C%20Misuse%2C%20Harm%2C%20Kill%20Chain.pdf)

**64** claims registered for verification.

Legend: **bold** = headline / table stat picked for high scrutiny.

## Bold / headline picks (why included)

- **cover.corpus_cases** (Cover): Corpus comprises 7,426 ICAC case records.
  - _Why:_ Primary scale claim; drives every rate and Q1 denominator.
- **cover.features** (Cover): Corpus yields 80,000+ structured features.
  - _Why:_ Headline pipeline scale; must match extraction dimension accounting.
- **cover.sources** (Cover): Cases collected from 56 law enforcement sources.
  - _Why:_ Source diversity claim on cover.
- **cover.task_forces** (Cover): Coverage spans 61 ICAC task forces.
  - _Why:_ ICAC ecosystem breadth; cross-check narrative + ingest mapping.
- **cover.agencies** (Cover): Corpus reflects 3,500+ law enforcement agencies.
  - _Why:_ Agency normalization headline.
- **cover.pacer_records** (Cover): PACER layer includes 8 federal prosecution records (3 indictments, 2 Statements of Offense).
  - _Why:_ Ground-truth court anchor count; must match BULK_FOLDER + anchor 5.
- **cover.timespan** (Cover): Corpus timespan is 2002–2026.
  - _Why:_ Temporal scope for era analysis.
- **cover.platforms_analyzed** (Cover): 30+ platforms analyzed in affordance framework.
  - _Why:_ Platform breadth for Q1 manifest.
- **s3.q1_stated_cases** (§3.1): 856 cases (45.8%) contain at least one stated platform-offense record.
  - _Why:_ Strongest evidentiary tier; headline Q1 quality stat.
- **manifest.kik** (§4 Table 1): Kik: 208 stated · 352 total in Q1 evidence.
  - _Why:_ Table 1 headline platform row; verified against q1_evidence.json tiers.
- **manifest.snapchat** (§4 Table 1): Snapchat: 169 stated · 257 total in Q1 evidence.
  - _Why:_ Table 1 headline platform row; verified against q1_evidence.json tiers.
- **manifest.discord** (§4 Table 1): Discord: 43 stated · 99 total in Q1 evidence.
  - _Why:_ Table 1 headline platform row; verified against q1_evidence.json tiers.
- **manifest.facebook** (§4 Table 1): Facebook: 55 stated · 274 total in Q1 evidence.
  - _Why:_ Table 1 headline platform row; verified against q1_evidence.json tiers.
- **manifest.instagram** (§4 Table 1): Instagram: 27 stated · 174 total in Q1 evidence.
  - _Why:_ Table 1 headline platform row; verified against q1_evidence.json tiers.
- **manifest.reddit** (§4 Table 1): Reddit: 10 stated · 22 total in Q1 evidence.
  - _Why:_ Table 1 headline platform row; verified against q1_evidence.json tiers.
- **manifest.tiktok** (§4 Table 1): TikTok: 4 stated · 25 total in Q1 evidence.
  - _Why:_ Table 1 headline platform row; verified against q1_evidence.json tiers.
- **manifest.dropbox** (§4 Table 1): Dropbox: 33 stated · 86 total in Q1 evidence.
  - _Why:_ Table 1 headline platform row; verified against q1_evidence.json tiers.
- **manifest.mega** (§4 Table 1): Mega.nz: 3 stated · 15 total in Q1 evidence.
  - _Why:_ Table 1 headline platform row; verified against q1_evidence.json tiers.
- **manifest.whisper** (§4 Table 1): Whisper: 3 stated · 11 total in Q1 evidence.
  - _Why:_ Table 1 headline platform row; verified against q1_evidence.json tiers.
- **manifest.omegle** (§4 Table 1): Omegle: 2 stated · 7 total in Q1 evidence.
  - _Why:_ Table 1 headline platform row; verified against q1_evidence.json tiers.
- **manifest.genai** (§4 Table 1): Gen AI: 21 stated · 54 total in Q1 evidence.
  - _Why:_ Table 1 headline platform row; verified against q1_evidence.json tiers.
- **manifest.p2p** (§4 Table 1): BitTorrent/P2P: 3 stated · 8 total in Q1 evidence.
  - _Why:_ Table 1 headline platform row; verified against q1_evidence.json tiers.
- **manifest.video** (§4 Table 1): Video streaming: 6 stated · 28 total in Q1 evidence.
  - _Why:_ Table 1 headline platform row; verified against q1_evidence.json tiers.
- **manifest.gaming** (§4 Table 1): Gaming platforms: 4 stated · 29 total in Q1 evidence.
  - _Why:_ Table 1 headline platform row; verified against q1_evidence.json tiers.
- **s4.affordance_predicts_harm** (§4): A platform's affordance profile predicts its harm profile.
  - _Why:_ Analytical thesis statement in §4 intro.
- **affordance.contact_cases** (§4.contact): Contact and approach affordances appear across 1,720 cases in Q1 evidence base.
  - _Why:_ Section affordance-class denominators; require harm_analysis crosswalk.
- **affordance.production_cases** (§4.production): Production affordances appear across 177 cases in Q1 evidence base.
  - _Why:_ Section affordance-class denominators; require harm_analysis crosswalk.
- **affordance.possession_cases** (§4.possession): Possession and trade affordances appear across 1,708 cases in Q1 evidence base.
  - _Why:_ Section affordance-class denominators; require harm_analysis crosswalk.
- **affordance.coordination_cases** (§4.coordination): Coordination affordances appear across 198 cases in Q1 evidence base.
  - _Why:_ Section affordance-class denominators; require harm_analysis crosswalk.
- **s7.law1_contact_primacy** (§7.3 Law 1): Law 1 (Contact Primacy): N=7,426 — no case documents exploitation without initial contact.
  - _Why:_ Formal invariant induced from corpus + PACER lifecycles.
- **s7.law2_backbone** (§7.3 Law 2): Backbone stages achieve 5/5 coverage across five anchor PACER offense types.
  - _Why:_ L* fundamental stages from state_machines compute_lstar.

## Abstract

| ID | Bold | Kind | Verify | Claim |
|---|---|---|---|---|
| `abstract.corpus` |  | corpus_stat | db | Analysis draws on 7,426 curated ICAC case records spanning 2002 to 2026. |
| `abstract.affordance_stability` |  | theoretical | paper_substring | Same capability types (anonymity, ephemerality, distribution, contact discovery, trust-building) recur across platforms. |

## Cover

| ID | Bold | Kind | Verify | Claim |
|---|---|---|---|---|
| `cover.corpus_cases` | **yes** | corpus_stat | db | Corpus comprises 7,426 ICAC case records. |
| `cover.features` | **yes** | corpus_stat | computed | Corpus yields 80,000+ structured features. |
| `cover.sources` | **yes** | corpus_stat | db | Cases collected from 56 law enforcement sources. |
| `cover.task_forces` | **yes** | corpus_stat | db | Coverage spans 61 ICAC task forces. |
| `cover.agencies` | **yes** | corpus_stat | db | Corpus reflects 3,500+ law enforcement agencies. |
| `cover.pacer_records` | **yes** | pacer | file | PACER layer includes 8 federal prosecution records (3 indictments, 2 Statements of Offense). |
| `cover.timespan` | **yes** | corpus_stat | db | Corpus timespan is 2002–2026. |
| `cover.platforms_analyzed` | **yes** | corpus_stat | db | 30+ platforms analyzed in affordance framework. |

## §1

| ID | Bold | Kind | Verify | Claim |
|---|---|---|---|---|
| `prior.livingstone_digital_physical` |  | literature | literature | Livingstone and Smith [12] document inseparability of digital and physical child risk. |

## §2.1

| ID | Bold | Kind | Verify | Claim |
|---|---|---|---|---|
| `prior.icac_task_forces` |  | external_citation | external | ICAC program: 61 federally coordinated task forces representing 5,400+ agencies (est. 1998). |
| `prior.icac_fy2024_investigations` |  | external_citation | external | FY2024 ICAC task forces conducted ~203,467 investigations. |
| `prior.icac_fy2024_arrests` |  | external_citation | external | FY2024 ICAC arrests exceeded 12,600 suspected offenders. |
| `prior.ncmec_cybertipline_2024` |  | external_citation | external | 2024 NCMEC received ~20.5M CyberTipline reports (~29.2M incidents). |
| `prior.tech_coalition_hash_89` |  | external_citation | external | Tech Coalition 2023 survey: 89% of members deploy image hash-matching. |
| `prior.thorn_safer_76m` |  | external_citation | external | Thorn Safer uses 76M+ verified CSAM hashes. |
| `prior.wolak_internet_initiated` |  | literature | literature | Wolak et al. documented internet-initiated sex crime dynamics via LE survey. |

## §2.2

| ID | Bold | Kind | Verify | Claim |
|---|---|---|---|---|
| `prior.gibson_affordance` |  | literature | literature | Affordance concept originates with Gibson [5] (ecological psychology). |

## §3.1

| ID | Bold | Kind | Verify | Claim |
|---|---|---|---|---|
| `s3.corpus_public` |  | methodology | paper_substring | All 7,426 records are publicly available; no private investigative files. |
| `s3.hrpo_determination` |  | methodology | paper_substring | Research under UMass HRPO NHSR Determination #7668. |
| `s3.agency_variants` |  | corpus_stat | db | Agency normalization resolves 3,796 unique agency string variants. |
| `s3.q1_candidates` |  | q1_stat | q1_json | Q1 candidate pool: 1,875 cases (25.1% of corpus) with named platforms. |
| `s3.q1_no_platform_pct` |  | q1_stat | computed | 74.9% of corpus lacks named platform for affordance-level analysis. |
| `s3.q1_platform_pairs` |  | q1_stat | q1_json | Q1 evidence base: 1,875 cases across 3,128 platform–case records. |
| `s3.q1_named_platforms` |  | q1_stat | q1_json | 54 named platforms in Q1 candidate pool. |
| `s3.q1_stated_cases` | **yes** | q1_stat | q1_json | 856 cases (45.8%) contain at least one stated platform-offense record. |
| `s3.q1_inferred_only` |  | q1_stat | q1_json | 134 cases (7.2%) carry inferred-only platform evidence. |
| `s3.q1_named_only` |  | q1_stat | q1_json | 881 cases (47.1%) are named-only platform mentions. |
| `s3.opensource_mit` |  | methodology | external | CaseLinker released open-source under MIT License at github.com/mrinaalr/CaseLinker. |

## §3.2

| ID | Bold | Kind | Verify | Claim |
|---|---|---|---|---|
| `s3.shacl_graphs` |  | corpus_stat | file | 1,500+ SHACL-validated case graphs support Q1 analysis. |
| `s3.mcp_tools` |  | corpus_stat | computed | CaseLinker MCP server exposes 37 structured tools. |
| `s3.case_uco_classes` |  | external_citation | external | CASE-UCO SDK implements 428+ ontology classes. |

## §3.3

| ID | Bold | Kind | Verify | Claim |
|---|---|---|---|---|
| `s3.pacer_expansion_four` |  | pacer | file | Four additional federal prosecution records captured via facet-tree traversal (targeting 50 total). |
| `s3.q2_anchor_five` |  | lifecycle | lifecycle | Q2 anchored on five PACER federal cases (Rehman, Amin, Pathmanathan, Bermudez, Riley). |

## §4

| ID | Bold | Kind | Verify | Claim |
|---|---|---|---|---|
| `s4.platform_labels` |  | q1_stat | q1_json | Q1 evidence base names 54 distinct platform labels. |
| `s4.affordance_predicts_harm` | **yes** | theoretical | paper_substring | A platform's affordance profile predicts its harm profile. |

## §4 Table 1

| ID | Bold | Kind | Verify | Claim |
|---|---|---|---|---|
| `manifest.kik` | **yes** | platform_manifest | q1_json | Kik: 208 stated · 352 total in Q1 evidence. |
| `manifest.snapchat` | **yes** | platform_manifest | q1_json | Snapchat: 169 stated · 257 total in Q1 evidence. |
| `manifest.discord` | **yes** | platform_manifest | q1_json | Discord: 43 stated · 99 total in Q1 evidence. |
| `manifest.facebook` | **yes** | platform_manifest | q1_json | Facebook: 55 stated · 274 total in Q1 evidence. |
| `manifest.instagram` | **yes** | platform_manifest | q1_json | Instagram: 27 stated · 174 total in Q1 evidence. |
| `manifest.reddit` | **yes** | platform_manifest | q1_json | Reddit: 10 stated · 22 total in Q1 evidence. |
| `manifest.tiktok` | **yes** | platform_manifest | q1_json | TikTok: 4 stated · 25 total in Q1 evidence. |
| `manifest.dropbox` | **yes** | platform_manifest | q1_json | Dropbox: 33 stated · 86 total in Q1 evidence. |
| `manifest.mega` | **yes** | platform_manifest | q1_json | Mega.nz: 3 stated · 15 total in Q1 evidence. |
| `manifest.whisper` | **yes** | platform_manifest | q1_json | Whisper: 3 stated · 11 total in Q1 evidence. |
| `manifest.omegle` | **yes** | platform_manifest | q1_json | Omegle: 2 stated · 7 total in Q1 evidence. |
| `manifest.genai` | **yes** | platform_manifest | q1_json | Gen AI: 21 stated · 54 total in Q1 evidence. |
| `manifest.p2p` | **yes** | platform_manifest | q1_json | BitTorrent/P2P: 3 stated · 8 total in Q1 evidence. |
| `manifest.video` | **yes** | platform_manifest | q1_json | Video streaming: 6 stated · 28 total in Q1 evidence. |
| `manifest.gaming` | **yes** | platform_manifest | q1_json | Gaming platforms: 4 stated · 29 total in Q1 evidence. |

## §4.contact

| ID | Bold | Kind | Verify | Claim |
|---|---|---|---|---|
| `affordance.contact_cases` | **yes** | affordance_count | manual | Contact and approach affordances appear across 1,720 cases in Q1 evidence base. |

## §4.coordination

| ID | Bold | Kind | Verify | Claim |
|---|---|---|---|---|
| `affordance.coordination_cases` | **yes** | affordance_count | manual | Coordination affordances appear across 198 cases in Q1 evidence base. |

## §4.possession

| ID | Bold | Kind | Verify | Claim |
|---|---|---|---|---|
| `affordance.possession_cases` | **yes** | affordance_count | manual | Possession and trade affordances appear across 1,708 cases in Q1 evidence base. |

## §4.production

| ID | Bold | Kind | Verify | Claim |
|---|---|---|---|---|
| `affordance.production_cases` | **yes** | affordance_count | manual | Production affordances appear across 177 cases in Q1 evidence base. |

## §5.3

| ID | Bold | Kind | Verify | Claim |
|---|---|---|---|---|
| `s5.amin_accounts` |  | lifecycle | paper_substring | Amin enterprise: 80+ Snapchat and 40+ Instagram accounts (indictment). |

## §5.4

| ID | Bold | Kind | Verify | Claim |
|---|---|---|---|---|
| `s5.bermudez_defendants` |  | lifecycle | paper_substring | Bermudez enterprise: six-defendant §2252A(g) coordinated network. |

## §6.1

| ID | Bold | Kind | Verify | Claim |
|---|---|---|---|---|
| `s6.ncmec_2023_incidents` |  | external_citation | external | 35.9 million suspected CSAM incidents reported to NCMEC in 2023. |
| `s6.report_act_2024` |  | external_citation | external | REPORT Act of 2024 extended mandatory reporting to enticement and trafficking. |

## §7.3

| ID | Bold | Kind | Verify | Claim |
|---|---|---|---|---|
| `s7.theorem_h_closed` |  | theoretical | paper_substring | Theorem 1: victim-facing harm set H is finite and closed. |

## §7.3 Law 1

| ID | Bold | Kind | Verify | Claim |
|---|---|---|---|---|
| `s7.law1_contact_primacy` | **yes** | theoretical | lifecycle | Law 1 (Contact Primacy): N=7,426 — no case documents exploitation without initial contact. |

## §7.3 Law 2

| ID | Bold | Kind | Verify | Claim |
|---|---|---|---|---|
| `s7.law2_backbone` | **yes** | lifecycle | lifecycle | Backbone stages achieve 5/5 coverage across five anchor PACER offense types. |

## §9 / PACER

| ID | Bold | Kind | Verify | Claim |
|---|---|---|---|---|
| `s9.pacer_cost` |  | pacer | file | PACER pull cost tracker totals $10.20 for three expansion cases. |
