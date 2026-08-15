# vNext proposal baseline

**Recorded:** 2026-08-15

**Upstream repository:** `mrinaalr/CaseLinker`

**Upstream commit:** `9da0a4ff8b45df03fed073a9af5c00d22aab0d9d`

**Proposal branch:** `proposal/v3-foundation`

## Purpose

This checkpoint establishes a reproducible engineering floor without changing
CaseLinker's research behavior, data model, API semantics, user interface, or
deployment. It is intentionally a foundation, not a feature release.

## Baseline findings

- The upstream snapshot had no Git tags, lockfile, GitHub Actions workflow,
  root Python tool configuration, `SECURITY.md`, or conventional automated test
  suite.
- Two Python files named as tests are ad-hoc evaluation/demo scripts and are not
  collected as deterministic unit tests.
- `scripts/verify/paper/claims_registry.py` contained three corrupt byte
  sequences and could not be decoded or compiled as UTF-8 Python.
- The inherited locked versions of FastAPI/Starlette, `lxml-html-clean`,
  `pypdf`, and pytest produced 19 known vulnerability findings in the resolved
  core/development environment.
- Large generated RDF/JSON-LD pools coexist with authored code. Quality checks
  must distinguish generators and authored configuration from artifacts.

## Changes in this checkpoint

- Added an engineering charter and maintainer-sovereignty/versioning ADR.
- Added UTF-8 and line-ending policy plus a dependency-free repository checker.
- Repaired the three corrupt en-dash sequences without changing claim meaning.
- Added non-product workspace metadata and a deterministic `uv.lock`.
- Upgraded the vulnerable dependency set within explicit compatibility bounds:
  FastAPI 0.141.1, Starlette 1.6.0, `lxml-html-clean` 0.4.5, `pypdf` 6.16.1,
  and pytest 9.1.1 in the resolved lock.
- Added strict tests for the repository checker and an application boot/health
  smoke contract.
- Added CI for integrity, strict proposal-surface lint/format/type checks,
  tests, dependency auditing, high-severity static analysis, CodeQL, dependency
  review, and scheduled dependency updates.
- Added a security-reporting policy designed for this corpus's harm profile.

## Verification evidence

The following commands pass from the repository root on Python 3.12:

```bash
uv sync --locked --no-extra ml
python scripts/quality/check_repository.py
uv run --locked ruff check scripts/quality tests
uv run --locked ruff format --check scripts/quality tests
uv run --locked mypy scripts/quality/check_repository.py
uv run --locked pytest tests/quality --cov=scripts/quality --cov-report=term-missing
CASELINKER_DISABLE_MCP=1 uv run --locked pytest -m smoke tests/smoke
uv run --locked pip-audit --local --skip-editable
uv run --locked bandit -q -lll -r scripts/quality
```

Observed results at this checkpoint:

- repository check: passed for 8,403 tracked/candidate files;
- strict lint and formatting: passed;
- strict type check: passed;
- quality tests: 15 passed, 96.61% branch-aware coverage;
- application smoke tests: 2 passed;
- dependency audit: no known vulnerabilities;
- high-severity Bandit scan of the strict proposal surface: no findings.

## Honest limitations

- The strict lint/type/security surface currently covers new proposal tooling,
  not all historical Python and JavaScript. Coverage expands monotonically as
  modules are touched or migrated.
- Smoke tests prove application construction and the liveness contract, not
  correctness against a production corpus, PostgreSQL, Redis, MCP clients, or
  external model providers.
- The optional ML environment is locked but not installed or audited by the
  core CI job. It requires a dedicated model-supply-chain and reproducibility
  gate before vNext relies on it.
- Generated graph and corpus artifacts are excluded from generic source-text
  checks; future snapshot manifests must hash and validate them separately.
- No release tag, deployment, database migration, public claim, or upstream pull
  request is created by this checkpoint.

## Rollback

All work is isolated on `proposal/v3-foundation`. Returning to the exact
upstream baseline requires checking out commit `9da0a4f`; no persistent schema,
data, or deployment state has been modified.
