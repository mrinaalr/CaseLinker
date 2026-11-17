# Hardy review 2: corpus-dependent verification

Commit `2cc50804c` (code clean) on `research/afh-q1-reconstruction`, local only. The frozen corpus stayed local and is not exported.

## Findings and corrections

| # | Finding | Status |
|---|---|---|
| 1 | The line-wrap tier was applied to the headline but not downstream | **Confirmed and fixed.** Conduct, inferred facilitation, explicit use, harm flags, AI material, manifest, temporal and platform-harm tables all used the baseline tier. Records now expose `primary_tier` (line-wrap), and every downstream level reads it; `tier` stays the baseline. |
| 2 | The 1,513 headline mixes tiers | **Reconciled.** 1,513 = 1,322 stated + 191 co-occurring (`inventory.json` → `headline_reconciliation`). Co-occurrence is reported as co-occurrence, with its blind-review rate (14/15 offender use, 5 of them known via platform reports). It is not presented as stated offender use. |

## Before → after (distinct cases)

| Class | B | I | C |
|---|---|---|---|
| Anonymity | 412 → 479 | 338 → 378 | 22 → 28 |
| Contact discovery | 454 → 529 | 30 → 38 | 9 → 10 |
| Unmonitored communication | 459 → 534 | 360 → 399 | 22 → 23 |
| Distribution infrastructure | 802 → 960 | 544 → 667 | 437 → 515 |
| Ephemerality | 322 → 363 | 177 → 181 | 0 → 0 |
| Generative synthesis | 121 → 137 | 54 → 66 | 19 → 21 |

- **Changed records:** 422 platform-case records in 378 cases changed. All had baseline tier named-only and a line-wrap tier of stated or inferred. No record lost a flag.
- **Manifest:** 34 → 36 platforms. Documented use rose: Kik 409 → 488, Snapchat 377 → 387, Facebook 132 → 181, Dropbox 69 → 107.
- **Temporal:** strict documented use by era moved from 33/23/249/952 to 47/30/319/1,116.
- **Exemplars:** 42 new manifest exemplars were blind-reviewed (22 supported, 16 partly, 4 not). The inventory now has 203, 144 supported.
- **Unchanged:** the inventory and the headline (1,513 / 1,257), level A, and the published `stated_vs_inferred` field.

## Regression tests (fail on the old code)

- `test_linewrap_promotion_reaches_downstream_levels`: a record promoted only by the repair reaches conduct, explicit use and documented harm.
- `test_committed_levels_never_rest_on_named_only_primary_tier`: no conduct or documented-harm flag sits on a named-only primary tier.
- `test_manifest_use_documented_matches_primary_tier`: manifest documented-use counts equal the primary-tier counts.

## Source attribution and privacy

- **Citations:** 203/203 exemplar citations resolve to the same content fingerprint (`manifest.json` → `citation_check`). Every exemplar has a blind verdict.
- **Outputs:** the privacy test passes; no output string of 25+ characters appears in any release.
- **Export:** reviewer notes were scanned against release text, and the four verbatim matches were paraphrased earlier. The masked review sheets and the corpus snapshot are gitignored and not exported.

## Commands (fresh clone)

Regenerate and verify every output (Python 3.12, PyYAML 6.0.3):

```bash
AFH_Q1_SOURCE_DB=/path/to/caselinker.db python research/afh_q1/run_all.py --export --verify
```

Run the tests:

```bash
DATABASE_URL='' python -m pytest -q tests/research tests/privacy tests/api tests/extraction/test_program_boilerplate_dates.py tests/extraction/test_field_assertions.py
```

Results on `2cc50804c`:
- snapshot `60f7bfaaa287b3c7cb7ad7a94a8eaf23eb704751860880f9c6663c3b5767d06b`, 10,802 cases;
- `--verify` → `identical`;
- tests: 324 passed, 34 skipped;
- no stray `caselinker.db`; tree clean.

## Hashes

| Config | Version | sha256 |
|---|---|---|
| `codebook.yaml` | codebook-6 | `b2a50baa9f549256…` |
| `platforms.yaml` | platforms-2 | `0bb0d6d89be75247…` |

| Output | sha256 (prefix) |
|---|---|
| `inventory.json` | `14850faa50138415…` |
| `affordance_coverage.json` | `02b561088d797513…` |
| `manifest.json` | `c46969b9bbc0d528…` |
| `harm.json` | `5d339e4e8015ac75…` |
| `recurrence.json` | `17f0254b4c66b7bc…` |
| `temporal.json` | `8c74c63188a69841…` |
| `exemplar_inventory.json` | `60cabc820ad0e27d…` |
| `citations.json` | `ee4c7b73fc1603c7…` |
| `tier_variants.json` | `5b1b25e820d5a3a9…` |
| `registry_checks.json` | `6483b8121a043918…` |
| `records.csv` | `a3407979005ff1a0…` |

Full hashes for every output are in `research/afh_q1/outputs/RUN_IDENTITY.json`.

## Unresolved

- **No human adjudication.** All validation is AI review with small per-cell samples (3–45).
- **Co-occurrence.** The 191 cases rest on a 15-row random sample (14 offender use) plus 6 promoted rows (5 offender use). A larger sample would tighten the rate.
- **AI cells.** 21 explicit generative-use cases (2/4 exemplars supported) and 21 likeness-synthesis cases (1/4). Do not claim identity-based synthesis beyond the supported example.
- **Registry dates.** 38 capability rows have uncertain start dates, 9 on manuscript example platforms.
- **Platform attribution.** A sentence naming two platforms can attribute conduct to the wrong one.
