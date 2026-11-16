# AfH 2.0 Q1 findings

Corpus snapshot `60f7bfaa…d06b` (10,802 cases, 78 sources), code `8d83621ec`, `platforms-1`, `codebook-2`. All numbers come from [outputs/](outputs/); [TABLES.md](outputs/TABLES.md) has every table. Nothing here changes the manuscript.

**Labels.** *Verified* means computed and reconciled by the pipeline. *Validated* means checked against source passages in the 107-row review (one reviewer, the agent; author adjudication pending). *Needs author check* means compiled without primary sources.

## The ten questions

### 1. Eligible case count

| Eligibility | Cases | Stated | Inferred only | Named only | Platform-case observations | Labels |
|---|---|---|---|---|---|---|
| Broad: any label but `online`/`internet` (AfH 1.0 rule) | 3,080 | 1,526 | 198 | 1,356 | 4,680 | 57 |
| **Strict: a specific named platform** | **1,863** | 1,080 | 177 | 606 | 2,487 | 52 |
| Assessed for affordances: specific + Gen AI + alias labels | 1,984 | 1,136 | 190 | 658 | 2,665 | 55 |

*Verified*: every row reconciles (tiers sum to cases and to observations; the corpus partitions into no label 4,384 + only online/internet 3,334 + lost to PSA/Gen AI filters 4 + broad 3,080). Broad minus strict is 1,096 generic-only cases ("social media", "chat"), 70 Gen-AI-only cases and 51 alias-only cases ("Webcam platform", "Mega").

**Use-documented (stated or inferred), strict: 1,257 cases.** This is a lower bound. In the review, all 10 inferred rows and 7 of 10 named-only rows (Wilson 95% 0.40–0.89) actually describe the platform being used. *Validated.*

### 2. Cases per affordance class

| Class | A available | B action-relevant | C instrumental | C platforms | C precision (sample) |
|---|---|---|---|---|---|
| Anonymity | 1,403 | 398 | 10 | 3 | 6/7 |
| Ephemerality | 670 | 235 | **0** | 0 | 0 of 10 review candidates |
| ContactDiscovery | 1,597 | 446 | 7 | 4 | 7/7 |
| UnmonitoredCommunication | 1,629 | 470 | 19 | 7 | 8/10 |
| DistributionInfrastructure | 1,774 | 668 | 281 | 22 | 14/15 |
| GenerativeSynthesis | 91 | 51 | 39 | 1 (Gen AI) | 9/10 |

A, B and C counts are distinct cases. Observations, labels, families and tier breakdowns are in `affordance_coverage.json`.

### 3. Capability-only vs supported use

Almost everything is capability-only. For every class except Distribution and Generative, at least 98% of A cases have no instrumental support. For example, Anonymity is available in 1,403 cases, action-relevant in 398 and instrumental in 10.

The B level shows conduct of the right kind on a platform with the feature. It is not evidence the feature mattered.

C is precise but has limited recall. Two of 8 review candidates were missed Anonymity cases: a cross-sentence persona and "two separate accounts" (the cue was widened in codebook-2). Releases also rarely describe *how* a feature helped. C counts are floors, not prevalence.

### 4. Recurrence across generations

Only **DistributionInfrastructure** recurs as documented misuse across platform families and periods:
- 281 cases across 22 platforms and 6 families (messaging, social, file hosting, P2P, video, Tor);
- instrumental cases in every publication era (8 / 5 / 53 / 215 for 2002–14 / 2015–19 / 2020–22 / 2023–26);
- top platform Kik at 36% of observations; top source DOJ Safe Childhood at 48% of cases.

The other classes:
- **Anonymity, ContactDiscovery, UnmonitoredCommunication:** appear in 2–3 families but with 7–19 cases, too few to compare periods.
- **Ephemerality:** no documented misuse at all. The capability recurs (670 cases on Snapchat, Instagram, Telegram, WhatsApp, Messenger and Wickr), but no release says disappearing content facilitated anything. The 10 candidates reviewed were screenshots or screen recordings: capture, the opposite of ephemerality.
- **GenerativeSynthesis:** one label, 2023–26 only. "Across generations" can't be tested.

