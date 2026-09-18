# Paper tested — claim verification report

_Generated 2026-06-24 07:16 UTC_

Paper: [Affordance, Misuse, Harm, Kill Chain](https://mrinaalr.github.io/website/Affordance%2C%20Misuse%2C%20Harm%2C%20Kill%20Chain.pdf)
Database: `/Users/mrinaalramachandran/Projects/CaseLinker/caselinker.db`

## Summary

| Status | Count |
|---|---:|
| ✅ pass | 36 |
| ⚠️ warn | 11 |
| 🌐 external | 10 |
| 📚 literature | 3 |
| ⏭️ skip | 4 |

## Warnings

### `s3.corpus_public`
- All 7,426 records are publicly available; no private investigative files.
- substring not found in extracted text

### `s3.hrpo_determination`
- Research under UMass HRPO NHSR Determination #7668.
- substring not found in extracted text

### `s3.q1_no_platform_pct`
- 74.9% of corpus lacks named platform for affordance-level analysis.
- unnamed share=74.8%

### `s3.mcp_tools`
- CaseLinker MCP server exposes 37 structured tools.
- @mcp.tool count=37

### `s3.pacer_expansion_four`
- Four additional federal prosecution records captured via facet-tree traversal (targeting 50 total).
- bulk folders=3

### `manifest.p2p`
- BitTorrent/P2P: 3 stated · 8 total in Q1 evidence.
- 3 stated · 12 total

### `manifest.video`
- Video streaming: 6 stated · 28 total in Q1 evidence.
- 9 stated · 94 total
  - Table 1 uses webcam/Twitch/YouTube subset.

### `manifest.gaming`
- Gaming platforms: 4 stated · 29 total in Q1 evidence.
- 4 stated · 19 total
  - Table 1 uses named game platforms only (not all GamePlatform-tagged rows).

### `s5.amin_accounts`
- Amin enterprise: 80+ Snapchat and 40+ Instagram accounts (indictment).
- substring not found in extracted text

### `s7.law2_backbone`
- Backbone stages achieve 5/5 coverage across five anchor PACER offense types.
- fundamental stages=4/5

### `s7.theorem_h_closed`
- Theorem 1: victim-facing harm set H is finite and closed.
- substring not found in extracted text

## Full results

| Status | ID | Section | Observed | Expected | Source | Detail |
|---|---|---|---|---|---|---|
| ✅ pass | `cover.corpus_cases` | Cover | 7427 | 7426 | caselinker.db | cases.count=7427 |
| ✅ pass | `cover.features` | Cover | 835042 | >=80000 | extracted_features | feature leaves=835,042 |
| ✅ pass | `cover.sources` | Cover | 56 | 56 | cases.source | distinct sources=56 |
| ✅ pass | `cover.task_forces` | Cover | 61 | 61 | icac_tf_verify | ICAC geographic roster |
| ✅ pass | `cover.agencies` | Cover | 3778 | >=3500 | extracted_features | agencies_involved unique=3778 |
| ✅ pass | `cover.pacer_records` | Cover | 8 | 8 | ontology/PACER | total PACER dirs=8 |
| ✅ pass | `cover.timespan` | Cover | 1992–2026 | 2002-2026 | cases.date_start | 1992–2026 |
| ✅ pass | `cover.platforms_analyzed` | Cover | 56 | >=30 | platforms_used | distinct platform labels=56 |
| ✅ pass | `abstract.corpus` | Abstract | 7427 | 7426 | caselinker.db | cases.count=7427 |
| ✅ pass | `abstract.affordance_stability` | Abstract |  |  | scripts/verify/paper/paper.txt | found in paper.txt |
| 🌐 external | `prior.icac_task_forces` | §2.1 |  |  | ICAC / OJJDP program materials | Requires manual or web verification against cited primary source. |
| 🌐 external | `prior.icac_fy2024_investigations` | §2.1 |  |  | ICAC annual report FY2024 | Requires manual or web verification against cited primary source. |
| 🌐 external | `prior.icac_fy2024_arrests` | §2.1 |  |  | ICAC annual report FY2024 | Requires manual or web verification against cited primary source. |
| 🌐 external | `prior.ncmec_cybertipline_2024` | §2.1 |  |  | NCMEC CyberTipline annual data | Requires manual or web verification against cited primary source. |
| 🌐 external | `prior.tech_coalition_hash_89` | §2.1 |  |  | Tech Coalition Transparency Report 2023 | Requires manual or web verification against cited primary source. |
| 🌐 external | `prior.thorn_safer_76m` | §2.1 |  |  | Thorn Safer product documentation | Requires manual or web verification against cited primary source. |
| 📚 literature | `prior.wolak_internet_initiated` | §2.1 | [24] |  | paper references | Citation [24] present in paper bibliography/body |
| 📚 literature | `prior.livingstone_digital_physical` | §1 | [12] |  | paper references | Citation [12] present in paper bibliography/body |
| 📚 literature | `prior.gibson_affordance` | §2.2 | [5] |  | paper references | Citation [5] present in paper bibliography/body |
| ⚠️ warn | `s3.corpus_public` | §3.1 |  |  | scripts/verify/paper/paper.txt | substring not found in extracted text |
| ⚠️ warn | `s3.hrpo_determination` | §3.1 |  |  | scripts/verify/paper/paper.txt | substring not found in extracted text |
| ✅ pass | `s3.agency_variants` | §3.1 | 3793 | 3796 | extracted_features | raw agency strings=3793 |
| ✅ pass | `s3.q1_candidates` | §3.1 | 1875 | 1875 | ontology/q1/candidates.json | candidates.json |
| ⚠️ warn | `s3.q1_no_platform_pct` | §3.1 | 74.8 | 74.9 | computed | unnamed share=74.8% |
| ✅ pass | `s3.q1_platform_pairs` | §3.1 | 3128 | 3128 | candidates.json | platform-case pairs |
| ✅ pass | `s3.q1_named_platforms` | §3.1 | 54 | 54 | candidates.json | named platforms |
| ✅ pass | `s3.q1_stated_cases` | §3.1 | 856 | 856 | q1_evidence.json | 856 (45.8%) |
| ✅ pass | `s3.q1_inferred_only` | §3.1 | 134 | 134 | q1_evidence.json | 134 |
| ✅ pass | `s3.q1_named_only` | §3.1 | 881 | 881 | q1_evidence.json | 881 |
| ✅ pass | `s3.shacl_graphs` | §3.2 | 2034 | >=1500 | ontology/graph_output/universe | universe/*.ttl count=2034 |
| ✅ pass | `s3.mcp_tools` | §3.2 | 37 | 37 | caselinker_mcp/server.py | @mcp.tool count=37 |
| 🌐 external | `s3.case_uco_classes` | §3.2 |  |  | CASE-UCO SDK / Project VIC | Requires manual or web verification against cited primary source. |
| 🌐 external | `s3.opensource_mit` | §3.1 |  |  | external source | Requires manual or web verification against cited primary source. |
| ⚠️ warn | `s3.pacer_expansion_four` | §3.3 | 3 | >=4 | BULK_FOLDER | bulk folders=3 |
| ✅ pass | `s3.q2_anchor_five` | §3.3 | 8 | 5 anchors | state_machines/graphs | jsonld graphs=8 |
| ✅ pass | `manifest.kik` | §4 Table 1 | 208 stated · 352 total | 208/352 | q1_evidence.json | 208 stated · 352 total |
| ✅ pass | `manifest.snapchat` | §4 Table 1 | 169 stated · 257 total | 169/257 | q1_evidence.json | 169 stated · 257 total |
| ✅ pass | `manifest.discord` | §4 Table 1 | 43 stated · 99 total | 43/99 | q1_evidence.json | 43 stated · 99 total |
| ✅ pass | `manifest.facebook` | §4 Table 1 | 55 stated · 274 total | 55/274 | q1_evidence.json | 55 stated · 274 total |
| ✅ pass | `manifest.instagram` | §4 Table 1 | 27 stated · 174 total | 27/174 | q1_evidence.json | 27 stated · 174 total |
| ✅ pass | `manifest.reddit` | §4 Table 1 | 10 stated · 22 total | 10/22 | q1_evidence.json | 10 stated · 22 total |
| ✅ pass | `manifest.tiktok` | §4 Table 1 | 4 stated · 25 total | 4/25 | q1_evidence.json | 4 stated · 25 total |
| ✅ pass | `manifest.dropbox` | §4 Table 1 | 33 stated · 86 total | 33/86 | q1_evidence.json | 33 stated · 86 total |
| ✅ pass | `manifest.mega` | §4 Table 1 | 3 stated · 15 total | 3/15 | q1_evidence.json | 3 stated · 15 total |
| ✅ pass | `manifest.whisper` | §4 Table 1 | 3 stated · 11 total | 3/11 | q1_evidence.json | 3 stated · 11 total |
| ✅ pass | `manifest.omegle` | §4 Table 1 | 2 stated · 7 total | 2/7 | q1_evidence.json | 2 stated · 7 total |
| ✅ pass | `manifest.genai` | §4 Table 1 | 21 stated · 54 total | 21/54 | q1_evidence.json | 21 stated · 54 total |
| ⚠️ warn | `manifest.p2p` | §4 Table 1 | 3 stated · 12 total | 3/8 | q1_evidence.json | 3 stated · 12 total |
| ⚠️ warn | `manifest.video` | §4 Table 1 | 9 stated · 94 total | 6/28 | q1_evidence.json | 9 stated · 94 total |
| ⚠️ warn | `manifest.gaming` | §4 Table 1 | 4 stated · 19 total | 4/29 | q1_evidence.json | 4 stated · 19 total |
| ✅ pass | `s4.platform_labels` | §4 | 54 | 54 | candidates.json | named platforms |
| ✅ pass | `s4.affordance_predicts_harm` | §4 |  |  | scripts/verify/paper/paper.txt | found in paper.txt |
| ⏭️ skip | `affordance.contact_cases` | §4.contact |  | 1720 | ontology/q1/q1_harm_analysis.json | Affordance-class case counts require hand-tuned crosswalk to q1_harm_analysis.json (not auto-verified yet). |
| ⏭️ skip | `affordance.production_cases` | §4.production |  | 177 | ontology/q1/q1_harm_analysis.json | Affordance-class case counts require hand-tuned crosswalk to q1_harm_analysis.json (not auto-verified yet). |
| ⏭️ skip | `affordance.possession_cases` | §4.possession |  | 1708 | ontology/q1/q1_harm_analysis.json | Affordance-class case counts require hand-tuned crosswalk to q1_harm_analysis.json (not auto-verified yet). |
| ⏭️ skip | `affordance.coordination_cases` | §4.coordination |  | 198 | ontology/q1/q1_harm_analysis.json | Affordance-class case counts require hand-tuned crosswalk to q1_harm_analysis.json (not auto-verified yet). |
| ⚠️ warn | `s5.amin_accounts` | §5.3 |  |  | scripts/verify/paper/paper.txt | substring not found in extracted text |
| ✅ pass | `s5.bermudez_defendants` | §5.4 |  |  | scripts/verify/paper/paper.txt | found in paper.txt |
| 🌐 external | `s6.ncmec_2023_incidents` | §6.1 |  |  | [21] NCMEC annual report | Requires manual or web verification against cited primary source. |
| 🌐 external | `s6.report_act_2024` | §6.1 |  |  | Public Law / DOJ summary | Requires manual or web verification against cited primary source. |
| ✅ pass | `s7.law1_contact_primacy` | §7.3 Law 1 | 7427 | 7426 | caselinker.db | cases.count=7427 |
| ⚠️ warn | `s7.law2_backbone` | §7.3 Law 2 | 4/5 | 5/5 | lifecycle_api | fundamental stages=4/5 |
| ⚠️ warn | `s7.theorem_h_closed` | §7.3 |  |  | scripts/verify/paper/paper.txt | substring not found in extracted text |
| ✅ pass | `s9.pacer_cost` | §9 / PACER | 10.2 | 10.20 | pacer_cost.csv | TOTAL=10.2 |

## External citations (manual follow-up)

Claims marked **external** cite ICAC, NCMEC, Tech Coalition, Thorn, statutes, or GitHub — verify against primary publications, not the CaseLinker DB.

- `prior.icac_task_forces`: ICAC program: 61 federally coordinated task forces representing 5,400+ agencies (est. 1998). _(source: ICAC / OJJDP program materials)_
- `prior.icac_fy2024_investigations`: FY2024 ICAC task forces conducted ~203,467 investigations. _(source: ICAC annual report FY2024)_
- `prior.icac_fy2024_arrests`: FY2024 ICAC arrests exceeded 12,600 suspected offenders. _(source: ICAC annual report FY2024)_
- `prior.ncmec_cybertipline_2024`: 2024 NCMEC received ~20.5M CyberTipline reports (~29.2M incidents). _(source: NCMEC CyberTipline annual data)_
- `prior.tech_coalition_hash_89`: Tech Coalition 2023 survey: 89% of members deploy image hash-matching. _(source: Tech Coalition Transparency Report 2023)_
- `prior.thorn_safer_76m`: Thorn Safer uses 76M+ verified CSAM hashes. _(source: Thorn Safer product documentation)_
- `s3.case_uco_classes`: CASE-UCO SDK implements 428+ ontology classes. _(source: CASE-UCO SDK / Project VIC)_
- `s3.opensource_mit`: CaseLinker released open-source under MIT License at github.com/mrinaalr/CaseLinker. _(source: see paper)_
- `s6.ncmec_2023_incidents`: 35.9 million suspected CSAM incidents reported to NCMEC in 2023. _(source: [21] NCMEC annual report)_
- `s6.report_act_2024`: REPORT Act of 2024 extended mandatory reporting to enticement and trafficking. _(source: Public Law / DOJ summary)_
