**CaseLinker Phase 3** expands how cases are read: four independent extraction layers, a resolver that stores only what the evidence supports, and every claim traced to its source passage.

This release makes every number in CaseLinker defensible. Each layer emits its own assertions: surface patterns, dependency parsing, named-entity recognition, and an optional local LLM that must quote its source. A value is stored only when the layers agree, or when one layer’s evidence is decisive. Around it, Phase 3 ships cleaner collection, stricter validation, and search that opens straight into the graphs.

## Highlights

- **Field assertions** — every reader writes a claim with method, version, evidence family, role, confidence, and a character span into the original text. Claims are append-only and kept beside the case.
- **Span gate** — verifies every extracted value is supported by source text, and that ages and sentences appear in their expected form.
- **Resolution by evidence family** — combines readings from each layer into a final verdict, holding back values still in dispute.
- **Roles from grammar** — uses the dependency parse to link each age to the person it describes, assigning roles such as defendant, victim, or decoy.
- **Optional local LLM** — writes assertions beside other layers and adjudicates disputed readings. It must quote its source and cannot finalize alone.
- **Provenance graphs** — every case graph gains a companion graph recording each reader's claim, its span, and how it was resolved, built on PROV-O and W3C Web Annotation.
- **Provenance in MCP** — `get_case_assertions` and `get_field_disagreements` let agents see every reader's claim and every open disagreement.
- **Corpus** — **10,711** case reports, **131,332** extracted features, and **4,428** law-enforcement agencies across **70** sources, after deduplication.

## What's new since Phase 2.5

### Extraction

Readers and their evidence families:

| Reader | Family |
|---|---|
| Regex, spaCy token patterns, victim-age gate, compiled rules | `surface_pattern` |
| spaCy dependency parse | `dependency` |
| Stanza NER, once per PDF | `ner` |
| Statute lookup | `lookup` |
| Temporal tags | `temporal` |
| Local LLM (optional) | `llm` |
| Human overrides | `human` |

Votes count by family: two readers in one family are one vote, and a family that contradicts itself abstains. Two families in agreement settle a value; one family at confidence ≥ 0.7 settles it alone; everything else goes to review. Stanza's name cue sits at 0.65, so NER can corroborate but never finalize. Settled values store even while others in the same case stay open.

Resolution never edits assertions, so `scripts/run/reresolve_assertions.py` can re-vote the corpus under a new rule set without re-extracting. Every run records its code revision, models, and rule set.

The columns the API and graphs read are representative of the settled vote. Maximum penalties, prior-case terms, and CyberTip boilerplate no longer pass as case facts, and real publication days replace year-only dates.

