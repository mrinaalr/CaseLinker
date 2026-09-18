# CaseLinker MCP tool registry

**Total: 47 tools.** Count `@mcp.tool()` decorators in `server.py`.

Authoritative implementation: `caselinker_mcp/server.py`. This file is the human-readable catalog for docs and agent hosts.

## Backend split

| Backend | Count | Notes |
|---------|------:|-------|
| REST API wrappers | **29** | Proxy to `GET`/`POST /api/*` |
| MCP-only (corpus graphs) | **8** | `tree_traversal`, `list_sources`, `case2cac`, four graph tools, `export_case_graph_ttl` |
| MCP-only (free public records) | **4** | DOJ press search + CourtListener/RECAP (`public_records.py`) |
| MCP-only (press collector suite) | **6** | Wrap `collector` via `collector_tools.py`. See **READ vs WRITE** below |
| **Total** | **47** | |

There are **32** REST `/api/*` routes in `run/main.py`. **29** have MCP tools; four are intentionally excluded from MCP (admin/write/index): `POST /api/cache/clear`, `POST /api/case-studies/notes/{id}`, `POST /api/ontology/cache/warm`, `GET /api`.

`POST /api/llm/chat` exposes an internal `query_cases_database` function-calling tool to the LLM; that helper is **not** a separate MCP tool. MCP clients use `llm_chat` instead.

No MCP resources (`@mcp.resource`) or prompts (`@mcp.prompt`) are registered.

## Tier model

| Category | Count | Meaning |
|----------|------:|---------|
| Public (trusted key irrelevant) | **42** | Same behavior with or without trusted key |
| Trusted-key sensitive | **5** | Blocked or reduced without trusted key |
| **Total** | **47** | |

Corpus REST tools do **not** mutate the CaseLinker database. Collector WRITE tools create files on disk (JSON, url-lists, PDFs) under `collector_output/` or `collector/sources/`. They do **not** auto-ingest into sqlite.

---

## READ vs WRITE (press + court collection)

Agents collecting cases should use this map. On disk the suite lives at repo-root `collector/`.

### READ (no files written)

| Tool | What it does |
|------|----------------|
| `search_doj_press_releases` | DOJ News API title search → JSON previews (method A discovery) |
| `probe_press_url` | One URL extract/resolve preview (no PDF) |
| `search_courtlistener` | Free RECAP / opinion search |
| `list_free_recap_documents` | Free filings for a `docket_id` |
| `resolve_free_recap_download` | Free storage URL when `is_available` |

### WRITE (creates files on disk; responses set `write: true` / `tool_kind: WRITE`)

| Tool | Collection method | Writes |
|------|-------------------|--------|
| `harvest_doj_press_topic` | **A: DOJ API** | `*_resolved.json`, url list |
| `fetch_press_listing_urls` | **B: URL path** (listing → urls) | `*.txt` url-file |
| `resolve_press_urls` | **B: URL path** (router) | `*_resolved.json` (`scrape_doj`) |
| `build_press_pdf` | A or B final step | merged `.pdf` under `out_dir` |
| `collect_case_dual_path` | A and B for one topic | both PDFs + resolve JSON + CourtListener search |

**Agent workflow**

1. Discover: `search_doj_press_releases` or `harvest_doj_press_topic`, or `fetch_press_listing_urls`
2. Optional QA: `probe_press_url`
3. If you have URLs: `resolve_press_urls` then `build_press_pdf`
4. Court filings ($0): `search_courtlistener` → `list_free_recap_documents` → `resolve_free_recap_download`
5. Shortcut: `collect_case_dual_path(title_term)` runs A and B for one topic

`justice.gov` article HTML is behind Akamai. Do not fetch it live. Resolve through the DOJ News API (`harvest_*` / `resolve_press_urls` / `probe_press_url`).

---

## Public tier (42 tools)

Trusted key does **not** change behavior (still subject to normal slowapi / public rate limits).

