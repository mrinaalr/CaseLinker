# caselinker-trajectory (`clt:`)

CaseLinker's own extension vocabulary for the PACER graphs: 2 classes and 43 properties, version 0.3.0, namespace `https://w3id.org/caselinker/trajectory#`. It is experimental and is never presented as CASE, UCO or CAC.

The graphs bind to existing vocabulary first. `clt:` carries only what those vocabularies cannot say. This page records, per group of terms, what was checked and whether the term stays.

**Contents:**
- [What existing vocabulary carries](#what-existing-vocabulary-carries)
- [Why each local term exists](#why-each-local-term-exists)
- [Candidates for an existing term](#candidates-for-an-existing-term)
- [Existing trajectory vocabularies](#existing-trajectory-vocabularies)

## What existing vocabulary carries

| Need | Term |
|---|---|
| case, documents, hashes | `case-investigation:Investigation`, `uco-observable:ObservableObject`, `uco-types:Hash` |
| acts, performers, instruments | `uco-action:Action`, `uco-action:performer`, `uco-action:instrument` |
| participants | `uco-identity:Person`, `uco-identity:Identity`, `uco-identity:Organization` |
| any relation between two things | `uco-core:Relationship` with `uco-core:kindOfRelationship` |
| trajectories | `uco-action:ActionLifecycle`, `uco-action:ArrayOfAction` |
| affordance classes | `cac-platforms:Anonymity`, `Ephemerality`, `ContactDiscovery`, `UnmonitoredCommunication`, `DistributionInfrastructure`, `GenerativeSynthesis` |
| citations and observations | W3C Web Annotation: `oa:Annotation`, `oa:SpecificResource`, `oa:FragmentSelector`, `oa:TextPositionSelector`, `oa:motivatedBy` |

The observation layer added no new `clt:` term (it reuses `clt:featureTerm`, `clt:sourceStatus` and the other evidence properties): placeholder-labelled services and generic service descriptions are W3C Web Annotations (`oa:identifying`, `oa:describing` with an `oa:TextualBody`).

## Why each local term exists

Read against the vendored UCO 1.5.0, CASE 1.5.0, CAC 3.1.0 and W3C OA files in [`ontology/vendor/`](../../vendor/). This is a reading of those files, not a formal alignment.

| Terms | What they carry | Closest existing term | Why it does not fit |
|---|---|---|---|
| `assertionStatus`, `supportFacet` | Whether the cited passage supports this exact claim, and which part of it | `uco-core:confidence` (ConfidenceFacet) | A 0–100 confidence in an object. Not a categorical statement of what a passage supports |
| `sourceStatus` | Legal standing of the passage: allegation, admission, finding | none found | UCO and CAC model investigations, not the procedural standing of a statement |
| `reviewStatus`, `verificationStatus` | Coder agreement; whether the quote was re-derived from the page | none found | Process metadata of this pipeline |
| `TimeAssertion`, `timeAssertion`, `timeEarliest`, `timeLatest`, `timePrecision`, `timeBasis`, `timeExpression`, `timeConflict` | Partial dates ("June 2022"), several dated statements per act, conflicts kept | `uco-action:startTime`, `endTime` | `xsd:dateTime` only, one value: cannot hold a month, or two conflicting statements with their sources |
| `Collective`, `countMin`, `countMax`, `countStated` | A group the source describes collectively, with an uncertain count | `uco-identity:Organization`, `Identity` | An Organization is people working together in an organized way; an Identity is one individual or organization |
| `legalStatus` | Sourced legal status of a participant, apart from event roles | `cac-core:Role` | A role in conduct, not a procedural status |
| `actionCode`, `harmCode`, `h0Category` | Codes from the codebook's action and harm schemes | CAC conduct classes | CAC covers some of these acts as classes, not the codebook's 64 action codes or its harm codes |
| `affordanceBasis`, `featureTerm`, `featureSetting` | What the record states for a level-C affordance, and the feature phrase | none found | CAC defines the affordance classes, not the evidence for one |
| `interactionMode`, `audience`, `channel` | Through, from, to or acted on; one-to-one, group or public; SMS, phone, email | `uco-action:instrument` | Says an instrument was used, not how or to what audience |
| `stepIndex`, `immediateAfterPrevious`, `stepAffordance`, `stepRelevantAffordance`, `stepAvailableAffordance`, `affordanceThreshold`, `derivationRule`, `capabilityEntry`, `capabilityConfidence`, `availability`, `trackKind` | The derived trajectory view and the three affordance levels | `uco-action:phase` | An ordered array of actions with no place for a step's evidence threshold, rule version or affordance levels |
| `victimKind` | Minor, adult, undercover persona, unknown | none found | Needed to count minor-directed harms |

## Candidates for an existing term

Terms whose meaning an existing term may cover. The decision for these releases is to keep them: each change would alter every published graph, and a wrong mapping is worse than a local term.

| Term | Candidate | Open question |
|---|---|---|
| `quoteSha256`, `pageTextSha256` | `uco-types:Hash` | UCO attaches hashes to observable objects through a facet; a quoted passage is not modelled as an observable |
| `eventRole`, `participationMode` | `uco-role:Role`, `cac-core:Role` | UCO roles are objects of their own; here a role belongs to one event and is cited |
| `outcome` | `uco-action:actionStatus` | UCO's statuses cover completed and failed, not refused, blocked or interrupted |
| `participantKind` | `rdf:type` | Repeats the node's class; may be dropped |
| `derivationRule` | `prov:wasGeneratedBy` | PROV-O is not vendored or validated here |
| `actionCode` and the other code properties | a SKOS concept scheme | SKOS is not vendored; codes would become IRIs |
| `featureTerm` on an observation | `oa:TextualBody` | Kept so a phrase reads the same on an observation and on a level-C relationship |

## Existing trajectory vocabularies

Two existing vocabularies model offence trajectories. The decision for these releases is not to use them, for the reasons below. Both are the first place to look before any new trajectory term.

| Vocabulary | What it models | Fit | Blocker |
|---|---|---|---|
| CASE-UCO SDK `ext.trajectories` (`traj:State`, `Transition`, `Trajectory`, `PhaseAssertion`, `StateMachineModel`, `TransitionEstimate`) | A subject occupying a state or phase over an interval; transitions between states; an estimated state machine with transition probabilities | Could carry the derived view (`stepIndex` and the other step terms) and is the natural home for the [theory](../../../state_machines/theory/README.md) layer's transition systems | Its namespace is `http://example.org/ontology/trajectories`, a placeholder, in SDK 1.34.0; it is not vendored or validated here; and it orders phase assertions, while the record gives dated acts with no phases |
| CAC 3.1.0 `cac-platforms:AffordanceMisuse` (`affordanceClass`, `enablesTransitionFrom`, `enablesTransitionTo`, `platform`) | An affordance on a trajectory edge, enabling the transition from one `cac-core:Phase` to another | The closest existing term to a level-3 feature relationship | It states that the affordance *enabled* a phase transition. The record supports "the act was done by means of this feature"; enablement and phases are claims of the model, not of the source |

The evidence terms that make up most of `clt:` (assertion status, legal standing, partial dates, codes) are outside both.

**Why the SDK extension is not used here.** It was contributed from this project (CASE-UCO-SDK PRs 104 and 135) and shipped in SDK v1.31.0 with status `candidate`.

- **An act is not a state.** A `traj:Trajectory` orders `traj:PhaseAssertion`s, each saying a subject occupied a `traj:State`. The record gives dated acts. Classifying an act by its codebook group does not show that anyone occupied a state, or that a transition happened. The extension keeps the same line itself: `traj:enactsAction` points from a model-level transition to a separate observed action. The PACER graphs therefore publish acts and their documented partial order, and no states.
- **The namespace is a placeholder.** The SDK keeps `http://example.org/ontology/trajectories/` until the CASE community agrees an IRI. A test here refuses `example.org` IRIs in published graphs, and it stays strict.
- **Where it fits.** The [theory](../../../state_machines/theory/README.md) layer's transition systems are state machines, and `traj:State`, `Transition` and `StateMachineModel` describe them. That is a model of what is feasible, kept apart from what the records document.
