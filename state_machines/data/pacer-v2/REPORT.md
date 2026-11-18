# Run report: pacer-v2

Review mode **machine**: two local models coded every case independently; a fixed rule published what both coded. Nothing here is human-adjudicated. Reliability is agreement between the coders on these cases; benchmark accuracy is measured on synthetic records ([benchmark](../../benchmark/README.md)). Neither is accuracy on these cases.

## What is published

| Content | Count |
|---|---:|
| acts | 258 |
| acts with a cited date | 133 |
| acts: law_enforcement | 13 |
| acts: offender | 152 |
| acts: procedure | 90 |
| acts: response | 3 |
| cases | 30 |
| cases with offender acts | 24 |
| harms recorded: victim minor | 15 |
| harms recorded: victim unknown | 1 |
| level-C affordances (feature stated in the sentence) | 4 |
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

| Case | Published | Events | Relations | Coder A acts | Coder B acts | Matched | Action κ | SHACL |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `anchorage_pd_2022_004` | yes | 6 | 0 | 108 | 214 | 52 | 0.168 | fails |
| `anchorage_pd_2022_006` | yes | 15 | 0 | 166 | 407 | 64 | 0.273 | fails |
| `doj_ceos_2025_004` | yes | 1 | 0 | 14 | 107 | 3 | 0.25 | partial |
| `doj_ceos_2025_014` | yes | 6 | 0 | 50 | 163 | 20 | 0.223 | partial |
| `doj_ceos_2025_023` | yes | 10 | 0 | 45 | 164 | 30 | 0.333 | fails |
| `doj_ceos_2025_025` | yes | 2 | 0 | 25 | 118 | 10 | 0.241 | fails |
| `doj_ceos_2025_031` | yes | 13 | 0 | 125 | 217 | 49 | 0.181 | fails |
| `doj_ceos_2026_003` | yes | 1 | 0 | 112 | 411 | 19 | 0.339 | partial |
| `doj_ceos_2026_007` | yes | 1 | 0 | 20 | 189 | 5 | 0.348 | partial |
| `doj_ceos_2026_008` | yes | 4 | 0 | 46 | 244 | 17 | 0.356 | fails |
| `doj_ceos_2026_012` | yes | 9 | 0 | 16 | 142 | 10 | 0.462 | fails |
| `enterprise` | yes | 5 | 0 | 81 | 173 | 27 | 0.346 | fails |
| `enticement` | yes | 15 | 0 | 32 | 27 | 21 | 0.439 | fails |
| `external_extortion` | yes | 1 | 0 | 22 | 99 | 15 | 0.227 | fails |
| `ky_sp_2025_038` | yes | 2 | 0 | 65 | 123 | 32 | 0.186 | fails |
| `ncis_2022_002` | yes | 4 | 0 | 22 | 152 | 15 | 0.207 | fails |
| `ncis_2023_001` | yes | 5 | 0 | 58 | 85 | 17 | 0.224 | fails |
| `ncmec_2022_586` | yes | 19 | 0 | 92 | 185 | 43 | 0.465 | fails |
| `ncmec_2023_190` | yes | 5 | 0 | 53 | 123 | 22 | 0.268 | fails |
| `ncmec_2023_224` | yes | 1 | 0 | 14 | 66 | 1 | None | partial |
| `ncmec_2025_1116` | yes | 1 | 0 | 18 | 100 | 4 | 0.2 | fails |
| `production` | yes | 32 | 0 | 146 | 105 | 56 | 0.446 | fails |
| `sextortion` | yes | 27 | 0 | 302 | 348 | 100 | 0.323 | fails |
| `svicac_2022_009` | yes | 19 | 0 | 58 | 92 | 15 | 0.534 | fails |
| `texas_ag_2019_013` | yes | 14 | 0 | 29 | 117 | 7 | 0.829 | fails |
| `trafficking` | yes | 11 | 0 | 180 | 354 | 87 | 0.201 | fails |
| `usss_2017_006` | yes | 13 | 0 | 99 | 85 | 38 | 0.294 | fails |
| `usss_2021_019` | yes | 7 | 0 | 88 | 178 | 32 | 0.354 | fails |
| `usss_2023_004` | yes | 3 | 0 | 43 | 126 | 21 | 0.255 | fails |
| `wy_dci_2023_005` | yes | 6 | 0 | 7 | 113 | 3 | 0.143 | partial |

## Coverage and drops

