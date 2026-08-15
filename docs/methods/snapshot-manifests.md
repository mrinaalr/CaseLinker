# Snapshot manifests

Snapshot manifests bind an analytical result to the exact bytes required to
reproduce it. They are integrity records, not claims of scientific validity.

## Build the policy-safe example

```bash
uv run --locked python scripts/run/snapshot_manifest.py \
  build \
  --spec data/manifests/example.snapshot-spec.json \
  --output /tmp/caselinker-example.snapshot.json
```

The example deliberately uses synthetic content and records the model bundle as
`not_applicable`. Before building a real snapshot, replace the example
`code_revision` with the reviewed Git commit that corresponds to the included
code.

## Verify a snapshot

```bash
uv run --locked python scripts/run/snapshot_manifest.py \
  verify \
  --manifest /tmp/caselinker-example.snapshot.json
```

Verification fails if the canonical manifest payload was edited or if any
referenced file is missing, changed, or replaced by a symlink.

## Required component kinds

Every specification declares `corpus`, `source_versions`,
`accepted_assertions`, `code`, `extraction_rules`, `model_bundles`, `ontology`,
`shapes`, `query`, `parameters`, and `outputs`. An unused component must be
recorded as `not_applicable` with a reason; omission is an error.

## Limitations

- SHA-256 proves byte identity, not truth, review quality, or authorization.
- The current adapter reads local repository files. Immutable object-storage
  locators and signature verification belong in a later adapter.
- The manifest does not yet sign releases or attest the build environment.
- The JSON Schema describes the serialized contract; the builder additionally
  enforces cross-component completeness and filesystem safety rules.
