# Run report: pacer-v1

Review mode **machine**: two local models coded every case independently; a fixed rule published what both coded. Nothing here is human-adjudicated. Reliability is agreement between the coders on these cases; benchmark accuracy is measured on synthetic records ([benchmark](../../benchmark/README.md)). Neither is accuracy on these cases.

## What is published

| Content | Count |
|---|---:|
| acts | 285 |
| acts with a cited date | 143 |
| acts: law_enforcement | 27 |
| acts: offender | 163 |
| acts: procedure | 92 |
| acts: response | 3 |
| cases | 30 |
| cases with offender acts | 24 |
| harms recorded: victim minor | 15 |
| harms recorded: victim unknown | 1 |
| level-C affordances (sentence states the feature as the means) | 0 |
| offender acts naming a victim or an undercover persona | 71 |
| offender acts with a documented platform | 9 |
| relations: possibly the same act | 7 |
| relations: stated order | 1 |

Order between acts comes mostly from cited dates; stated order is published only where a sentence names the earlier act or follows it directly. An act with no date and no stated order is unordered, not placed.

## Models

| Coder | Model | Digest | Quantization |
|---|---|---|---|
| coder_A | `qwen3:4b` | `sha256:359d7dd4bcda…` | Q4_K_M |
| coder_B | `llama3.2:3b` | `sha256:a80c4f17acd5…` | Q4_K_M |

Inference: `{"temperature": 0, "seed": 7, "num_ctx": 8192, "num_predict": 1500}`; runtime `{"OLLAMA_HOST": "127.0.0.1:11435", "OLLAMA_FLASH_ATTENTION": "1", "OLLAMA_KV_CACHE_TYPE": "q8_0", "OLLAMA_MAX_LOADED_MODELS": "1", "OLLAMA_NUM_PARALLEL": "2"}`; prompt `coder-prompt-2.0`.

## Cases

30 published, 0 not published.

| Case | Published | Events | Relations both coders asserted | Coder A acts | Coder B acts | Matched | Action κ | SHACL |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `anchorage_pd_2022_004` | yes | 6 | 0 | 108 | 214 | 52 | 0.168 | fails |
| `anchorage_pd_2022_006` | yes | 15 | 0 | 166 | 407 | 64 | 0.273 | fails |
| `anchorage_pd_2022_007` | yes | 27 | 0 | 302 | 348 | 100 | 0.323 | fails |
| `doj_ceos_2025_004` | yes | 1 | 0 | 14 | 107 | 3 | 0.25 | partial |
| `doj_ceos_2025_007` | yes | 5 | 0 | 81 | 173 | 27 | 0.346 | fails |
| `doj_ceos_2025_014` | yes | 6 | 0 | 50 | 163 | 20 | 0.223 | partial |
| `doj_ceos_2025_023` | yes | 10 | 0 | 45 | 164 | 30 | 0.333 | fails |
| `doj_ceos_2025_025` | yes | 20 | 0 | 442 | 655 | 217 | 0.224 | fails |
| `doj_ceos_2025_026` | yes | 15 | 0 | 32 | 27 | 21 | 0.439 | fails |
| `doj_ceos_2025_031` | yes | 15 | 0 | 184 | 291 | 74 | 0.238 | fails |
| `doj_ceos_2026_001` | yes | 32 | 0 | 146 | 105 | 56 | 0.446 | fails |
| `doj_ceos_2026_003` | yes | 1 | 0 | 112 | 411 | 19 | 0.339 | partial |
| `doj_ceos_2026_006` | yes | 11 | 0 | 180 | 354 | 87 | 0.201 | fails |
| `doj_ceos_2026_007` | yes | 3 | 0 | 53 | 399 | 17 | 0.318 | partial |
| `doj_ceos_2026_008` | yes | 4 | 0 | 46 | 244 | 17 | 0.356 | fails |
| `doj_ceos_2026_012` | yes | 9 | 0 | 16 | 142 | 10 | 0.462 | fails |
| `doj_safe_childhood_2023_420` | yes | 5 | 0 | 53 | 123 | 22 | 0.268 | fails |
| `external_extortion` | yes | 1 | 0 | 22 | 99 | 15 | 0.227 | fails |
| `ky_sp_2025_038` | yes | 2 | 0 | 65 | 123 | 32 | 0.186 | fails |
| `ncis_2022_002` | yes | 4 | 0 | 22 | 152 | 15 | 0.207 | fails |
| `ncis_2023_001` | yes | 5 | 0 | 58 | 85 | 17 | 0.224 | fails |
| `ncmec_2022_575` | yes | 19 | 0 | 92 | 185 | 43 | 0.465 | fails |
| `ncmec_2023_222` | yes | 1 | 0 | 14 | 66 | 1 | None | partial |
| `ncmec_2025_1035` | yes | 1 | 0 | 18 | 100 | 4 | 0.2 | fails |
| `svicac_2022_009` | yes | 19 | 0 | 58 | 92 | 15 | 0.534 | fails |
| `texas_ag_2019_013` | yes | 19 | 0 | 102 | 225 | 45 | 0.344 | fails |
| `usss_2017_006` | yes | 13 | 0 | 99 | 85 | 38 | 0.294 | fails |
| `usss_2021_017` | yes | 7 | 0 | 88 | 178 | 32 | 0.354 | fails |
| `usss_2023_004` | yes | 3 | 0 | 43 | 126 | 21 | 0.255 | fails |
| `wy_dci_2023_005` | yes | 6 | 0 | 7 | 113 | 3 | 0.143 | partial |

Relations made by rule from agreed acts (stated order, possible retellings) are counted under "What is published", not in this column. **SHACL:** our own shapes have 0 violations in every case. `fails` means a violation only of an upstream CAC shape listed in `state_machines/graphs/shacl_upstream_defects.json`; `partial` means upstream constraints that apply could not be run (see [graphs](../../graphs/README.md)).


## Coverage and drops

