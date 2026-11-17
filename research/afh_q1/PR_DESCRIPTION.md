# Reproducible platform-affordance manifest for AfH 2.0 (Q1)

## Why

AfH 1.0's Q1 numbers could not be regenerated:
- the published evidence snapshot had been built from a stale candidate list;
- nearly half the cited examples (51 of 118) pointed at case ids that had since been renumbered;
- the six CAC affordance classes were never assigned to cases;
- platform capability dates had no sources.

This PR replaces that with a pipeline that rebuilds every Section 3–4 number from a pinned corpus snapshot, byte for byte. It also fixes the three pipeline defects behind the drift.

## What it establishes

All counts are from the 10,802-case snapshot `60f7bfaa…`.

| | Cases | Platform-case observations |
|---|---|---|
| Specific named platform | 1,863 | 2,487 |
| Documented platform use: stated 1,322 + co-occurring 191 | **1,513** | 1,834 |
| Same, original tier rules (baseline) | 1,257 | 1,477 |

Six CAC affordance classes, in distinct cases at four nested levels:

| Class | Available | Relevant conduct | Inferred facilitation | Explicit use |
|---|---|---|---|---|
| Distribution infrastructure | 1,898 | 960 | 667 | 515 |
| Unmonitored communication | 1,729 | 534 | 399 | 23 |
| Anonymity | 1,782 | 479 | 378 | 28 |
| Contact discovery | 1,798 | 529 | 38 | 10 |
| Ephemerality | 926 | 363 | 181 | 0 |
| Generative synthesis | 733 | 137 | 66 | 21 |

How to read them:
- Distribution and anonymity recur as documented conduct across platform families and all four publication eras.
- Ephemerality is present by design (Snapchat) but never described as instrumental in a release.
- Generative synthesis appears from 2023 only.
- Low explicit-use counts describe how press releases are written. They are not evidence against the affordance.

## How

| Step | Method |
|---|---|
| Snapshot | Read-only export of the corpus DB; `dataset_identity` hashes every case's id, content fingerprint, text, platforms and topics |
| Platform presence | 59 registered labels, each specific, technology, generic, alias or excluded; strict and broad denominators reported separately |
| Documented use | Existing sentence-level tier rules, plus an additive hard-wrap repair that refuses agency social-media boilerplate. Every downstream level uses the same primary tier. |
| Capabilities | 216 capability rows (56 platforms researched), each dated against company, press or scholarly sources. 25 manuscript claims checked on fetched pages (23 confirmed, 2 corrected). |
| Affordance levels | Available in the publication year → capability-relevant conduct → inferred facilitation (feature on by design) → explicit instrumental use |
| Harm | Potential (AfH ψ(a) pathway open) vs documented (harm stated in the release), reported separately |
| Citations | Every exemplar is bound to its case's content fingerprint, so a renumbered id cannot silently redirect it |

## Validation

Blind AI reviewers coded masked passages without seeing classifier labels; the author agent adjudicated disagreements. **No human adjudication yet.**

| Sample | Rows | Result |
|---|---|---|
| Classification | 107 | κ 0.78 (explicit use), 0.84 (tiers) between two reviewers |
| Line-wrap promoted cases | 45 of 269 | 39 offender use; the boilerplate guard removed 4 of the 6 misses; about 96% estimated precision after it |
| Tier samples | 70 + 120 | Stated 13/15 and co-occurring 14/15 offender use; named-only still hides use in about a third |
| Harm cues | 74 | Direct cues 67–100% precise by harm; case-level cues weak |
| Inferred facilitation | 36 | Reasonable for generative 6/6, unmonitored 5/6, contact 4/6; "present by design" only for anonymity and ephemerality |
| Manifest exemplars | 203 | 144 supported |

## Changes to existing code

| File | Change |
|---|---|
| `run/platform_affordance_evidence_freshness.py`, `run/main.py` | A snapshot is current only if corpus identity, every `(case, platform)` pair and the builder code match. The API uses the same check. |
| `ontology/platform_affordance_evidence/platform_affordance_evidence.py`, `build_candidates.py`, `scripts/run/rebuild_platform_affordance_evidence.py` | Candidates are recomputed on every build. `repair_line_wraps` and `linewrap_tiers` add `stated_vs_inferred_linewrap`; `stated_vs_inferred` is unchanged. |
| `src/Processing Layer/Pattern Processing Layer/temporal_tags.py` | 1.1.0: program-history dates ("launched in May 2006", 2,358 cases) become `program_boilerplate`; event dates gain `event_kind`. Applies to future extractions only. |
| `tests/conftest.py` | Removes an empty `caselinker.db` left by importing `run/main.py`, so later runs skip corpus tests instead of failing them |
| `ontology/platform_affordance_evidence/platform_affordance_evidence.json` | Regenerated. The published tier is identical for all 4,680 records. |

## Effect on the deployed app

No visualization code changes. After deploy:
- **Platform & Harm Explorer and Q1 pages:** same layout, corrected counts from the fresh candidate pool. For example, Kik stated 299 → 353; Instagram total 240 → 151, after footer links stopped counting as platform use.
- **`/api/platform-affordance-evidence` freshness:** stricter. It reports `stale` if production platform tags differ from the snapshot.
- **The harm-analysis panel:** unchanged.

## Reproduce

Regenerate and verify every output (Python 3.12, PyYAML 6.0.3):

```bash
AFH_Q1_SOURCE_DB=/path/to/caselinker.db python research/afh_q1/run_all.py --export --verify
```

Run the tests:

```bash
DATABASE_URL='' python -m pytest -q tests/research tests/privacy tests/api tests/extraction/test_program_boilerplate_dates.py tests/extraction/test_field_assertions.py
```

`--verify` prints `identical` when every output hash matches `research/afh_q1/outputs/RUN_IDENTITY.json`. The corpus snapshot and LaTeX tables are generated locally and not committed.

## Limits

- All validation is AI review, with 3–45 rows per cell.
- Generative synthesis and likeness-synthesis cells are small (21 cases each); cite examples only after a human read.
- 38 capability rows have uncertain start dates, 9 of them on manuscript example platforms.
- A sentence naming two platforms can attribute conduct to the wrong one.
- Enforcement releases measure coverage, not prevalence.
- The public evidence API still serves raw excerpts.

## Review guide

1. `research/afh_q1/FINDINGS.md`: results, evidence levels, uncertainties.
2. `research/afh_q1/DECISION_1_TIERS.md`: why 1,513 and not 1,526 or 1,577.
3. `research/afh_q1/config/codebook.yaml` and `config/platforms.yaml`: the rules and the registry.
4. `research/afh_q1/afhq1/pipeline.py`: classification.
5. `tests/research/test_afh_q1_pipeline.py`: what each rule is held to.
