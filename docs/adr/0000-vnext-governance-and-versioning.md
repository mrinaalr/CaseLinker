# ADR 0000: vNext governance and versioning

- **Status:** Accepted for proposal work
- **Date:** 2026-08-15
- **Decision owners:** Proposal contributors; upstream adoption remains an
  upstream maintainer decision
- **Upstream baseline:** `9da0a4ff8b45df03fed073a9af5c00d22aab0d9d`

## Context

The proposal is intended to reach production-grade completeness while
preserving the original maintainer's authority over CaseLinker's roadmap and
official `v3.0.0` release. Calling the fork `2.8.9` would look like an official
predecessor inserted into upstream's version sequence. Calling it `v3.0.0`
would pre-empt the upstream release decision.

## Decision

1. The architecture target is described as **CaseLinker vNext** or a
   **proposed v3 architecture**.
2. Git branches use the `proposal/` namespace.
3. Optional development checkpoints use `proposal-0.x.y` identifiers.
4. The workspace metadata version is `0.0.0` and is explicitly non-product
   metadata.
5. No official-looking CaseLinker release tag is created from the proposal.
6. The fork retains the MIT license, upstream history, copyright, and a clear
   upstream remote.
7. Upstream alone decides whether the work becomes CaseLinker 3.0, in whole or
   in part.

## Consequences

- The implementation can be engineered against v3-level requirements without
  implying authority over upstream naming.
- Proposal checkpoint identifiers cannot be mistaken for CaseLinker releases.
- Documentation must consistently distinguish architectural target, proposal
  maturity, and official upstream version.
- If upstream adopts the work, release metadata is assigned during the upstream
  integration process rather than migrated from a fork-owned product version.

## Rejected alternatives

- **`2.8.9`:** falsely suggests an authorized position in upstream's release
  sequence and creates compatibility expectations that do not exist.
- **`3.0.0-alpha`:** still claims the upstream major-version namespace.
- **A renamed competing product:** weakens provenance and collaboration, and is
  contrary to the purpose of the contribution.