| Measure | Count |
|---|---:|
| coder_A acts dropped: procedure act repeating a dated anchor | 241 |
| coder_A acts dropped: procedure act without a stated date | 2978 |
| coder_A acts dropped: quote not located on the page | 1037 |
| coder_A acts proposed: docket parser | 84 |
| coder_A acts proposed: model | 6974 |
| coder_A acts proposed: skipped: judgment form page | 0 |
| coder_A pages: docket parser | 201 |
| coder_A pages: model | 886 |
| coder_A pages: skipped: judgment form page | 60 |
| coder_B acts dropped: procedure act repeating a dated anchor | 6 |
| coder_B acts dropped: procedure act without a stated date | 586 |
| coder_B acts dropped: quote not located on the page | 1840 |
| coder_B acts proposed: docket parser | 84 |
| coder_B acts proposed: model | 8388 |
| coder_B acts proposed: skipped: first coder found no act | 0 |
| coder_B acts proposed: skipped: judgment form page | 0 |
| coder_B pages: docket parser | 201 |
| coder_B pages: model | 878 |
| coder_B pages: skipped: first coder found no act | 8 |
| coder_B pages: skipped: judgment form page | 60 |

## Reliability on the real cases

```json
{
 "cases": 30,
 "events_coder_A": 2718,
 "events_coder_B": 5956,
 "matched": 1117,
 "mean_event_f1": 0.242,
 "pooled_action_agreement": {
  "exact": 375,
  "of": 1117
 },
 "mean_action_kappa": 0.298,
 "note": "agreement on acts the models coded; the docket parser's acts are excluded"
}
```

## What the records name (observation layer)

Read by rule from every page except docket sheets, independent of the coders. An observation says that a cited sentence names a listed platform, refers to a service by a placeholder ("Website A", name withheld, a label that means nothing outside its case), uses a generic description of an online service ("social media application"), or states a codebook feature phrase. It does not say anyone used it, and a withheld name is not evidence of anonymity or of any feature. A relationship exists only where a published act's own sentence states the means; a generic description is never tied to an act.

| Content | Count |
|---|---:|
| cases | 30 |
| observations | 875 |
| observations of a listed platform's name | 539 |
| observations of a platform under a placeholder (name withheld) | 176 |
| observations of a generic service description | 73 |
| feature observations | 87 |
| cases naming at least one listed platform | 25 |
| cases with a platform whose name is withheld | 2 |
| cases with a generic service description | 18 |
| cases with no listed platform, a withheld one | 0 |
| cases with neither, a generic service description | 2 |
| cases with none of the three | 3 |
| cases stating at least one feature phrase | 13 |
| distinct case and listed-platform pairs | 70 |
| distinct case and withheld-platform pairs | 5 |
| observations tied to a published act by a stated means | 10 |
| cases with at least one such relationship | 7 |
| observations in documents with standing ADVOCACY | 147 |
| observations in documents with standing ALLEGATION | 221 |
| observations in documents with standing COURT_RECORD | 27 |
| observations in documents with standing ADMITTED | 197 |
| observations in documents with standing SWORN_AFFIDAVIT | 282 |
| observations in documents with standing ADMITTED_UNDER_OATH | 1 |

**Machine-read; no person reviewed these observations on the real text.** The release is complete without such a review. A researcher who wants one can draw a stratified local packet (`python -m state_machines.observations.validation packet`); its score is printed here when a decisions file is scored.

On the reference cases (another coding, not truth): cases 5; listed platforms the reference coding names 3; of which observed 3; platform surfaces in the reference that are not on the list 4; listed platforms observed 6.

### Level 1. Which listed platforms do the records name, in how many cases?

```sparql
PREFIX oa: <http://www.w3.org/ns/oa#>
PREFIX core: <https://ontology.unifiedcyberontology.org/uco/core/>
PREFIX action: <https://ontology.unifiedcyberontology.org/uco/action/>
PREFIX clt: <https://w3id.org/caselinker/trajectory#>
SELECT ?platform (COUNT(DISTINCT ?g) AS ?cases) (COUNT(?obs) AS ?mentions) WHERE {
  GRAPH ?g { ?obs oa:motivatedBy oa:identifying ; oa:hasBody ?p . ?p core:name ?platform }
  FILTER(STRSTARTS(STR(?p), "https://w3id.org/caselinker/resource/platform/"))
} GROUP BY ?platform ORDER BY DESC(?cases) DESC(?mentions) ?platform
```

| platform | cases | mentions |
|---|---|---|
| Facebook | 12 | 41 |
| Snapchat | 10 | 173 |
| Instagram | 8 | 104 |
| Kik | 6 | 49 |
| Omegle | 4 | 6 |
| Grindr | 3 | 22 |
| Facebook Messenger | 2 | 39 |
| Dropbox | 2 | 38 |
| FaceTime | 2 | 13 |
| Google Drive | 2 | 3 |
| WhatsApp | 2 | 3 |
| TikTok | 2 | 2 |
| Wickr | 2 | 2 |
| YouTube | 2 | 2 |
| Pinterest | 1 | 10 |
| Skype | 1 | 8 |
| Discord | 1 | 7 |
| PayPal | 1 | 6 |
| Telegram | 1 | 4 |
| Imgsrc | 1 | 2 |
| Flickr | 1 | 1 |
| Hotmail | 1 | 1 |
| Tumblr | 1 | 1 |
| Twitter | 1 | 1 |
| iCloud | 1 | 1 |

### Level 1. Which services does a record refer to by a placeholder, case by case? (A label means nothing outside its case.)

