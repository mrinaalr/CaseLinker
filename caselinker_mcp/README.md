# CaseLinker MCP Server

The CaseLinker MCP (Model Context Protocol) server exposes structured tools to agents and AI Applications (Cursor, Claude Desktop, and other MCP clients). Tools include corpus search and analysis, knowledge graphs, triage, free court records search (CourtListener/RECAP), and the **press-release collector suite**.

- **29** tools wrap the CaseLinker REST API
- **8** are MCP-only corpus / graph helpers
- **4** search free public court and DOJ press records
- **1** collector READ (`probe_press_url`) always
- **5** collector WRITE — **local MCP only** (not registered on Railway)

**Local stdio / local FastAPI mount:** **47 tools** (full READ + WRITE).
**Railway hosted MCP:** **42 tools** (WRITE omitted — no writes to ephemeral Railway disk).

Corpus and analysis tools are read-only against the database. Collector WRITE tools write local JSON/PDFs only; they do not ingest into sqlite.

See [`tool_registry.md`](tool_registry.md) for the full catalog, including **READ vs WRITE** and the host split.

## Prerequisites

```bash
pip install mcp httpx
```

Outside a virtual environment you may need:

```bash
pip install mcp httpx --break-system-packages
```

Or install from the repo root after activating `.venv`:

```bash
pip install -r requirements.txt
```

## Run standalone (verify)

```bash
CASELINKER_API_URL=https://caselinker.up.railway.app \
python -m caselinker_mcp.server
```

The process starts silently on stdin/stdout (MCP wire protocol). Diagnostic logs go to stderr only. Press Ctrl+C to stop.

Point at a local server instead:

```bash
CASELINKER_API_URL=http://localhost:8000 python -m caselinker_mcp.server
```

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `CASELINKER_API_URL` | `https://caselinker.up.railway.app` | Base URL for the CaseLinker REST API |
| `CASELINKER_KEY` | (unset) | Sent as `CaseLinker-Key` header when set (trusted bulk access) |
| `MCP_COLLECTOR_WRITE` | auto | `1` force-enable / `0` force-disable collector WRITE tools. Default: on locally, off when `RAILWAY_*` is set |

Set `CASELINKER_KEY` to a value listed in `CASELINKER_TRUSTED_KEYS` on Railway only if you need bulk export, unsanitized single-case narratives, lifecycle exports, or LLM daily-cap exemption (see **Trusted-key sensitive** below).

## Tool tiers

**42 public** + **5 trusted-key sensitive** = **47 tools** on local MCP.
On Railway hosted MCP the five collector WRITE tools are omitted → **37 public** + **5 trusted** = **42 tools**.

### Public tier

Trusted key does **not** change behavior. Includes corpus search, analysis, ontology, stats, on-demand graphs, free public-record search, and collector helpers:

- Corpus: `get_corpus_stats`, `get_cases_page`, `get_cases_by_ids`
- Search / cohorts: `filter_cases_by_tags`, `get_facet_tree`, `get_cohort_members`, `tree_traversal`
- Analysis: `run_automated_analysis`, `triage_text`, `get_triage_eval_metrics`
- Stats / filters: `get_case_count`, `get_facet_distinct`, `get_unique_tags`, `tag_threader`, `get_case_ids_by_filter`, `get_stats_detailed`, `get_technology_revolver`, `get_cluster_groups`, `get_location_stats`, `get_triage_model_corpus`
- Ontology (pre-merged): `get_knowledge_graph`, `get_case_graph_manifest`
- Reference: `get_case_studies`, `get_case_study_notes`, `list_sources`
- Q1 research: `q1_platform_evidence` (platform harm evidence cohorts)
- On-demand graphs (MCP-only): `case2cac`, `graph_get_neighbors`, `graph_find_cases_by_concept`, `graph_summarize`, `graph_compare_cohorts`, `export_case_graph_ttl`
- Free public records (**READ**, all hosts): `search_doj_press_releases`, `search_courtlistener`, `list_free_recap_documents`, `resolve_free_recap_download`, `probe_press_url`
- Press collector **WRITE** (**local MCP only**): `harvest_doj_press_topic`, `fetch_press_listing_urls`, `resolve_press_urls`, `build_press_pdf`, `collect_case_dual_path`