| Measure | Count |
|---|---:|
| coder_A acts dropped: procedure act repeating a dated anchor | 240 |
| coder_A acts dropped: procedure act without a stated date | 2729 |
| coder_A acts dropped: quote not located on the page | 980 |
| coder_A acts proposed: docket parser | 84 |
| coder_A acts proposed: model | 6085 |
| coder_A acts proposed: skipped: judgment form page | 0 |
| coder_A pages: docket parser | 201 |
| coder_A pages: model | 766 |
| coder_A pages: skipped: judgment form page | 60 |
| coder_B acts dropped: procedure act repeating a dated anchor | 6 |
| coder_B acts dropped: procedure act without a stated date | 543 |
| coder_B acts dropped: quote not located on the page | 1605 |
| coder_B acts proposed: docket parser | 84 |
| coder_B acts proposed: model | 7181 |
| coder_B acts proposed: skipped: first coder found no act | 0 |
| coder_B acts proposed: skipped: judgment form page | 0 |
| coder_B pages: docket parser | 201 |
| coder_B pages: model | 758 |
| coder_B pages: skipped: first coder found no act | 8 |
| coder_B pages: skipped: judgment form page | 60 |

## Reliability on the real cases

```json
{
 "cases": 30,
 "events_coder_A": 2136,
 "events_coder_B": 5027,
 "matched": 835,
 "mean_event_f1": 0.226,
 "pooled_action_agreement": {
  "exact": 291,
  "of": 835
 },
 "mean_action_kappa": 0.314,
 "note": "agreement on acts the models coded; the docket parser's acts are excluded"
}
```

## What the records name (observation layer)

Read by rule from every page except docket sheets, independent of the coders. An observation says a listed platform is named or a codebook feature phrase is stated in a cited sentence. It does not say anyone used it. A relationship exists only where a published act's own sentence states the means.

| Content | Count |
|---|---:|
| cases | 30 |
| observations | 497 |
| platform observations | 478 |
| feature observations | 19 |
| cases naming at least one listed platform | 22 |
| cases stating at least one feature phrase | 10 |
| distinct case-platform pairs | 59 |
| observations tied to a published act by a stated means | 10 |
| cases with at least one such relationship | 7 |
| observations in documents with standing ADVOCACY | 82 |
| observations in documents with standing ALLEGATION | 200 |
| observations in documents with standing COURT_RECORD | 19 |
| observations in documents with standing ADMITTED | 149 |
| observations in documents with standing SWORN_AFFIDAVIT | 47 |

**Not yet reviewed on the real text.** A stratified local packet (`python -m state_machines.observations.validation packet`) covers every relationship, every feature observation and a sample of platform observations; its score is printed here once a reviewer has answered it.

On the reference cases (another coding, not truth): cases 5; listed platforms the reference coding names 3; of which observed 3; platform surfaces in the reference that are not on the list 4; listed platforms observed 3.

### Level 1. Which platforms do the records name, in how many cases?

```sparql
PREFIX oa: <http://www.w3.org/ns/oa#>
PREFIX core: <https://ontology.unifiedcyberontology.org/uco/core/>
PREFIX action: <https://ontology.unifiedcyberontology.org/uco/action/>
PREFIX clt: <https://w3id.org/caselinker/trajectory#>
SELECT ?platform (COUNT(DISTINCT ?g) AS ?cases) (COUNT(?obs) AS ?mentions) WHERE {
  GRAPH ?g { ?obs oa:motivatedBy oa:identifying ; oa:hasBody ?p . ?p core:name ?platform }
} GROUP BY ?platform ORDER BY DESC(?cases) DESC(?mentions) ?platform
```