```sparql
PREFIX oa: <http://www.w3.org/ns/oa#>
PREFIX core: <https://ontology.unifiedcyberontology.org/uco/core/>
PREFIX action: <https://ontology.unifiedcyberontology.org/uco/action/>
PREFIX clt: <https://w3id.org/caselinker/trajectory#>
SELECT ?case ?label (COUNT(?obs) AS ?mentions) WHERE {
  GRAPH ?g { ?obs oa:motivatedBy oa:identifying ; oa:hasBody ?p . ?p core:name ?label }
  FILTER(!STRSTARTS(STR(?p), "https://w3id.org/caselinker/resource/platform/"))
  BIND(REPLACE(REPLACE(STR(?g), "^urn:caselinker:pacer:", ""), ":observations$", "") AS ?case)
} GROUP BY ?case ?label ORDER BY ?case ?label
```

| case | label | mentions |
|---|---|---|
| doj_ceos_2025_025 | Website A (name withheld) | 26 |
| doj_ceos_2025_025 | Website B (name withheld) | 27 |
| doj_ceos_2025_025 | Website C (name withheld) | 29 |
| doj_ceos_2025_025 | Website D (name withheld) | 30 |
| doj_ceos_2025_031 | Website A (name withheld) | 64 |

### Level 1. Which generic descriptions of an online service do the records use? (Not platforms; no use claimed.)

```sparql
PREFIX oa: <http://www.w3.org/ns/oa#>
PREFIX core: <https://ontology.unifiedcyberontology.org/uco/core/>
PREFIX action: <https://ontology.unifiedcyberontology.org/uco/action/>
PREFIX clt: <https://w3id.org/caselinker/trajectory#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
SELECT ?description (COUNT(DISTINCT ?g) AS ?cases) (COUNT(?obs) AS ?mentions) WHERE {
  GRAPH ?g { ?obs oa:motivatedBy oa:describing ; oa:hasBody ?b . ?b rdf:value ?description }
} GROUP BY ?description ORDER BY DESC(?cases) DESC(?mentions) ?description
```

| description | cases | mentions |
|---|---|---|
| chat room | 6 | 18 |
| messaging application | 5 | 8 |
| social media platform | 5 | 7 |
| social networking service | 3 | 3 |
| social media app | 2 | 5 |
| online social media application | 2 | 3 |
| instant messaging service | 2 | 2 |
| online forum | 2 | 2 |
| social media website | 2 | 2 |
| social networking forum | 2 | 2 |
| chat site | 1 | 3 |
| online messaging platform | 1 | 3 |
| internet forum | 1 | 2 |
| online dating application | 1 | 2 |
| chat program | 1 | 1 |
| electronic bulletin board | 1 | 1 |
| instant messaging application | 1 | 1 |
| internet cloud storage service | 1 | 1 |
| live-streaming platform | 1 | 1 |
| online chat room | 1 | 1 |
| online gaming platform | 1 | 1 |
| photo-sharing website | 1 | 1 |
| social media application | 1 | 1 |
| social networking application | 1 | 1 |
| social networking website | 1 | 1 |

### Level 1. Which feature phrases do the records state, under which CAC class?

```sparql
PREFIX oa: <http://www.w3.org/ns/oa#>
PREFIX core: <https://ontology.unifiedcyberontology.org/uco/core/>
PREFIX action: <https://ontology.unifiedcyberontology.org/uco/action/>
PREFIX clt: <https://w3id.org/caselinker/trajectory#>
SELECT ?class ?phrase (COUNT(DISTINCT ?g) AS ?cases) (COUNT(?obs) AS ?mentions) WHERE {
  GRAPH ?g { ?obs oa:motivatedBy oa:classifying ; oa:hasBody ?c ; clt:featureTerm ?phrase }
  BIND(REPLACE(STR(?c), "^.*#", "") AS ?class)
} GROUP BY ?class ?phrase ORDER BY ?class DESC(?mentions) ?phrase
```

| class | phrase | cases | mentions |
|---|---|---|---|
| Anonymity | Tor | 1 | 56 |
| Anonymity | VPN | 1 | 1 |
| Anonymity | burner phone | 1 | 1 |
| ContactDiscovery | public group | 1 | 1 |
| DistributionInfrastructure | uploaded | 7 | 10 |
| DistributionInfrastructure | cloud storage | 3 | 3 |
| DistributionInfrastructure | peer-to-peer | 1 | 1 |
| Ephemerality | self-destructing | 1 | 1 |
| UnmonitoredCommunication | encrypted | 4 | 9 |
| UnmonitoredCommunication | private messages | 3 | 4 |

### Level 2. Which acts did both coders agree on?

```sparql
PREFIX oa: <http://www.w3.org/ns/oa#>
PREFIX core: <https://ontology.unifiedcyberontology.org/uco/core/>
PREFIX action: <https://ontology.unifiedcyberontology.org/uco/action/>
PREFIX clt: <https://w3id.org/caselinker/trajectory#>
SELECT ?action (COUNT(DISTINCT ?g) AS ?cases) (COUNT(?act) AS ?acts) WHERE {
  GRAPH ?g { ?act a action:Action ; clt:actionCode ?action ; clt:reviewStatus "agreed" }
  FILTER(STRENDS(STR(?g), ":evidence"))
} GROUP BY ?action ORDER BY DESC(?acts) ?action
```