### Trusted-key sensitive (5 tools)

| Tool | Without trusted key | With trusted key |
|------|---------------------|------------------|
| `get_all_cases` | **403** (bulk export blocked) | Full corpus export; optional `include_raw_data` |
| `get_lifecycle_cases` | **403** (lifecycle export blocked) | Lifecycle swimlane / visualization payload |
| `get_lifecycle_lstar` | **403** (L* export blocked) | Full `lstar_all_cases.json` (transition matrix, global L*, per-case details) |
| `get_case` | Sanitized case (no `raw_data`) | Full case including narratives |
| `llm_chat` | 50 requests/IP/day | Daily cap exempt (slowapi 15/min still applies) |

`get_all_cases` and lifecycle tools are blocked without trusted access. `get_case` and `llm_chat` are publicly accessible with reduced payload or stricter rate limits.

**Database:** no MCP tool mutates CaseLinker sqlite or triggers PDF ingestion into the corpus.

**Disk WRITE (local MCP only):** collector WRITE tools write under `collector_output/` or `collector/sources/` on the machine running MCP. They are **not registered** on Railway hosted MCP (ephemeral FS; callers would never see the files). Override with `MCP_COLLECTOR_WRITE=1|0`. Responses include `"write": true` / `"tool_kind": "WRITE"`. See `tool_registry.md` → *READ vs WRITE*. `collector_output/` is gitignored.

## Cursor configuration

Add to `.cursor/mcp.json` at the repo root (do **not** commit this file if it contains your API key):

```json
{
  "mcpServers": {
    "caselinker": {
      "command": "python",
      "args": ["-m", "caselinker_mcp.server"],
      "cwd": "${workspaceFolder}",
      "env": {
        "CASELINKER_API_URL": "https://caselinker.up.railway.app",
        "CASELINKER_KEY": ""
      }
    }
  }
}
```

Fill in `CASELINKER_KEY` locally only if you need bulk export, full case narratives, lifecycle exports, or LLM daily-cap exemption.

## Hosted (Railway)

CaseLinker exposes **two HTTP transports** on Railway (pick one in your MCP client config). Hosted MCP is **42 tools**: corpus + READ collector/public-records. Collector **WRITE** tools are not registered here — run local stdio MCP or the `collector/` CLI to write PDFs on your machine.

| Transport | Client URL | How messages flow |
|-----------|------------|-------------------|
| **SSE** (legacy dual-endpoint) | `https://caselinker.up.railway.app/mcp/sse` | `GET /mcp/sse` opens the stream; the server sends an `endpoint` event; **POST JSON-RPC to `/mcp/messages?session_id=…`** (not to `/sse`) |
| **Streamable HTTP** (recommended) | `https://caselinker.up.railway.app/mcp-http/` | **Same URL** for `GET` and `POST` (trailing slash avoids 307 redirects) |

**Cursor config (Streamable HTTP, recommended):**

```json
{
  "mcpServers": {
    "caselinker-hosted": {
      "url": "https://caselinker.up.railway.app/mcp-http/",
      "headers": {
        "Authorization": "Bearer <your MCP_ACCESS_KEY>",
        "CaseLinker-Key": "<your trusted key>"
      }
    }
  }
}
```

**Cursor config (SSE):**

```json
{
  "mcpServers": {
    "caselinker-hosted": {
      "url": "https://caselinker.up.railway.app/mcp/sse",
      "headers": {
        "Authorization": "Bearer <your MCP_ACCESS_KEY>",
        "CaseLinker-Key": "<your trusted key>"
      }
    }
  }
}
```

Public tier only (no trusted key): omit `CaseLinker-Key` from `headers`.

**Railway environment variables:**

| Variable | Purpose |
|----------|---------|
| `MCP_ACCESS_KEY` | Gates inbound MCP HTTP requests on **SSE** (`/mcp/sse`) and **Streamable HTTP** (`/mcp-http/`) via `Authorization: Bearer …` |

