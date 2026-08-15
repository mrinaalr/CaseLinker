# ADR 0006: Model attributed legal events without terminal-status collapse

- **Status:** Accepted for the proposal branch
- **Date:** 2026-08-15
- **Decision owners:** Proposal contributors; upstream adoption remains a maintainer decision

## Context

The legacy pattern layer searches an entire narrative for prosecution words and
stores the highest-precedence word as `booking_status`. This can silently assign
another person's conviction to the featured case, turn an earlier proceeding
into the current state, discard intervening events, and attach a publication or
nearby date to the wrong event.

Charges and indictments are allegations and procedural acts, not findings of
guilt. A trustworthy substrate must preserve that distinction in identifiers,
predicates, evidence, and downstream policy.

## Decision

Create one stable reported-event entity for every explicit, rule-supported
subject/event phrase. Emit separate `extracted` candidates:

- `party caselinker:reportedSubjectOf event`;
- `event caselinker:reportedLegalEventType procedural_type`;
- when directly grammar-bound, `event caselinker:reportedEventDate date`.

The procedural types remain distinct: arrest, charge, indictment, guilty plea,
conviction, and sentencing. No precedence rule collapses them into a terminal
status. “Reported” describes what the public source states; it does not make the
source statement an accepted fact or authorize publication.

Subject attribution requires a caller-supplied opaque party identity and one or
more explicit multiword aliases. The first rule set accepts tightly constrained
target-first forms and active forms with allowlisted institutional actors. It
does not resolve pronouns, carry a subject through coordination, or scan for an
unattributed status word.

A date is emitted only for `On <full date>, <event phrase>` or `<event phrase>
on <full date>`. A phrase carrying an invalid date or a date after the
extraction timestamp is rejected as an internally inconsistent candidate. The
date assertion cites both the event phrase and the exact date span.

Negated, expected, and intended forms are deliberately outside the patterns.
For example, “was not charged,” “is expected to be sentenced,” and “agreed to
plead guilty” produce no event candidate.

## Allegation and review semantics

An arrest, charge, or indictment event type records the procedural report only.
It never implies that the alleged conduct occurred. Guilty-plea and conviction
types are emitted only when those exact completed forms are attributed to the
known party. Every output remains unreviewed and numerically uncalibrated until
an independent review policy acts on it.

## Threats and controls

| Threat | Control |
|---|---|
| Another person's status contaminates the case | Explicit known-party alias in every match |
| Charge represented as guilt | Distinct procedural type identifiers and reported predicates |
| Historical events disappear behind “latest” status | One immutable event per explicit occurrence |
| Publication or hearing date becomes event date | Only immediate grammatical date binding |
| Negated or future-intent language becomes an event | Completed-form allowlist excludes those constructions |
| Partial extraction run leaves a broken event graph | One atomic ledger batch for all event assertions |
| Alias text becomes a stable identifier | Opaque party ID remains separate from display aliases |

## Compatibility and migration

This adapter is additive. It does not write `prosecution_outcomes`, backfill
legacy `booking_status`, or change existing graph output. A later resolver may
map reviewed event candidates to CAC legal phases, but lexical candidates are
not accepted CAC facts by default.

## Limitations

- The precision-first rules require explicit multiword aliases and omit
  pronouns, surnames alone, coordinated ellipsis, arbitrary active-voice actors,
  charge details, sentence duration, and uncertain dates.
- The synthetic golden set is a regression contract, not a corpus-wide accuracy
  estimate. Representative source-stratified adjudication is required before
  publishing precision or recall.
- Rule-based extraction cannot determine whether a public-source statement is
  legally current, later vacated, or factually correct. Resolution and review
  remain separate stages.

## Rollback and recovery

Disable the `LegalEventPipeline` caller. No legacy schema or data requires
reversal. Already appended candidates remain historical evidence and are
rejected or retracted through ledger lineage rather than deleted.