| platform | cases | mentions |
|---|---|---|
| Facebook | 10 | 29 |
| Snapchat | 9 | 154 |
| Instagram | 7 | 98 |
| Kik | 6 | 49 |
| Grindr | 3 | 22 |
| Omegle | 3 | 3 |
| Facebook Messenger | 2 | 39 |
| Dropbox | 2 | 38 |
| Google Drive | 2 | 3 |
| WhatsApp | 2 | 3 |
| TikTok | 2 | 2 |
| Wickr | 2 | 2 |
| YouTube | 2 | 2 |
| FaceTime | 1 | 12 |
| Skype | 1 | 8 |
| Discord | 1 | 7 |
| Telegram | 1 | 4 |
| Tumblr | 1 | 1 |
| Twitter | 1 | 1 |
| iCloud | 1 | 1 |

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
| Anonymity | VPN | 1 | 1 |
| Anonymity | burner phone | 1 | 1 |
| ContactDiscovery | public group | 1 | 1 |
| DistributionInfrastructure | uploaded | 5 | 5 |
| DistributionInfrastructure | cloud storage | 3 | 3 |
| Ephemerality | self-destructing | 1 | 1 |
| UnmonitoredCommunication | encrypted | 2 | 4 |
| UnmonitoredCommunication | private messages | 2 | 3 |

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
| DISTRIBUTE_MATERIAL | 11 | 35 |
| PROC_PLEA | 10 | 31 |
| PROC_CHARGE | 11 | 26 |
| PROC_SENTENCE | 12 | 24 |
| DIRECT_CONDUCT | 7 | 14 |
| LE_ARREST | 8 | 11 |
| SOLICIT_IMAGERY | 8 | 11 |
| ACQUIRE_MATERIAL | 5 | 9 |
| COMMUNICATE | 4 | 9 |
| PROC_VERDICT | 8 | 9 |
| THREATEN_EXPOSURE | 5 | 9 |
| TRAVEL_TO_MEET | 6 | 9 |
| INITIATE_CONTACT | 5 | 7 |
| IN_PERSON_SEXUAL_ABUSE | 4 | 5 |
| OFFER_INDUCEMENT | 3 | 5 |
| RECORD_LIVE_SESSION | 2 | 5 |
| SEEK_TARGETS | 4 | 5 |
| ADMINISTER_SPACE | 1 | 4 |
| RECEIVE_SELF_GENERATED | 4 | 4 |
| ACQUIRE_REPRESENTATION | 2 | 3 |
| ARRANGE_MEETING | 2 | 3 |
| STORE_MATERIAL | 3 | 3 |
| EVADE_DETECTION | 1 | 2 |
| LE_RECEIVE_TIP | 2 | 2 |
| PAY_THIRD_PARTY | 1 | 2 |
| RESP_BLOCK | 1 | 2 |
| CONCEAL_OR_DESTROY_EVIDENCE | 1 | 1 |
| FLEE | 1 | 1 |
| MISREPRESENT_IDENTITY | 1 | 1 |
| PRODUCE_IN_PERSON | 1 | 1 |
| RECONTACT | 1 | 1 |
| RECREATE_ACCOUNT | 1 | 1 |
| RESP_REPORT | 1 | 1 |
| SET_RULES | 1 | 1 |
| THREATEN_HARM | 1 | 1 |

### Level 3. Where does a record state that an act was done by means of a platform or feature?

```sparql
PREFIX oa: <http://www.w3.org/ns/oa#>
PREFIX core: <https://ontology.unifiedcyberontology.org/uco/core/>
PREFIX action: <https://ontology.unifiedcyberontology.org/uco/action/>
PREFIX clt: <https://w3id.org/caselinker/trajectory#>
SELECT DISTINCT ?case ?action ?relationship ?what ?phrase ?standing WHERE {
  GRAPH ?og { ?obs oa:motivatedBy ?m ; oa:hasTarget ?span ; oa:hasBody ?body ; clt:sourceStatus ?standing .
              ?evidence oa:hasTarget ?span ; oa:hasBody ?rel . FILTER(?evidence != ?obs)
              OPTIONAL { ?obs clt:featureTerm ?phrase } OPTIONAL { ?body core:name ?name } }
  GRAPH ?rg { ?rel core:kindOfRelationship ?relationship ; core:source ?s ; core:target ?t }
  GRAPH ?eg { ?act clt:actionCode ?action } FILTER(?act IN (?s, ?t)) FILTER(STRENDS(STR(?eg), ":evidence"))
  FILTER(?body IN (?s, ?t) || BOUND(?phrase))
  BIND(COALESCE(?name, REPLACE(STR(?body), "^.*#", "")) AS ?what)
  BIND(REPLACE(REPLACE(STR(?og), "^urn:caselinker:pacer:", ""), ":observations$", "") AS ?case)
} ORDER BY ?case ?action ?what
```

