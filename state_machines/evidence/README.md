# Evidence

The canonical record of a case: what the court documents say happened, who took part in what role, when, and on which page. A coded **bundle** (JSON Schema 2.0, [`schema/case_bundle.schema.json`](schema/case_bundle.schema.json)) holds one case. Codes are defined in the [codebook](CODEBOOK.md); how to code a case is in the [coder guide](CODER_GUIDE.md).

**Contents:**
- [What a bundle holds](#what-a-bundle-holds)
- [Participants and roles](#participants-and-roles)
- [Time](#time)
- [Relations and identity](#relations-and-identity)
- [Two kinds of status](#two-kinds-of-status)
- [Validation](#validation)
- [Migrating older bundles](#migrating-older-bundles)

## What a bundle holds

| Part | Contents |
|---|---|
| `documents` | Each court document: type, SHA-256, page count, and per page the text method and the hash of its normalized text |
| `passages` | Locators into page text: document, page, character offsets, quote hash, legal standing, verification. Quote text stays in the local store (`local/pacer_text/`), never in the bundle |
| `participants` | Role-neutral P1, P2, … with kind and sourced legal status |
| `events` | One per source observation: action, actor, co-actors, targets, outcome, dated assertions, affordances, harms, access, platform mentions and interactions, channels, supporting passages |
| `relations` | Typed links between events, each with a basis, a status and passages |
| `tracks` | Groupings of events per victim, undercover persona, body of material, co-offender network or case procedure |

Every claim cites at least one passage, with a facet (`action`, `actor`, `target`, `time`, `platform`, `feature`, …) and its own status.

## Participants and roles

A participant is the same person, persona or group across the case. What they did is recorded on each event:

| Field | Meaning |
|---|---|
| `actor` | Who performed the act, and in which role (`offender`, `co_offender`, `victim`, `undercover`, `law_enforcement`, …) |
| `co_actors` | Others who took part: `assisting`, or `directing` (instructed the act) |
| `targets` | Whom the act was directed at: `victim`, `recipient`, `counterparty`, `subject` |
| `unresolved_participants` | Someone the record ties to the event whose role is not decided yet; blocks release |
| `legal_status` (on the participant) | Charged defendant, uncharged co-conspirator, named victim, …, each with its own passage |

The same participant can be a co-offender in one event and a victim in another. A role is never carried from one event to the next. A **collective** ("at least ten members of the group") is its own participant kind, with sourced membership and a count stated as exact, at least, at most, approximate or unknown.

Harms record the victim and their kind (`minor`, `adult`, `undercover_persona`, `unknown`). The AfH harm set $\mathcal H_{0}$ counts minor-directed harms; adult-directed harms stay in the data under their own kind.

## Time

Each event keeps every dated assertion the record makes about it:

| Field | Meaning |
|---|---|
| `expression` | The date as the source states it |
| `earliest`, `latest` | Calendar bounds (`2024-02` becomes 2024-02-01 to 2024-02-29) |
| `precision` | `day`, `month`, `season`, `year`, `range` |
| `basis` | `explicit_date`, `date_range`, `count_window`, `enclosing_window`, `relative_statement` |
| `status` | DIRECT or INFERRED |

A date taken from an enclosing count or conspiracy window is an `enclosing_window` constraint and is INFERRED. When two assertions contradict each other, both are kept and `conflict_flagged` is set; that event contributes no date order. Relative statements ("two days later") are relations, not dates.

## Relations and identity

| Type | Use |
|---|---|
| `BEFORE` | Known to come earlier |
| `MEETS` | Immediately before, only with explicit sequence language |
| `OVERLAPS`, `DURING`, `SAME_TIME`, `UNORDERED` | Interval relations, and an assessed lack of order |
| `INTERRUPTS`, `RESPONDS_TO`, `RESUMES_AFTER`, `REPEATS`, `PART_OF`, `BACKED_BY_THREAT`, `SAME_MATERIAL` | As named |
| `SAME_ACT` | Two observations may describe one act |

`SAME_ACT` is INFERRED (possible) or records a rejected candidate. It never merges events, orders them or changes a count. Confirmed identity is one event citing every passage.

A relation's `basis` says where the order comes from: `explicit_sequence_language`, `dated_events`, `count_windows`, `document_structure`, `coder_inference`.

## Two kinds of status

| Status | Question | Values |
|---|---|---|
| Assertion status | Does the cited passage support this claim? | DIRECT, INFERRED, UNSUPPORTED, CONTRADICTED |
| Legal standing (per passage) | What is the passage's claim, legally? | allegation (indictment), sworn affidavit (complaint), admitted (statement of facts, plea), admitted under oath (plea transcript), judicial finding, verdict element, court record, advocacy (sentencing memo), procedural (docket) |

An allegation stays an allegation when the case ends in a conviction. Coder review status (`single_coder`, `agreed`, `adjudicated`, `disputed`) is a third, separate field.

## Validation

[`validate.py`](validate.py) returns findings with a code and a severity; a bundle is valid when no finding is an error.

| Code | Rule |
|---|---|
| T01 | Schema |
| T02 | Unique ids |
| T03 | Every reference resolves |
| T04, T05 | Every passage re-derives from the page text; OCR pages need the page image checked |
| T06 | A passage's standing is one its document type can carry; a change needs a reason |
| T07 | Event status is backed by its action passage |
| T08 | The actor's role in the event fits the action family |
| T09 | Instrumental affordances need a named feature or mechanism |
| T10 | Harms name a victim target of the event, never an undercover persona |
| T11, T16 | No order cycle, including through cited dates |
| T12 | A coded BEFORE is not contradicted by every dated assertion |
| T13 | Real calendar dates; enclosing windows INFERRED; contradictions flagged |
| T14 | No names, initials, handles, phone numbers or emails in coded text |
| T15 | A platform interaction cites a passage on the platform |
| T17 | Participants, collectives and roles are consistent |
| T18 | `SAME_ACT` is never DIRECT; an ordered pair warns |
| T19 | Telephony, email and mail are channels, not platforms |

`release_errors()` adds the release gate: no errors, verified passages, no undecided role, and a review state that fits the mode. In `adjudicated` mode every event and relation is adjudicated; in `machine` mode every event is one both model coders agreed on (`review.status = agreed`), and the release is labelled machine-coded, never adjudicated.

## Migrating older bundles

```bash
python -m state_machines.evidence.migrate old.json new.json
```

[`migrate.py`](migrate.py) converts a schema 1.x bundle mechanically. It records the old actor refs in each participant's description, never infers legal status, and lists what needs a person: legal status, roles that may differ by event, collectives, dates that may come from an enclosing window, platform interactions, and co-actors whose role must be decided.
