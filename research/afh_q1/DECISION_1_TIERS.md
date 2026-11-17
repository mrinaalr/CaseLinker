# Decision 1: evidence-tier correction

**Recommendation:** adopt **B+, the additive line-wrap repair**. It gives **1,526** strict cases documenting platform use, against 1,257 under the original rules. Do not adopt the verb expansion (C) or the combined rule (D, 1,577).

The published denominator is unchanged until you decide. `stated_vs_inferred` is still the original `tiers-1` result. The repair is carried beside it as `stated_vs_inferred_linewrap` (`tiers-1+linewrap-1`), and the research outputs show both.

Numbers come from `outputs/tier_variants.json` (snapshot `60f7bfaa…`); the review rows are in `config/review_round3_tier_variants.csv`. Case counts are strict: cases naming a specific platform, 1,863 in total.

## The variants

| Variant | Rule | Use-documented cases | Case moves vs A |
|---|---|---|---|
| A original | Published `classify_sentence` on stored text | **1,257** (1,080 stated, 177 inferred) | – |
| B line-wrap repair | Same rules on text with single line breaks joined, unless the line ends in `. ! ? :` (paragraph breaks kept) | 1,486 | +186 named→stated, +83 named→inferred, +57 inferred→stated; **but −21 stated→named, −18 inferred→named, 4 lost** |
| B+ additive repair | Per record, the better of A and B | **1,526** | +186 named→stated, +83 named→inferred, +57 inferred→stated; no demotions |
| C extra verbs | A plus keyword stems `stor, sav, receiv, request, purchas, possess, download, account contain, member of, joined, post` | 1,398 | +135 named→stated, +6 named→inferred, +37 inferred→stated |
| D combined | B and C | 1,577 | +299 named→stated, +59 named→inferred, +91 inferred→stated; −19 stated→named, −18 inferred→named |

**Why B demotes.** Joining wrapped lines makes longer sentences. The original "app list" heuristic (3+ commas and no listed verb) then fires: 50 of 66 demoted records. The bare "such as" awareness trigger accounts for 7, and a PSA-boundary shift for 1.

**Why C is noisy.** The verbs that unlock its promotions are mostly ambiguous stems: `post` 36 (posted bond, post office), `stor` 15 (story, store), `receiv` 13 (received a sentence or tip).

## Blind review

One blind reviewer coded 120 records in two halves of 60. They saw only masked passages, in shuffled order, with no variant or tier shown. Each record got one code:

| Code | Meaning |
|---|---|
| offender use: stated | the release says the offender used the platform |
| offender use: via report | a platform report or CyberTip describes the offender's activity or account contents |
| victim or third-party use | only a victim, co-defendant or other person used it |
| law-enforcement use | undercover or police account or posting only |
| reporting only | company named as a tip source, no activity described |
| evidence receipt | records or warrant returns, no activity described |
| generic discussion | PSA, app list, background, unrelated |
| not in passage | the platform doesn't appear |

An offender chatting with an undercover officer counts as offender use.

| Stratum | n | Offender use (stated + via report) | Non-use codes |
|---|---|---|---|
| Random original named-only | 40 | 26 (19 + 7) | 13 generic, 1 evidence receipt |
| Random original stated | 15 | 13 (9 + 4) | 1 reporting only, 1 not in passage |
| Random original inferred | 15 | 14 (9 + 5) | 1 generic |
| B promotions | 15 | 11 (9 + 2) | 3 generic, 1 not in passage |
| C-only promotions | 15 | 11 (5 + 6) | 3 generic, 1 law-enforcement use |
| D-only promotions (need both) | 10 | 10 (8 + 2) | – |
| B demotions | 10 | **10 (6 + 4)** | – |

No sampled promotion was victim-only use. Law-enforcement use appeared once (a police Facebook post, C-only). Of the 8 false promotions, 7 are Facebook or YouTube boilerplate (agency page links, share buttons, police posts cited as the source); the eighth is a promoted Tor record whose passage never names Tor.

## Precision and recall

The design supports two kinds of estimate:
- **Precision of promotions** comes from the targeted strata.
- **Recall and false-promotion rate inside the published named-only tier** come only from the random named-only sample. That sample doesn't support corpus-wide recall: offender use that the platform extractor never tagged is outside it.

| Variant | Precision of its promotions | Recall within named-only (of 26 offender-use records) | False promotions (of 14 non-use records) |
|---|---|---|---|
| B | 11/15 = 0.73 (0.48–0.89) | 14/26 = 0.54 (0.36–0.71) | 2/14 = 0.14 (0.04–0.40) |
| B+ | same promotions as B; its demotions are undone (B demotions were 10/10 real use) | 14/26 = 0.54 | 2/14 = 0.14 |
| C | 11/15 = 0.73 (0.48–0.89) | 4/26 = 0.15 (0.06–0.34) | 2/14 = 0.14 |
| D | 10/10 for D-only promotions (0.72–1.00) | 17/26 = 0.65 (0.46–0.81) | 4/14 = 0.29 (0.12–0.55) |

