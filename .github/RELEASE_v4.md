**CaseLinker Phase 4** makes every case graph **ontology-conformant**, **entity-grounded** and **provenance-annotated**. Case graphs use the terms UCO, CASE and CAC declare. Places and agencies resolve to the Census gazetteer and the FBI's agency registry. Ages, sentences, CyberTips, their reporters and prior convictions link to the quote that supports them. Only graphs that pass SHACL validation enter the corpus, and every case graph connects to its provenance graph, both accessible via their w3id IRIs in HTML, Turtle or JSON-LD. CaseLinker repairs and expands through its MCP server, with targeted fixes measured against the whole corpus before review.

## Highlights

- **Declared terms.** Case graphs hold the features extracted from each release, in declared UCO, CASE and CAC terms.
- **Grounded.** Places resolve to the 2024 Census gazetteer, agencies to the FBI CDE registry. State police now ground; county sheriffs keep their county.
- **Evidence on the node.** Each age, sentence, CyberTip, reporter and prior conviction in a case graph links to its quote in the provenance graph.
- **Prior convictions per defendant.** Earlier conviction, registration and supervision, stored per defendant; registered offenders are typed with CAC registry roles.
- **CyberTip recall.** 492 more cases record a CyberTip origin, and the platform that filed it when the release names one.
- **Reproducible AfH evidence.** Every *Affordances for Harm* 2.0 platform figure regenerates byte for byte from a pinned corpus snapshot.
- **Repair and expand.** CaseLinker repairs and expands through its MCP server. Targeted fixes are diagnosed per stored value and replayed over the whole corpus, base against checkout, with full NER.
- **Corpus.** **10,802** cases, **132,676** features, **76** sources, **6,305,673** triples.

----

## Phase 4 in detail

### Pinned ontologies

