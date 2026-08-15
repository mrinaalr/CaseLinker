# ADR 0008: Policy-gated deterministic CAC graph projection

- **Status:** Accepted for the proposal branch
- **Date:** 2026-08-15
- **Decision owners:** Proposal contributors; upstream retains release authority

## Outcome

Turn a coherently reviewed legal-event resolution into byte-reproducible RDF that
uses CAC Ontology identifiers and fails a pinned SHACL projection contract before
it can enter research artifacts.

## Invariant

Graph projection is not a new fact-acceptance step. It may represent only a complete
bundle of `resolved`, affirmed assertions that passes the live research-publication
eligibility policy. Projection does not confer disclosure authorization, access
permission, or permission to publish identifying information.

## Decision

Introduce an independent vNext graph adapter with these boundaries:

1. It accepts exactly one resolved subject/event/type bundle, with an optional date.
2. Every assertion must pass the live eligibility policy at projection time.
3. All members share the same extraction inputs, review decisions, resolution run,
   method version, and code revision.
4. CAC class mappings are conservative. The exact procedural distinction remains in
   `cl:legalEventType` even where the available CAC class is broader.
5. Output is sorted canonical N-Triples with a SHA-256 identity. Input order cannot
   alter bytes or digest.
6. Each event links to the resolved assertion IRIs that generated it. Full candidate,
   review, evidence-span, and document lineage remains authoritative in the assertion
   ledger.
7. The graph names its projection profile. SHACL shapes are pinned inside this
   repository and injected into the validator. Each result binds both the projection
   digest and canonical shapes digest. Validation performs no network fetch and no
   sibling-repository lookup.

The adapter is deliberately separate from `ontology/features_to_cac.py`. That legacy
pipeline maps mutable case dictionaries and currently relies on broken symlinks to an
adjacent CAC Ontology checkout. Replacing it silently would mix two evidence models.

## Threats and controls

| Threat | Control |
|---|---|
| A superseded review remains in an old resolution | Live eligibility rejects it before projection |
| Assertions from different events or runs are combined | Exact bundle, lineage, subject, and method checks |
| Serialization order changes an artifact hash | Lexically sorted N-Triples and a golden digest |
| A partial graph appears valid | Pinned SHACL cardinality and datatype constraints |
| A broad CAC class obscures the procedural claim | Exact allowlisted `cl:legalEventType` retained |
| Validation unexpectedly reaches external resources | Injected local shapes; inference and advanced rules disabled |
| Research eligibility is mistaken for public release approval | API names and documentation state it is only a necessary research gate |

## Acceptance evidence

- Byte-identical output for every permutation of the same bundle.
- A pinned golden profile, digest, triple count, and assertion set.
- SHACL success for the valid fixture and failure after removing the subject link.
- Rejection of stale reviews, duplicate assertions, partial bundles, mixed methods,
  cross-event subjects/dates, and unmapped event types.

## Compatibility and migration

No existing graph, endpoint, database table, or legacy mapper changes. The new profile
is opt-in and uses `/resource/vnext/` IRIs to prevent accidental collision with legacy
artifacts. No data migration is required.

## Recovery and rollback

Disable callers of `CacLegalEventProjector`; resolved assertions remain intact in the
ledger. Generated RDF is disposable and can be regenerated. Reverting this adapter
does not alter source documents, reviews, resolutions, or legacy graph outputs.

## Limitations

- This profile validates the CaseLinker projection contract, not the entirety of the
  CAC Ontology release.
- It covers explicit legal events only; platform and offense projections remain out of
  scope.
- It does not provide de-identification, disclosure review, access control, cohort
  sufficiency, or statistical claim approval.
