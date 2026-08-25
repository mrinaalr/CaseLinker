# CaseLinker

**CaseLinker** is a project designed to group and visualize **statistical** and **contextual** information from cases involving crimes against children and child sexual exploitation & abuse (CSEA).

## Live Demo

**Try the latest version online:** [https://caselinker.up.railway.app/](https://caselinker.up.railway.app/)

The live release includes all features and a processed case corpus from publicly available ICAC / NCMEC / DOJ / State Attorneys General press materials. The corpus holds **7,426 cases** across **56** ingestion sources. Live counts and per-source coverage are on the in-app **Sources** page. These reports summarize investigations, arrests, and prosecutions, redacted for public release. No PII was processed; all data was already in the public domain. No installation required — just open the link in your browser.

## Technical Reports

- **Report #1: [CaseLinker: An Open-Source System for Cross-Case Analysis of Internet Crimes Against Children Reports](https://arxiv.org/abs/2603.18020)** - Initial technical report documenting the prototype architecture, deterministic extraction pipeline, and evaluation baseline on 47 cases.

- **Report #2: [Interpretable ML Approaches for Analyzing Internet Crimes Against Children Reports](https://mrinaalr.github.io/website/CaseLinker-%20Interpretable%20ML%20Approaches%20for%20Analyzing%20Internet%20Crimes%20Against%20Children%20Reports.pdf)** - Second report covering NER integration, dataset expansion to 207 cases, and emerging patterns from the expanded dataset including the distributed network of 215 law enforcement organizations.

- **Report #3: [5 Sources, 500 Cases, and Scaling Considerations](https://mrinaalr.github.io/website/Scaling.pdf)** - Third report covering the addition of 3 new sources, facet-tree search, and data utility.

- **Report #4: [Framework for Retrospective Analysis and Case Studies of Internet Crimes Against Children Across U.S. Task Forces](https://mrinaalr.github.io/website/Framework.pdf)** - Fourth report establishing a replicable and extensible case study methodology: four-era framework (2010-2026), stratified sampling across eras, a five-dimension case study structure, and the legal and ethical grounding for the analysis.

- **Report #5: [Painting the Landscape of Internet Crimes Against Children with Interpretive Tooling](https://mrinaalr.github.io/website/PaintingTheLandscapeOfInternetCrimesAgainstChildrenWithInterpretiveTooling.html)** - Fifth and final report: a ten-page visual briefing on sixteen years of U.S. ICAC enforcement, presenting the extraction and analysis framework, 20 case studies across four eras, and aggregate findings across 5,000+ cases.

## Motivation

This project was motivated by challenges I encountered with understanding child exploitation cases, including:

- **Fragmented data sources**: Cases are scattered across numerous organizations, states, and agencies
- **Cross-case analysis**: Identifying patterns, similarities, and connections between cases becomes challenging without a unified system, even when cases share common characteristics such as abuse patterns, platforms, or perpetrator demographics
- **Limitations in trend analysis**: Analyzing the evolution of child exploitation, the mediums in which it occurs, and recurring case topics
- **Emotional impact**: The challenge of repeatedly reading and processing highly disturbing case material

CaseLinker aims to address these challenges by serving as a tool for case analysis, enabling researchers, law enforcement, and advocacy organizations to better understand the landscape of child exploitation.

## Emphasis

- **Feature extraction**: Robust extraction of information from cases and explainability for clusters and analysis
- **Clustering and linking**: Cases based on shared characteristics such as victim context, platforms used, and law enforcement actions
- **Visualization**: With particular attention to tasteful presentation of case content, and pattern analysis across investigations

## System Architecture

CaseLinker follows a modular, layered architecture:

1. **Ingestion Layer**: Handles PDF data sources with text extraction and validation
2. **Processing Layer**: Extracts features, assigns comparison values, and fills case schema
3. **Storage Layer**: PostgreSQL (production) / SQLite (local development) - Database-agnostic implementation
4. **Clustering & Analysis Layer**: Case comparison, similarity detection, automated grouping, triage, and insights generation
5. **Visualization Layer**: Interactive web dashboards (platform harm dashboard, lifecycle state machines, facet tree search, analysis views)

## Installation

### Option 1: Use Live Demo (Recommended for Quick Testing)

**No installation required.** Visit the live deployment:
- **Live Application**: [https://caselinker.up.railway.app](https://caselinker.up.railway.app)

The live version includes all features and a processed case corpus. Created for quick testing and demonstrations.

### Option 2: Local Setup (Works Out of the Box)

```bash
# Clone the repository
git clone https://github.com/mrinaalr/CaseLinker.git
cd CaseLinker

# Run setup script (creates venv and installs dependencies)
./setup.sh

# Activate virtual environment
source .venv/bin/activate

# Start the main application
python3 run/main.py
```

Then open your browser to:
- **Home**: http://localhost:8000/
- **Visualizations**: http://localhost:8000/visualization
- **Advanced Analysis**: http://localhost:8000/analysis
- **Clusters**: http://localhost:8000/clusters
- **Stats**: http://localhost:8000/stats
- **Search**: http://localhost:8000/search
- **Query**: http://localhost:8000/query 
- **Lifecycle**: http://localhost:8000/lifecycle
- **Triage**: http://localhost:8000/triage
- **Patterns (Phase 2)**: http://localhost:8000/patterns
- **Tech Landscape**: http://localhost:8000/tech-landscape
- **LLM**: http://localhost:8000/llm
- **Data Sources**: http://localhost:8000/sources
- **Data Audit**: http://localhost:8000/audit
- **Look Under the Hood**: http://localhost:8000/under-the-hood
- **Case Studies**: http://localhost:8000/case-studies
- **API Documentation**: http://localhost:8000/docs


**Database:**
- **Production (Railway)**: PostgreSQL with encrypted connections and managed backups
- **Local Development**: SQLite (`caselinker.db`) - created automatically when 
running locally, initially empty

**What a fresh clone includes** (works with an empty DB):

| Included | Path | Local use |
|-------|------|-----------|
| Ontology case graphs (~7k+ expressed via CASE/UCO/CAC) | `ontology/graph_output/` | `/patterns/graph`, `/api/ontology/*` |
| PACER lifecycle state machines (30 cases) | `state_machines/graphs/`, `ontology/PACER/` | `/lifecycle` |
| L* trajectories / transition matrix | `state_machines/data/lstar_all_cases.json` | `/api/lifecycle/lstar` |
| Case studies (21 across 4 eras) | `data/case_studies.json` | `/case-studies` |
| Triage model bundle | `models/triage_bundle.joblib` | `/triage`, `/api/triage-live` |


**Reproduce the local corpus DB** (two options):

1. **Trusted API export** (full production corpus in one shot) — request a `CaseLinker-Key` at **mramachandra@umass.edu**, then:

```bash
source .venv/bin/activate
export CASELINKER_KEY='your-trusted-key'
python3 scripts/run/import_corpus_from_api.py
python3 run/main.py
```

2. **PDF ingest** (build from public data you collect; see **Process Your Own PDF Files** below):

```bash
source .venv/bin/activate
python3 src/main.py "path/to/your/file.pdf"

# or, after placing multiple PDFs in the repo root:

./scripts/run/ingest_all_pdfs.sh
python3 run/main.py
```

You can process additional PDFs to add more cases to the database.

## Usage

### ⚠️ Important: Data Content and Warning

**CaseLinker processes publicly available case reports and related records for research, analytical, and investigative workflow purposes.**

**While all source materials are drawn from public reports, content involves descriptions of child exploitation, abuse, or other disturbing criminal case details that may be difficult to read.**

**Please proceed with awareness of the sensitive nature of the material and use the project responsibly for research, academic, or authorized analytical purposes.**


## Entry Points

1. **`src/main.py`** - **CLI Tool for Processing PDFs**
   - Processes PDF files to extract and store cases in the database
   - Run this when you want to add new cases from PDF files
   - Extracts text, identifies sources, splits cases, extracts features, and stores them
   - Pre-computes clusters after storing new cases

2. **`run/main.py`** - **Main application**
   - Starts the web server that serves the visualization interface and API
   - Run this to access the web interface and visualizations
   - Uses pre-computes clusters on startup for fast performance
   - Provides REST API endpoints for case data, analysis, and statistics

3. **`caselinker_mcp/server.py`** — **MCP server for agent and LLM analysis**
   - Exposes **37 tools**: corpus search, triage, Q1 platform evidence, on-demand `case2cac` cohort graphs, Turtle export (`export_case_graph_ttl`), and graph traversal
   - Read-only; wraps the existing REST API; no database mutation
   - Reach out for private mcp.json keys and review `caselinker_mcp/README.md` & `caselinker_mcp/tool_registry.md` for setup, auth and the full tool catalog

**Typical use case:**
1. First, populate the database with processed PDFs or request a trusted API key
2. Then, start the web server with `run/main.py` to view and analyze cases
3. Optionally, connect an MCP client (Cursor, Claude Desktop, or any MCP-compatible host) via **stdio**, **SSE**, or **Streamable HTTP**

## Process Your Own PDF Files

**The local database starts empty.** To populate it with cases, you need to process PDF files you want to ingest.

### Finding PDF Sources

Visit the **Sources** page to see links for collecting sources:
- **Live Demo Sources Page**: [https://caselinker.up.railway.app/sources](https://caselinker.up.railway.app/sources)
- Or visit `/sources` when running locally: http://localhost:8000/sources

Processed sources include:
- **Arizona ICAC (AZICAC)**: Annual case reports and arrests (AZICAC)
- **National Center for Missing & Exploited Children (NCMEC)**: Case 
summaries and CyberTipline-related publications
- **Georgia Bureau of Investigation (GBI)**: CEACC / Georgia ICAC press releases
- **Idaho Office of Attorney General (Idaho ICAC)**: ICAC newsroom press releases
- **Texas Office of the Attorney General (Texas AG)**: Cyber Crimes / ICAC-related press releases
- **Michigan State Police (Michigan ICAC)**: MSP newsroom ICAC releases
- **Silicon Valley ICAC (SVICAC)**: Regional "In The News" articles
- **Tennessee Bureau of Investigation (TBI ICAC)**: TBI newsroom ICAC search results
- **South Carolina Attorney General (SCAG ICAC)**: ICAC-tagged news releases
- **New York State Police (NEWYORK SP)**: NYSP newsroom ICAC keyword search
- **Illinois Attorney General (ILLINOIS AG)**: ICAC press release search
- **Pennsylvania Office of the Attorney General (PA AG)**: Child Predator / ICAC-related releases
- **New Jersey Office of the Attorney General (NJ AG)**: ICAC site search
- **Washoe County Sheriff's Office (WCSO)**: Nevada ICAC newsroom search
- **Fresno County Sheriff's Office (FRESNO SO)**: ICAC site search
- **Osceola County Sheriff's Office (OSCEOLA SO)**: ICAC site search
- **Las Vegas Metropolitan Police Department (LVMPD)**: ICAC site search
- **San Jose Police Department (SJPD)**: ICAC / child exploitation press search
- **Los Angeles Police Department (LAPD)**: ICAC news search
- **Seattle Police Department (SPD)**: SPD Blotter ICAC search
- **San Diego Police Department (SDPD)**: City of San Diego ICAC site search
- **Colorado Springs Police Department (CSPD)**: ICAC site search
- **Hawaii Department of the Attorney General (HI AG)**: HICAC media and press
- **Cook County State's Attorney (CCSAO)**: ICAC unit news releases
- **South Florida ICAC (SOUTH FLORIDA ICAC)**: Regional task force news index
- **Florida Office of the Attorney General (FL AG)**: ICAC site search
- **Vermont Office of the Attorney General (VT AG)**: Child-related / ICAC releases
- **Rhode Island Office of the Attorney General (RI AG)**: ICAC site search
- **Ohio Attorney General (OHIO AG)**: ICAC / child-related news search
- **Delaware Department of Justice (DE AG)**: Child Predator Task Force / ICAC releases
- **Sedgwick County Sheriff's Office (SEDGWICK SO)**: Child exploitation press search
- **Anchorage Police Department (ANCHORAGE PD)**: Alaska ICAC-related releases
- **Mississippi Attorney General (MS AG)**: ICAC media releases
- **Montana Department of Justice (MT DOJ)**: Child-related press releases
- **New Mexico Attorney General's Office (NM AG)**: ICAC site search
- **North Carolina State Bureau of Investigation (NC SBI)**: ICAC news search
- **Louisiana Office of the Attorney General (LA AG)**: ICAC news releases
- **Utah Attorney General (UT AG)**: ICAC site search
- **Washington State Office of the Attorney General (WA AG)**: Child-related news search
- **Oregon Department of Justice (OREGON DOJ)**: ICAC site search
- **Wyoming Division of Criminal Investigation (WY DCI)**: ICAC / Computer Crime news
- **Iowa Division of Criminal Investigation (IA DCI)**: ICAC site search
- **Arkansas Department of Public Safety (ARKANSAS DPS)**: ICAC / ASP news search
- **Alabama Law Enforcement Agency (ALEA)**: SBI / ICAC news search
- **South Dakota Office of the Attorney General (SD AG)**: ICAC press releases
- **Kentucky State Police (KY SP)**: News archive ICAC search
- **Nebraska State Patrol (NE SP)**: Child exploitation press search
- **U.S. Army Criminal Investigation Division (ARMY CID)**: ICAC releases
- **U.S. Air Force Office of Special Investigations (AF OSI)**: Child sexual abuse material and exploitation press releases 
- **U.S. Customs and Border Protection (CBP)**: Newsroom releases on child sexual exploitation and related border enforcement (site search)
- **U.S. Immigration and Customs Enforcement (ICE)**: HSI child-exploitation press releases
- **Naval Criminal Investigative Service (NCIS)**: Child exploitation and related investigation press releases 
- **U.S. DOJ CEOS (DOJ CEOS)**: Child Exploitation and Obscenity Section press releases
- **U.S. DOJ CEOS Archives (DOJ ARCHIVES)**: Archived CEOS criminal press releases (2002-2008)
- **U.S. Secret Service (USSS)**: ICAC-related newsroom press releases (ICAC task forces, CSAM, and child exploitation search results)
- **U.S. Marshals Service (US MARSHALS)**: Press releases on child predators, sexual-assault fugitives, and recovered minors 

### Processing PDFs to Populate Database

Once you have PDF files, process them using the CLI tool:

**Single PDF:**
```bash
source .venv/bin/activate
python3 src/main.py "path/to/your/file.pdf"
```

**Multiple PDFs:**
```bash
python3 src/main.py "2011 Cases and Arrests – AZICAC.ORG.pdf" "2020 Reports" "2024-media-coverage-cybertipline-success-stories.pdf" 
```

**All PDFs under the repo** (e.g. after a fresh DB wipe):
```bash
./scripts/run/ingest_all_pdfs.sh

# Skip NCMEC/DOJ on first pass if you want state feeds first:

./scripts/run/ingest_all_pdfs.sh --no-aggregate
```

The system will:
1. Extract text from each PDF
2. Identify organization name from filename (AZICAC, NCMEC, etc.)
3. Batch cases, extract features, assign case IDs
4. Store all cases in the local SQLite database
5. Pre-compute clusters for fast visualization

## Using the Visualizations

Access the **Platform Harm Dashboard** via the [live demo](https://caselinker.up.railway.app/visualization) or locally at http://localhost:8000/visualization.

**Dashboard features**:

- **Lifecycle map**: platforms placed on six exploitation lanes (distribution, storage, communities, discovery, messaging, production)
- **Detail panel**: per-platform analysis with four tabs:
  - **Affordances** → what the medium enables
  - **Misuse Surface** → how offenders abuse those properties
  - **Harm Vectors** → victim-facing harm pathways
  - **Case Evidence** → expandable quotes from `q1_evidence.json`; links to Audit for full case review
- **Filters**: search by platform name; narrow by evidence tier


## Using Search

Access Search via the [live demo](https://caselinker.up.railway.app/search) or locally at http://localhost:8000/search

Search provides a **facet decision tree** over the stored case corpus: the server builds a deterministic partition tree from structured facets (not a precomputed file on disk). The view uses **D3.js** (SVG) to render cohort nodes and edges. You can limit tree depth, **prune** which partition dimensions apply and optionally filter allowed values per facet (extracted feature), then **click any node** (branch or leaf) to list **case IDs** in that cohort for use elsewhere (e.g. single-case visualization, manual cross-case analysis). Small cohorts (fewer than three cases) have IDs gated behind a demo access key. See `src/Storage Layer/facet_tree.py` and `/api/facet-tree` for the partition order and semantics.


## Using Advanced Case Analysis and Triage

Navigate to [live demo](https://caselinker.up.railway.app/analysis) or run server locally and navigate to http://localhost:8000/analysis.


1. **Tag-Based Analysis (Run Advanced Analysis)**:
   - Select one or more tags from categories: Case Topics, Severity Indicators, Platforms & Environments, Investigation Types, Perpetrator Relationships, Perpetrator Status
   - Click "Run Advanced Analysis" to find all cases matching ALL selected tags (intersection logic)
   - View matching cases with highlighted text showing where tags were found in the raw case data
   - See case counts for each selected tag

2. **Automated Analysis (Run Automated Analysis)**:
   - Click "Run Automated Analysis" to run the full automated analysis pipeline
   - **Case Groups**: View cases grouped by similarity (platforms, demographics, topics, severity, investigation)
   - **Top Priority Cases**: See cases sorted by priority score (normalized to 5-10 scale) based on:
     - Severity indicators (35%): infant, rape, very_young, physical_abuse
     - Victim count (30%): Higher scores for multiple victims
      - Case type (25%): production, hands_on, possession, online_only
     - Severity phrases (15%): dangerous, stated, told, continue, attacked, out_of_control, attracted
     - Evidence volume (10%): images, videos, storage size
     - Registered sex offender (10%): Repeat offender status
   - **Automated Insights**: View insights about most common platforms, severity distribution, and case topics
   - **Patterns Detected**: See patterns like repeat offenders, relationship patterns, and investigation focus
   - **Top Keywords**: View most frequent keywords extracted from case text
   - **Expandable Details**: Click any box to view raw case data with highlighted priority indicators and detailed explanations of why the analysis prioritized/grouped the case

Access Triage via the [live demo](https://caselinker.up.railway.app/triage) or locally at http://localhost:8000/triage. Current implementation uses **rule-based** priority tiers, **ML Classification for triage** (random forest or decision tree trained on features from the database with labels derived from deterministic rules), optionally constrained by the same facet-dimension filtering used in Search, and supports **paste-in live triage** that scores text in memory without writing to the database. For the full triage documentation (rules, bundle paths, APIs, live paste), see **`triage.md`** in the repo root.

## Phase 2: Patterns ([local](http://localhost:8000/patterns) · [live](https://caselinker.up.railway.app/patterns)) is an ongoing stage of research for cross-case pattern analysis ontop of the corpus.

### Section A — The Research Questions

Three questions drive Phase 2; each builds on the last. Findings pages: [`/patterns/questions/q01`](https://caselinker.up.railway.app/patterns/questions/q01) (Q1), [`q02`](https://caselinker.up.railway.app/patterns/questions/q02) (Q2), [`q03`](https://caselinker.up.railway.app/patterns/questions/q03) (Q3).

| Question | Focus | Why it matters |
|----------|--------|----------------|
| **Q1 — Platform harm** | What is the platform and what capabilities does it have? How has it been misused in practice, and what surfaces, vectors, and avenues for exploitation does it expose? What specifically about this medium makes it usable for exploitation? Can those properties be  generalized into a framework for stress-testing future platforms? | Press releases and online harms research often name platforms but rarely explain *what about the medium* enabled the offense. Affordance-level analysis turns platform mentions and documented crimes into a transferable framework. Evidence: `ontology/q1/` ([`q1_evidence.json`](ontology/q1/q1_evidence.json)) |
| **Q2 — Exploitation lifecycle** | What does offending and enforcement look like at scale across offense subsets (familial abuse, grooming, sextortion, production, possession, etc.)? What platforms, methods, and patterns recur within each? | Most ICAC research works in hashing, aggregate counts, or single-case narratives. The lifecycle view, stratified by subset, shows how offending and enforcement unfold across thousands of cases. Evidence: `ontology/q2/` ([`q2_lifecycle.json`](ontology/q2/q2_lifecycle.json), [`q2_evidence.py`](ontology/q2/q2_evidence.py)). |
| **Q3 — Kill-chain interventions** | Given Q1 and Q2, where can technology, investigation, or enforcement intervene with the most leverage? | Platform mapping and lifecycle analysis exist to answer the operational question: where disruption is most plausible (detection, reporting, warrant execution, prevention). Evidence: `ontology/q3/` ([`q3_interventions.json`](ontology/q3/q3_interventions.json), [`q3_evidence.py`](ontology/q3/q3_evidence.py)). |

Rebuild evidence tables locally:

```bash
python3 ontology/q1/build_candidates.py && python3 ontology/q1/q1_evidence.py
python3 ontology/q2/build_candidates.py && python3 ontology/q2/q2_evidence.py
python3 ontology/q3/build_candidates.py && python3 ontology/q3/q3_evidence.py
```

### Section B — The Method: Ontology Pipeline

To answer Q1–Q3 at corpus scale, enforcement narratives cannot stay only in relational tables and regex-derived tags. They must be expressed in a **structured, graph-queryable** form so patterns can be queried, validated, and compared across cases. CaseLinker already extracts consistent features from each narrative; the **ontology pipeline** maps those features into a standard investigation vocabulary and builds a validated knowledge graph as the mechanism for cross-case analysis.

**What is an ontology:** The [CAC Ontology](https://github.com/Project-VIC-International/CAC-Ontology) (Crimes Against Children Ontology) is a formal vocabulary developed to model the entities of a child-exploitation investigation as typed, related objects: platforms, victims, offenders, investigations, and outcomes. CAC is shepherded by [Project VIC International](https://www.projectvic.org/) and is built on the Linux Foundation's [Cyber Domain Ontology](https://cyberdomainontology.org/) stack ([UCO](https://unifiedcyberontology.org/) and [CASE](https://caseontology.org/)). CaseLinker case data is being aligned to this vocabulary so graphs can be shared, validated, and queried with the same tools used in forensic and intelligence workflows.

**How CaseLinker uses ontologies:** A deterministic mapping layer translates each case's extracted features into CAC entities and relationships, emits per-case RDF graphs, validates them, and merges conformant graphs into a queryable knowledge graph.

**Pipeline flow**:

1. **CaseLinker case features** — already extracted (platforms, topics, investigation signals, prosecution outcomes).
2. **Mapping layer** — deterministic translation to CAC entities and relationships (`ontology/graph_generate.py`).
3. **RDF emission** — per-case graphs as Turtle and JSON-LD under `ontology/graph_output/`.
4. **SHACL validation** — only conformant graphs enter the merged corpus.
5. **SPARQL-queryable corpus** — canonical per-case graphs are loaded into Oxigraph (named graph per case; union default graph) and served at `GET|POST /sparql`.

Agents can also build cohort graphs on demand via MCP (`case2cac` → `graph_summarize` → `export_case_graph_ttl`), or query the live store with the [CASE/UCO SDK](https://github.com/vulnmaster/CASE-UCO-SDK) `execute_sparql_query` tool.


**Public SPARQL** (`GET|POST /sparql`) — SPARQL 1.1 Query only (`SELECT`, `CONSTRUCT`, `ASK`, `DESCRIBE`). No auth. Update and `SERVICE` are rejected. Rate limit is **30/minute** per IP. If a query has no outer `LIMIT`, the proxy injects **1000**; outer `LIMIT` above **10,000** is rejected. Each case is named graph `https://caselinker.up.railway.app/resource/case/{case_id}`; default-graph patterns see the union. Request formats, namespaces, errors, and more examples: **[ontology/docs/SPARQL.md](ontology/docs/SPARQL.md)**.

```bash
curl -sS -X POST 'https://caselinker.up.railway.app/sparql' \
  -H 'Content-Type: application/sparql-query' \
  -H 'Accept: application/sparql-results+json' \
  --data-binary @- <<'SPARQL'
PREFIX cac: <https://cacontology.projectvic.org#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?platform ?label (COUNT(DISTINCT ?case) AS ?cases)
WHERE {
  ?event cac:usesChannel ?platform .
  ?platform rdfs:label ?label .
  ?case a cac:CACInvestigation ; cac:hasStep ?event .
}
GROUP BY ?platform ?label
ORDER BY DESC(?cases)
LIMIT 8
SPARQL
```

Full ontology documentation (vocabulary, pipeline, graph pools, Q1–Q3, PACER, code map): **[ontology/README.md](ontology/README.md)**.


**References**
- [CAC Ontology repository](https://github.com/Project-VIC-International/CAC-Ontology)
- [CASE/UCO SDK with CAC bindings](https://github.com/vulnmaster/CASE-UCO-SDK)
- [CASE](https://github.com/casework/CASE)
- [UCO](https://github.com/ucoProject/UCO)
- [Project VIC International](https://projectvic.org/)


## Other Features

- **Sources Tab**: View data sources and access original case reports
- **Clusters Tab**: View pre-computed clusters and analyze case reports
- **Stats Tab**: Coverage over the dataset and case distributions
- **Tech Landscape**: Technology revolver (platforms, investigation tech, anonymization, P2P) by era
- **Lifecycle**: PACER exploitation lifecycles. Five offense types as CAC ontology state machines
- **Query**: Custom analysis lab (public APIs)
- **LLM**: Natural-language queries over case statistics (SQL-backed; rate limited on production)
- **Case Studies Tab**: Era-organized narrative case studies (`data/case_studies.json`)
- **Audit Tab**: Review extracted features case-by-case with interactive highlighting to verify extraction accuracy

## Project Structure

```
CaseLinker/
├── src/
│   ├── Ingestion Layer/              # PDF extraction, source detection, ingest_file
│   ├── Processing Layer/             # batching.py, processing.py, merge_processing.py
│   │   ├── Pattern Processing Layer/ # Regex / rule-based feature extraction
│   │   └── ML Processing Layer/      # NER, semantic concepts, content sanitization
│   ├── Storage Layer/                # SQLite + PostgreSQL storage, facet_tree.py
│   ├── Clustering & Analysis Layer/  # analysis.py, triage.py
│   ├── Visualization Layer/          # Server-side viz helpers
│   └── main.py                       # CLI: ingest PDFs → process → store
├── run/
│   ├── main.py                       # FastAPI app: pages + REST API + /sparql
│   ├── sparql_proxy.py               # SPARQL parser policy (LIMIT / Update / SERVICE)
│   ├── redis_cache.py                # Optional Redis caching (production)
│   └── auth.py                       # Access gates / keys for sensitive views
├── scripts/
│   ├── rebuild_oxigraph.py           # Wholesale Oxigraph reload (N-Quads PUT /store)
│   ├── stats/                        # Corpus statistics scripts
│   ├── verify/                       # Claims, uniqueness, ICAC TF alignment, triage tests
│   ├── run/                          # ingest_all_pdfs.sh, import_corpus_from_api.py, clear_postgres.py, train_triage_model.py
│   └── scraper/                      # fetch_source_urls.py, scrape_pdf.py
├── visualization/                    # Static HTML (served by run/main.py)
│   ├── assets/                       # caselinker-api.js, cover.png
│   ├── home.html                     # /
│   ├── visualization.html            # /visualization
│   ├── search.html                   # /search (facet tree)
│   ├── analysis.html                 # /analysis
│   ├── clusters.html                 # /clusters
│   ├── stats.html                    # /stats
│   ├── query.html                    # /query
│   ├── lifecycle.html                # /lifecycle
│   ├── triage.html                   # /triage
│   ├── patterns.html                 # /patterns
│   ├── patterns-graph.html           # /patterns/graph
│   ├── questions/                    # /patterns/questions/q01–q03
│   ├── tech-landscape.html           # /tech-landscape
│   ├── LLM.html                      # /llm
│   ├── sources.html                  # /sources
│   ├── case-studies.html             # /case-studies
│   ├── audit.html                    # /audit
│   └── under-the-hood.html           # /under-the-hood
├── ontology/
│   ├── README.md                     # Ontology docs (vocabulary, pipeline, pools)
│   ├── docs/SPARQL.md                # Public SPARQL 1.1 API guide
│   ├── features_to_cac.py            # Case features → CAC RDF
│   ├── graph_generate.py             # Batch TTL / JSON-LD
│   ├── oxigraph_rebuild.py           # Canonical TTL → named-graph N-Quads
│   ├── q1/ q2/ q3/                   # Research evidence
│   ├── PACER/                        # PACER → lifecycle facts
│   └── graph_output/                 # staging + universe/ + big_bang/ + analysis/
├── caselinker_mcp/                   # MCP server (37 tools; SSE + Streamable HTTP on Railway)
│   ├── server.py                     # FastMCP entry point
│   ├── README.md                     # Hosted auth, Cursor config, graph workflow
│   └── tool_registry.md              # Full tool catalog
├── models/                           # triage_bundle.joblib (optional; see /triage)
├── data/                             # case_studies.json for /case-studies
├── setup.sh
├── requirements.txt                  # Core deps
├── requirements-ml.txt               # Optional ML / NER stack
├── config.py
├── caselinker.db                     # SQLite (local; created on first ingest)
├── triage.md                         # Triage rules and model docs
├── Procfile                          # Railway / Heroku start command
└── Architecture design.md
```

## Case Schema & Feature Extraction

Each case includes structured features extracted from case narratives:

### **Regex extraction**

- **Perpetrator**: Age(s), registered sex offender status, gender when stated; flags for multi-defendant operations
- **Victim**: Age(s), age ranges, count when explicitly stated in victim-clause phrasing, gender after validation
- **Relationship**: Kin and role labels (father, mother, parent, sibling, teacher, coach, stranger, etc.); unknown when not stated
- **Platforms**: Named apps and surfaces — social, messaging, gaming, file hosting, livestreaming, early-era chat, Gen AI tools when cited — plus generic online, chat, or social media when no product matches
- **Technology signals** (stored separately from the platform list): investigation tooling (PhotoDNA, hash matching, CyberTipline language), anonymization (Tor, dark web, cryptocurrency), P2P clients
- **Prosecution**: Charge phrases with counts, booking stage (arrest through sentenced), jail mentions, sentence durations
- **Evidence volume**: Image, video, storage, and message counts when quantified in text
- **Investigation**: Non-exclusive types — proactive, reactive, online, undercover, CyberTipline-origin, or unknown; agencies from pattern matching plus NER supplements
- **Prior record**: Registered status and age at prior arrest when stated

### **Pattern-based classification**

- **Case topics**: production, possession, distribution, trafficking, csam, ai_csam, sextortion, hands_on vs online_only, family vs stranger, international, multi_state
- **Severity indicators**: infant, very_young, under_12, sexual_abuse; multiple_perpetrators when several offender ages are extracted
- **Severity phrases**: dangerous, stated, told, continue, attacked, out_of_control, attracted — used in priority scoring

### **ML enrichment**
When the ML stack is enabled, NER adds organizations, locations, dates, and ages, merged with regex output. A victim-age gate drops decoy and headline ages. Semantic sentence scoring stores concept scores on each case; grooming may add a severity tag, and strong possession or AI-generation language may reinforce case topics. Most concept scores are kept for analysis; only selected ones are merged in with main fields.

### **Clustering & storage**
- **Comparison values**: Normalized vectors (platforms, demographics, investigation, evidence, topics, severity, date) for similarity and pre-computed clusters
- **Agency pathways**: Federal vs state/local splits where inferable from narrative context
- **Preserved data**: Raw narrative, source organization, source URL when present, source publication date from formatted PDFs, timestamps

## API Endpoints

- `GET /` - Home page
- `GET /api/cases` - Full bulk case export (localhost or `CaseLinker-Key` in `CASELINKER_TRUSTED_KEYS`)
- `GET /api/cases-summaries-chunk` - Public paginated summaries (`offset`, `limit` ≤ 500); UI loads the full timeline via many small responses, not one bulk JSON
- `POST /api/cases-summaries-by-ids` - Public batched summaries (max 500 ids per request) for cluster membership and similar flows
- `GET /api/cases/{case_id}` - Single case (public responses omit `raw_data`; narrative available as `case_text` for UI drill-down)
- `GET /api/case-count` - Total case count (public, rate limited)
- `GET /api/case-ids-by-filter` - Case IDs matching filter query params (public, rate limited)
- `GET /api/tags` - Distinct tag values across the corpus (public, rate limited)
- `POST /api/tag-threader` - Tag co-occurrence threading analysis (public, rate limited)
- `GET /visualization` - Platform Harm Dashboard (Q1 affordance-misuse-harm analysis, tiered evidence, manual platform analysis)
- `GET /api/q1/platform-evidence` - Q1 platform evidence index or per-platform cohort (`platform`, optional `tier`)
- `GET /search` - Facet decision tree over stored cases (D3); prune filters; cohort case IDs via API
- `GET /query` - Custom analysis lab (browser-only JavaScript calling public APIs; see page for examples)
- `GET /lifecycle` - Exploitation lifecycle visualization (public HTML; payload embedded server-side)
- `GET /api/lifecycle/cases` - Lifecycle JSON (trusted `CaseLinker-Key` or localhost; same gate as `GET /api/cases`)
- `GET /api/lifecycle/lstar` - Full L* output (`state_machines/data/lstar_all_cases.json`; trusted key or localhost)
- `GET /api/lifecycle/canonical` - Public JSON for the 5 canonical PACER state-machine cases (no key; rate limited; intended for external embeds)
- `GET /analysis` - Advanced case analysis page with tag-based filtering and automated analysis
- `GET /api/facet-tree` - Build facet tree JSON (`max_depth`, optional prune query params)
- `GET /api/facet-distinct` - Distinct primary-bucket values per facet (for Search prune UI)
- `POST /api/facet-cohort-members` - Case IDs for a facet path (same prune semantics as tree; small cohorts gated)
- `GET /triage` - Triage page (rules, model evaluation, corpus model tiers, live paste)
- `GET /patterns` - Phase 2: Patterns research documentation page
- `GET /patterns/graph` - Merged CAC ontology graph explorer (compare / Big Bang pools)
- `GET /patterns/questions/{question_id}` - Q01–Q03 narrative question pages
- `GET /mcp/sse` - MCP SSE transport (requires `Authorization: Bearer <MCP_ACCESS_KEY>`)
- `GET|POST /mcp-http/` - MCP Streamable HTTP transport (same auth)
- `GET|POST /sparql` - SPARQL 1.1 Query proxy over the CASE/UCO/CAC case graphs (public, 30/minute; query-only; [ontology/docs/SPARQL.md](ontology/docs/SPARQL.md))
- `GET /api/ontology/merged` - Merged graph JSON (`pool=compare|all|universe|analysis`; public, cached)
- `GET /api/ontology/cases` - Per-case graph catalog (`pool=compare|all|universe|analysis`; public metadata: `case_id`, `path`, `ttl_path`)
- `GET /ontology/graph_output/{pool}/{case_id}.jsonld|.ttl` - Static per-case CAC graph files (public)
- `GET /ontology/q1/*`, `/ontology/q2/*`, `/ontology/q3/*`, `/ontology/question_data/*` - Static Q1–Q3 evidence JSON (public)
- `GET /ontology/q_results.json` - Aggregated question results JSON when present (public)
- `POST /api/ontology/cache/warm` - Rebuild/warm the merged-graph cache (`pool=compare|all|universe|analysis|both`)
- `GET /api/triage-eval` - Stratified train/test metrics on live cases (same pipeline as `scripts/verify/test_triage.py`)
- `GET /api/triage-model-corpus` - Saved bundle predictions over live DB; optional `facet_constraints` JSON query param (rate limited)
- `POST /api/triage-live` - Classify pasted batch text in memory only; requires bundle; no persistence
- `GET /sources` - Data sources page
- `GET /case-studies` - Case studies reading room (eras + studies from `data/case_studies.json`)
- `GET /api/case-studies` - Case study content document (eras, studies, default form URL)
- `GET /api/case-studies/notes/{case_id}` - Community notes for a study id
- `POST /api/case-studies/notes/{case_id}` - Append a community note (rate limited)
- `GET /audit` - Data audit page for reviewing extracted features case-by-case
- `GET /api/automated-analysis` - Run automated analysis (case grouping, triage, insights)
- `POST /api/return-tagged-cases` - Get cases matching selected tags (intersection logic)
- `GET /api/stats` - Get case statistics (total cases, extracted features count, sources)
- `GET /api/stats-detailed` - Detailed corpus statistics (public, rate limited)
- `GET /api/location-stats` - Location/geography aggregates (public, rate limited)
- `GET /api/technology-revolver` - Technology-by-era data keyed by era buckets (public, rate limited)
- `GET /api/cluster-groups` - Pre-computed similarity cluster groups (public, rate limited)
- `GET /stats` - Statistics dashboard page
- `GET /clusters` - Cluster explorer page
- `GET /tech-landscape` - Technology landscape page
- `GET /under-the-hood` - Architecture/methodology page
- `GET /llm` - LLM chat page
- `POST /api/llm/chat` - LLM chat endpoint (public; per-IP daily cap, exempt for localhost/trusted key)
- `POST /api/cache/clear` - Clear server caches (rate limited 10/hour)
- `GET /api` - API info root; `GET /healthz` - health check
- `GET /docs` - Interactive API documentation

## Technology Stack

- **Backend**: Python 3, FastAPI, Uvicorn
- **Data Processing**: Pandas, NumPy
- **PDF Processing**: pdfplumber
- **Database**: PostgreSQL (production) / SQLite (local development)
  - Production: Railway PostgreSQL with encrypted connections
  - Local: SQLite database auto-created on first run
- **Visualization**: D3.js, HTML/CSS/JavaScript
- **ML/NER**: 
  - Stanza primary NER model; optional Transformers/spaCy paths in code
  - Semantic concept scoring (grooming, possession, AI-generated CSAM language, and related themes) merged into case topics and severity where thresholds are met
  - **Supervised triage (experimental)**: scikit-learn random forest or decision tree; labels from rule-based priority scores; `joblib` bundle loaded at inference time
- **Architecture**: Modular 5-layer design

## Deployment

CaseLinker can be deployed to cloud platforms for public access. The app includes a `Procfile` for deployment to Railway, Heroku, and similar platforms. The SPARQL proxy reads `OXIGRAPH_URL` (private Oxigraph base URL). After regenerating case graphs, reload the store with `python3 scripts/rebuild_oxigraph.py` (wholesale overwrite, not incremental).


## Sources and Ethics
- **No Sensitive Data**: This system contains cases from publicly available sources (ICAC Task Forces Cases and Arrests, NCMEC CyberTipline Success Stories, DOJ CEOS Press Releases, and State Attorneys General's Office Press Releases). These reports are publicly available, summarize investigations, arrests, and case details, and are redacted for public release. All data was already in the public domain. This project received a determination from the University of Massachusetts Amherst Human Research Protection Office (HRPO Determination #7668); this research does not contain private or identifiable information under federal regulations [45 CFR 46.102(f)(1), (2)].
- **See `/sources` page for full disclaimer regarding data usage**

## Contributing

Contributors can help by:
- Adding ideas to the README
- Contributing to the architecture design
- Code implementation