The mapper was rewritten against the pinned ontologies ([#68](https://github.com/mrinaalr/CaseLinker/pull/68)). CAC 3.1.0 (all 97 files), UCO 1.5.0, CASE 1.5.0 and gUFO, the foundation CAC is built on, are vendored and checksummed, and `term_resolution.py` fails the build on any IRI they do not declare.

- `dcterms:source` holds the release URL, and the issuing agency moves to `dcterms:publisher` ([#89](https://github.com/mrinaalr/CaseLinker/pull/89)).
- Every person and platform is a `uco-core:object` of the case's investigation node, so a query that starts at the case reaches them ([#82](https://github.com/mrinaalr/CaseLinker/pull/82)).
- When a release names a platform, its case graph carries the full platform node, including its encryption level (end-to-end for WhatsApp or Signal) and platform type (legacy, classifieds, VR) ([#45](https://github.com/mrinaalr/CaseLinker/pull/45)).

### Grounding

Locations ground to the pinned 2024 Census gazetteer and agencies to the FBI Crime Data Explorer (CDE) registry. Every mention keeps a `groundStatus`: grounded, ungrounded, ambiguous, out of registry, international or out of scope. Two cases share a place or agency node only when both resolve to the same authority record.

- **State police ground** ([#93](https://github.com/mrinaalr/CaseLinker/pull/93)). A state-police mention resolves to the agency's CDE record or, where CDE lists only local stations (New Jersey, Michigan, Pennsylvania, Virginia), one shared statewide node without an ORI (the FBI's agency identifier). On the stored corpus, 1,850 of 1,916 state-police mentions now ground, where none did before.
- **County sheriffs keep their county** ([#93](https://github.com/mrinaalr/CaseLinker/pull/93)). In run-on partner lists, NER left the county outside the span ("Camden County | Sheriff's Office"). The county is recovered only when it is a county or parish in the Census gazetteer. That recovers 315 sheriffs in 189 cases, and no name or sentence fragment is taken as a county.
- **The public agency count merges spelling variants** ([#92](https://github.com/mrinaalr/CaseLinker/pull/92)), such as Sheriff's Department / Office and state abbreviations, and drops unit fragments: 4,462 → 4,278 on the Phase 3 corpus.

### Evidence on the node

A provenance annotation now names the case-graph node it supports ([#74](https://github.com/mrinaalr/CaseLinker/pull/74)): an age, an imposed sentence, a CyberTip report, its reporter, or a prior conviction. From any of them, one SPARQL hop returns the field, value, method, confidence and exact quote with offsets. Evidence-coverage shapes fail an age, sentence, CyberTip or reporter node that has no annotation. **50,297** node links are live.

Identifiers resolve. `https://w3id.org/caselinker/…` answers 303 to the app, which serves HTML, Turtle or JSON-LD for any case, node or provenance graph ([#40](https://github.com/mrinaalr/CaseLinker/pull/40)), and [/explore](https://caselinker.up.railway.app/explore) walks them by hand.

### Extraction

- **Prior convictions** ([#98](https://github.com/mrinaalr/CaseLinker/pull/98)). `prior_history` is a new field: one record per defendant (`p1`, `p2`) with a kind (earlier conviction, registered offender, or on supervision at the time), the count and year the release states, whether the earlier offense was sexual, and a span-gated quote. Negations, statute boilerplate ("whether or not the defendant has any prior conviction"), this case's own conviction and terms of this sentence are dropped.
- **CyberTips** ([#99](https://github.com/mrinaalr/CaseLinker/pull/99)). These now count:
  - tips named without the word ("a tip from the National Center for Missing …");
  - tips with verbs the reader lacked ("followed up on", "acting on", "stem from");
  - reporters named in the sentence after the tip.

  The reporter reader added in #68 says which platform filed the tip, or that the release does not say.
- **Ages** ([#39](https://github.com/mrinaalr/CaseLinker/pull/39), [#63](https://github.com/mrinaalr/CaseLinker/pull/63), [#72](https://github.com/mrinaalr/CaseLinker/pull/72)). Victim age spans stay spans ("ages 8 to 13"). Arrest objects ("arrested 21-year-old …") and acted-on ages ("to entice a 13-year-old") get roles.
- **Platforms and prosecution** ([#47](https://github.com/mrinaalr/CaseLinker/pull/47), [#63](https://github.com/mrinaalr/CaseLinker/pull/63), [#88](https://github.com/mrinaalr/CaseLinker/pull/88)). Agency social-media footers no longer count as platforms. Case phase ignores conditional wording, so "if convicted" leaves an arrest release at arrest. "Jailed for" and "imprisoned for" a term count as sentenced.
- **Dates** ([#95](https://github.com/mrinaalr/CaseLinker/pull/95)). Program-history dates ("the task force was launched in 2006") get their own role, so they never date the case.

### Court records, machine-coded

The PACER phase machines and the 297 legacy `urn:pacer:kg:*` graphs are replaced by a source-grounded evidence model ([#100](https://github.com/mrinaalr/CaseLinker/pull/100)).

- **Two model coders.** Each case is coded independently by two local models from different families. `qwen3:4b` and `llama3.2:3b`, pinned by content digest and running on a local Ollama server, code participants, events, cited dates, relations and page-level provenance, with the legal standing of each passage. In `adjudicated` mode a manual human reviewer decides every disagreement, open role and possible retelling of the same act, and `apply` refuses while any item is open. `pacer-v1` is released in `machine` mode, where a deterministic rule publishes the acts both coders agree on, links possible retellings of the same act, and leaves unresolved roles unassigned.
- **Trajectories** are the longest sequences of acts the court record puts in order, each act documented as coming before the next. Where the record leaves the order open, it stays open. A platform feature counts toward an act in the *Affordances for Harm* sets when the court record documents the feature as instrumental to that act.
- **Graphs.** Each court record's coding, platforms, and features named on its pages are written as evidence, trajectory and observation graphs with the CASE-UCO SDK, then validated against UCO/CASE 1.5.0 and CAC 3.1.0's 47 SHACL shape files (with its 50 ontology modules). Each is released as a named graph: `urn:caselinker:pacer:<case_id>:evidence`, `:trajectories` or `:observations`. CaseLinker's own output has no violations; the 417 reported come from an upstream CAC shape that rejects valid `uco-action:ActionLifecycle` nodes, filed as [CAC-Ontology#74](https://github.com/Project-VIC-International/CAC-Ontology/issues/74).
- **First dataset.** `pacer-v1`: 30 cases (98 documents), 284 agreed acts and 90 graphs.
- **Public and local.** `/lifecycle` shows each case's documented acts in order. Court text, coder text and quotes stay local; the repository holds codes, statuses, dates, page numbers and hashes.

### *Affordances for Harm* 2.0 evidence

`ontology/platform_affordance_evidence/afh_manifest/` regenerates every AfH 2.0 Section 3–4 platform figure from a pinned, read-only snapshot of the corpus, byte for byte ([#95](https://github.com/mrinaalr/CaseLinker/pull/95)).

| | Cases |
|---|---:|
| Name a specific platform (the paper's analytic set) | 1,843 |
| Stated platform-use evidence | 1,308 |
| Weaker co-occurrence evidence | 187 |
| Platform named only, no use stated | 348 |

A snapshot counts as current only when its corpus identity, every case–platform pair and the builder's code hashes all match.

### MCP

- **Repair and expand** ([#85](https://github.com/mrinaalr/CaseLinker/pull/85), [#96](https://github.com/mrinaalr/CaseLinker/pull/96)):

  | Tool | What it does |
  |---|---|
  | `describe_pipeline` | Maps every reader and every field to the code that sets it |
  | `diagnose_case` | Replays one stored value with its source excerpts |
  | `profile_new_source` | Reads a new PDF before ingest |
  | `scaffold_extension` | Stubs a new reader |
  | `run_gate` | Replays a code change over every case, base commit against checkout, and lists before and after for each case that moves; `full=true` adds NER and spaCy |

  A change never runs inside the process that grades it, and nothing writes to the corpus. The counts in #98 and #99 were measured with `run_gate`.
- **First extension: restitution** ([#85](https://github.com/mrinaalr/CaseLinker/pull/85)). Written against the repair-and-expand tools, it reads the restitution amount a release orders and marks a ceiling ("faces up to …") as exposure, not an order. On a 1,000-case sample it settles an amount in 67 cases and moves no core field. It runs in rehearsal: nothing is stored or mapped until the maintainer admits it.
- **New tools** ([#49](https://github.com/mrinaalr/CaseLinker/pull/49), [#50](https://github.com/mrinaalr/CaseLinker/pull/50), [#51](https://github.com/mrinaalr/CaseLinker/pull/51), [#69](https://github.com/mrinaalr/CaseLinker/pull/69)): `build_conduct_cohort`, `get_sentencing_stats` split by federal, state and unknown jurisdiction, and `filter_cases_by_jurisdiction`.
- **Tool count:** 62 local, 47 hosted.

### Sources, corpus and stores

- **Six new sources** ([#77](https://github.com/mrinaalr/CaseLinker/pull/77), [#78](https://github.com/mrinaalr/CaseLinker/pull/78)): Metro Nashville PD, Louisiana State Police, Ocean County Prosecutor (NJ), Kentucky AG, Maricopa County Attorney (AZ) and Sacramento County Sheriff, for 76 in all.
- **Full re-ingest and graph rebuild** on the merged code ([#80](https://github.com/mrinaalr/CaseLinker/pull/80) and this release). A fresh ingest of all 87 PDFs took **2.5** hours locally, and the Postgres load 3 minutes.
- **Oxigraph** bulk-loads into an empty store, so the full corpus fits its volume, and `--verify` checks the loaded graphs against the release manifest ([#86](https://github.com/mrinaalr/CaseLinker/pull/86), [#100](https://github.com/mrinaalr/CaseLinker/pull/100)).
- **Bulk ingest** resumes after a crash, reconnects after a dropped Postgres connection, and marks a PDF done only when every case it yielded was stored ([#91](https://github.com/mrinaalr/CaseLinker/pull/91)).

### Web app

The site is rebuilt around its tools: Analysis (question → SPARQL → answer → passage), Graph, Explore, State machines, Affordances, Search, Audit, Sources, and Under the hood.

## Replaced and retired

| Phase 3 | Phase 4 |
|---|---|
| `cac-core:hasRole`, `uco-role:VictimRole` | `uco-core:Relationship` `Has_Role`, declared CAC role classes |
| A `Location` node for every place string | Only for grounded places; others stay in provenance with `groundStatus` |
| Admission frame, theme and context, `chargeCluster`, `investigationStatus` in the graph | No longer in the graph (no declared term); still in the database and API. Each admission stays a `cacontology-undercover:IncriminatingStatement` |
| `urn:pacer:kg:*` (297 graphs) | `urn:caselinker:pacer:<case_id>:evidence`, `:trajectories` and `:observations`, released datasets |
| `GET /api/lifecycle/lstar`, `/api/lifecycle/anchors`, MCP `get_lifecycle_lstar` | 410 Gone / removed; `/api/lifecycle/analysis` and MCP `get_trajectory_analysis` (trusted) |
| Phase 3 case ids | Keyed to a fingerprint of the release text ([#38](https://github.com/mrinaalr/CaseLinker/pull/38)); ids stay provisional until the id map is frozen (target Phase 5) |
| `/clusters`, `/stats`, `/query`, `/llm`, `/triage`, `/case-studies`, `/tech-landscape` | Pages retired; their APIs remain |

Rewritten queries are in [`ontology/docs/SPARQL.md`](https://github.com/mrinaalr/CaseLinker/blob/main/ontology/docs/SPARQL.md).

## Measured

Replayed over the 10,802 stored cases before the rebuild; the cases that moved were read, all of them where few moved and seeded samples of 30 where many did.

| Change | Cases | Read |
|---|---:|---|
| `prior_history` resolved | 964 | 30 of 30 seeded new flags correct |
| `previous_conviction` newly true / newly false | 333 / 3 | all 3 removals correct |
| Registration roles gained / lost | 46 / 0 | all 46 are "failure to register", which CAC defines as required to register |
| New case-scoped CyberTips | 492 | 30 of 30 seeded per shape correct |
| Named CyberTip reporters | 21 | 20 of 21 correct |
| State-police mentions grounded | 1,850 of 1,916 | bare "State Police" grounded from the source state: 12 of the 85 New York cases and all 5 others read, all correct |
| County sheriffs recovered | 315 in 189 cases | every added label checked against its text |

## Data & Ethics

- Records come from public, redacted sources (ICAC reports, NCMEC materials, DOJ CEOS and State AG press releases, federal PACER filings).
- UMass Amherst HRPO Determination **#7668**: no identifiable private information under 45 CFR 46.102(e)(1), (4).

## Citation

> Ramachandran, M. (2026). *CaseLinker: An Open-Source System for Cross-Case Analysis of Internet Crimes Against Children Reports* (Version 4.0) [Computer software]. https://doi.org/10.5281/zenodo.18743600

## Links

- **Live demo:** https://caselinker.up.railway.app/
- ***Affordances for Harm*:** [10.5281/zenodo.21347780](https://doi.org/10.5281/zenodo.21347780)
- **Phase 3:** [10.5281/zenodo.23461974](https://doi.org/10.5281/zenodo.23461974)
- **Phase 2.5:** [10.5281/zenodo.22803051](https://doi.org/10.5281/zenodo.22803051)
- **Phase 2:** [10.5281/zenodo.21348119](https://doi.org/10.5281/zenodo.21348119)
- **Research site:** https://end-child-exploitation.com/

## Pull requests

Merged in Phase 4: [#26](https://github.com/mrinaalr/CaseLinker/pull/26), [#38](https://github.com/mrinaalr/CaseLinker/pull/38), [#39](https://github.com/mrinaalr/CaseLinker/pull/39), [#40](https://github.com/mrinaalr/CaseLinker/pull/40), [#41](https://github.com/mrinaalr/CaseLinker/pull/41), [#42](https://github.com/mrinaalr/CaseLinker/pull/42), [#44](https://github.com/mrinaalr/CaseLinker/pull/44), [#45](https://github.com/mrinaalr/CaseLinker/pull/45), [#46](https://github.com/mrinaalr/CaseLinker/pull/46), [#47](https://github.com/mrinaalr/CaseLinker/pull/47), [#49](https://github.com/mrinaalr/CaseLinker/pull/49), [#50](https://github.com/mrinaalr/CaseLinker/pull/50), [#51](https://github.com/mrinaalr/CaseLinker/pull/51), [#52](https://github.com/mrinaalr/CaseLinker/pull/52), [#54](https://github.com/mrinaalr/CaseLinker/pull/54), [#56](https://github.com/mrinaalr/CaseLinker/pull/56), [#63](https://github.com/mrinaalr/CaseLinker/pull/63), [#65](https://github.com/mrinaalr/CaseLinker/pull/65), [#66](https://github.com/mrinaalr/CaseLinker/pull/66), [#68](https://github.com/mrinaalr/CaseLinker/pull/68), [#69](https://github.com/mrinaalr/CaseLinker/pull/69), [#70](https://github.com/mrinaalr/CaseLinker/pull/70), [#72](https://github.com/mrinaalr/CaseLinker/pull/72), [#74](https://github.com/mrinaalr/CaseLinker/pull/74), [#76](https://github.com/mrinaalr/CaseLinker/pull/76), [#77](https://github.com/mrinaalr/CaseLinker/pull/77), [#78](https://github.com/mrinaalr/CaseLinker/pull/78), [#80](https://github.com/mrinaalr/CaseLinker/pull/80), [#82](https://github.com/mrinaalr/CaseLinker/pull/82), [#83](https://github.com/mrinaalr/CaseLinker/pull/83), [#84](https://github.com/mrinaalr/CaseLinker/pull/84), [#85](https://github.com/mrinaalr/CaseLinker/pull/85), [#86](https://github.com/mrinaalr/CaseLinker/pull/86), [#87](https://github.com/mrinaalr/CaseLinker/pull/87), [#88](https://github.com/mrinaalr/CaseLinker/pull/88), [#89](https://github.com/mrinaalr/CaseLinker/pull/89), [#90](https://github.com/mrinaalr/CaseLinker/pull/90), [#91](https://github.com/mrinaalr/CaseLinker/pull/91), [#92](https://github.com/mrinaalr/CaseLinker/pull/92), [#93](https://github.com/mrinaalr/CaseLinker/pull/93), [#94](https://github.com/mrinaalr/CaseLinker/pull/94), [#95](https://github.com/mrinaalr/CaseLinker/pull/95), [#96](https://github.com/mrinaalr/CaseLinker/pull/96), [#97](https://github.com/mrinaalr/CaseLinker/pull/97), [#98](https://github.com/mrinaalr/CaseLinker/pull/98), [#99](https://github.com/mrinaalr/CaseLinker/pull/99), [#100](https://github.com/mrinaalr/CaseLinker/pull/100).
