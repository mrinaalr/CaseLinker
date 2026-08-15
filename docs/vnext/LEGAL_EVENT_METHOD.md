# Reported Legal Event Extraction Method

- **Method family:** deterministic pattern
- **Rule version:** `1.0.0`
- **Output state:** `extracted`
- **Confidence:** unquantified

## Research outcome

Represent each explicitly attributed procedural event as an independently
citable reported-event node without treating allegations as guilt or reducing a
case history to one terminal status.

## Input and identity

The caller supplies the immutable normalized document version, stable extraction
run, and an `AttributedSubject` containing an opaque party ID plus explicit
multiword aliases. Text hashing fails closed. Event identity is derived from the
party, source version, exact event span, event type, rule variant, and rule
version; it remains stable across extraction runs. Assertion identity also
includes the run so retries are idempotent while distinct runs remain auditable.

Aliases are matching inputs, never entity identifiers. They are not written to
logs or assertion values by this adapter.

## Event grammar

The first rule set supports completed target-first constructions such as “was
charged,” “has been indicted,” “pled guilty,” and “was subsequently sentenced.”
It also supports a narrow active-voice actor allowlist such as “Police arrested
<alias>,” “A grand jury indicted <alias>,” and “The court sentenced <alias>.”

The rules do not cross line boundaries between subject and event. They exclude
negation, prediction, scheduling, intent, and bare legal-status words. They do
not infer a second event from “<alias> was arrested and was later charged”
because the second clause does not repeat the attributed subject.

## Date binding

Only a valid full Gregorian date in one of these forms is eligible:

- `On March 4, 2026, <event phrase>`;
- `<event phrase> on March 4, 2026`;
- the same two forms with ISO `2026-03-04`.

The date cannot be invalid or later than the UTC extraction time. If an
otherwise matching phrase carries such a date, the event itself fails closed;
the adapter does not hide the contradiction by emitting an undated event. A
date candidate cites two immutable evidence anchors: the attributed event
phrase and date text. Nearby publication, hearing, and narrative dates are not
associated.

## Output semantics

Each event produces a reported-subject relation and reported procedural type.
An eligible date adds a third assertion. Arrest, charge, indictment, guilty
plea, conviction, and sentencing remain separate types. All outputs are review
candidates; the adapter creates no review decision and performs no CAC phase
resolution.

## Evaluation boundary

The policy-safe golden set contains 12 expected events across ten adversarial
documents and requires exact ordered agreement with zero extra or missing
events. It tests three directly bound dates, invalid/future/nearby dates, subject
confusion, alias overlap, active and passive voice, negation, future intent,
coordination, token boundaries, and line boundaries. This is regression
evidence, not a representative accuracy measurement.

## Operations and rollback

The pipeline persists every assertion for one extraction request in a single
atomic batch. A retry of the same run returns `existing`; a write failure rolls
back the complete event graph. Disable the pipeline caller to roll back behavior
without deleting historical ledger records.