Capability recurrence (A) spans 6–10 families and all four eras for the four contact/communication classes. That is a statement about platform design, not offender behaviour.

### 5. Evidence-grounded harm associations

*Verified* as co-occurrence; harm cues not separately validated. "Direct" means the harm cue is in the same platform sentence.

| Association | Direct cases | Status |
|---|---|---|
| DistributionInfrastructure → h3 material distributed | 271 of 281 | Grounded but near-definitional: the same verbs trigger both. Report as "documented distribution", not as an independent harm finding. |
| GenerativeSynthesis → h6 likeness synthesized | 37 of 39 | Same caveat |
| Anonymity → h4 sextorted | 3 | Thin |
| Platform → h4 sextorted (any C) | Instagram 5, Snapchat 2, Facebook 2 | Thin; sextortion is a case topic in only 117 cases |
| Anonymity / ContactDiscovery / Unmonitored → h1 groomed toward in-person | 0 direct; 4–5 case-level each | Case-level only |
| Any class → h2 coerced self-generated | 0 direct | Not supported in platform sentences |
| Ephemerality → h2, h4 | 0 | Unsupported |

### 6. What changed from AfH 1.0, and why

| Change | Effect |
|---|---|
| Corpus 7,426 → 10,802 cases (78 sources now; the June DB was not retained) | Candidate pool 1,875 → 3,080 broad |
| Denominator made explicit | 1,875 "named platforms" included 622 generic-only cases. The June strict equivalent is 1,193. AfH 1.0 percentages used 1,871, not 1,875. |
| 858 / 136 | No committed output or paper text has these numbers. The June files and the June paper both say 856 / 134 / 881. |
| Stale snapshot (fixed) | The 2026-11-12 published snapshot was built from a 23-day-old candidate list (3,183 vs 3,083 live). The builder now recomputes candidates on every run, and freshness also checks platform pairs and code hashes. |
| Case ids (fixed for research use) | Ids before #38 were positional. 48 of the 104 AfH 1.0 exemplars that still verify now sit under a different id. Between the 2026-10-20 local backup and the current DB, 919 more ids moved to different text (840 DOJ Safe Childhood), most likely in the 2026-11-12 rebuild while the fingerprint table was still empty. Citations now carry content fingerprints. |
| Platform re-resolution upstream | Footer handles ("Follow us on Twitter") no longer count as platforms. CBP and others dropped out. |
| Tier and candidate rules | Unchanged since June apart from FaceTime being added. Changes come from data, not rules. |
| Dates (fixed) | "May 2006" program boilerplate was tagged as an event date in 2,358 cases. `temporal_tags` 1.1.0 moves 3,183 dates to `program_boilerplate`. Stored assertions still hold the old roles until the next extraction run. |

### 7. Section 4 claims that survive

- Platforms recur across offense types as instruments of **distribution**: documented in 281 cases on 22 platforms in six families and in every era.
- Messaging and social platforms dominate the use-documented record (Kik 409, Snapchat 377, Facebook 132, Discord 70 cases).
- Generative synthesis is a distinct documented misuse (39 instrumental cases, 2023–26).
- Of the 118 AfH 1.0 harm-vector exemplars, 104 still verify as use-documented on that platform once resolved by content. 13 are unresolved (7 ambiguous, 6 probable) and 1 is named-only.
- The footnote's caution that distribution dominates because it is most detectable is consistent with the data.

### 8. Claims to revise or remove

