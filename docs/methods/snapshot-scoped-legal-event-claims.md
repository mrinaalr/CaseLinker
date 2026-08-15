# Snapshot-scoped legal-event claim method

## Required inputs

- A snapshot manifest whose identity and referenced files have passed
  `verify_manifest`.
- One or more legal-event graph projections included by that snapshot.
- A conforming SHACL result bound to each projection digest.
- One allowlisted event type query with a stable `qry_` identifier.

After file-level `verify_manifest` succeeds, construct the analysis reference with
`SnapshotReference.from_manifest`. It independently verifies the manifest's canonical
identity and extracts the included output digests; it does not replace file verification.

## Counting rule

The analytical unit is a distinct vNext legal-event IRI. The denominator is the complete
set of supplied, valid event IRIs. The numerator is the subset whose exact
`cl:legalEventType` equals the query value. Event IDs and projection hashes are sorted;
input ordering has no effect. A repeated event IRI is an error because silent
deduplication could conceal an upstream join defect. Every projection digest must be
listed among the bound snapshot's output artifacts; a conforming graph from another
snapshot is still rejected.

Zero matches are reported as `0 of N`. An empty denominator is not a claim and fails.
The core result stores no floating-point fraction, percent, confidence interval, risk
ratio, or prevalence estimate.

## Claim card

The statement template is:

> Within snapshot `{snapshot_id}`, `{numerator}` of `{denominator}` distinct eligible
> legal-event units were classified as `{event_type_label}` events.

The card also contains the exact unit, snapshot manifest digest, query digest, complete
membership lists, projection digests, shapes digest, and mandatory limitations. Its
`claim_` identifier is the SHA-256 digest of that canonical content.

## Evidence Pack

The `epack_` artifact is canonical JSON containing the claim card and an inventory of
its snapshot, query, projection, and shape digests. It excludes evidence text, personal
display labels, and any representation of disclosure approval. Its identifier is the
SHA-256 digest of the exact bytes.

To audit a pack, verify its content hash, resolve and verify the snapshot manifest,
re-run graph projection and SHACL validation, re-run the cohort query, and compare the
claim and pack identities. A current access and disclosure policy remains independently
required before showing any referenced material.
