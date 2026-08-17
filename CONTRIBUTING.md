# Contributing to the vNext proposal

This branch is a respectful proposal for possible upstream adoption. Read
[`AGENTS.md`](AGENTS.md) and the
[`ENGINEERING_CHARTER.md`](docs/vnext/ENGINEERING_CHARTER.md) before beginning.

## Local setup

Install [uv](https://docs.astral.sh/uv/), then run:

```bash
uv sync --locked --no-extra ml
python scripts/quality/check_repository.py
uv run --locked pytest tests/quality
uv run --locked pytest -m smoke tests/smoke
```

The ML extra is intentionally opt-in:

```bash
uv sync --locked --extra ml
```

Do not use real case material in tests. Build minimal synthetic fixtures that
exercise the relevant structure without reproducing victim details or harmful
content.

## Developer Certificate of Origin

Every commit must include a `Signed-off-by` trailer that matches the commit
author:

```text
Signed-off-by: Your Name <your.email@example.com>
```

Use `git commit -s`. This certifies the contribution under the
[Developer Certificate of Origin, version 1.1](https://developercertificate.org/).
Unsigned commits should not be merged.

## Change design

Keep changes small and auditable. Material decisions require an ADR. Every pull
request must identify:

- the user or research outcome;
- the evidence/scientific invariant preserved;
- privacy, misuse, and security threats;
- executable acceptance evidence;
- compatibility and migration behavior;
- rollback or safe-disable behavior;
- known limitations.

Generated outputs must be changed through their generator and manifest. Do not
hand-edit RDF, JSON-LD, model bundles, or corpus outputs as the only fix.

## Versioning

Do not create CaseLinker release tags from this fork. Proposal checkpoints use
the `proposal-*` namespace; upstream decides official versioning. Workspace
metadata remains `0.0.0` and is not a product version.
