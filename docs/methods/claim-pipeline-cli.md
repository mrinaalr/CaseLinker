# Claim pipeline CLI

## Pipeline specification

Create a v1 JSON specification containing repository-relative paths:

```json
{
  "schema_version": "1.0",
  "snapshot_manifest": "path/to/snapshot.json",
  "shapes": "path/to/legal-event-shapes.ttl",
  "query": "path/to/query.json",
  "projections": ["path/to/event-001.nt"]
}
```

The snapshot must list the shapes under `shapes`, the query under `query`, and every
projection under `outputs`. Run snapshot verification before interpreting any claim.

## Build

```text
python scripts/run/claim_pipeline.py --root . build \
  --spec path/to/pipeline.json --output path/to/evidence-pack.json
```

The output is the exact canonical Evidence Pack bytes. Repeated supported runs over the
same inputs must be byte-identical.

## Check

```text
python scripts/run/claim_pipeline.py --root . check \
  --spec path/to/pipeline.json --expectation path/to/expectation.json
```

Exit codes are `0` for exact agreement, `1` for a valid regenerated claim that differs
from the expectation, and `2` for invalid or unverifiable inputs. The JSON report on
standard output contains the closed Claim CI drift codes. Diagnostics go to standard
error and never include evidence text.

The CLI deliberately has no `--accept`, `--update-expectation`, or automatic pinning
flag. Review the scientific and governance implications of a change before creating a
new expectation through the typed API and normal code-review process.
