# Tests

```bash
DATABASE_URL='' .venv/bin/python -m pytest -q tests/
```

**`DATABASE_URL=''` every time.** A test that loads `run/main.py` runs table DDL against whatever `DATABASE_URL` names, and in a shell with Railway variables that is production Postgres. One process runs the whole suite; `run_gate` still runs one file per process. [`extraction/test_module_names_unique.py`](extraction/test_module_names_unique.py) fails if two folders on `sys.path` define the same module name, which is what broke whole-suite runs before.

| Folder | Covers |
|---|---|
| [`collection/`](collection/) | Collectors, listing and URL fetchers, robots policy, source routing and batching, release filter, case-id collisions, cross-source dedupe, document identity |
| [`extraction/`](extraction/) | Field assertions end to end, module names unique on `sys.path`, dates and sentences, topics, CyberTip reporter, prosecution status, platform names, NER places, LLM residue pass, re-resolve |
| [`grounding/`](grounding/) | Location and agency grounding, pinned gazetteer and registry, location backfill |
| [`graphs/`](graphs/) | CAC mapping, SHACL, term resolution, provenance graphs, shared nodes, graph generate, Big Bang pool, cohort SPARQL, PACER JSON-LD, Oxigraph N-Quads |
| [`storage/`](storage/) | SQLite / Postgres parity, provenance tables, corpus import, provenance sidecar paths |
| [`api/`](api/) | Routes, HEAD, localhost peer, jurisdiction, filters, sources stats, `/resource`, SPARQL proxy and NL → SPARQL, Oxigraph wake, affordance evidence |
| [`mcp/`](mcp/) | MCP tools and the repair-and-expand gate |
| [`privacy/`](privacy/) | No names stored or served; age-tied names stay on localhost |
| [`research/`](research/) | Paper claims and snapshots, phase-3 Wilson intervals, state-machine estimators |

## Gate tier

`run_gate` pins these to `origin/main` and fails a change that removes a line from them ([`TEST_TIER`](../caselinker_mcp/repair_expand.py)). Add tests beside them; do not weaken them.

- [`extraction/test_field_assertions.py`](extraction/test_field_assertions.py)
- [`privacy/test_no_direct_identifiers.py`](privacy/test_no_direct_identifiers.py)
- [`privacy/test_public_assertion_names.py`](privacy/test_public_assertion_names.py)
- [`mcp/test_repair_expand.py`](mcp/test_repair_expand.py)

## Conditions

| Needs | Without it |
|---|---|
| `caselinker.db` at the repo root | tests that read stored case text skip |
| `CASELINKER_SPARQL_LIVE=1` | [`api/test_sparql_live.py`](api/test_sparql_live.py) skips; it hits production `/sparql` |
| A local Postgres | the Postgres half of [`storage/test_storage_parity.py`](storage/test_storage_parity.py) skips |

## Writing one

- Put it in the folder for the layer it guards. A file goes in as `tests/<folder>/test_<what>.py`, with `ROOT = Path(__file__).resolve().parents[2]`.
- Made-up people only: `FICTIONAL_SURNAMES` in [`privacy/test_no_direct_identifiers.py`](privacy/test_no_direct_identifiers.py). Never paste a real release or a real name.
- Name a `case_id` or issue number for a regression, and show the test fails without the fix.
- No network. Live checks sit behind an env flag.

Shared: [`conftest.py`](conftest.py) puts the repo root and `src/Storage Layer` on the path; [`ontology_fixtures.py`](ontology_fixtures.py) holds made-up cases that reach every branch of the CAC mapper; [`snapshot-manifest-v1.schema.json`](snapshot-manifest-v1.schema.json) is the paper snapshot schema.