| case | action | relationship | platform_or_class | phrase | standing |
|---|---|---|---|---|---|
| anchorage_pd_2022_006 | DISTRIBUTE_MATERIAL | Carried_Out_Through | Snapchat |  | ADVOCACY |
| enticement | SOLICIT_IMAGERY | Carried_Out_Through | Snapchat |  | ADMITTED |
| ky_sp_2025_038 | DISTRIBUTE_MATERIAL | Carried_Out_Through | Facebook Messenger |  | ADMITTED |
| ncmec_2022_586 | INITIATE_CONTACT | Carried_Out_Through | Snapchat |  | ADMITTED |
| ncmec_2023_190 | DIRECT_CONDUCT | Carried_Out_Through | Snapchat |  | ADMITTED |
| production | ACQUIRE_MATERIAL | Carried_Out_Through | Instagram |  | ADMITTED |
| production | INITIATE_CONTACT | Carried_Out_Through | Instagram |  | ADMITTED |
| sextortion | INITIATE_CONTACT | Carried_Out_Through | Instagram |  | ALLEGATION |
| sextortion | STORE_MATERIAL | Carried_Out_Through | Dropbox |  | ALLEGATION |

## Accuracy on the synthetic benchmark

Scores per rule version and split. `resolved` is what a machine release publishes; `resolved_2b` is the candidate cue rule, not released. Synthetic pages are cleaner than real filings: none of this is accuracy on the real cases.

### Observation layer (observe-1.2.0)

Platform names and feature terms are kept verbatim in every split, so these rates measure finding listed terms in new sentence constructions, not recognising unlisted wording.

| Measure | development cases | held-out cases | confirmation cases |
|---|---:|---:|---:|
| gold platform mentions found | 1.0 (71/71) | 1.0 (63/63) | 1.0 (71/71) |
| gold feature statements found | 1.0 (27/27) | 1.0 (30/30) | 1.0 (32/32) |
| observed platforms the gold names in that sentence | 0.973 (71/73) | 0.926 (63/68) | 0.947 (71/75) |
| observed feature phrases the gold codes as an affordance there | 0.973 (36/37) | 0.905 (38/42) | 0.947 (36/38) |
| relationships that the gold also holds | 0.985 (65/66) | 0.903 (65/72) | 0.97 (32/33) |
| relationships to the right platform, wrong kind | 1 | 0 | 1 |
| relationships to a platform the gold says is only named | 0 | 0 | 0 |
| relationships on an act that is not a gold act | 0 | 3 | 0 |
| gold relationships found, on published acts | 0.903 (65/72) | 0.915 (65/71) | 0.762 (32/42) |
| observations outside gold act sentences (not judged) | 20 | 20 | 20 |

### resolve-1.0.0, held-out cases

Frozen baseline: rules resolve-1.0.0, held-out cases scored once, before any later rule was written.

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


### resolve-1.1.0, confirmation cases (wording written without sight of the rules; scored once)

Scored once, after the rules were frozen and committed. Wording written without sight of the rules.

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


### resolve-1.1.0, held-out cases

Second look: these cases were scored once under resolve-1.0.0 before the 1.1.0 rules were written; no rule was tuned on them.

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


## Agreement with reference coding of real cases

Cases `anchorage_pd_2022_006`, `enticement`, `ncis_2023_001`, `svicac_2022_009`, `texas_ag_2019_013` were coded earlier by two agent coders of a larger model (their agreed coding, not adjudicated). For each non-procedure act published here: did the reference code an act in the same sentence, and did it give the same action code there. The reference is another coding and does not code every act; this is agreement, not accuracy.

| Measure | Released | Candidate 2b |
|---|---:|---:|
| agreed: published acts | 32 | 32 |
| agreed: reference coded an act in the same sentence | 24 | 24 |
| agreed: reference gave the same action code there | 19 | 19 |
| reference acts | 115 | 115 |
| reference acts in a sentence the release also cites | 28 | 39 |
| settled: published acts | 0 | 12 |
| settled: reference coded an act in the same sentence | 0 | 11 |
| settled: reference gave the same action code there | 0 | 7 |

## Privacy

186 committed files checked against 248 deny-list terms (names from the case captions) and 5693 stored quotes; 510 platform names and feature words checked against the fixed lists they must come from: **0 hits**.

## Runtime

```json
{
 "llama3.2:3b": {
  "calls": 991,
  "seconds_per_page": 30.0,
  "prompt_tokens": 1357,
  "prompt_seconds": 2.5,
  "output_tokens": 351,
  "output_seconds": 27.3,
  "output_tokens_per_second": 12.9
 },
 "qwen3:4b": {
  "calls": 999,
  "seconds_per_page": 46.1,
  "prompt_tokens": 1371,
  "prompt_seconds": 3.38,
  "output_tokens": 356,
  "output_seconds": 42.3,
  "output_tokens_per_second": 8.4
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

