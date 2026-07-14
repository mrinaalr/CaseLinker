# CaseLinker MCP Server

The CaseLinker MCP (Model Context Protocol) server exposes the corpus, knowledge graphs, triage scoring, and automated analysis as **37 structured tools** for agent and LLM workflows. Twenty-nine tools wrap the existing CaseLinker REST API over HTTP; eight are MCP-only (facet traversal, on-demand graphs, static source catalog). Read-only — no direct database mutation via MCP — so it works the same against local `run/main.py` and the Railway production deployment.

See [`tool_registry.md`](tool_registry.md) for the full tool catalog and tier breakdown.

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

Set `CASELINKER_KEY` to a value listed in `CASELINKER_TRUSTED_KEYS` on Railway only if you need bulk export, unsanitized single-case narratives, lifecycle exports, or LLM daily-cap exemption (see **Trusted-key sensitive** below).

## Tool tiers

**32 public** + **5 trusted-key sensitive** = **37 tools**. See [`tool_registry.md`](tool_registry.md) for the full table.

### Public tier (32 tools)

Trusted key does **not** change behavior. Includes all corpus search, analysis, ontology, stats, and on-demand graph tools:

- Corpus: `get_corpus_stats`, `get_cases_page`, `get_cases_by_ids`
- Search / cohorts: `filter_cases_by_tags`, `get_facet_tree`, `get_cohort_members`, `tree_traversal`
- Analysis: `run_automated_analysis`, `triage_text`, `get_triage_eval_metrics`
- Stats / filters: `get_case_count`, `get_facet_distinct`, `get_unique_tags`, `tag_threader`, `get_case_ids_by_filter`, `get_stats_detailed`, `get_technology_revolver`, `get_cluster_groups`, `get_location_stats`, `get_triage_model_corpus`
- Ontology (pre-merged): `get_knowledge_graph`, `get_case_graph_manifest`
- Reference: `get_case_studies`, `get_case_study_notes`, `list_sources`
- Q1 research: `q1_platform_evidence` (platform harm evidence cohorts)
- On-demand graphs (MCP-only): `case2cac`, `graph_get_neighbors`, `graph_find_cases_by_concept`, `graph_summarize`, `graph_compare_cohorts`, `export_case_graph_ttl`

### Trusted-key sensitive (5 tools)

| Tool | Without trusted key | With trusted key |
|------|---------------------|------------------|
| `get_all_cases` | **403** (bulk export blocked) | Full corpus export; optional `include_raw_data` |
| `get_lifecycle_cases` | **403** (lifecycle export blocked) | Lifecycle swimlane / visualization payload |
| `get_lifecycle_lstar` | **403** (L* export blocked) | Full `lstar_all_cases.json` (transition matrix, global L*, per-case details) |
| `get_case` | Sanitized case (no `raw_data`) | Full case including narratives |
| `llm_chat` | 50 requests/IP/day | Daily cap exempt (slowapi 15/min still applies) |

`get_all_cases` and lifecycle tools are blocked without trusted access. `get_case` and `llm_chat` are publicly accessible with reduced payload or stricter rate limits.

No write tools, PDF ingestion, or database mutation endpoints are exposed via MCP. 


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

CaseLinker exposes **two HTTP transports** on Railway (pick one in your MCP client config):

| Transport | Client URL | How messages flow |
|-----------|------------|-------------------|
| **SSE** (legacy dual-endpoint) | `https://caselinker.up.railway.app/mcp/sse` | `GET /mcp/sse` opens the stream; the server sends an `endpoint` event; **POST JSON-RPC to `/mcp/messages?session_id=…`** (not to `/sse`) |
| **Streamable HTTP** (recommended) | `https://caselinker.up.railway.app/mcp-http/` | **Same URL** for `GET` and `POST` (trailing slash avoids 307 redirects) |

**Cursor config — Streamable HTTP (recommended):**

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

**Cursor config — SSE:**

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

- **`MCP_ACCESS_KEY`** — who may connect to the MCP server (`Authorization: Bearer …`); required for SSE and Streamable HTTP
- **`CASELINKER_KEY` env** (stdio) or **`CaseLinker-Key` header** (SSE / Streamable HTTP) — forwarded on REST calls; affects the five trusted-key-sensitive tools (see `tool_registry.md`)

Per-user trusted access over HTTP: pass `CaseLinker-Key` in `mcp.json` `headers` (works for SSE and Streamable HTTP). The server forwards it on outbound REST calls. If the header is absent, it falls back to server-side `CASELINKER_KEY` env (if set), then public tier only.

Add `.cursor/mcp.json` to `.gitignore` if it contains secrets.

## On-Demand Graph Generation

Workflow for cohort-specific CAC ontology graphs (MCP-only; not REST):

1. Use `filter_cases_by_tags` or `get_cohort_members` to find case IDs
2. Call `case2cac(case_ids)` — returns `graph_id` and a structural summary
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

**37 tools total** — see [`tool_registry.md`](tool_registry.md) for the authoritative list. Summary by tier:

| Tier | Count | Examples |
|------|------:|----------|
| Public (trusted key irrelevant) | 32 | `get_cases_page`, `case2cac`, `q1_platform_evidence`, `tree_traversal` |
| Trusted-key sensitive | 5 | `get_all_cases`, `get_lifecycle_cases`, `get_lifecycle_lstar`, `get_case`, `llm_chat` |

Authoritative implementation: `@mcp.tool()` definitions in `server.py`. Tool docstrings there remain the source of parameter and behavior detail.
