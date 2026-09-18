# Search and corpus discovery

This document maps how CaseLinker lets researchers, law enforcement, and agents **find, narrow, and query** the corpus. **Search** (the `/search` tab) is one surface: a **facet decision tree**. It is not SPARQL, not the Query lab, and not the LLM chat. Those are sibling discovery tools on different backends.

Live: [Search](https://caselinker.up.railway.app/search) · [Query](https://caselinker.up.railway.app/query) · [LLM](https://caselinker.up.railway.app/llm) · [Patterns / graphs](https://caselinker.up.railway.app/patterns) · [SPARQL](https://caselinker.up.railway.app/sparql) (API). Local: same paths on `http://localhost:8000`.

---

## 1. Goals and constraints

### Primary goals

- **Cohort-first exploration**: Drill the corpus along structured dimensions (topics, platforms, severity, jurisdiction, era, …) and land on **groups** (counts, signatures, opaque cohort ids), not a phone-book of case narratives.
- **Deterministic partitions**: The facet tree is reproducible given the same features and prune settings (suitable for audit and replication).
- **Hand-off to the rest of the app**: Cohort case IDs (when policy allows) feed Audit, Patterns, triage, MCP graph tools, and manual cross-case review.
- **Mosaic-oriented disclosure**: Small cohorts gate raw case IDs behind a demo / access key so Search does not become a directory service by default.

### Non-goals (current design)

- Search is **not** free-text full-text search over narratives (no Lucene/Elastic layer today).
- Search is **not** SPARQL. Graph pattern queries live on Oxigraph via `/sparql` and the Patterns UI.
- Search is **not** natural-language SQL. That is the LLM tab (`/llm` → `/api/llm/chat`).
- Search is **not** the collector. Finding new press releases is `collector/` CLI or **local** MCP WRITE tools (see `collector/README.md`). Hosted Railway MCP is READ-only for collection.

---

## 2. Discovery map (what is which)

| Surface | What it answers | Backend | UI / entry |
|---------|-----------------|---------|------------|
| **Search** | “Partition the corpus by facets; show cohort sizes and (gated) members” | SQLite / Postgres case store + `facet_tree.py` | `/search` |
| **Query** | Ad-hoc analysis recipes calling public REST APIs from the browser | Same REST APIs as the app | `/query` |
| **Tag / analysis** | Intersection of extracted tags; automated grouping | `/api/return-tagged-cases`, analysis pipeline | `/analysis` |
| **LLM** | Natural-language questions over **stats / SQL-shaped** answers | `/api/llm/chat` (function-calling over DB stats) | `/llm` |
| **Patterns** | Browse / compare CAC case graphs, Q1–Q3 evidence | RDF under `ontology/graph_output/` + APIs | `/patterns` |
| **SPARQL** | Formal graph queries (platforms, steps, agencies, PACER kgs, …) | Oxigraph `GET\|POST /sparql` | API + Patterns; guide `ontology/docs/SPARQL.md` |
| **MCP tools** | Agents do the above without the browser | REST wrappers + MCP-only graph helpers + collector | `caselinker_mcp/` |

**Facet vs SPARQL (short):** facets slice the **tabular** case store (extracted features). SPARQL queries the **graph** store (CASE/UCO/CAC + PACER named graphs). Same corpus story, different representation. Use Search for cohort exploration; use SPARQL when the question is relational over ontology edges.

---

## 3. What ships today (Search / facets)

### UI

- **D3.js** SVG tree of cohort nodes and edges.
- **Depth control**: `max_depth` limits how many partition dimensions are used.
- **Prune**: enable/disable dimensions and optionally restrict allowed values per facet.
- **Click a node**: load cohort case IDs for hand-off elsewhere. Cohorts with fewer than three cases gate IDs behind a demo access key.

### Partition order (default)

Implemented in `src/Storage Layer/facet_tree.py` as `DEFAULT_FACET_ORDER` (Topic → Severity → Platform → Inv. type → Source → Agency → Prosecution outcome → Location → Severity phrase → Perp admission → Date range / era, …). Counts use **any-tag** semantics: a case with multiple topics can appear under each matching branch for membership/count.

### HTTP APIs

| Endpoint | Role |
|----------|------|
| `GET /api/facet-tree` | Build tree JSON (`max_depth`, prune query params) |
| `POST /api/facet-cohort-members` | Case IDs for a facet path |
| `GET /api/facet-distinct` | Distinct values for prune UI |
| `POST /api/return-tagged-cases` | Tag intersection (Analysis / MCP) |
| `POST /api/tag-threader` | Tag intersection + thread-style grouping |
| `GET /api/case-ids` (and related filters) | Filtered ID lists for labs |

Code: `visualization/search.html`, `run/main.py` routes, `facet_tree.py`.

### MCP (agent-facing, same ideas)

| Tool | Role |
|------|------|
| `get_facet_tree` | Facet tree; optional `case_ids` subset |
| `get_cohort_members` | Cohort membership for a path |
| `get_facet_distinct` | Prune values |
| `tree_traversal` | MCP-only random + targeted facet samples over a subset |
| `filter_cases_by_tags` / `tag_threader` / `get_case_ids_by_filter` | Tag and filter cohorts |
| `case2cac` → `graph_*` / `export_case_graph_ttl` | Cohort → on-demand CAC graph (not the facet tree itself) |
| `llm_chat` | NL over stats (trusted-key sensitive rate limits) |
| Collector + CourtListener tools | Press/PDF collection and free RECAP lookup (orthogonal to Search) |

Catalog: `caselinker_mcp/tool_registry.md`.

---

## 4. Related shipped surfaces (not Search, but discovery)

- **Query lab** (`/query`): browser-only recipes over public APIs without requiring an MCP host.
- **Audit** (`/audit`): case-level feature highlighting for **data accuracy** review (pairs with Search cohorts).
- **Stats / Clusters / Tech landscape**: aggregate views; not interactive facet drill-down.
- **Lifecycle** (`/lifecycle`): PACER state machines; see `state_machines/README.md`.
- **Public SPARQL**: rate-limited, query-only; see `ontology/docs/SPARQL.md`. LLM-assisted SPARQL and CASE/UCO SDK `execute_sparql_query` are optional agent paths into the same store.

---

## 5. Research and open work

Directions worth exploring (not committed product plans):

1. **Cross-walk facet cohorts ↔ SPARQL / Patterns**  
   Export a Search cohort as a SPARQL `VALUES` block or named-graph filter; open Patterns with the same case set. Today that hand-off is mostly manual (copy IDs).

2. **Guided NL → facet path (not full-text)**  
   Map short analyst phrases (“Discord + production + 2024”) onto prune constraints or a path, keeping mosaic defaults. Distinct from `/llm` SQL chat and from Elastic-style keyword search.

3. **Richer graph search UX**  
   Patterns already browse CAC classes / platforms / agencies. Deeper “search the graph” (path queries, shared-neighbor cohorts) without requiring hand-written SPARQL.

4. **Full-text / hybrid retrieval**  
   Optional narrative index for press-release bodies, always behind the same disclosure policy as small cohorts. Not started; would be a new stack beside facets.

5. **Agent evaluation**  
   Compare MCP facet tools (`get_facet_tree`, `tree_traversal`, `get_cohort_members`) against the UI and SPARQL for the same cohort: sizes and membership should agree.

6. **Privacy policy tightening**  
   Formalize when cohort IDs are public vs key-gated; align Query lab and MCP exports with the same rules as `/search`.

7. **Facet schema evolution**  
   Adding a dimension is an append to `DEFAULT_FACET_ORDER` (see docstring in `facet_tree.py`). Research which new extractors (agencies, modalities, eras) earn a permanent tree level without exploding width.

---

## 6. Quick paths

| Task | Start here |
|------|------------|
| Explore cohorts visually | `/search` |
| Verify extraction on a cohort | Search → copy IDs → `/audit` |
| Count platforms / ontology relations | `/sparql` or Patterns; `ontology/docs/SPARQL.md` |
| Agent-driven cohort work | MCP `get_facet_tree` / `get_cohort_members` / `filter_cases_by_tags` |
| Collect new press / court docs | `collector/README.md` + MCP collector tools (not Search) |
| Accuracy / CAC gates on PDFs | `scripts/verify/verify_cac.py`, `check_expand_novelty.py` |

Product overview also lives in the root **README** (Using Search, Ontology & Graphs, MCP). This file is the discovery map and research backlog for Search-adjacent work.