| action | cases | acts |
|---|---|---|
| DISTRIBUTE_MATERIAL | 12 | 36 |
| PROC_PLEA | 10 | 31 |
| PROC_CHARGE | 11 | 26 |
| PROC_SENTENCE | 13 | 26 |
| DIRECT_CONDUCT | 7 | 14 |
| LE_ARREST | 10 | 14 |
| SOLICIT_IMAGERY | 8 | 11 |
| ACQUIRE_MATERIAL | 5 | 10 |
| SEEK_TARGETS | 5 | 10 |
| COMMUNICATE | 4 | 9 |
| PROC_VERDICT | 8 | 9 |
| THREATEN_EXPOSURE | 5 | 9 |
| TRAVEL_TO_MEET | 6 | 9 |
| INITIATE_CONTACT | 5 | 7 |
| ADMINISTER_SPACE | 2 | 5 |
| IN_PERSON_SEXUAL_ABUSE | 4 | 5 |
| OFFER_INDUCEMENT | 3 | 5 |
| RECEIVE_SELF_GENERATED | 5 | 5 |
| RECORD_LIVE_SESSION | 2 | 5 |
| LE_RECEIVE_TIP | 3 | 4 |
| LE_SURVEIL | 1 | 4 |
| STORE_MATERIAL | 4 | 4 |
| ACQUIRE_REPRESENTATION | 2 | 3 |
| ARRANGE_MEETING | 2 | 3 |
| LE_SEARCH_SEIZE | 2 | 3 |
| EVADE_DETECTION | 1 | 2 |
| LE_LEGAL_PROCESS | 1 | 2 |
| PAY_THIRD_PARTY | 1 | 2 |
| RESP_BLOCK | 1 | 2 |
| SET_RULES | 2 | 2 |
| CONCEAL_OR_DESTROY_EVIDENCE | 1 | 1 |
| FLEE | 1 | 1 |
| MISREPRESENT_IDENTITY | 1 | 1 |
| PRODUCE_IN_PERSON | 1 | 1 |
| RECONTACT | 1 | 1 |
| RECREATE_ACCOUNT | 1 | 1 |
| RESP_REPORT | 1 | 1 |
| THREATEN_HARM | 1 | 1 |

### Level 3. Where does a record state that an act was done by means of a platform or feature?

```sparql
PREFIX oa: <http://www.w3.org/ns/oa#>
PREFIX core: <https://ontology.unifiedcyberontology.org/uco/core/>
PREFIX action: <https://ontology.unifiedcyberontology.org/uco/action/>
PREFIX clt: <https://w3id.org/caselinker/trajectory#>
SELECT DISTINCT ?case ?event ?action ?relationship ?what ?phrase ?standing WHERE {
  GRAPH ?og { ?obs oa:motivatedBy ?m ; oa:hasTarget ?span ; oa:hasBody ?body ; clt:sourceStatus ?standing .
              ?evidence oa:hasTarget ?span ; oa:hasBody ?rel . FILTER(?evidence != ?obs)
              OPTIONAL { ?obs clt:featureTerm ?phrase } OPTIONAL { ?body core:name ?name } }
  GRAPH ?rg { ?rel core:kindOfRelationship ?relationship ; core:source ?s ; core:target ?t }
  GRAPH ?eg { ?act clt:actionCode ?action } FILTER(?act IN (?s, ?t)) FILTER(STRENDS(STR(?eg), ":evidence"))
  FILTER(?m != oa:describing)
  FILTER(?body IN (?s, ?t) || (BOUND(?phrase) && EXISTS { GRAPH ?any { ?s a ?body } }))
  BIND(COALESCE(?name, REPLACE(STR(?body), "^.*#", "")) AS ?what)
  BIND(REPLACE(REPLACE(STR(?og), "^urn:caselinker:pacer:", ""), ":observations$", "") AS ?case)
  BIND(REPLACE(STR(?act), "^.*[/#:-](e[0-9]+)$", "$1") AS ?event)
} ORDER BY ?case ?event ?what
```

| case | act | action | relationship | platform_or_class | phrase | standing |
|---|---|---|---|---|---|---|
| anchorage_pd_2022_006 | e133 | DISTRIBUTE_MATERIAL | Carried_Out_Through | Snapchat |  | ADVOCACY |
| anchorage_pd_2022_007 | e077 | STORE_MATERIAL | Carried_Out_Through | Dropbox |  | ALLEGATION |
| anchorage_pd_2022_007 | e176 | INITIATE_CONTACT | Carried_Out_Through | Instagram |  | ALLEGATION |
| doj_ceos_2025_026 | e035 | SOLICIT_IMAGERY | Carried_Out_Through | Snapchat |  | ADMITTED |
| doj_ceos_2026_001 | e050 | INITIATE_CONTACT | Carried_Out_Through | Instagram |  | ADMITTED |
| doj_ceos_2026_001 | e056 | INITIATE_CONTACT | Carried_Out_Through | Instagram |  | ADMITTED |
| doj_ceos_2026_001 | e121 | ACQUIRE_MATERIAL | Carried_Out_Through | Instagram |  | ADMITTED |
| doj_safe_childhood_2023_420 | e034 | DIRECT_CONDUCT | Carried_Out_Through | Snapchat |  | ADMITTED |
| ky_sp_2025_038 | e052 | DISTRIBUTE_MATERIAL | Carried_Out_Through | Facebook Messenger |  | ADMITTED |
| ncmec_2022_575 | e077 | INITIATE_CONTACT | Carried_Out_Through | Snapchat |  | ADMITTED |

## Accuracy on the synthetic benchmark

Scores per rule version and split. `resolved` is what a machine release publishes; `resolved_2b` is the candidate cue rule, not released. Synthetic pages are cleaner than real filings: none of this is accuracy on the real cases.

### Observation layer (observe-1.3.0)

Platform names and feature terms are kept verbatim in every split, so these rates measure finding listed terms in new sentence constructions, not recognising unlisted wording.

| Measure | development cases | held-out cases | confirmation cases |
|---|---:|---:|---:|
| gold platform mentions found | 1.0 (71/71) | 1.0 (63/63) | 1.0 (71/71) |
| gold feature statements found | 1.0 (27/27) | 1.0 (30/30) | 1.0 (32/32) |
| observed platforms the gold names in that sentence | 0.973 (71/73) | 0.926 (63/68) | 0.947 (71/75) |
| observed feature phrases the gold codes as an affordance there | 0.973 (36/37) | 0.905 (38/42) | 0.947 (36/38) |
| relationships that the gold also holds | 0.985 (65/66) | 0.942 (65/69) | 0.97 (32/33) |
| relationships to the right platform, wrong kind | 1 | 0 | 1 |
| relationships to a platform the gold says is only named | 0 | 0 | 0 |
| relationships on an act that is not a gold act | 0 | 0 | 0 |
| gold relationships found, on published acts | 0.903 (65/72) | 0.915 (65/71) | 0.762 (32/42) |
| observations outside gold act sentences (not judged) | 20 | 20 | 20 |

