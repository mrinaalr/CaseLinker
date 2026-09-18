**CaseLinker v2** brings some substantial upgrades since the initial release. The corpus grew from 47 cases to **7,426 case records (2002–2026) across 56 public sources**, the single-source prototype became a mature platform, and analysis expanded from feature extraction and clustering into an affordance-level platform harm framework, ontology-backed knowledge graphs, federal-case lifecycle state machines, and an MCP server for agent workflows.

## Highlights

- **Corpus at scale** — 7,426 ICAC case records from 56 public sources: state ICAC task forces, State Attorneys General, NCMEC, DOJ CEOS (including 2002–2008 archives), ICE/HSI, CBP, NCIS, Army CID, AF OSI, USSS, and the U.S. Marshals Service
- **Platform Harm Dashboard (Q1)** — affordance → misuse surface → harm vector analysis across 30+ platforms, backed by tiered case evidence
- **Exploitation lifecycle state machines** — 30 federal PACER records (indictments and Statements of Offense) modeled as CAC-ontology state machines across five offense types
- **Ontology pipeline** — deterministic mapping of case features into Project VIC's CAC Ontology (CASE/UCO stack), per-case RDF emission, SHACL validation gate, and a merged SPARQL-queryable corpus graph
- **MCP server** — 37 read-only tools over stdio, SSE, and Streamable HTTP for agent/LLM analysis
- **Production infrastructure** — Railway deployment, PostgreSQL with encrypted connections, Redis caching, and trusted-key gates on sensitive endpoints

## What's New Since v1

