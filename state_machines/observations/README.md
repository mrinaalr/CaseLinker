# Observations

What a court record names: the platforms and technological features stated in its text, each cited to its sentence. Read by rule from the pages, independent of the model coders and of which acts they agreed on.

**Contents:**
- [Three levels of evidence](#three-levels-of-evidence)
- [What is observed](#what-is-observed)
- [Supported relationships](#supported-relationships)
- [Dates](#dates)
- [Graph](#graph)
- [Queries](#queries)
- [Measured](#measured)
- [Limits](#limits)

## Three levels of evidence

```mermaid
flowchart LR
  pages["page text<br/>(local)"] --> obs["1. observation<br/>a platform is named,<br/>a feature phrase is stated"]
  pages --> acts["2. act<br/>both coders agree<br/>someone did this"]
  obs --> rel["3. supported relationship<br/>the act's own sentence<br/>states the means"]
  acts --> rel
```

| Level | Claim | Gate | Where |
|---|---|---|---|
| 1. Observation | The record mentions this platform or feature, here | The name or phrase is on a fixed list and on the page | [`observe.py`](observe.py), `:observations` graph |
| 2. Act | The record states someone did this | Two model coders agree on sentence, action and actor | [`coding/`](../coding/README.md), `:evidence` graph |
| 3. Supported relationship | The record states the act was done by means of it | The observation lies in the act's cited sentence, and that sentence states the means | [`observe.relate`](observe.py) |

A level is never promoted by proximity. A mention is not use. A platform name is not an affordance. Sharing a case, a page, a sentence or a date ties nothing together. A sparse graph is a correct graph: most observations stand alone.

## What is observed

```bash
python -m state_machines.observations.observe <case_id> --text-root local/pacer_text [--bundle <resolved bundle>]
python -m state_machines.coding.pipeline release <release_id> <case> [...] --observations
```

- **Platforms:** a service on the list of known services ([`enrich.PLATFORMS`](../coding/enrich.py)). A name that is also an ordinary word ("Signal", "Zoom", "Discord") counts only beside a service word ("on Signal", "a Discord server").
- **Features:** a phrase on the codebook's list per affordance class (`FEATURES` in [`observe.py`](observe.py)), matched as whole words. The phrase is recorded under the class the codebook lists it in; no affordance is asserted.
- **Every page except docket sheets.** Docket sheets record court business ("hearing held via Zoom").
- **Each observation holds:** document, page, the sentence's character span and hash, the page text hash, the document's legal standing, and the term's own span. No quote text, no free text.
- **Checked on every build** (`observe.check`): each span is re-read from the page and re-hashed, each name and phrase is on its list, and each relationship's act cites that sentence.

## Supported relationships

`relate` ties an observation to a published offender act only when both hold:

1. the observed term lies inside the sentence the act cites;
2. that sentence states the means.

| Kind | Construction | Relationship |
|---|---|---|
| Platform | "through / via / using / on / over the Kitebox application", "in a Kitebox group" | `Carried_Out_Through` |
| Platform | the same after "moved / continued / switched ... to" | `Moved_To` |
| Feature | "used / using / through / with the disappearing-message feature", or the feature is what the act made or sent ("created a new account under a false name", "posted ... in a group chat") | `Supports_Action` |

A negated sentence ("did not reply on Kitebox"), a platform that is only present ("had the Snapwire application installed") and a non-offender act give no relationship.

## Dates

Dates stated in an observation's sentence are kept in the observations file as `dates_in_sentence`: calendar bounds, with no claim about what the date refers to (the act, an account, the investigation, the filing). They are not written to the graph and never enter a timeline. Chronology comes only from the dated acts of level 2.

## Graph

No new vocabulary. An observation is a W3C Web Annotation, the pattern the evidence graph already uses for citations.

| Record | Graph |
|---|---|
| platform observation | `oa:Annotation`, `oa:motivatedBy oa:identifying`, `oa:hasBody` the platform (`uco-observable:ObservableObject`, the IRI the evidence graph uses) |
| feature observation | `oa:Annotation`, `oa:motivatedBy oa:classifying`, `oa:hasBody` the CAC affordance class, `clt:featureTerm` the phrase. The passage is classified; no individual of the class is created |
| source | `oa:SpecificResource` on the document, page `oa:FragmentSelector` refined by `oa:TextPositionSelector`; `clt:quoteSha256`, `clt:pageTextSha256`, `clt:sourceStatus` |
| rule | `clt:derivationRule "observe-1.0.0"` on every observation |
| supported relationship | the canonical relationship (`Carried_Out_Through`, `Moved_To`, `Supports_Action`) under the IRI the evidence graph would use, plus an evidence `oa:Annotation` on the observation's own target |

Graph IRI: `urn:caselinker:pacer:<case>:observations`. A case with nothing observed has no observation graph.

## Queries

[`queries.py`](queries.py) holds one query per level; each release's `REPORT.md` prints them with their results.

```bash
python -m state_machines.observations.queries pacer-v2
```

```sparql
PREFIX oa: <http://www.w3.org/ns/oa#>
PREFIX core: <https://ontology.unifiedcyberontology.org/uco/core/>
SELECT ?platform (COUNT(DISTINCT ?g) AS ?cases) (COUNT(?obs) AS ?mentions) WHERE {
  GRAPH ?g { ?obs oa:motivatedBy oa:identifying ; oa:hasBody ?p . ?p core:name ?platform }
} GROUP BY ?platform ORDER BY DESC(?cases)
```

## Measured

On the [synthetic benchmark](../benchmark/README.md) (`pipeline bench-observations --split <split> --record`). The rule was developed on dev; held-out and confirm were scored once after it was committed.

| Measure | Dev | Held-out | Confirm |
|---|---:|---:|---:|
| Gold platform mentions found | 71/71 | 63/63 | 71/71 |
| Gold feature statements found | 27/27 | 30/30 | 32/32 |
| Relationships the gold also holds | 67/68 | 67/74 | 33/33 |
| Relationships to a platform the gold says is only named | 0 | 0 | 0 |
| Gold relationships found, on published acts | 67/72 | 67/71 | 33/42 |

On the 30 real cases (`pacer-v2`): 594 observations (478 platform, 116 feature) in 22 cases naming a listed platform and 12 stating a feature phrase; 60 distinct case-platform pairs; 12 observations tied to a published act, in 9 cases.

## Limits

- **Listed terms only.** A service or a feature wording that is not on the lists is not observed. All benchmark splits keep platform names and feature terms verbatim, so the rates above measure finding listed terms in new sentence constructions, not recognising new wording.
- **Mentions are not validated one by one on real text.** A listed name on the page is a mention by definition; whether it concerns the offence is not decided. On the five reference cases the three listed platforms the reference coding names were all observed, and the reference names four platform surfaces that are not on the list.
- **"website" dominates the feature observations** (97 of 116). It is on the codebook's list for distribution infrastructure and is weak evidence on its own.
- **Relationships are few because acts are few.** A relationship needs a published act in that sentence, and the release publishes 152 offender acts.
- **Aliases are separate entries** ("Kik" and "Kik Messenger").
- **Not shown on `/lifecycle`.** The API payload carries a per-case `observed` summary; the page does not draw it yet.