`MCP_ACCESS_KEY` is separate from `CASELINKER_KEY` / `CaseLinker-Key`:

- **`MCP_ACCESS_KEY`**: who may connect to the MCP server (`Authorization: Bearer …`); required for SSE and Streamable HTTP
- **`CASELINKER_KEY` env** (stdio) or **`CaseLinker-Key` header** (SSE / Streamable HTTP): forwarded on REST calls; affects the five trusted-key-sensitive tools (see `tool_registry.md`)

Per-user trusted access over HTTP: pass `CaseLinker-Key` in `mcp.json` `headers` (works for SSE and Streamable HTTP). The server forwards it on outbound REST calls. If the header is absent, it falls back to server-side `CASELINKER_KEY` env (if set), then public tier only.

Add `.cursor/mcp.json` to `.gitignore` if it contains secrets.

## Local corpus

Useful once you are pointing MCP at localhost. The processed sqlite corpus is **10,282 case reports**, **125,891 extracted features**, and **4,000+ distinct law-enforcement agencies** (**56** sources, **10,282** per-case CAC graphs under `ontology/graph_output/`).

- **Railway:** same deployed snapshot, public rate limits. Set `CASELINKER_API_URL=https://caselinker.up.railway.app`.
- **Localhost:** set `CASELINKER_API_URL=http://localhost:8000` after `python3 run/main.py`. The local DB starts empty unless you populate it.

If the local DB is empty, request a trusted `CaseLinker-Key` at **mramachandra@umass.edu**, then:

```bash
export CASELINKER_KEY='your-trusted-key'
export CASELINKER_API_URL=https://caselinker.up.railway.app
python3 scripts/run/import_corpus_from_api.py
```

That pulls the full production corpus via the trusted bulk API (`get_all_cases` / `GET /api/cases`). Without a trusted key, bulk export returns 403. You can also build a local DB by ingesting press-release PDFs yourself (see the repo root README and `collector/`).

## On-Demand Graph Generation

Workflow for cohort-specific CAC ontology graphs (MCP-only; not REST):

1. Use `filter_cases_by_tags` or `get_cohort_members` to find case IDs
2. Call `case2cac(case_ids)` (returns `graph_id` and a structural summary)
3. Use `graph_id` with `graph_get_neighbors`, `graph_find_cases_by_concept`, or `graph_summarize`
4. Call `export_case_graph_ttl(graph_id, case_id=..., pool="analysis")` to get JSON-LD + Turtle and optionally save `{case_id}.jsonld`/`.ttl` under `ontology/graph_output/analysis/` for Patterns
5. Optionally run `case2cac` on a second cohort and call `graph_compare_cohorts` to diff them (e.g. Discord vs Roblox for Q1/Q2/Q3 research)

Session graphs are stored in Redis on Railway (`caselinker:mcp:graph:{id}`, 2-hour TTL) with in-memory fallback when Redis is unavailable (local dev). `export_case_graph_ttl` reconstructs RDF from session `flat_nodes` via rdflib (strips merge metadata `_cases` / `_isShared` / `_isNlp`).

## Local stdio transport

The default entry point uses stdio (local agent hosts):

```bash
python -m caselinker_mcp.server
```

For a standalone SSE process (not via Railway mount), set `MCP_TRANSPORT=sse` and optionally `PORT` (default 8001).

## Tools

**47 tools locally / 42 on Railway.** See [`tool_registry.md`](tool_registry.md) for the authoritative list. Summary by tier:

| Tier | Local | Railway | Examples |
|------|------:|--------:|----------|
| Public (trusted key irrelevant) | 42 | 37 | `get_cases_page`, `search_courtlistener`; WRITE only local |
| Trusted-key sensitive | 5 | 5 | `get_all_cases`, `get_lifecycle_cases`, `get_lifecycle_lstar`, `get_case`, `llm_chat` |

Authoritative implementation: `@mcp.tool()` definitions in `server.py`. Tool docstrings there remain the source of parameter and behavior detail.