Working doc: [`src/Processing Layer/README.md`](https://github.com/mrinaalr/CaseLinker/blob/main/src/Processing%20Layer/README.md).

### The LLM, used narrowly

The Phase 3 pipeline is fully reproducible.

A local LLM (`CASELINKER_LLM=1`, Ollama `qwen3:8b`) is the resolver's optional fourth witness, testifying only on mentions the deterministic layers could not settle. LLM input is restricted to sentence windows rather than the full release, and it returns a role from a fixed list with a quote from its window. Quotes that fail the span gate are dropped. LLM claims carry confidence 0.6, below the 0.7 needed to finalize alone, so the LLM can confirm or veto but never store a value by itself. Replies are cached by model digest, prompt, and parameters.

`scripts/run/llm_residue_pass.py` runs the LLM as its own pass over a stored corpus: it reads open mentions, appends the model's assertions, and re-resolves. The pass is resumable, and its added finals and vetoes are counted separately, so the LLM's contribution is measured on its own.

`scripts/run/propose_compiled_rule.py` turns confirmed evidence into rules: an LLM drafts a regex from reviewer-confirmed quotes, and the draft runs only after a person commits it to `APPROVED` in `field_assertions/compiled_rules.py`. What the model learns becomes deterministic, auditable code. No rules are approved in Phase 3.

### Identifiers

Cases, agencies, platforms, and locations are named under `https://w3id.org/caselinker/resource/`. A case and its SPARQL named graph are `https://w3id.org/caselinker/resource/case/{case_id}`.

Every CaseLinker IRI resolves through `https://w3id.org/caselinker/`, CaseLinker's permanent namespace. If the host moves, only the redirect changes; the IRIs remain stable. The demo, SPARQL endpoint, and API are `https://caselinker.up.railway.app/`.

Case graphs are typed with the CAC ontology (`https://cacontology.projectvic.org/`), UCO, and CASE. Those vocabularies are unchanged. CaseLinker's own identifiers are the w3id IRIs above.

### Provenance graphs

Each case graph now has a companion, `{case_id}.provenance.ttl`, written beside it. Every assertion is a W3C Web Annotation and a CAC `AssessmentResult`, with its span as a `TextPositionSelector` and `TextQuoteSelector`, its confidence, its method, and its issue time. Extraction runs and methods are PROV-O activities and software agents, and each field resolution records the assertions it was derived from. Three terms are new, under `https://w3id.org/caselinker/ns/provenance#`: `evidenceFamily`, `resolutionStatus`, and `ruleSetVersion`. SHACL rejects a provenance graph that is missing `ruleSetVersion`, `evidenceFamily`, or an annotation's quote, span, confidence, or issue time. The public store loads each file as named graph `https://w3id.org/caselinker/resource/case/{case_id}/provenance`. The case_id is linked via `dcterms:provenance`, so a query can walk back and forth from cases to quoted evidence in one hop.

### Built for documents beyond press releases

Detectors register by document kind. Only press-release detectors ship in Phase 3; court filings, court opinions, and other public records can plug in as tailored detector functions that return the same assertion shape, with no change to the span gate or resolver.

### Collection & sources

- Collector MCP tools for press releases and free court records (CourtListener / RECAP first) ([#13](https://github.com/mrinaalr/CaseLinker/pull/13))
- New sources: Australian Federal Police (25), Queensland Police Service (7), Brazil Federal Police (108; local Portuguese-to-English translation), Europol (61), National Crime Agency (24), New Zealand Department of Internal Affairs (141), Wisconsin Department of Justice (16), Alberta ALERT Internet Child Exploitation unit (60), Police Scotland (82), Northern Virginia–DC Internet Crimes Against Children Task Force (9), Philippines National Bureau of Investigation (47), Minnesota Bureau of Criminal Apprehension (2), An Garda Síochána (4), Maryland State Police (10)
- A duplicate-URL gate so one article is never stored twice, across sources or ingests
- NCMEC duplicate-article noise removed
- Michigan ICAC re-collected as a 47-article scrape that splits cleanly

### Speed

- Stanza NER runs in batches of 64, cutting NER time by about a fifth with identical output
- spaCy parses cases in batches with its unused NER component excluded
- Models stay warm across PDF groups instead of reloading per file
- A full deterministic re-extraction of the corpus took **10.8** hours (10.2 hours across the 70 re-extracted PDFs, plus the nine sources added after)

### Validation & fixes

- Age-extraction validation sampling from [Uriel Tulinabo](https://github.com/uriel274) ([#18](https://github.com/mrinaalr/CaseLinker/pull/18))
- Year-only dates no longer stored as December 31 ([#23](https://github.com/mrinaalr/CaseLinker/issues/23)); statutory sentence extraction hardened ([#24](https://github.com/mrinaalr/CaseLinker/issues/24), [#27](https://github.com/mrinaalr/CaseLinker/issues/27))
- CAC ontology shapes pinned in-repo; SHACL fails loudly when shapes cannot load
- Graph export writes the mapped triples instead of an empty Turtle file
- Provenance export reads from the same database as the case export, SQLite or Postgres
- Oxigraph cold start returns a retry instead of a 502

### Search

The facet-search UI is redesigned, and a search cohort opens its matching graphs.

## Results

Measured on the full Phase 3 re-ingest (**10,711** cases), on two samples of 200 paired case ids. The development sample (seed 20261017) was used to find and fix errors; the holdout (seed 20261018, excluding the development sample) was judged after all fixes, with no changes made from it. Both give one seat to each of the 63 sources present in both versions and fill the rest by source size. A final is wrong when it does not match its source passage in context: the right role for an age, the right kind for a sentence. Frozen ids and per-case judgments for both samples are in `scripts/verify/`.

| | 2.x stored | 2.x wrong | 2.x error rate | Phase 3 stored | Phase 3 wrong | Phase 3 error rate |
|---|---|---|---|---|---|---|
| Development sample, age finals | 177 | 0 | 0% | 179 | 0 | 0% |
| Development sample, sentence finals | 249 | 33 | 13.3% | 95 | 0 | 0% |
| Holdout sample, age finals | 172 | 1 | 0.6% | 201 | 2 | 1.0% |
| Holdout sample, sentence finals | 281 | 55 | 19.6% | 118 | 1 | 0.8% |
| Age finals with two-family agreement | — | — | — | 73.7% | — | — |
| Age mentions left in review | — | — | — | 19.0% | — | — |
| Cases with an open mention | — | — | — | 24.1% | — | — |

On the holdout, Phase 3 cuts the sentence error rate from 19.6% to 0.8% and stores 17% more ages at comparable accuracy (1.0% against 0.6%, a one-error difference).

## Scope

Phase 3 changes extraction and adds provenance; the case graph model is unchanged. The CAC mapper still draws the same `OffenderRole`, `VictimRole`, and `ageEstimate` shapes, now from cleaner values, with provenance in a separate graph beside each case. Sentence finals rest on one evidence family plus the clause gate. Ambiguous ages stay in review and are not stored. Only press-release detectors ship; detectors for other public records come later.

## Data & Ethics

- Records come from public, redacted sources (ICAC reports, NCMEC materials, DOJ CEOS and State AG press releases, federal PACER filings). No PII was processed.
- UMass Amherst HRPO Determination **#7668** — no private or identifiable information under 45 CFR 46.102(e)(1), (4).

## Citation

> Ramachandran, M. (2026). *CaseLinker: An Open-Source System for Cross-Case Analysis of Internet Crimes Against Children Reports* (Version 3.0) [Computer software]. https://github.com/mrinaalr/CaseLinker

Phase 3 DOI: [10.5281/zenodo.23461974](https://doi.org/10.5281/zenodo.23461974).

## Links

- **Live demo:** https://caselinker.up.railway.app/
- **Crash Course:** https://caselinker.up.railway.app/crash-course
- **Ontology & Graphs:** https://caselinker.up.railway.app/patterns
- **SPARQL:** https://caselinker.up.railway.app/sparql · `ontology/docs/SPARQL.md`
- **API docs:** https://caselinker.up.railway.app/docs
- **Phase 2.5:** [10.5281/zenodo.22803051](https://doi.org/10.5281/zenodo.22803051)
- **Phase 2:** [10.5281/zenodo.21348119](https://doi.org/10.5281/zenodo.21348119)
- **Research site:** https://end-child-exploitation.com/