### resolve-1.0.0, held-out cases (a second register, scored repeatedly while the coder was developed; not a blind set)

Rules resolve-1.0.0. Held-out cases were scored beside dev in four code states while the coder was developed on 2026-11-17 (resolved recall 98, 138, 141, then 148 of 228); this is the last of those. A second development register, not a blind set.

| Measure | coder_A | coder_B | resolved |
|---|---:|---:|---:|
| gold acts found (recall) | 0.899 (205/228) | 0.807 (184/228) | 0.649 (148/228) |
| coded acts that are gold acts (precision) | 0.958 (205/214) | 0.868 (184/212) | 0.98 (148/151) |
| action code | 0.927 (190/205) | 0.777 (143/184) | 0.912 (135/148) |
| actor | 0.971 (199/205) | 0.962 (177/184) | 0.993 (147/148) |
| legal standing | 1.0 (205/205) | 1.0 (184/184) | 1.0 (148/148) |
| dates | 1.0 (114/114) | 1.0 (107/107) | 1.0 (102/102) |
| gold sequence sentences recovered (stated order recall) | 0.26 (20/77) | 0.273 (21/77) | 0.065 (5/77) |
| level C found (recall) | 1.0 (29/29) | 1.0 (29/29) | 1.0 (26/26) |
| level C correct (precision) | 0.906 (29/32) | 0.906 (29/32) | 0.897 (26/29) |
| harms found (recall) | 0.795 (31/39) | 0.457 (16/35) | 0.727 (16/22) |
| harms correct (precision) | 0.969 (31/32) | 0.762 (16/21) | 1.0 (16/16) |
| possible retellings linked | 0.0 (0/18) | 0.0 (0/18) | 0.5 (9/18) |

Recall of the released coding by hard-case tag: advocacy 1.0 (3/3); allegation 0.8 (12/15); allegation_only 0.0 (0/7); explicit_order 0.403 (29/72); harm 0.55 (22/40); interrupted 0.4 (4/10); level_c 0.867 (26/30); mention_only 0.0 (0/6); no_level_c 0.8 (12/15); procedure 1.0 (40/40); response 0.125 (1/8); retelling 0.833 (15/18); undated 0.489 (22/45); undercover 0.4 (10/25).


### resolve-1.1.0, confirmation cases (wording written without sight of the rules; the only blind split)

The one scoring of this split under resolve-1.1.0, after the rules were frozen and committed. Wording written without sight of the rules. The pages were first coded earlier the same day under pre-freeze code and were not scored then; this run is a second coding under the committed rules.

| Measure | coder_A | coder_B | resolved | resolved_2b |
|---|---:|---:|---:|---:|
| gold acts found (recall) | 0.794 (196/247) | 0.733 (181/247) | 0.421 (104/247) | 0.457 (113/247) |
| coded acts that are gold acts (precision) | 0.827 (196/237) | 0.595 (181/304) | 0.945 (104/110) | 0.95 (113/119) |
| action code | 0.929 (182/196) | 0.818 (148/181) | 0.971 (101/104) | 0.973 (110/113) |
| actor | 0.974 (191/196) | 0.757 (137/181) | 1.0 (104/104) | 0.991 (112/113) |
| legal standing | 1.0 (196/196) | 1.0 (181/181) | 1.0 (104/104) | 1.0 (113/113) |
| dates | 1.0 (94/94) | 1.0 (87/87) | 1.0 (64/64) | 1.0 (66/66) |
| order relations: correct against the documented order | 0.889 (8/9) | 1.0 (5/5) | 1.0 (1/1) | 1.0 (2/2) |
| order relations: reversed | 0 | 0 | 0 | 0 |
| order relations: not documented | 0 | 0 | 0 | 0 |
| gold sequence sentences recovered (stated order recall) | 0.1 (8/80) | 0.062 (5/80) | 0.013 (1/80) | 0.025 (2/80) |
| gold-ordered pairs also ordered, both acts coded | 0.598 (153/256) | 0.573 (138/241) | 0.732 (71/97) | 0.675 (77/114) |
| gold-ordered pairs also ordered, all | 0.34 (153/450) | 0.307 (138/450) | 0.158 (71/450) | 0.171 (77/450) |
| level C found (recall) | 0.968 (30/31) | 0.964 (27/28) | 1.0 (16/16) | 1.0 (16/16) |
| level C correct (precision) | 0.938 (30/32) | 0.931 (27/29) | 0.889 (16/18) | 0.889 (16/18) |
| harms found (recall) | 0.81 (34/42) | 0.674 (31/46) | 0.833 (15/18) | 0.864 (19/22) |
| harms correct (precision) | 1.0 (34/34) | 0.838 (31/37) | 1.0 (15/15) | 1.0 (19/19) |
| possible retellings linked | 0.0 (0/27) | 0.0 (0/27) | 0.222 (6/27) | 0.259 (7/27) |

Recall of the released coding by hard-case tag: advocacy 0.273 (3/11); allegation 0.5 (8/16); allegation_only 0.111 (1/9); explicit_order 0.303 (23/76); harm 0.353 (18/51); interrupted 0.75 (6/8); level_c 0.5 (16/32); mention_only 0.0 (0/11); no_level_c 0.455 (10/22); procedure 0.5 (20/40); response 0.0 (0/14); retelling 0.407 (11/27); undated 0.396 (19/48); undercover 0.55 (11/20).


### resolve-1.1.0, development cases (rules were tuned on these)

Rules were developed on these cases.

