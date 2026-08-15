## Outcome

<!-- What user or research capability becomes possible? -->

## Preserved invariant

<!-- What evidence, safety, compatibility, or reproducibility property must remain true? -->

## Design and evidence semantics

<!-- Describe boundaries, assertion states, provenance, units, and alternatives considered. -->

## Threat analysis

<!-- Consider data exposure, misuse, authorization, model egress, provenance corruption, and misleading claims. -->

## Verification

<!-- List exact commands, fixtures, results, and any manual checks. -->

## Compatibility and migration

<!-- Name affected APIs, schemas, artifacts, consumers, and migration/recovery behavior. -->

## Rollback

<!-- Explain how to disable or reverse this safely. -->

## Limitations

<!-- State what this change does not establish. -->

## Checklist

- [ ] Tests fail without the change and pass with it, or the rationale is documented.
- [ ] Evidence states and provenance remain explicit.
- [ ] No model-generated value is promoted directly to canonical fact.
- [ ] Public outputs use policy-shaped allowlists.
- [ ] No secrets, source PDFs, victim-identifying data, or unapproved artifacts are committed.
- [ ] Documentation, migration, telemetry, and recovery behavior are updated.
- [ ] The locked environment and required quality gates pass.
- [ ] This change does not claim an official CaseLinker release designation.
