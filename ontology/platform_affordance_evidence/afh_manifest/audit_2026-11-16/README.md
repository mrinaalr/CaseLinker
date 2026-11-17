# Q1 audit, 2026-11-16 (preserved)

Read-only audit that motivated this reconstruction. Kept as run, not maintained.

| File | What it is |
|---|---|
| `afh-q1-audit.html` | The audit report as published for review |
| `rebuild.py` | Rebuilt candidates + evidence from the live DB into a scratch dir |
| `analyze.py` | Inventory, tier, cue-probe and era numbers used in the report |
| `compare.py` | June (`24b31e9cd`) vs stale (`HEAD` candidates) vs fresh comparison |

Inputs the scripts read from scratch (`old_cand.json`, `old_ev.json`, `stale_cand.json`) are
reproducible from git: `git show 24b31e9cd:ontology/q1/candidates.json`,
`git show 24b31e9cd:ontology/q1/q1_evidence.json`,
`git show be7bb8f02:ontology/platform_affordance_evidence/candidates.json`.

The cue probe in `analyze.py` is an unvalidated regex scan. Its counts are superseded by
`ontology/platform_affordance_evidence/afh_manifest/` outputs and must not be cited as prevalence.
