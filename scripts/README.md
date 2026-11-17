# Scripts

Operator scripts, run from the repo root. **Writes** names what a script changes; a dash means it only reads or prints a report. Back up before anything that writes the database (`pg_dump`, or copy `caselinker.db`).

| Folder | For |
|---|---|
| [`run/`](run/) | Ingest, backfills, re-resolve, caches, models. On `run/main.py`'s import path: keep the name |
| [`oxigraph/`](oxigraph/) | Build and load the SPARQL store |
| [`verify/`](verify/) | Precision samples, holdouts, paper claims, corpus checks |
| [`ontology_audit/`](ontology_audit/) | Term and graph audits (#57) |
| [`stats/`](stats/) | Corpus statistics |

## run/

| Script | Does | Writes |
|---|---|---|
| [`ingest_all_pdfs.sh`](run/ingest_all_pdfs.sh) · [`ingest_grouped.py`](run/ingest_grouped.py) | Ingest repo-root PDFs through `src/main.py` | DB |
| [`import_corpus_from_api.py`](run/import_corpus_from_api.py) | Pull production through `CaseLinker-Key` into a local DB | `caselinker.db` |
| [`reresolve_assertions.py`](run/reresolve_assertions.py) | Re-run field resolution over stored assertions; no re-extraction | DB resolutions |
| [`llm_residue_pass.py`](run/llm_residue_pass.py) | LLM pass over open mentions (`CASELINKER_LLM=1`) | DB assertions |
| [`backfill_stored_locations.py`](run/backfill_stored_locations.py) | Re-derive location strings from stored text | DB copy (`--dest`) |
| [`backfill_case_fingerprints.py`](run/backfill_case_fingerprints.py) | Content fingerprint per case id; never renumbers | DB (`--sqlite`/`--postgres`); `--report-*` read only |
| [`compute_person_spans.py`](run/compute_person_spans.py) | Person-name offsets via Stanza; no name strings | spans file (`--out`) |
| [`migrate_person_names.py`](run/migrate_person_names.py) | Replace stored names with per-case tokens | DB with `--apply` |
| [`precompute_clusters.py`](run/precompute_clusters.py) | Slim cluster / revolver rows | Postgres, Redis |
| [`rebuild_platform_affordance_evidence.py`](run/rebuild_platform_affordance_evidence.py) | Rebuild evidence when corpus identity changes | `ontology/platform_affordance_evidence/`; `--check` read only |
| [`propose_compiled_rule.py`](run/propose_compiled_rule.py) | Draft a compiled rule from confirmed quotes | – |
| [`train_triage_model.py`](run/train_triage_model.py) | Train triage classifiers | `models/` |
| [`fetch_agency_registry.py`](run/fetch_agency_registry.py) · [`.sh`](run/fetch_agency_registry.sh) | FBI CDE agencies by state | `data/agency_registry/` |
| [`fetch_gazetteer.sh`](run/fetch_gazetteer.sh) | Census 2024 gazetteer | `data/gazetteer/` |
| [`local_oxigraph.sh`](run/local_oxigraph.sh) | Local Oxigraph at the repo root | local store |
| [`clear_postgres.py`](run/clear_postgres.py) | **Deletes every row in every table** | Postgres |

## oxigraph/

| Script | Does | Writes |
|---|---|---|
| [`rebuild_oxigraph.py`](oxigraph/rebuild_oxigraph.py) | Canonical TTL plus a PACER release (`--pacer-release`) → named-graph N-Quads → bulk load into an empty store, checked with `--verify` ([reload procedure](../ontology/docs/SPARQL.md#reloading-the-store)) | N-Quads; Oxigraph unless `--no-load` |
| [`warm_oxigraph.py`](oxigraph/warm_oxigraph.py) | Wake the store before a demo | – |

## verify/

| Path | Does | Writes |
|---|---|---|
| [`extraction/`](verify/extraction/) | Location and agency grounding: freeze samples and holdouts, judge, measure precision; age-review samples; grounding corpus report. Frozen ids, judgments and reports are committed beside the scripts | frozen samples, reports |
| [`phase_3/`](verify/phase_3/) | Phase 3 vs 2.x on paired 200-case samples, Wilson intervals | results `.jsonl` |
| [`paper/`](verify/paper/) | Paper claims registry; `verify_paper.py [--snapshot]` | `claims.md`, `paper_tested.md`, snapshot |
| [`verify_cac.py`](verify/verify_cac.py) | Every case is a crimes-against-children case | `--fail-csv` |
| [`validate_case_uniqueness.py`](verify/validate_case_uniqueness.py) | Uniqueness and aggregator overlap | – |
| [`icac_tf_verify.py`](verify/icac_tf_verify.py) | ICAC task-force text hits vs `source` | – |
| [`scan_public_surfaces_for_names.py`](verify/scan_public_surfaces_for_names.py) | Every outward surface scanned for person names; counts only | – |
| [`test_triage.py`](verify/test_triage.py) | Triage model, 80/20 split | – |

## ontology_audit/ · stats/

| Script | Does | Writes |
|---|---|---|
| [`audit_graphs.py`](ontology_audit/audit_graphs.py) | Map every case with today's mapper; count what #57 measures | `--out` |
| [`analyze_stats.py`](stats/analyze_stats.py) · [`interesting_icac_stats.py`](stats/interesting_icac_stats.py) · [`policy_research_stats.py`](stats/policy_research_stats.py) | Corpus statistics over SQLite | – |

Re-extraction, backfills and store reloads are the maintainer's call. Say in the PR whether `caselinker.db`, `ontology/graph_output/` or Oxigraph still hold old values.
