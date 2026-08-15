# Draft pull request package

## Suggested title

`draft: propose an auditable vNext research provenance pipeline`

## Suggested body

> **Draft for architectural review; not a release request.**
>
> This proposes a selectively adoptable vNext research path on top of upstream commit
> `9da0a4ff8b45df03fed073a9af5c00d22aab0d9d`. It intentionally does not claim the
> upstream `v3.0.0` designation. Architecture, merge strategy, naming, release timing,
> and publication remain entirely with the CaseLinker maintainer.
>
> The path preserves source identity and evidence spans through append-only review,
> coherent legal-event resolution, deterministic CAC-aligned RDF, pinned SHACL,
> explicit-unit cohort analysis, Claim Cards, Evidence Packs, Claim CI, and a strict
> repository-bound CLI. It is additive and does not replace the legacy database,
> graph, API, UI, or pipeline.
>
> The branch is larger than an ideal review unit. I recommend reviewing and, if useful,
> restacking it as the seven independent stages in
> `docs/vnext/ADOPTION_PLAN.md`. The machine-verifiable commit/file/ADR/migration map is
> `docs/vnext/traceability.v1.json`; the consolidated safety analysis is
> `docs/vnext/THREAT_MODEL.md`.
>
> Important boundaries: research eligibility is not disclosure authorization or
> access control; reported legal events are not findings of guilt; cohort results are
> counts of explicit legal-event resources in a selected snapshot, not prevalence,
> causal effect, platform risk, or counts of people/cases/documents. The CLI never
> approves an expectation automatically.
>
> No deployment, release tag, corpus publication, or database migration has been
> performed by this proposal.

## Maintainer questions

1. Is immutable assertion/review lineage a useful foundation for CaseLinker's research
   workflow, independent of the later graph and claim layers?
2. Do the legal-event subject, procedural-status, and date-binding semantics match the
   project's intended evidentiary standard?
3. Should CAC projection remain a separate adapter, or eventually replace a legacy
   mapper after a dedicated compatibility study?
4. Which disclosure authority and reviewer identity model should surround the
   deliberately narrower research-eligibility policy?
5. Would the maintainer prefer the seven-stage stack, a smaller proof-of-concept subset,
   or design review before any code PR?

## Reviewer checklist

- [ ] Review ADRs and non-goals before implementation details.
- [ ] Confirm upstream baseline and the seven milestones with the traceability checker.
- [ ] Review all three additive SQLite migrations and recovery posture.
- [ ] Challenge subject attribution, negation, allegation, event-date, and stale-review
      tests with representative edge cases.
- [ ] Review CAC mappings and the scope of the pinned SHACL profile.
- [ ] Confirm unit, denominator, generated wording, and mandatory limitations.
- [ ] Confirm disclosure and access control remain external mandatory gates.
- [ ] Run the locked quality, test, smoke, dependency-audit, and security-scan commands.
