# Claim CI method

## Pinning

After source verification, review, resolution, graph validation, snapshot binding,
cohort analysis, and claim review, call `ClaimExpectation.pin` with the exact Claim Card
and Evidence Pack. Commit the resulting expectation only after reviewing its human-
readable claim, numerator, denominator, unit, membership changes, limitations, snapshot,
query, shape profile, and provenance inputs.

The `expect_` identifier covers the canonical expectation content. Editing any expected
field requires a new identifier and therefore a visible review event.

## Evaluation

Regenerate the complete pipeline and call `ClaimCiEvaluator.evaluate`. A passing report
has an empty findings array. A failing report may contain multiple independent codes:

- `snapshot`, `query`, or `unit` for scope drift;
- `counts`, `numerator_membership`, or `denominator_membership` for result drift;
- `projections` or `shapes` for semantic-input drift;
- `limitations` for interpretation drift;
- `claim_id` or `claim_content_identity` for card drift;
- `evidence_pack_id` or `evidence_pack_content` for pack drift.

Equal counts do not excuse changed membership. A new valid result should be reviewed,
explained, and pinned as a new expectation rather than overwriting history.

## Operational boundary

Claim CI is a reproducibility and semantic-regression gate. Separate controls must still
verify source-file access, disclosure authorization, privacy shaping, cohort suitability,
statistical methods, and upstream permission to publish or release.