### Corpus & Ingestion
- 47 AZICAC cases → **7,426 cases across 56 ingestion sources** — live counts and per-source coverage on the [Sources tab](https://caselinker.up.railway.app/sources)
- Federal coverage added: DOJ CEOS + archives, ICE/HSI, CBP, NCIS, Army CID, AF OSI, USSS, U.S. Marshals
- Collector utilities (`collector/`, formerly `scripts/scraper/`) and one-shot batch ingestion (`./scripts/run/ingest_all_pdfs.sh`)

### Platform Harm Dashboard (Q1) — [/visualization](https://caselinker.up.railway.app/visualization)
- Lifecycle map placing platforms on six exploitation lanes: distribution, storage, communities, discovery, messaging, production
- Per-platform detail panel with four tabs: **Affordances** (what the medium enables), **Misuse Surface** (how offenders abuse those properties), **Harm Vectors** (victim-facing harm pathways), and **Case Evidence** (expandable quotes from `q1_evidence.json`, linked to Audit for full case review)
- Evidence-tier filtering and platform search

### Exploitation Lifecycles — [/lifecycle](https://caselinker.up.railway.app/lifecycle)
- 30 federal PACER cases rendered as state machines over CAC-ontology phases, spanning five offense types
- Public visualization with server-embedded payload; full lifecycle JSON and L* exports gated behind trusted `CaseLinker-Key` (`/api/lifecycle/cases`, `/api/lifecycle/lstar`)

### Ontology & Knowledge Graphs
- Deterministic mapping layer (`ontology/graph_generate.py`) translating extracted case features into CAC entities and relationships
- Per-case RDF graphs emitted as Turtle and JSON-LD (`ontology/graph_output/`); only SHACL-conformant graphs enter the merged corpus
- Merged graph explorer at [/patterns/graph](https://caselinker.up.railway.app/patterns/graph) with compare, Big Bang, and Universe pools
- Built on the [CAC Ontology](https://github.com/Project-VIC-International/CAC-Ontology) (shepherded by [Project VIC International](https://www.projectvic.org/)) and the Linux Foundation's [Cyber Domain Ontology](https://cyberdomainontology.org/) stack ([UCO](https://github.com/ucoProject/UCO), [CASE](https://github.com/casework/CASE)); see also the [CASE/UCO SDK with CAC bindings](https://github.com/vulnmaster/CASE-UCO-SDK)
### Phase 2: Patterns — [/patterns](https://caselinker.up.railway.app/patterns)
- Three research questions with narrative findings pages: [Q1 — platform harm](https://caselinker.up.railway.app/patterns/questions/q01), [Q2 — exploitation lifecycle](https://caselinker.up.railway.app/patterns/questions/q02), [Q3 — kill-chain interventions](https://caselinker.up.railway.app/patterns/questions/q03)
- Backbone for *Affordance-Misuse-Harm* framework 
### MCP Server — `caselinker_mcp/`
- **37 tools**: corpus search, triage, Q1 platform evidence, on-demand `case2cac` cohort graphs, `graph_summarize`, Turtle export (`export_case_graph_ttl`), and graph traversal
- Three transports: stdio, SSE (`/mcp/sse`), and Streamable HTTP (`/mcp-http/`), with bearer-key auth; hosted on Railway
- Read-only by design — wraps the existing REST API with no database mutation; see `caselinker_mcp/README.md` and `caselinker_mcp/tool_registry.md`
### Search, Triage & Analysis
- **Facet decision tree** ([/search](https://caselinker.up.railway.app/search)) — deterministic partition tree over structured facets, rendered in D3; prune dimensions, filter values, and export cohort case IDs via API
- **Triage** ([/triage](https://caselinker.up.railway.app/triage)) — rule-based priority tiers plus supervised ML classification (random forest / decision tree), stratified evaluation endpoint (`/api/triage-eval`), and paste-in live triage that scores text in memory without persistence; full docs in `triage.md`
- **Advanced analysis** ([/analysis](https://caselinker.up.railway.app/analysis)) — tag-based intersection filtering plus automated grouping, priority scoring, insights, and pattern detection
### ML Enrichment
- Stanza NER (organizations, locations, dates, ages) merged with regex extraction; victim-age gate drops decoy and headline ages
- Semantic concept scoring (grooming, possession, AI-generated CSAM language, and related themes) merged into case topics and severity where thresholds are met
### New Pages
- [/tech-landscape](https://caselinker.up.railway.app/tech-landscape) — technology revolver (platforms, investigation tech, anonymization, P2P) by era
- [/case-studies](https://caselinker.up.railway.app/case-studies) — reading room with 20 era-organized case studies and community notes
- [/audit](https://caselinker.up.railway.app/audit) — case-by-case extraction review with interactive highlighting
- [/llm](https://caselinker.up.railway.app/llm) — natural-language queries over case statistics (SQL-backed, rate-limited in production)
- [/query](https://caselinker.up.railway.app/query) — custom analysis lab on public APIs
- [/under-the-hood](https://caselinker.up.railway.app/under-the-hood) — system internals
### Infrastructure
- PostgreSQL (production) / SQLite (local) behind a database-agnostic storage layer
- Redis caching, Railway deployment, and trusted-key auth gates for bulk and sensitive APIs
- Public paginated summary APIs (`/api/cases-summaries-chunk`, `/api/cases-summaries-by-ids`) replacing bulk JSON loads
- **Live demo moved to https://caselinker.up.railway.app/** — the v1 URL (`web-production-13a2.up.railway.app`) is deprecated
## Research Outputs
 
Five technical reports track the system's evolution:
 
1. **[CaseLinker: An Open-Source System for Cross-Case Analysis of Internet Crimes Against Children Reports](https://arxiv.org/abs/2603.18020)** — prototype architecture, deterministic extraction pipeline, evaluation baseline on 47 cases (arXiv:2603.18020)
2. **[Interpretable ML Approaches for Analyzing Internet Crimes Against Children Reports](https://mrinaalr.github.io/website/CaseLinker-%20Interpretable%20ML%20Approaches%20for%20Analyzing%20Internet%20Crimes%20Against%20Children%20Reports.pdf)** — NER integration, expansion to 207 cases, distributed network of 215 law-enforcement organizations
3. **[5 Sources, 500 Cases, and Scaling Considerations](https://mrinaalr.github.io/website/Scaling.pdf)** — new sources, facet-tree search, data utility
4. **[Framework for Retrospective Analysis and Case Studies of ICAC Across U.S. Task Forces](https://mrinaalr.github.io/website/Framework.pdf)** — four-era framework (2010–2026), stratified sampling, five-dimension case study structure, legal and ethical grounding
5. **[Painting the Landscape of Internet Crimes Against Children with Interpretive Tooling](https://mrinaalr.github.io/website/PaintingTheLandscapeOfInternetCrimesAgainstChildrenWithInterpretiveTooling.html)** — ten-page visual briefing: 20 case studies across four eras and aggregate findings across 5,000+ cases


**Companion paper (July 2026):** *Affordances for Harm: How Offenders Misuse Platform Capabilities to Exploit Children, and Where to Intervene* — an affordance framework mapping platform capabilities to documented harm vectors across 30+ platforms and 61 task forces, anchored in the 30 federal PACER records modeled in this release. **PDF: [Affordances for Harm](https://mrinaalr.github.io/website/Affordance%2C%20Misuse%2C%20Harm%2C%20Kill%20Chain.pdf)** 
 
## Data & Ethics
 
- All records are drawn from publicly available, redacted sources (ICAC task force reports, NCMEC CyberTipline materials, DOJ CEOS press releases, State AG press releases, and federal PACER filings). No PII was processed; all data was already in the public domain.
- UMass Amherst Human Research Protection Office Determination **#7668** — this research does not contain private or identifiable information under 45 CFR 46.102(f)(1), (2).
- **Content warning:** case material describes child exploitation and abuse and may be difficult to read. Please use responsibly for research, academic, or authorized analytical purposes.
## Citation
 
> Ramachandran, M. (2026). *CaseLinker: An Open-Source System for Cross-Case Analysis of Internet Crimes Against Children Reports* (Version 2) [Computer software]. https://github.com/mrinaalr/CaseLinker
  
## Links
 
- **Live demo:** https://caselinker.up.railway.app/
- **Documentation:** see `README.md` in the repository
- **Archive DOI (first version)**: [10.5281/zenodo.18744216](https://doi.org/10.5281/zenodo.18744216)
- **API docs:** https://caselinker.up.railway.app/docs
- **Research site:** https://end-child-exploitation.com/
 