| Measure | coder_A | coder_B | resolved | resolved_2b |
|---|---:|---:|---:|---:|
| gold acts found (recall) | 0.963 (233/242) | 0.909 (220/242) | 0.773 (187/242) | 0.872 (211/242) |
| coded acts that are gold acts (precision) | 0.975 (233/239) | 0.853 (220/258) | 0.995 (187/188) | 0.995 (211/212) |
| action code | 0.957 (223/233) | 0.841 (185/220) | 0.957 (179/187) | 0.962 (203/211) |
| actor | 1.0 (233/233) | 0.991 (218/220) | 1.0 (187/187) | 1.0 (211/211) |
| legal standing | 1.0 (233/233) | 1.0 (220/220) | 1.0 (187/187) | 1.0 (211/211) |
| dates | 1.0 (117/117) | 1.0 (117/117) | 1.0 (108/108) | 1.0 (113/113) |
| order relations: correct against the documented order | 0.911 (41/45) | 0.875 (35/40) | 0.952 (20/21) | 0.973 (36/37) |
| order relations: reversed | 0 | 0 | 0 | 0 |
| order relations: not documented | 0 | 0 | 0 | 0 |
| gold sequence sentences recovered (stated order recall) | 0.506 (41/81) | 0.432 (35/81) | 0.247 (20/81) | 0.444 (36/81) |
| gold-ordered pairs also ordered, both acts coded | 0.722 (340/471) | 0.756 (329/435) | 0.757 (253/334) | 0.77 (314/408) |
| gold-ordered pairs also ordered, all | 0.695 (340/489) | 0.673 (329/489) | 0.517 (253/489) | 0.642 (314/489) |
| level C found (recall) | 1.0 (27/27) | 1.0 (27/27) | 1.0 (24/24) | 1.0 (27/27) |
| level C correct (precision) | 0.964 (27/28) | 0.964 (27/28) | 1.0 (24/24) | 0.964 (27/28) |
| harms found (recall) | 0.894 (42/47) | 0.636 (28/44) | 0.848 (28/33) | 0.886 (39/44) |
| harms correct (precision) | 1.0 (42/42) | 0.933 (28/30) | 1.0 (28/28) | 1.0 (39/39) |
| possible retellings linked | 0.0 (0/24) | 0.0 (0/24) | 0.583 (14/24) | 0.667 (16/24) |

Recall of the released coding by hard-case tag: advocacy 0.833 (5/6); allegation 0.889 (16/18); allegation_only 0.143 (1/7); explicit_order 0.696 (55/79); harm 0.702 (33/47); interrupted 0.75 (3/4); level_c 0.889 (24/27); mention_only 0.0 (0/10); no_level_c 0.826 (19/23); procedure 1.0 (40/40); response 0.667 (6/9); retelling 0.875 (21/24); undated 0.704 (38/54); undercover 0.6 (6/10).


### resolve-1.1.0, held-out cases (a second register, scored repeatedly while the coder was developed; not a blind set)

A later look: these cases had been scored repeatedly during coder development under resolve-1.0.0 before the 1.1.0 rules were written. No 1.1.0 rule was written against them, but they are not a blind set.

| Measure | coder_A | coder_B | resolved | resolved_2b |
|---|---:|---:|---:|---:|
| gold acts found (recall) | 0.934 (213/228) | 0.842 (192/228) | 0.671 (153/228) | 0.768 (175/228) |
| coded acts that are gold acts (precision) | 0.955 (213/223) | 0.869 (192/221) | 0.975 (153/157) | 0.978 (175/179) |
| action code | 0.93 (198/213) | 0.766 (147/192) | 0.915 (140/153) | 0.926 (162/175) |
| actor | 0.967 (206/213) | 0.964 (185/192) | 0.993 (152/153) | 0.989 (173/175) |
| legal standing | 1.0 (213/213) | 1.0 (192/192) | 1.0 (153/153) | 1.0 (175/175) |
| dates | 1.0 (119/119) | 1.0 (110/110) | 1.0 (106/106) | 1.0 (107/107) |
| order relations: correct against the documented order | 0.676 (23/34) | 0.733 (22/30) | 0.857 (6/7) | 0.733 (11/15) |
| order relations: reversed | 0 | 0 | 0 | 0 |
| order relations: not documented | 0 | 0 | 0 | 0 |
| gold sequence sentences recovered (stated order recall) | 0.299 (23/77) | 0.286 (22/77) | 0.078 (6/77) | 0.143 (11/77) |
| gold-ordered pairs also ordered, both acts coded | 0.746 (314/421) | 0.749 (269/359) | 0.804 (226/281) | 0.767 (240/313) |
| gold-ordered pairs also ordered, all | 0.667 (314/471) | 0.571 (269/471) | 0.48 (226/471) | 0.51 (240/471) |
| level C found (recall) | 1.0 (29/29) | 1.0 (30/30) | 1.0 (27/27) | 1.0 (28/28) |
| level C correct (precision) | 0.879 (29/33) | 0.882 (30/34) | 0.871 (27/31) | 0.875 (28/32) |
| harms found (recall) | 0.8 (32/40) | 0.444 (16/36) | 0.727 (16/22) | 0.786 (22/28) |
| harms correct (precision) | 0.97 (32/33) | 0.762 (16/21) | 1.0 (16/16) | 1.0 (22/22) |
| possible retellings linked | 0.0 (0/18) | 0.0 (0/18) | 0.556 (10/18) | 0.556 (10/18) |

Recall of the released coding by hard-case tag: advocacy 1.0 (3/3); allegation 0.867 (13/15); allegation_only 0.0 (0/7); explicit_order 0.417 (30/72); harm 0.55 (22/40); interrupted 0.5 (5/10); level_c 0.9 (27/30); mention_only 0.0 (0/6); no_level_c 0.8 (12/15); procedure 1.0 (40/40); response 0.125 (1/8); retelling 0.889 (16/18); undated 0.489 (22/45); undercover 0.52 (13/25).


### resolve-1.2.0, confirmation cases (wording written without sight of the rules; the only blind split)

