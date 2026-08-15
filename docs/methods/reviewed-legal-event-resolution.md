# Reviewed legal-event resolution

## Purpose

Convert one coherently reviewed reported-event candidate bundle into immutable
canonical assertions without losing source, extraction, or human-decision
lineage.

## Required bundle

The resolver requires exactly one `caselinker:reportedSubjectOf` candidate and
one `caselinker:reportedLegalEventType` candidate. It permits one
`caselinker:reportedEventDate` candidate. Every candidate must:

- be in the `extracted` state with affirmed polarity;
- have a current `accepted` `ReviewDecision`;
- originate from the same extraction run and code revision;
- identify the same stable event entity;
- satisfy exact event/date evidence-span coherence.

The caller may provide candidates in any order. The resolver orders them by
semantic role before computing identity and lineage.

## Outputs

The canonical predicates are:

- `caselinker:subjectOfLegalEvent`;
- `caselinker:legalEventType`;
- optional `caselinker:eventDate`.

All outputs use `resolved` state, an unquantified resolution-confidence
dimension, and the `reported_legal_event_bundle` resolution method. Each output
cites every input assertion ID and every exact authorizing review-decision ID.
No direct evidence is copied; source spans remain reachable through input
assertions.

Resolution run identity makes an exact retry idempotent. A distinct run creates
a distinct, auditable resolution rather than overwriting history.

## Live eligibility

The research-publication gate requires `resolved` state, complete assertion and
review lineage, and a cited review decision that is still the current accepted
head for each input. A superseded or rejected review makes the resolution
ineligible without deleting it.

This gate does not authorize disclosure, shape public fields, or grant access.
Those controls remain mandatory downstream.

## Failure and recovery

Partial bundles, extra predicates, duplicate candidates, mixed extraction runs,
event-identity mismatches, span mismatches, and non-accepted reviews fail before
any resolution write. The SQLite repository writes the complete output bundle
atomically. Rollback disables the service caller and retains append-only audit
history.
