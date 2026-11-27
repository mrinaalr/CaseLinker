# Coding

How a court record becomes a coded bundle. Two coders work from the page text and their agreement is measured; neither sees the other's answers (with the selective second pass the second is not asked to read a page where the first found no act). Then either a fixed rule publishes what both coded (**machine-coded**), or a manual human reviewer decides every disagreement (**adjudicated**).

**Contents:**
- [Automated coding](#automated-coding)
- [Steps](#steps)
- [Agreement](#agreement)
- [Machine resolution](#machine-resolution)
- [Throughput](#throughput)
- [Adjudication](#adjudication)

## Automated coding

```bash
export CASELINKER_PACER_TEXT=local/pacer_text CASELINKER_PACER_SOURCE=<folder of the PDFs>
python -m state_machines.coding.workflow extract <case> [...]        # page text, local
python -m state_machines.coding.pipeline code <case> [...]           # coder_A, coder_B → local/auto/
python -m state_machines.coding.pipeline resolve <case> [...]        # local/auto/resolved, reports
python -m state_machines.coding.pipeline bench --split confirm --record   # score a benchmark split → benchmark/results/
python -m state_machines.coding.pipeline release pacer-v1 <case> [...] --observations   # bundles, graphs, and what the record names
```

| Part | What it does |
|---|---|
| [`coder.py`](coder.py) | Reads a case page by page. Docket pages go to a deterministic parser (charge, plea, verdict, sentence and arrest entries only). Judgment form pages are skipped and counted. Every other page goes to a local model, which names each act's sentence (its first words) and action code, and the actor when it is not the defendant. Code locates the whole sentence (exactly, also where the page breaks a word across a line; the quote kept is the page's own text), applies the sentence rules, maps role names to participants, writes descriptions from codes, and drops (and logs) every act that breaks a rule. |
| [`enrich.py`](enrich.py) | Sentence rules for what the model is not asked: targets (victim, persona, recipient mentions; victims by number, letter or pseudonym, and a pseudonym is a minor only where the sentence says so), dates (exact words, real bounds), platforms and channels, level-C features (a fixed phrase list per class, so B0 holds by construction), harms that follow from the act code with a minor target, order from sequence words ("after that first contact" → the contact act; "then" → the act in the sentence before; otherwise no relation). Identical for both coders, so reliability is reported on acts and action codes only. |
| [`models.json`](models.json) | The two coders, pinned by content digest with every inference setting: **coder_A** `qwen3:4b`, **coder_B** `llama3.2:3b` (two model families, so their errors are not shared), chosen on dev cases (`selection`). A model whose local digest differs is refused. |
| [`select_models.py`](select_models.py) | Scores candidate models on dev benchmark cases (accuracy and seconds per page); held-out cases are never used. |
| [`resolve.py`](resolve.py) | Publishes what both coders coded (see [machine resolution](#machine-resolution)). |
| [`cues.py`](cues.py) | Cue words per action code for candidate rule 2b (off by default). |
| [`pipeline.py`](pipeline.py) | Runs both coders (cached, resumable, a failed case recorded rather than forced), resolves, scores the [benchmark](../benchmark/README.md), builds the dataset. |

**Rule statements.** An offender act coded on a sentence that states a rule or policy and names no one acting ("the Terms of Service prohibit …") is dropped and logged. One agreed act in the 30 cases was of this kind.

**Where the PDFs go.** `<source>/BULK_FOLDER/pacer -- <case id> -- <document type>.pdf`, where the document type is one of the labels in `DOC_TYPE_WORDS` ("indictment", "plea agreement", "criminal complaint", "sentencing memorandum", "docket", …). The type sets the default legal standing of every passage in the file, so `extract` reports a file whose label it does not recognise, fails on a case with no PDF, and reads a file collected under two names once. After adding a filing to a coded case, rerun the same commands: `code` sees that the case's documents changed and codes it again (old pages are answered from the cache), and a build refuses a bundle that does not cover the stored documents.

**Case ids and files.** A case id is the corpus id of the press release for the same prosecution; every `pacer-v2` case has one. PDFs keep the names they were collected under, and `COLLECTED_AS` in [`workflow.py`](workflow.py) maps ids that have since moved. Records outside the release (no press match) sit in `<source>/EXTERNAL/`. A bundle records each document by a normalized `source_path` and its SHA-256, never the name on disk.

**Court text never leaves the machine.** The models run in a local Ollama server, and page text, quotes, model answers and the response cache stay in `local/`. People are named by role; the labels exist only in memory and are never stored. The coders can make mistakes a human would not; their reliability is the agreement between them, and their accuracy is measured on the synthetic benchmark.

## Steps

| Step | Tool | Output |
|---|---|---|
| 1. Page text | `workflow.py extract` | per page: text (text layer, or OCR; the OCR text is not checked against the page image) and its hash, under `local/pacer_text/<case_id>/` |
| 2. Draft | each coder, following the [coder guide](../evidence/CODER_GUIDE.md) | a draft bundle per coder, with quotes in the local store |
| 3. Check | `workflow.py check` | validation findings (T01–T19) against the page text |
| 4. Compile | `workflow.py compile` | the coder's bundle: passages located and hashed, quotes kept local |
| 5. Agree | `workflow.py agree` | event matching by passage overlap, action κ, affordance and harm agreement, order agreement |
| 6. Agreed core | `release_report.py` | what both coders coded, labelled `agreed` |
| 7. Dossier | `adjudication.py dossier` | every open item per case, with fixed decision options |
| 8. Decide | `adjudication_packet.py` | a local HTML packet: both codings, passages, PDF page links, a choice per item; exports `<case>.decisions.json` |
| 9. Apply | `adjudication.py apply` | the adjudicated bundle in the dataset, validated; refused while anything is undecided |
| 10. Publish | `graphs/release.py build` | derived views, graphs, SHACL, manifest; `ADJUDICATION.md` counts what was decided |

Page text, quotes and the adjudication packet stay in `local/` (gitignored): they contain court text.

## Agreement

Events are matched across coders by the overlap of the passages they cite, never by action code, so agreement is not inflated by matching like with like. Reported per case: event precision, recall and F1; action κ on matched events; affordance agreement per class; harm agreement; order agreement on matched pairs. The agreed core keeps what both coders coded.

## Throughput

Measured on an Apple M4 with 16 GB, one model in memory at a time (`python -m state_machines.coding.throughput`).

- **Where the time goes:** writing the answer, not reading the page. Reading the prompt takes about 0.1 s cached and 2–11 s cold; models write 10–25 tokens/s. Prompt 1.x asked the model for every field (300–625 tokens a page); prompt 2.0 asks only for each act's first words, code and non-defendant actor (140–280 tokens), and the sentence rules derive the rest.
- **Model choice (5 dev cases, prompt 2.0):**

  | Model | s/page | Event F1 | Action | Level C (R/P) | Harms (R/P) |
  |---|---:|---:|---:|---|---|
  | `qwen3:4b` (coder_A) | 7.9 | 0.87 | 0.91 | 1.0 / 0.78 | 0.80 / 1.0 |
  | `llama3.2:3b` (coder_B) | 7.1 | 0.76 | 0.68 | 1.0 / 0.78 | 0.50 / 0.80 |
  | `qwen3:8b` | 29.6 | 0.80 | 0.81 | 1.0 / 0.70 | 0.60 / 1.0 |

  The 8B model was slower and not more accurate; `llama3.1:8b` ran about 50 s a page under the old prompt.
- **Requests in flight:** on synthetic pages two in flight gave 5.1 s per page against 7.9 s serial. Real filings are denser (prompts of about 1,400 tokens, answers of 200–900 tokens, up to 24 acts a page) and cost about 19–22 s per page with `qwen3:4b`; going from two to four in flight barely helps there, because the GPU's memory bandwidth, not request concurrency, is the limit, and four slots cost about 2.5 GB more cache (the memory guard then pauses the run). Two is the default.
- **The first 91 documents** (1,027 pages) took about 4 hours for coder_A and, with the selective second pass, about 1.5 hours for coder_B on this laptop; the 120 pages added on 2026-11-18 were coded at the same rate. At that rate 500 more cases of this size are about 90 hours of model time per coder (extrapolated, not measured). Shorter answers would be faster but would change what the benchmark measured, so they were not used.
- **Page routing for the 30 real cases:** 1,147 pages; 201 docket pages to the parser (procedure entries only), 60 judgment form pages skipped, 886 pages read by the first coder and 878 by the second (it skips a page where the first found no act). Every substantive filing is read.
- **Rejected: a page prefilter.** On the pilot's real pages (agent-coded), the best keyword prefilter kept 90% of pages with acts while saving only 19% of model pages; the strictest kept 71%. Losing acts to save time is not acceptable, so every non-docket, non-form page is read.
- **Memory:** a dedicated Ollama server (`models.json` `runtime`) with one model loaded, an 8-bit KV cache, flash attention and an 8k context; the coder pauses while free memory is under 20% instead of swapping.
- **Selective second pass (`--selective`):** the second coder reads only pages where the first found acts. The dataset is unchanged (only acts both coded are published); reliability is then reported on those pages.
- **Scaling:** this laptop codes on the order of a hundred pages an hour per model. Hundreds of cases need a GPU host running the same pinned open models; the code does not change, only `runtime.base_url`.

## Machine resolution

[`resolve.py`](resolve.py) turns two codings into one bundle by a fixed rule:
1. **Events:** published when both coders coded the act (matched by cited passages) with the same action and the same actor. Participants are aligned by the matched events they act in.
2. **Status, affordances, harms:** the status is the weaker of the two; affordances, candidate affordances, access and harms are kept only where both coders annotated them.
   **Everything else is coder A's.** The published act is a copy of coder A's event: its platform interactions, platform mentions, channels, targets, co-actors, outcome and repetition are coder A's reading of an act both coders agreed on, and coder B's values are never compared. So `stated_platform_means` (derived from `platform_interactions`) is a single-coder attribute; graphs mark these relationships `clt:reviewStatus "single_coder"`. The full table is `resolve.FIELD_STANDING`, printed in each release's `REPORT.md`.
3. **Dates:** every cited date of either coder is kept, and disjoint dates are flagged as a conflict (T1–T5).
4. **Relations:** those both coders asserted. Order implied by cited dates is derived later.
5. **Stated order, restated (rule 5c):** each coder could link a sequence sentence only to acts in its own list, so the same sentence rule ([`enrich.stated_prior`](enrich.py)) runs once more over the agreed acts. It never guesses:
   - the opening clause names the earlier act ("After that first contact") → the nearest earlier agreed act with that code;
   - the sentence only says "then", "in response" or "thereafter" → the act in the sentence immediately before it;
   - neither is among the agreed acts → no relation.
6. **Possible retellings** (same action, overlapping dates) are linked `SAME_ACT`, never merged (R05).
7. **Open roles** stay open.

**Rule 2b, evaluated and not adopted.** Where both coders cite the same sentence and actor but give different codes, [`cues.py`](cues.py) reads the sentence against a cue table written from the codebook definitions and takes the one code it cues (`pipeline resolve --settle-codes`, output in `resolved_2b`).
- On the synthetic benchmark it recovers acts at no cost in precision.
- On five real cases its codes agreed with reference coding less often than codes both models gave (7 of 11 sentences against 19 of 24; the candidate's scores are in `benchmark/results/` under `resolved_2b`): real sentences are long and often state several acts.
- A machine-coded dataset states that two coders agreed on everything published. Settled codes are one coder's code confirmed by a word rule, so they are not published. The rule stays in the code, off, so the measurement can be repeated.

Everything else is left out and counted. What the record names (platforms, feature phrases) does not depend on this rule: the [observation layer](../observations/README.md) reads it from the pages and publishes it apart from the acts. Published items carry `review.status = agreed`. A dataset built from these is `review_mode: machine`: served and labelled "Machine-coded", never called adjudicated.

## Adjudication

```bash
export CASELINKER_PACER_TEXT=<page text store> CASELINKER_PACER_SOURCE=<folder of the PDFs>
python -m state_machines.coding.adjudication dossier <release> <case> [...]
python -m state_machines.coding.adjudication_packet <release> [case ...]      # open local/adjudication/<release>/packet.html
python -m state_machines.coding.adjudication apply <release> <case> local/adjudication/<release>/<case>.decisions.json
python -m state_machines.graphs.release build <release>
```

Each item is one question with a fixed set of answers that `apply` carries out:

| Kind | What it is | Answers |
|---|---|---|
| `only_a`, `only_b` | an event one coder coded and the other did not | include / exclude (`only_b`: exclude / edit) |
| `action_mismatch` | matched events with different action codes | coder A's code / coder B's code / exclude / edit |
| `status_mismatch`, `affordance_mismatch` | different status or level-C affordances | keep (the agreed, weaker or shared) / coder A / coder B / edit |
| `actor_mismatch`, `harm_mismatch`, `time_mismatch` | different actor, harms or dates | keep / the other coder's where it can be applied / edit |
| `order_only_a`, `order_only_b`, `single_coder_relation` | a relation only one coder asserted | include / exclude |
| `platform_recode`, `single_step` | a platform or affordance coding, a one-step trajectory | keep / edit |
| `possible_same_act` | same action, overlapping dates, nothing linking them | same act (adds `SAME_ACT`, INFERRED; both events kept) / distinct |
| `unresolved_role` | a participant whose role the source leaves open | a target role / a co-actor mode / not involved / edit |

`edit` means the reviewer changes the frozen agreed core (`local/adjudication/<release>/agreed/<case>.json`) by hand; `apply` always rebuilds from that file and the decisions, so it can be rerun. `defer` blocks the dataset. `apply` marks every event and relation `adjudicated` with the reviewer's name and refuses a result that does not validate. Coder A's ids, participants and passages are the agreed core's own; coder B's passages are imported under a `b.` prefix, and anything needing coder B's participants is an `edit`.

## Act extraction v2

A second path for section labels, actor ids, event frames, propose-then-verify, disagreement sheets, a quote check and a case-id preflight. Every flag is off unless it is set. With the flags unset, resolution is `intersection-1.0` and a release is built as before. A release refuses an empty capability registry when `require_registry` is set or any v2 flag is on; `--allow-empty-registry` records that it was allowed and builds anyway. Reading `pacer-v1` does not build.

| Flag or mode | Default | Pipeline function it changes |
|---|---|---|
| `CASELINKER_SECTION_FILTER` | off | `coder.assemble` drops an act whose own quote sentence is a technology explainer or affiant background. Other sentences on the page still publish |
| `CASELINKER_COREFERENCE` | off | `observe.relate` calls `coreference.means_with_resolved_subject` before it attributes a means |
| `CASELINKER_ADJACENT_LEVEL` | off | `observe.relate` writes `adjacent_sentence` from `coreference.adjacent_links`, kept out of the means relations |
| `CASELINKER_EXTRACTOR` | unset | `coder.code_case` still calls each coder's own model, with the frames schema and prompt. The model returns plain text (act code, actor, object, quote, means, means level). `acts_from_model_frames` stamps the page hash, re-locates each span, and drops a frame whose span is not on the page or whose actor is not the defendant. The actor matches the head phrase exactly: `the defendant`, `the accused`, the caption name or surname, or `defendant <Name>`. A pronoun matches only when `CASELINKER_COREFERENCE=1`. `extract_frames` is not either coder |
| `CASELINKER_ACT_POLICY` | `intersection-1.0` | `pipeline.resolve_cases` calls `propose_verify.from_bundles`, including the missed-act pass when page text is available |
| `CASELINKER_MEANS_PARSER` | unset | `observe.relate` calls `means_parse.instrument_means` when the five-word window misses. `dep` loads `en_core_web_sm` once (override with `CASELINKER_MEANS_SPACY_MODEL`) and `pipeline preflight` loads it too. A model that cannot load raises. `CASELINKER_MEANS_PARSER_FALLBACK=1` uses the small tokenizer and records `parser: fallback` |
| `CASELINKER_MEANS_RULE` | unset | `observe.features_in` and `observe._means` also match `virtual private network(s)`, `VPN(s)`, and `on` / `via` after a conduct verb |
| `CASELINKER_DISAGREEMENT` | off | `pipeline.resolve_cases` writes the adjudication sheet from `disagreement.rows_from_intersection` or `rows_from_propose_verify` |

```bash
python -m state_machines.coding.pipeline preflight <case_id> [...] --text-root DIR --out DIR [--release-root DIR]
python -m state_machines.coding.quote_check records.json --pages pages.json
```

`CASELINKER_MEANS_PARSER=dep` needs the spaCy model pinned in `requirements-sdk.txt` (`en-core-web-sm` 3.8.0). `./setup.sh` installs that wheel and checks its sha256.

`preflight` compares the release id, the text-directory id, the coder-bundle id and `COLLECTED_AS`. Passed an `fp-1` fingerprint table, it also reports a stored id whose fingerprint changed or disappeared, and a fingerprint shared by several PACER ids. It reads those ids and does not open page text, and it does not rename anything. The PDF name and `COLLECTED_AS` are plain strings, so a later ingest that mints ids from the article text does not move them. `quote_check` reports each quote that is not the page text at its offsets. Neither command reads `state_machines/data`, `local/` or `caselinker_oxigraph/`. Disagreement rows are written by `coding/disagreement.py`; the human columns are blank, and a count from adjudicated events is labelled `adjudicated`.
