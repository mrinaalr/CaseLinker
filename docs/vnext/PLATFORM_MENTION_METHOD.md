# Platform Mention Extraction Method

- **Method family:** deterministic pattern
- **Rule version:** `1.0.0`
- **Output predicate:** `caselinker:platformMentioned`
- **Output state:** `extracted`

## Research outcome

Create auditable candidates showing exactly where an allowlisted platform name
appears in a normalized public document, without claiming that the platform was
used or connected to alleged conduct.

## Input contract

The caller supplies an opaque subject, an immutable `SourceDocumentVersion`, the
normalized text for that exact version, and stable run metadata. Extraction
fails closed if the SHA-256 digest of the supplied text differs from the version
record. Timestamps must be UTC.

## Rule policy

Rules recognize a precision-first subset of the legacy vocabulary: Facebook
Messenger, Facebook, Instagram, Snapchat, TikTok, Twitter/X web domains,
WhatsApp, Telegram, Discord, YouTube Live, and YouTube. The bare token `X` and
generic surfaces are excluded. Word boundaries reject partial forms such as
“Instagrammer,” “discordant,” and “YouTubers.”

Rules are evaluated without hidden network, filesystem, database, or clock
access. Compound matches take precedence over overlapping base matches. Every
non-overlapping occurrence is retained in source order.

## Evidence and uncertainty

Each candidate binds to the normalized-text hash, exact character offsets, and
span hash. Confidence is explicitly unquantified: the adapter has not been
calibrated on a representative corpus, so it does not emit a numerical score.
No candidate is automatically accepted.

`affirmed` describes the mention proposition only. Surrounding negation must not
be reinterpreted as an affirmed use claim.

## Evaluation boundary

The synthetic, policy-safe golden set contains 11 expected mentions across five
documents and requires exact ordered agreement: zero missing candidates, zero
extra candidates, and valid hashes for every span. This set is a regression
contract, not evidence of corpus-wide precision or recall. Broader evaluation
requires an independently adjudicated, source-stratified sample before the rule
set can support analytical claims.

## Compatibility and operations

The adapter is additive and does not write legacy case dictionaries. It can be
disabled by removing its caller. If a rule changes, increment its version;
never revise the meaning of an existing rule version in place.