resolve-1.2.0: level C now needs the sentence to state the feature as the means (the stated-means rule of the observation layer); under 1.1.0 a listed phrase anywhere in the act's sentence was enough, which a sign-off review showed asserts use the text does not state. Acts, action codes, actors, dates and order are unchanged from 1.1.0; only the level-C rows differ. Model answers are the cached ones. All three splits had been scored before, so none is a first look; the rule was not tuned on held-out or confirm.

| Measure | coder_A | coder_B | resolved | resolved_2b |
|---|---:|---:|---:|---:|
| gold acts found (recall) | 0.794 (196/247) | 0.733 (181/247) | 0.421 (104/247) | 0.457 (113/247) |
| coded acts that are gold acts (precision) | 0.827 (196/237) | 0.595 (181/304) | 0.945 (104/110) | 0.95 (113/119) |
| action code | 0.929 (182/196) | 0.818 (148/181) | 0.971 (101/104) | 0.973 (110/113) |
| actor | 0.974 (191/196) | 0.757 (137/181) | 1.0 (104/104) | 0.991 (112/113) |
| legal standing | 1.0 (196/196) | 1.0 (181/181) | 1.0 (104/104) | 1.0 (113/113) |
| dates | 1.0 (94/94) | 1.0 (87/87) | 1.0 (64/64) | 1.0 (66/66) |
| order relations: correct against the documented order | 0.889 (8/9) | 1.0 (5/5) | 1.0 (1/1) | 1.0 (2/2) |
| order relations: reversed | 0 | 0 | 0 | 0 |
| order relations: not documented | 0 | 0 | 0 | 0 |
| gold sequence sentences recovered (stated order recall) | 0.1 (8/80) | 0.062 (5/80) | 0.013 (1/80) | 0.025 (2/80) |
| gold-ordered pairs also ordered, both acts coded | 0.598 (153/256) | 0.573 (138/241) | 0.732 (71/97) | 0.675 (77/114) |
| gold-ordered pairs also ordered, all | 0.34 (153/450) | 0.307 (138/450) | 0.158 (71/450) | 0.171 (77/450) |
| level C found (recall) | 0.516 (16/31) | 0.607 (17/28) | 0.625 (10/16) | 0.625 (10/16) |
| level C correct (precision) | 1.0 (16/16) | 1.0 (17/17) | 1.0 (10/10) | 1.0 (10/10) |
| harms found (recall) | 0.81 (34/42) | 0.674 (31/46) | 0.833 (15/18) | 0.864 (19/22) |
| harms correct (precision) | 1.0 (34/34) | 0.838 (31/37) | 1.0 (15/15) | 1.0 (19/19) |
| possible retellings linked | 0.0 (0/27) | 0.0 (0/27) | 0.222 (6/27) | 0.259 (7/27) |

Recall of the released coding by hard-case tag: advocacy 0.273 (3/11); allegation 0.5 (8/16); allegation_only 0.111 (1/9); explicit_order 0.303 (23/76); harm 0.353 (18/51); interrupted 0.75 (6/8); level_c 0.5 (16/32); mention_only 0.0 (0/11); no_level_c 0.455 (10/22); procedure 0.5 (20/40); response 0.0 (0/14); retelling 0.407 (11/27); undated 0.396 (19/48); undercover 0.55 (11/20).


### resolve-1.2.0, development cases (rules were tuned on these)

resolve-1.2.0: level C now needs the sentence to state the feature as the means (the stated-means rule of the observation layer); under 1.1.0 a listed phrase anywhere in the act's sentence was enough, which a sign-off review showed asserts use the text does not state. Acts, action codes, actors, dates and order are unchanged from 1.1.0; only the level-C rows differ. Model answers are the cached ones. All three splits had been scored before, so none is a first look; the rule was not tuned on held-out or confirm.

| Measure | coder_A | coder_B | resolved | resolved_2b |
|---|---:|---:|---:|---:|
| gold acts found (recall) | 0.963 (233/242) | 0.909 (220/242) | 0.773 (187/242) | 0.872 (211/242) |
| coded acts that are gold acts (precision) | 0.975 (233/239) | 0.853 (220/258) | 0.995 (187/188) | 0.995 (211/212) |
| action code | 0.957 (223/233) | 0.841 (185/220) | 0.957 (179/187) | 0.962 (203/211) |
| actor | 1.0 (233/233) | 0.991 (218/220) | 1.0 (187/187) | 1.0 (211/211) |
| legal standing | 1.0 (233/233) | 1.0 (220/220) | 1.0 (187/187) | 1.0 (211/211) |
| dates | 1.0 (117/117) | 1.0 (117/117) | 1.0 (108/108) | 1.0 (113/113) |
| order relations: correct against the documented order | 0.911 (41/45) | 0.875 (35/40) | 0.952 (20/21) | 0.973 (36/37) |
| order relations: reversed | 0 | 0 | 0 | 0 |
| order relations: not documented | 0 | 0 | 0 | 0 |
| gold sequence sentences recovered (stated order recall) | 0.506 (41/81) | 0.432 (35/81) | 0.247 (20/81) | 0.444 (36/81) |
| gold-ordered pairs also ordered, both acts coded | 0.722 (340/471) | 0.756 (329/435) | 0.757 (253/334) | 0.77 (314/408) |
| gold-ordered pairs also ordered, all | 0.695 (340/489) | 0.673 (329/489) | 0.517 (253/489) | 0.642 (314/489) |
| level C found (recall) | 0.963 (26/27) | 0.963 (26/27) | 0.958 (23/24) | 0.963 (26/27) |
| level C correct (precision) | 0.963 (26/27) | 0.963 (26/27) | 1.0 (23/23) | 0.963 (26/27) |
| harms found (recall) | 0.894 (42/47) | 0.636 (28/44) | 0.848 (28/33) | 0.886 (39/44) |
| harms correct (precision) | 1.0 (42/42) | 0.933 (28/30) | 1.0 (28/28) | 1.0 (39/39) |
| possible retellings linked | 0.0 (0/24) | 0.0 (0/24) | 0.583 (14/24) | 0.667 (16/24) |

