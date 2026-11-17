# Trajectory codebook v0.2.0 (proposed; pilot)

Codes live in [`vocab.py`](vocab.py); the [schema](schema/case_bundle.schema.json), [validator](validate.py) and [extension shapes](../ontology/extensions/caselinker-trajectory/0.2.0/) read them. Change both together and bump `CODEBOOK_VERSION`.

**Contents:**
- [Unit of coding](#unit-of-coding)
- [A. Actions](#a-actions)
- [B. Affordances: three levels](#b-affordances-three-levels)
- [C. Candidates](#c-candidate-affordances)
- [D. Access](#d-access)
- [E. Harm](#e-harm)
- [F. Time, order, branching](#f-time-order-branching)
- [G. Evidence and source status](#g-evidence-and-source-status)
- [H. Citation and verification](#h-citation-and-verification)
- [I. Double coding](#i-double-coding-and-adjudication)

## Unit of coding

An **event** is one documented act by one actor, supported by one or more passages.

**Split when:**
- the source gives separate dates or occasions (two meetings are two events);
- the actor changes;
- the action code changes.

**Merge only** when the source itself describes a continuous course of conduct. In that case, use `repetition.kind = continuous_period` or `repeated_count_*`.

**Never code from:**
- the June state machines;
- `_facts.txt`;
- the audit tables;
- press releases.

Code only from the PDF page text.

## A. Actions

The actor's role decides the family (rule T08). Only **offender** actions become trajectory steps. The other families stay events: they order, interrupt or contextualise steps.

### Offender actions (`offender`, `co_offender`)

**Access and targeting**

| Code | Definition |
|---|---|
| `SEEK_TARGETS` | Searches, browses or posts to find people to contact (incl. a public solicitation post) |
| `INITIATE_CONTACT` | First communication with a specific person documented in the record |
| `ACQUIRE_REPRESENTATION` | Obtains images of, or identifying information about, an identifiable person (profile, follower list, photos) |
| `ACQUIRE_MATERIAL` | Receives or downloads existing abuse material not produced in this case's conduct |

**Communication and influence**

| Code | Definition |
|---|---|
| `COMMUNICATE` | Sustained communication not better coded below (use sparingly) |
| `MISREPRESENT_IDENTITY` | False age, identity or persona *in the conversation* |
| `BUILD_RAPPORT` | Flattery, attention, gifts (non-monetary), emotional bonding the source describes |
| `OFFER_INDUCEMENT` | Money, goods or drugs offered for sexual conduct or imagery |
| `SEXUALIZE_COMMUNICATION` | Introduces sexual content into the communication |
| `SOLICIT_IMAGERY` | Requests sexual images or video |
| `DIRECT_CONDUCT` | Instructs specific sexual conduct, live or recorded |
| `THREATEN_EXPOSURE` | Threatens to distribute images or information |
| `THREATEN_HARM` | Threatens violence or other harm |
| `DIRECT_VICTIM_TO_RECRUIT` | Directs a victim to recruit others or to supply contacts |
| `MOVE_CHANNEL` | Directs communication onto another platform or medium (renaming a group is not a move) |
| `RECREATE_ACCOUNT` | Creates a new account after a block, ban or removal, to resume |
| `RECONTACT` | Resumes contact after a gap, refusal or block, on the same account |

**Production**

| Code | Definition |
|---|---|
| `RECEIVE_SELF_GENERATED` | Receives imagery the victim produced at the offender's request |
| `RECORD_LIVE_SESSION` | Captures a live session (e.g. screen recording) |
| `PRODUCE_IN_PERSON` | Records abuse in person |
| `SYNTHESIZE_OR_ALTER_IMAGERY` | Generates or manipulates imagery (AI, morphing, editing) |

**Possession and distribution**

| Code | Definition |
|---|---|
| `STORE_MATERIAL` | Retains material on a device or service. **The source must state retention**; seizure alone is not enough. |
| `ORGANIZE_MATERIAL` | Catalogues or sorts a collection |
| `DISTRIBUTE_MATERIAL` | Sends or shares material to others, including groups |
| `ADVERTISE_MATERIAL_OR_ACCESS` | Advertises availability of material or access |
| `EXPOSE_TO_VICTIM_NETWORK` | Sends a victim's images to the victim's own contacts |

**Coordination**

| Code | Definition |
|---|---|
| `ADMINISTER_SPACE` | Creates, runs or moderates a group, server or site |
| `GATEKEEP_MEMBERSHIP` | Vets, admits or removes members |
| `SET_RULES` | Posting rules, quotas, content requirements |
| `ASSIGN_ROLE` | Promotes, ranks |
| `COORDINATE_CO_OFFENDERS` | Plans or divides tasks with co-offenders |
| `SHARE_TRADECRAFT` | Detection-avoidance advice |
| `PAY_THIRD_PARTY` | Pays a facilitator or producer |

**In person and commercial**

| Code | Definition |
|---|---|
| `ARRANGE_MEETING` | Arranges an in-person meeting |
| `TRAVEL_TO_MEET` | Travels to an arranged meeting |
| `IN_PERSON_SEXUAL_ABUSE` | Hands-on sexual abuse |
| `ADVERTISE_COMMERCIAL_SEX` | Advertises a person for commercial sex |
| `ARRANGE_COMMERCIAL_SEX` | Booking, transport |
| `COLLECT_PROCEEDS` | Collects payment from commercial sex |
| `CONTROL_VICTIM` | Harbouring, confiscation, dependency, drugs, weapons used to control |

**Concealment**

| Code | Definition |
|---|---|
| `CONCEAL_OR_DESTROY_EVIDENCE` | Deletes data, discards devices |
| `EVADE_DETECTION` | Explicitly avoids detection |
| `OBSTRUCT_OR_TAMPER` | Witness tampering |
| `FLEE` | Flees |
| `OTHER_OFFENDER_ACTION` | Requires `other_action_label`; goes to adjudication |

### Responses (`victim`, `guardian`, `platform`, `third_party`)

| Code | Definition |
|---|---|
| `RESP_REFUSE` | Declines a request |
| `RESP_BLOCK` | Blocks the account |
| `RESP_REPORT` | Reports to a platform, guardian or police |
| `RESP_DISCLOSE` | Tells someone |
| `RESP_PLATFORM_ENFORCE` | Account removed or banned by the platform |

Compliance is not an event. It is the outcome of the offender's action.

### Law enforcement (`law_enforcement`, `undercover`)

`LE_RECEIVE_TIP`, `LE_UNDERCOVER_ENGAGE`, `LE_SURVEIL`, `LE_LEGAL_PROCESS`, `LE_SEARCH_SEIZE`, `LE_FORENSIC_EXAM`, `LE_INTERVIEW`, `LE_INTERDICT`, `LE_ARREST`.

**An undercover officer's messages are `LE_UNDERCOVER_ENGAGE`, never offender conduct.** The offender's messages *to* the officer are offender actions with `target_refs` pointing at the `UC` actor.

### Procedure (`court`)

`PROC_CHARGE`, `PROC_PLEA`, `PROC_VERDICT`, `PROC_SENTENCE`, `PROC_OTHER`. These are time anchors only.

### Outcome

| Value | Meaning |
|---|---|
| `completed` | The action was carried out |
| `attempted_not_completed` | Attempted, e.g. against an undercover officer, or a meeting that did not happen |
| `refused` | The target declined |
| `blocked` | The target or platform blocked it |
| `interrupted` | Stopped by another party |
| `unknown` | The source does not say |

## B. Affordances: three levels

**Status: codebook 0.2.0, proposed. Awaits author review**, including the relevance table R and the capability registry.

O holds the six classes of AfH §7. Each maps to the CAC 3.1.0 class of the same meaning (`cac-platforms:*`, all subclasses of `PlatformAffordance`). Affordances are recorded at three levels, and they never merge:

| Level | What it says | Evidence | Where it lives | In O_i? |
|---|---|---|---|---|
| **A. Available** | The platform provided the capability during the period | Cited public platform documentation (help pages, archived product pages). Not the court record. | [`capabilities/platform_capabilities.json`](capabilities/platform_capabilities.json): platform-level, with `valid_from`/`valid_to`, sources and review status | no |
| **B. Action-relevant** | A documented action was carried out *through* that platform, and the capability is relevant to that kind of action | Derived: a `platform_interactions` entry (court record) × registry entry valid at the event's time × R(action) | Derived step fields `action_relevant_affordances`, with the registry entries they rest on | no |
| **C. Instrumental** | The court record supports that the capability was *used* to carry out the action | Coded per event, with passage and status (rule B0) | Event `affordances` | **yes** |

### Coding the court record

- **`platform_mentions`**: the platform is named in connection with the event. This makes no claim that the act went through it. Example: "the phone contained Kik".
- **`platform_interactions`**: the passage supports that the act was carried out through the platform. Example: "sent the images to the minor through Kik". It needs a passage on facet `platform` (rule T15). In the graph this is canonical `uco-action:instrument` plus a cited `Carried_Out_Through` relationship.
- **`affordances` (level C)**: the passage names the feature or mechanism and links it to the act. Example: "using a Kik account under a false name to conceal his identity".

**Rule B0. A platform name is never level C.** A level-C annotation needs `basis = feature_stated` or `mechanism_stated`:
- `DIRECT` needs a passage that names the feature or mechanism and links it to the action (facet `feature`).
- `INFERRED` needs a named feature or mechanism whose link to this action is interpretive.

A platform name, and a documented interaction, are level A/B material.

### Worked example: Kik (illustrative only; registry entries are proposed until reviewed)

| Court record says | Mention | Interaction | Level A (if the registry has a reviewed entry for the period) | Level B | Level C / O_i |
|---|---|---|---|---|---|
| Kik is named, but no act through it | yes | — | — (no step-level levels without an interaction) | — | — |
| Messages were sent through Kik | — | yes | e.g. pseudonymous accounts, private messaging | `unmonitored_communication` (R(COMMUNICATE)) | ∅ |
| A Kik account under a false name was used to hide identity | — | yes | as above | as above | `anonymity` |

Messaging through a service that offers pseudonymous accounts does not, by itself, show that anonymity was exploited. R(action) therefore lists anonymity only for identity-bearing actions (`MISREPRESENT_IDENTITY`, `RECREATE_ACCOUNT`, `EVADE_DETECTION`).

### Relevance table R(action) (`vocab.ACTION_RELEVANCE`, proposed)

| Action | Relevant classes |
|---|---|
| Communication and production-over-channel actions (`COMMUNICATE`, `BUILD_RAPPORT`, `SOLICIT_IMAGERY`, `DIRECT_CONDUCT`, `THREATEN_*`, `RECEIVE_SELF_GENERATED`, `RECORD_LIVE_SESSION`, `ARRANGE_*`, `RECONTACT`, …) | `unmonitored_communication`, `ephemerality` |
| `SEEK_TARGETS` | `contact_discovery` |
| `ACQUIRE_REPRESENTATION` | `contact_discovery` |
| `INITIATE_CONTACT` | `contact_discovery`, `unmonitored_communication` |
| Identity-bearing actions (`MISREPRESENT_IDENTITY`, `RECREATE_ACCOUNT`, `EVADE_DETECTION`) | `anonymity` |
| Movement of material (`DISTRIBUTE_MATERIAL`, `ACQUIRE_MATERIAL`, `EXPOSE_TO_VICTIM_NETWORK`) | `distribution_infrastructure` |
| Advertising (`ADVERTISE_MATERIAL_OR_ACCESS`, `ADVERTISE_COMMERCIAL_SEX`) | `distribution_infrastructure`, `contact_discovery` |
| Running a space (`ADMINISTER_SPACE`, `GATEKEEP_MEMBERSHIP`, `SET_RULES`) | `distribution_infrastructure` |
| `SYNTHESIZE_OR_ALTER_IMAGERY` | `generative_synthesis` |
| `CONCEAL_OR_DESTROY_EVIDENCE` | `ephemerality` |
| In-person, storage and payment actions | none |

### Period checks

A capability counts for an event only if its validity period overlaps the event's cited date interval:

| Check result | Meaning | Reported? |
|---|---|---|
| `in_period` | The event lies wholly inside the period | yes |
| `period_partial` | The two intervals partly overlap | yes |
| `period_unchecked` | The event is undated | yes |
| disjoint | The intervals do not overlap | left out |

Only `reviewed` registry entries enter released outputs.

### Level-C inclusion criteria

| Class | Include when the source states | Exclude |
|---|---|---|
| `anonymity` | Action done under an identity not linked to the person, *enabled by the technology*: pseudonymous or new accounts, fake profiles, Tor, burner numbers | Lying about age in a chat (that is `MISREPRESENT_IDENTITY`, with no level C unless account-level concealment is stated) |
| `ephemerality` | Content designed to disappear or expire (disappearing/view-once/expiring messages), or the victim's stated belief on that basis | Retention, screenshots, a platform name alone |
| `contact_discovery` | A feature surfaced or located the contact: search, recommendations, public groups or posts, listings or ads, follower lists, location features | Handing over a phone number (`MOVE_CHANNEL`) |
| `unmonitored_communication` | A private, direct or encrypted channel the source describes as private, or as hidden from guardians or the platform | A channel in general; a group chat for distribution (use `distribution_infrastructure`) |
| `distribution_infrastructure` | A capability that moved or hosted material to third parties or for retrieval: groups, links, cloud, P2P, sites, upload | One-to-one transfer to the offender (that is the solicited transfer itself) |
| `generative_synthesis` | AI generation, morphing or manipulation of imagery is stated | — |

When the counterpart is an undercover officer, set `counterparty_is_undercover = true`. The channel's affordance is coded as the offender used it, and analyses can exclude these.

## C. Candidate affordances

`persistent_storage` and `multi_party_coordination` are coded in `candidate_affordances`, never in O. They use the same basis and status rules as O.

**Promotion criteria** (decided after the 30 cases, by codebook version bump):
1. DIRECT evidence in at least 3 cases and 2 offense families.
2. Coders could not code the same support with an existing O class without loss: `would_otherwise_map_to` disagreement or `null`.
3. A distinct mitigation follows from it.

## D. Access

Access forms follow AfH H2: `person_physical`, `person_communicative`, `representation` (identifying images or information) and `material` (existing content). Each has its own status. **Never infer access from a harm.**

## E. Harm

| Code | H0 | Code only when the source documents |
|---|---|---|
| `HARM_IN_PERSON_SEXUAL_ABUSE` | h1 | Hands-on abuse |
| `HARM_COERCED_SELF_GENERATED_IMAGERY` | h2 | The victim produced imagery at the offender's request or under threat |
| `HARM_PRODUCTION_IN_PERSON_RECORDED` | — | Abuse recorded in person |
| `HARM_DISTRIBUTION_RECIRCULATION` | h3 | The victim's material was shared or circulated |
| `HARM_EXPOSURE_THREAT` | h4 | A threat to expose (sextortion) |
| `HARM_EXPOSURE_REALIZED` | h3 | Images were sent to the victim's contacts |
| `HARM_COMMERCIAL_SEXUAL_EXPLOITATION` | h5 | Commercial sex |
| `HARM_SYNTHETIC_LIKENESS` | h6 | A real child's likeness was synthesised |
| `HARM_SEXUALIZED_CONTACT_ONLINE` | — | Sexual messages or exposure to the child, without imagery |
| `HARM_PSYCHOLOGICAL_DISTRESS_DOCUMENTED` | — | The source states fear, distress or self-harm statements. Category only; no detail. |
| `HARM_PHYSICAL_VIOLENCE_OR_CONTROL` | — | Violence, weapons, confinement |
| `HARM_OTHER` | — | Needs `other_label` |

- "—" means outside H0. These feed the closure test; they are never forced into h1–h6.
- **No harm is coded against an undercover persona.**
- Harm stated only in a sentencing memorandum carries `ADVOCACY` source status, through its passage.

## F. Time, order, branching

- **Time** is an interval (`earliest`, `latest`) with a precision and a basis, plus supporting passages.
- **Relations:**

  | Relation | Meaning |
  |---|---|
  | `BEFORE` | Known to precede. Nothing is implied about what lies between. |
  | `MEETS` | Immediately precedes; only with explicit sequence language ("then", "within a day", "immediately") |
  | `OVERLAPS`, `DURING`, `SAME_TIME` | Interval relations |
  | `UNORDERED` | Assessed, and the order is unknown |
  | `REPEATS`, `RESUMES_AFTER`, `RESPONDS_TO`, `BACKED_BY_THREAT`, `INTERRUPTS`, `PART_OF`, `SAME_MATERIAL` | As named |

- **Do not add order you cannot cite.** Two events with no supported relation stay unordered. Derivation then puts them in different chains.
- **Cycles in `BEFORE` are errors** (T11). Model a resumption or loop as a *new event* linked by `RESUMES_AFTER` / `REPEATS`.
- **Tracks** group events per victim, per undercover persona, per material set, or per co-offender network. A case may have many tracks. An event may sit in several.
- **Phases** are never coded. If an analysis wants phase labels, it derives them by rule from action codes, outside the evidence layer.

## G. Evidence and source status

**Assertion status** (every event, relation, affordance, access and harm, separately):

| Status | Meaning |
|---|---|
| `DIRECT` | The cited passage states it |
| `INFERRED` | A plausible reading of the passage; not stated |
| `UNSUPPORTED` | No adequate passage found. Recorded so the absence is visible. |
| `CONTRADICTED` | The source conflicts with it |

There is no `SYNTHETIC` status. Nothing introduced for modelling enters the evidence layer.

**Source status** (per passage) is the legal standing of the passage's claim, defaulting from the document type:
- indictment/information → `ALLEGATION`
- complaint → `SWORN_AFFIDAVIT`
- statement of offense or facts, factual basis, proffer → `ADMITTED`
- plea transcript → `ADMITTED_UNDER_OATH`
- findings of fact → `JUDICIAL_FINDING`
- judgment → `COURT_RECORD`
- sentencing memo or trial brief → `ADVOCACY`
- docket → `PROCEDURAL`

**An allegation stays an allegation when the case ends in conviction** (T06). `VERDICT_ELEMENT` is allowed only on a judgment passage, with a reason, for the elements of a count of conviction.

**Coder review status** (`single_coder`, `agreed`, `adjudicated`, `disputed`) records agreement between coders. It is never the court's adjudication.

## H. Citation and verification

- **Every support names a passage:** document, 1-based PDF page, character offsets into the *normalized* page text, and the SHA-256 of the quote and of the page text.
- **Quote text lives only in the local store** (`local/pacer_text/<case>/quotes.json`). Bundles and graphs carry hashes.
- **Normalization:** NFKC, straight quotes, soft hyphens removed, whitespace collapsed, case kept (`evidence.normalize`).
- **Verified** means the validator re-derived the quote from the page text (T04).
  - On an OCR page, the page image must also have been checked (`image_checked`, T05).
  - Struck-through or handwritten text is noted in `limitations`, and is never quoted as the document's content.
- **No identifiers in coder-written text:** no names, initials, handles, phone numbers, emails or addresses (T14; the deny list comes from the case caption, kept locally).

## I. Double coding and adjudication

- **Two coders code each case independently,** blind to each other and to the June artifacts. Each records `coding.method`: `human`, `agent_assisted` or `agent`. Agent coders are disclosed as agents and are never described as independent human reviewers.
- **Agreement:**
  - event matching by passage overlap → precision, recall and F1;
  - action code κ on matched events;
  - per-class affordance κ and Jaccard on O_i;
  - harm κ;
  - order agreement on matched pairs.
- **Adjudication** produces the adjudicated bundle. Each disagreement gets a decision and a note (`review.status = adjudicated`).