Intervals are 95% Wilson. Precision of the original tiers on the same scale is stated 13/15 = 0.87 and inferred 14/15 = 0.93.

- **C** buys little recall (4 of 26) at the same false-promotion cost as B.
- **D** adds 3 recoveries over B but doubles the false promotions.
- **B+** keeps every record the original rules support, recovers about half of the hidden use, and adds no new kind of error beyond Facebook boilerplate. That error is a separate, fixable filter (see below).

## False negatives

Nine named-only records with offender use remain under every variant:
- `ncmec_2022_522` Kik
- `ncmec_2022_466` Instagram
- `doj_safe_childhood_2025_408` Telegram
- `usss_2025_003` Cash App
- `ncmec_2022_585` Instagram
- `nj_ag_2019_002` Skout
- `doj_safe_childhood_2025_258` iCloud
- `pa_ag_2026_029` Instagram
- `ncmec_2025_915` Instagram

Their causes were not diagnosed one by one. Likely candidates are text past the 6,000-character cap, use described in a neighbouring sentence, and reports of account contents. B+ remains a lower bound.

## How the earlier 1,480 was calculated

```
1,480 ≈ 1,080 × 13/15  +  177 × 14/15  +  606 × 25/40
        (stated cases)    (inferred-only)   (named-only)
bounds: the same sum using each rate's Wilson lower (1,080) and upper (1,674) limit
```

Three limits, in order of importance:
1. **The rates are record-level but were applied to case-level tier counts.** A named-only case can have its use documented by a record that wasn't sampled.
2. **Summing per-tier Wilson limits is not a joint interval.** It is wider than a proper one.
3. **"Use" in that review counted implied use** without separating reporting from offender use.

Re-coded with the offender-use scheme here (26/40 named-only, 13/15 stated, 14/15 inferred), the same calculation gives 1,495. A normal-approximation 95% interval gives 1,288–1,702.

At record level the comparable figure is 1,953 offender-use records (95% CI 1,693–2,214) out of 2,487. A case-level estimate with a proper interval would need a case-level random sample. Treat 1,480 and 1,495 as rough guides, not as counts.

## Implementation

| Change | Where | Test |
|---|---|---|
| `repair_line_wraps`, `linewrap_tiers` (additive) and versions `tiers-1` / `tiers-1+linewrap-1` | `ontology/platform_affordance_evidence/platform_affordance_evidence.py` | `tests/api/test_platform_affordance_evidence_linewrap.py`: wraps join and paragraphs stay; a wrapped sentence goes from named-only to stated; idempotent; additive under a lower repaired tier; published version unchanged |
| Records carry `stated_vs_inferred_linewrap`; `_meta` records both rule versions | evidence JSON rebuilt. The published tier is identical for all 4,680 records (checked). | freshness gate flagged the builder change and forced the rebuild |
| Research outputs carry `tier_linewrap`; the inventory shows the B+ strict row as an alternative, not the denominator | `afhq1/pipeline.py`, `afhq1/build.py`, `outputs/tier_variants.json` | `tests/research/test_afh_q1_pipeline.py`: B+ never demotes; published denominator equals A; record line-wrap tier ≥ published tier |

## If you adopt B+

1. Switch the Section 3 count to 1,526 and state the rule: original tiers plus a hard-wrap repair that can only add evidence.
2. Keep 1,257 as the strict original-rule figure in a footnote or supplementary table.
3. Optionally, add a Facebook/YouTube boilerplate filter (agency page links, share buttons, "posted on the sheriff's Facebook page") before publication. It accounts for 7 of 8 sampled false promotions. That is a separate rule change and would need its own check.

Unrelated, noted only: running `tests/api` creates an empty `caselinker.db` in a worktree, which makes the `caselinker.db`-dependent extraction tests fail instead of skipping. This behaviour predates this work.

## Addendum: final rule (linewrap-2)

The authors adopted the repair on condition of targeted validation. A blind review covered 45 of the 269 cases promoted under B+, oversampling the 87 social-platform promotions (`config/review_round4_promoted_cases.csv`):
- **39 of 45 showed offender use:** 14/20 social and 25/25 other.
- **All 6 misses were agency social-media boilerplate:** a sheriff posting arrest news on its Facebook page, a Facebook/X/YouTube footer, a facebook.com post URL, "mugshots are available on the Attorney General's Twitter page", and a police video embed.

`linewrap-2` refuses a promotion whose earning sentence matches `AGENCY_SOCIAL_BOILERPLATE`. Effect:
- it blocks 4 of the 6 misses and none of the 39 true promotions;
- in the earlier record sample, it blocks 1 of 4 false promotions and keeps all 11 true ones;
- promoted cases fall from 269 to 256, and documented use from 1,526 to **1,513**, now the primary count;
- weighted precision of the promoted cases is about 96%, with a conservative lower bound of about 80% (strata 14/16 social of 74, 25/25 other of 182).

1,257 remains the original-rule baseline. The published `stated_vs_inferred` field is still `tiers-1`; `stated_vs_inferred_linewrap` carries `tiers-1+linewrap-2`.
