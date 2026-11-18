# Benchmark

Synthetic gold PACER cases for measuring the automated coder's accuracy on known truth. Each case is written as a gold coding first; its court documents are then rendered from the gold with fixed templates. No model writes any of the text, so no coder is scored on its own wording.

**Contents:**
- [What is in it](#what-is-in-it)
- [Splits](#splits)
- [Scoring](#scoring)
- [Limits](#limits)

## What is in it

```bash
python -m state_machines.benchmark.generate            # writes data/ (deterministic: seed 7, 40 cases; confirm seed 4099, 20 cases)
python -m state_machines.coding.pipeline bench --split dev
python -m state_machines.benchmark.score local/bench/resolved --split heldout
```

[`data/`](data/) holds, per case, `sources.json`, the page text (`<doc>/pNNNN.txt`, with court headers, wrapped lines and some hyphenation) and `gold.json`, a schema 2.0 bundle that validates against its own pages. Everything is fictional and clinical: invented platforms, "the defendant", "Minor Victim 1", no real names.

| | |
|---|---|
| Cases | 60 (20 dev, 20 held-out, 20 confirm): sextortion, enticement with a meeting, undercover sting, distribution |
| Gold events | 717 across 19 action codes (242 dev, 228 held-out, 247 confirm) |
| Documents | docket, indictment, statement of offense or factual basis, often a sentencing memorandum |

Every gold event carries tags (in `notes`) for the hard cases built in on purpose:

| Tag | What it tests |
|---|---|
| `explicit_order` | order stated only in words ("after that first contact") |
| `retelling` | the same act told again in an indictment count or a sentencing memo (gold `SAME_ACT`) |
| `allegation_only` | an act only the indictment alleges |
| `advocacy` | an act told only in a sentencing memorandum |
| `mention_only` | a platform named but not used |
| `level_c` / `no_level_c` | a feature stated and tied to the act, or only a platform name |
| `undercover`, `interrupted` | an undercover persona as counterparty; an attempt an arrest interrupts |
| `harm`, `procedure`, `response`, `undated` | child-directed harms; court acts; victim responses; acts with no date |

## Splits

Cases 1–20 are **dev**: prompts and rules may be tuned on them. Cases 21–40 are **heldout**: they are scored once, with the final prompt, and never used for tuning. Held-out cases are written in a register the dev cases never use ("DEFENDANT", "MV-1", "initiated contact with", "on or about", statutory phrasing), so a prompt fitted to the dev wording does not carry over for free.

Cases 41–60 are **confirm** (`--split confirm`, gold version `benchmark-1.1-confirm`): a third register for the final check, added after the held-out score had been looked at. Its wording was written without sight of the coding rules (`state_machines/coding/` and its tests were not read), from how federal indictments, statements of facts, complaint affidavits and sentencing memoranda phrase the same acts: other party designations, other verbs and constructions, dates inside or at the end of the sentence, other sequence wording, and a few extra boilerplate sentences that use conduct words without describing an act. Confirm cases come from their own seed (`confirm_seed` in [`data/MANIFEST.json`](data/MANIFEST.json)), so cases 1–40 are byte-identical with or without them. The confirm split is scored once; do not read its pages or tune on it before that run.

## Scoring

[`score.py`](score.py) matches coded events to gold events by the overlap of the passages they cite, and participants by the matched events they act in. Every rate is reported with its numerator and denominator.

| Measure | Question |
|---|---|
| events | recall, precision, F1 of acts |
| action, actor | the right code; the right participant |
| standing | the act's passage has the gold legal standing (an allegation stays an allegation) |
| dates | the gold date among the coded dates |
| order | recall and precision of stated order between matched acts |
| order_claims | every coded order relation judged against the gold's full documented order (listed relations and cited dates, closed transitively): correct, reversed, not documented |
| order_pairs | gold-ordered pairs of acts the coded bundle also orders, by stated relations and cited dates together |
| level_c, harms | recall and precision of level-C affordances and H0 harms |
| same_act | gold retellings the coded bundle links |
| by_tag | recall per hard-case tag |

`score_observations` scores the [observation layer](../observations/README.md) apart from the acts: gold platform mentions and feature statements found, and whether each supported relationship is one the gold holds (`pipeline bench-observations`, results in `results/observe-<version>.<split>.json`).

## Results

[`results/`](results/) holds the scores of each rule version on each split (`pipeline bench --split <split> --record`), one file per `<rule version>.<split>`. Each release's `REPORT.md` prints them as tables.

| Rule version, split | Gold acts found | Published acts that are gold acts | Action code | Order relations correct |
|---|---:|---:|---:|---:|
| `resolve-1.0.0`, held-out (frozen baseline, scored once) | 0.649 (148/228) | 0.980 (148/151) | 0.912 | not measured this way |
| `resolve-1.1.0`, dev (rules tuned here) | 0.773 (187/242) | 0.995 (187/188) | 0.957 | 20 of 21 |
| `resolve-1.1.0`, held-out (second look, no tuning) | 0.671 (153/228) | 0.975 (153/157) | 0.915 | 6 of 7 |
| `resolve-1.1.0`, confirm (scored once) | 0.421 (104/247) | 0.945 (104/110) | 0.971 | 1 of 1 |

All rows are the resolved coding a machine release publishes. No coded order relation was reversed or undocumented on any split; the ones not counted correct touch an act that is not a gold act.

**Reading the confirm row.** On wording the rules had never met, what is published stays right and much less is published. The lost acts, of 247: neither model coded it (34); only one model did (49); both did but named different actors (27) or different codes (31); cited spans that did not pair (2). Victim responses (0 of 14), platform-mention-only acts (0 of 11) and docket procedure entries (20 of 40) are the weakest categories.

## Limits

- **Same generator.** Dev, held-out and confirm cases come from one generator; the held-out and confirm registers change the wording, not the scenario shapes. Accuracy here is accuracy on these shapes.
- **Cleaner than real filings.** No OCR errors inside quoted sentences, no tables, no redactions. Real-record accuracy is likely lower.
- **What it does not measure.** Whether a model would find acts these templates never express.

Report benchmark accuracy beside the real corpus's inter-coder reliability, never as accuracy on the real cases.