Recall of the released coding by hard-case tag: advocacy 0.833 (5/6); allegation 0.889 (16/18); allegation_only 0.143 (1/7); explicit_order 0.696 (55/79); harm 0.702 (33/47); interrupted 0.75 (3/4); level_c 0.889 (24/27); mention_only 0.0 (0/10); no_level_c 0.826 (19/23); procedure 1.0 (40/40); response 0.667 (6/9); retelling 0.875 (21/24); undated 0.704 (38/54); undercover 0.6 (6/10).


### resolve-1.2.0, held-out cases (a second register, scored repeatedly while the coder was developed; not a blind set)

resolve-1.2.0: level C now needs the sentence to state the feature as the means (the stated-means rule of the observation layer); under 1.1.0 a listed phrase anywhere in the act's sentence was enough, which a sign-off review showed asserts use the text does not state. Acts, action codes, actors, dates and order are unchanged from 1.1.0; only the level-C rows differ. Model answers are the cached ones. All three splits had been scored before, so none is a first look; the rule was not tuned on held-out or confirm.

| Measure | coder_A | coder_B | resolved | resolved_2b |
|---|---:|---:|---:|---:|
| gold acts found (recall) | 0.934 (213/228) | 0.842 (192/228) | 0.671 (153/228) | 0.768 (175/228) |
| coded acts that are gold acts (precision) | 0.955 (213/223) | 0.869 (192/221) | 0.975 (153/157) | 0.978 (175/179) |
| action code | 0.93 (198/213) | 0.766 (147/192) | 0.915 (140/153) | 0.926 (162/175) |
| actor | 0.967 (206/213) | 0.964 (185/192) | 0.993 (152/153) | 0.989 (173/175) |
| legal standing | 1.0 (213/213) | 1.0 (192/192) | 1.0 (153/153) | 1.0 (175/175) |
| dates | 1.0 (119/119) | 1.0 (110/110) | 1.0 (106/106) | 1.0 (107/107) |
| order relations: correct against the documented order | 0.676 (23/34) | 0.733 (22/30) | 0.857 (6/7) | 0.733 (11/15) |
| order relations: reversed | 0 | 0 | 0 | 0 |
| order relations: not documented | 0 | 0 | 0 | 0 |
| gold sequence sentences recovered (stated order recall) | 0.299 (23/77) | 0.286 (22/77) | 0.078 (6/77) | 0.143 (11/77) |
| gold-ordered pairs also ordered, both acts coded | 0.746 (314/421) | 0.749 (269/359) | 0.804 (226/281) | 0.767 (240/313) |
| gold-ordered pairs also ordered, all | 0.667 (314/471) | 0.571 (269/471) | 0.48 (226/471) | 0.51 (240/471) |
| level C found (recall) | 0.931 (27/29) | 0.933 (28/30) | 0.926 (25/27) | 0.929 (26/28) |
| level C correct (precision) | 0.871 (27/31) | 0.875 (28/32) | 0.862 (25/29) | 0.867 (26/30) |
| harms found (recall) | 0.8 (32/40) | 0.444 (16/36) | 0.727 (16/22) | 0.786 (22/28) |
| harms correct (precision) | 0.97 (32/33) | 0.762 (16/21) | 1.0 (16/16) | 1.0 (22/22) |
| possible retellings linked | 0.0 (0/18) | 0.0 (0/18) | 0.556 (10/18) | 0.556 (10/18) |

Recall of the released coding by hard-case tag: advocacy 1.0 (3/3); allegation 0.867 (13/15); allegation_only 0.0 (0/7); explicit_order 0.417 (30/72); harm 0.55 (22/40); interrupted 0.5 (5/10); level_c 0.9 (27/30); mention_only 0.0 (0/6); no_level_c 0.8 (12/15); procedure 1.0 (40/40); response 0.125 (1/8); retelling 0.889 (16/18); undated 0.489 (22/45); undercover 0.52 (13/25).


## Agreement with reference coding of real cases

Cases `anchorage_pd_2022_006`, `doj_ceos_2025_026`, `ncis_2023_001`, `svicac_2022_009`, `texas_ag_2019_013` were coded earlier by two agent coders of a larger model (their agreed coding, not adjudicated). For each non-procedure act published here: did the reference code an act in the same sentence, and did it give the same action code there. The reference is another coding and does not code every act; this is agreement, not accuracy.

| Measure | Released | Candidate 2b |
|---|---:|---:|
| agreed: published acts | 37 |  |
| agreed: reference coded an act in the same sentence | 24 |  |
| agreed: reference gave the same action code there | 19 |  |
| reference acts | 115 |  |
| reference acts in a sentence the release also cites | 28 |  |

## Privacy

189 committed files checked against 248 deny-list terms (names from the case captions) and 6940 stored quotes; 982 platform names and feature words checked against the fixed lists they must come from: **0 hits**.

## Runtime

```json
{
 "llama3.2:3b": {
  "calls": 1111,
  "seconds_per_page": 42.7,
  "prompt_tokens": 1369,
  "prompt_seconds": 6.04,
  "output_tokens": 359,
  "output_seconds": 36.4,
  "output_tokens_per_second": 9.9
 },
 "qwen3:4b": {
  "calls": 1119,
  "seconds_per_page": 45.8,
  "prompt_tokens": 1383,
  "prompt_seconds": 3.45,
  "output_tokens": 361,
  "output_seconds": 41.9,
  "output_tokens_per_second": 8.6
 },
 "qwen3:8b": {
  "calls": 16,
  "seconds_per_page": 29.6,
  "prompt_tokens": 1130,
  "prompt_seconds": 2.83,
  "output_tokens": 277,
  "output_seconds": 26.4,
  "output_tokens_per_second": 10.5
 }
}
```

