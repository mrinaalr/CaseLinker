# ADR 0005: Separate platform mentions from platform-use claims

- **Status:** Accepted for the proposal branch
- **Date:** 2026-08-15
- **Decision owners:** Proposal contributors; upstream adoption remains a maintainer decision

## Context

The legacy pattern layer populates `platforms_used` when a configured platform
name appears anywhere in case text. A name can instead occur in a denial,
footnote, comparison, source boilerplate, or discussion of evidence that was not
attributed to the featured matter. Treating lexical presence as use silently
strengthens the source and can contaminate platform-level analysis.

The vNext assertion ledger can preserve a narrower observation without losing
the evidence needed for later interpretation.

## Decision

The first deterministic adapter emits only
`caselinker:platformMentioned(subject, platform)` candidates in the `extracted`
state. Each occurrence has its own assertion and exact character span. It uses a
small, versioned allowlist of unambiguous names and aliases. Specific compound
names win over overlapping base names.

The assertion polarity is `affirmed` even in a sentence such as “did not
identify Snapchat,” because the asserted proposition is that the document
mentions the name—not that Snapchat was identified or used.

The adapter does not:

- populate or backfill legacy `platforms_used`;
- infer platform use, investigative relevance, affordances, harm, prevalence,
  or causation;
- accept its own candidates or create review decisions;
- recognize generic terms such as “online,” “chat,” “social media,” or bare “X.”

Candidate identity includes the source version, span, rule and rule version,
subject, value, and extraction run. A retry with the same run metadata is
idempotent; a distinct run creates distinct provenance.

## Consequences

Downstream consumers must adopt an explicit resolution policy before converting
mentions into stronger relations. Precision is favored over recall in this
milestone. Repeated mentions remain visible rather than being collapsed, so a
resolver can inspect all supporting and contradictory context.

The legacy application remains compatible because the adapter is additive and
has no hidden I/O.

## Acceptance evidence

The versioned golden set covers compound-name overlap, aliases, casing,
repetition, negated surrounding language, partial tokens, ambiguous “X,” and an
empty document. Tests verify exact-span hashes, state and method separation,
unquantified confidence, idempotence, and rejection of mismatched source text.

## Rollback and recovery

Disable callers of `PlatformMentionExtractor`; no legacy table or API changes
need reversal. Assertions already appended to a ledger remain historical
candidates and may be rejected or retracted through normal lineage rather than
deleted.