| Tool | Backend | Notes |
|------|---------|-------|
| `get_corpus_stats` | `GET /api/stats` | Corpus-wide counts |
| `get_cases_page` | `GET /api/cases-summaries-chunk` | Paginated summaries |
| `get_cases_by_ids` | `POST /api/cases-summaries-by-ids` | Batch summaries |
| `filter_cases_by_tags` | `POST /api/return-tagged-cases` | Tag intersection |
| `get_facet_tree` | `GET /api/facet-tree` or MCP-local | Facet tree; optional `case_ids` for subset |
| `get_cohort_members` | `POST /api/facet-cohort-members` or MCP-local | Cohort case IDs; optional `case_ids` |
| `tree_traversal` | MCP-only | Random + targeted facet samples over a case subset |
| `run_automated_analysis` | `GET /api/automated-analysis` | Similarity + triage insights |
| `triage_text` | `POST /api/triage-live` | In-memory narrative triage |
| `get_triage_eval_metrics` | `GET /api/triage-eval` | Classifier eval metrics |
| `get_knowledge_graph` | `GET /api/ontology/merged` | Pre-merged ontology pool |
| `get_case_graph_manifest` | `GET /api/ontology/cases` | Graph coverage metadata |
| `get_case_studies` | `GET /api/case-studies` | Era-based narratives |
| `q1_platform_evidence` | `GET /api/q1/platform-evidence` | Q1 platform harm cohort index or per-platform evidence |
| `list_sources` | (static) | Source catalog |
| `case2cac` | MCP-only | On-demand cohort graph → `graph_id` |
| `graph_get_neighbors` | MCP-only | Traverse session graph |
| `graph_find_cases_by_concept` | MCP-only | Concept → case IDs |
| `graph_summarize` | MCP-only | Structural graph summary |
| `graph_compare_cohorts` | MCP-only | Diff two session graphs |
| `export_case_graph_ttl` | MCP-only | Session graph → JSON-LD + Turtle; optional save to graph_output pool |
| `get_case_count` | `GET /api/case-count` | Fast COUNT |
| `get_facet_distinct` | `GET /api/facet-distinct` | Facet prune values |
| `get_unique_tags` | `GET /api/tags` | All tag dimensions |
| `tag_threader` | `POST /api/tag-threader` | Tag intersection + threads |
| `get_case_ids_by_filter` | `GET /api/case-ids-by-filter` | Structured ID filters |
| `get_stats_detailed` | `GET /api/stats-detailed` | Chart-ready stats |
| `get_technology_revolver` | `GET /api/technology-revolver` | Tech by era |
| `get_cluster_groups` | `GET /api/cluster-groups` | Similarity clusters |
| `get_location_stats` | `GET /api/location-stats` | Map aggregation |
| `get_triage_model_corpus` | `GET /api/triage-model-corpus` | Bundle predictions |
| `get_case_study_notes` | `GET /api/case-studies/notes/{id}` | Community notes |
| `search_doj_press_releases` | DOJ News API | **READ** press search |
| `search_courtlistener` | CourtListener | **READ** free RECAP search |
| `list_free_recap_documents` | CourtListener | **READ** free filings |
| `resolve_free_recap_download` | CourtListener | **READ** free download URL |
| `probe_press_url` | `collector_tools` / `collector` | **READ** extract/resolve probe |
| `harvest_doj_press_topic` | `harvest_doj_psc.py` | **WRITE** DOJ API harvest JSON |
| `fetch_press_listing_urls` | `fetch_source_urls.py` | **WRITE** listing → url-file |
| `resolve_press_urls` | `scrape_doj.py` | **WRITE** URL-path resolve JSON |
| `build_press_pdf` | `scrape_pdf.py` | **WRITE** merged PDF |
| `collect_case_dual_path` | collector suite | **WRITE** A+B dual collect |

### On-demand graph workflow

1. `case2cac(case_ids)` → `graph_id`
2. `graph_get_neighbors` / `graph_find_cases_by_concept` / `graph_summarize`
3. `export_case_graph_ttl(graph_id, case_id?, pool?)` → `{ jsonld, turtle, triple_count, node_count, saved? }`

Session graphs are stored in Redis when available (`caselinker:mcp:graph:{id}`, 2-hour TTL); otherwise in-process memory for local dev.

## Trusted-key sensitive (5 tools)

Requires `CASELINKER_KEY` / `CaseLinker-Key` listed in server `CASELINKER_TRUSTED_KEYS` for full behavior.

| Tool | Without trusted key | With trusted key |
|------|---------------------|------------------|
| `get_all_cases` | **403** from API (or MCP local error if no key configured) | Full bulk export; optional `include_raw_data` |
| `get_lifecycle_cases` | **403** from API (or MCP local error if no key configured) | Lifecycle swimlane / visualization payload |
| `get_lifecycle_lstar` | **403** from API (or MCP local error if no key configured) | Full `lstar_all_cases.json` (transition matrix, global L*, per-case details) |
| `get_case` | Works; **sanitized** (no `raw_data` / narrative blobs) | Works; **full** case payload including `raw_data` |
| `llm_chat` | Works; **50 requests/IP/day** (+ slowapi 15/min) | Works; **daily cap exempt** (+ slowapi 15/min still applies) |

`get_all_cases` and both lifecycle tools are blocked without trusted access. `get_case` and `llm_chat` are public tools with richer responses or limits when a trusted key is forwarded on REST calls. The public `/lifecycle` page embeds visualization data server-side and does not require a browser API key.