| AfH 1.0 claim | Action |
|---|---|
| Counts 1,875 / 3,128 / 54 / 858 / 136 / 881 | Replace with the broad and strict rows above, stating both denominators |
| "54 named platforms" | 52 specific labels; generics listed separately |
| Snapchat signature "Ephemerality … evidence destruction by design" as documented misuse | Recast as a capability. No case documents it. |
| Kik "anonymity" as offender use | Capability. 2 Kik cases document identity concealment. |
| ψ(a): Anonymity/ContactDiscovery/Unmonitored → h1, h2, h4; Ephemerality → h2, h4 | Label as conceptual. Observed direct support is 0–3 cases. |
| "The same chat affordance, on a platform from 2008 or 2025, produces the same offense pattern" | Supported only for distribution; contact classes are too sparse to compare eras |
| "A platform's affordance profile predicts its harm profile" | Not tested by this corpus. Drop or call it a hypothesis. |
| Manifest per-platform stated/total (Kik 208/352, Snapchat 169/257, Discord 43/99, Facebook 55/274) | Now Kik 353/561, Snapchat 287/417, Discord 59/129, Facebook 112/318 (stated / all cases) |

### 9. Analyses strong enough to publish

1. Inventory funnel with broad and strict denominators and validated tier precision.
2. The capability vs action-relevant vs instrumental table (question 2). This is the central result.
3. Distribution recurrence across families and eras.
4. Generative synthesis as a separate class.
5. Within-source DOJ Safe Childhood 2021–26 series: 67–79% of named-platform cases document use, flat.
6. The manifest table with capability profiles (after author check) and fingerprint-verified exemplars (146 citations, all `ok`).

Not publishable as trends: cross-era comparisons. 84% of cases are from 2021–26, no source spans both eras at volume, and pre-2015 years hold 0–8 use-documented cases each.

### 10. Needs author adjudication

1. **Capability years** in `config/platforms.yaml`: every year was compiled without primary sources. Wrong years move A counts.
2. **Named-only under-classification**: 7 of 10 named-only rows document use. Accept stated ∪ inferred as a lower bound, or invest in tier recall with manual or LLM review.
3. **Second reviewer** for the 107-row sample, plus a harm-cue sample (harm cues were not sampled).
4. **Ephemerality**: keep it as a capability-only class or drop it. Also whether screenshot and screen-recording evidence (capture of live or ephemeral content) belongs in a seventh class; CAC's CoercionLeverage is out of AfH scope.
5. **Gen AI** is a technology label, not a platform. Decide whether the manifest lists it beside platforms.
6. **Alias labels**: "Webcam platform" and "Mega.nz". Mega matched 8/8 in the sample.
7. **13 unresolved AfH 1.0 exemplars**: listed in `outputs/legacy_afh1_exemplars.json`.
8. **Re-extraction** to store the fixed date roles in `caselinker.db` and production (needs your go-ahead).
9. **The public API serves raw `evidence_quote` text** from `platform_affordance_evidence.json`. That file is declared research-scope in `scan_public_surfaces_for_names.py`, but the API is public.

## Proposed Section 3 / 4 changes

| Section | Change |
|---|---|
| §3.1 corpus | 10,802 cases, 78 sources, publication years 2002–2026 (one 1992 date error). Name the snapshot identity and code commit. |
| §3.1 Q1 pool | Report broad (3,080) and strict (1,863) eligibility, observations (4,680 / 2,487), and tiers per row. State that tiers are a lower bound on documented use, with the validation table. |
| §3 timeline | Publication year only, labelled as such. Coverage table by era and source. No offense-date claims: 2,601 cases have any offense-typed date. |
| §4 manifest | Columns: platform, family, capability profile (years), cases, use-documented, conduct mix, A/B/C per class, verified exemplars. Separate "capability" from "documented misuse" in the signature column. |
| §4 harm | Two tables: empirical (question 5) and conceptual ψ(a), the latter labelled as hypothesis |
| Figures | F1 coverage by year and source under any timeline. F2 A/B/C funnel per class. F3 distribution C cases by family × era. |

## Limitations

- An enforcement-report corpus measures what agencies publish, not offending.
- Text is capped at 6,000 characters per release (87 cases hit the cap). Cues are sentence-local, so cross-sentence descriptions are missed.
- The tiers and cues are deterministic regexes, validated on small samples (n = 7–15 per item; wide intervals).
- Capability years have no primary-source verification yet.
- Harm cues are unvalidated, and the distribution/h3 and generative/h6 links are partly definitional.
- One reviewer.
