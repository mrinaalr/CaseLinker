**CaseLinker Phase 2.5** expands on Phase 2 with a cleaner, faster mid-cycle release.

[Phase 2](https://zenodo.org/records/21348119) created research infrastructure: corpus-scale ICAC analysis, Affordance-Misuse-Harm questions, CAC graphs, PACER lifecycle machines, and the MCP server. Phase 2.5 polishes and scales, making day-to-day use of CaseLinker more reliable — faster ingestion, fuller graph mapping, a public SPARQL endpoint, a rebuilt Ontology & Graphs explorer, CASE/UCO PACER graphs you can query, additive provenance, and a Crash Course for orientation.

## Highlights

- **Corpus** — **10,282** case reports (up from 7,426), **125,891** extracted features, **4,000+** law-enforcement agencies, **56** sources ([Sources](https://caselinker.up.railway.app/sources))
- **Faster PDF ingest** — **PyMuPDF** is the primary extractor; pdfplumber stays as a layout fallback
- **Better CAC mapping** — richer press-release → CAC graphs, extraction gap-fill, and location labels that show real places in the viewer
- **Ontology & Graphs** — rebuilt explorer at [/patterns](https://caselinker.up.railway.app/patterns) (class / platform / agency / case-ID search, Audit links, full-corpus find)
- **Public SPARQL** — query-only Oxigraph at `/sparql`, plus in-app SPARQL and optional NL→SPARQL ([guide](https://github.com/mrinaalr/CaseLinker/blob/main/ontology/docs/SPARQL.md))
- **PACER graphs** — **41** investigations, **128** docs, **297** graphs via the [CASE/UCO SDK](https://github.com/vulnmaster/CASE-UCO-SDK), live in Oxigraph and the explorer
- **Provenance** — scrape/ingest lineage and claim-snapshot drift, from [Forest Savage](https://github.com/forest-savage1234) ([#6](https://github.com/mrinaalr/CaseLinker/pull/6), [#7](https://github.com/mrinaalr/CaseLinker/pull/7))
- **Crash Course** — [/crash-course](https://caselinker.up.railway.app/crash-course)

## What's new since Phase 2

### Corpus & ingestion

The live corpus is **10,282** reports / **125,891** features / **4,137** agencies across 56 sources. A Project Safe Childhood / USAO harvest added federal prosecutions coverage. Local reproduce can pull production data with a trusted key (`scripts/run/import_corpus_from_api.py`).

PDF text extract prefers **PyMuPDF** for speed. pdfplumber remains available when layouts need it.

### Ontology pipeline & SPARQL

Press-release cases map into CAC Turtle/JSON-LD under `ontology/graph_output/`. Oxigraph reloads wholesale via `scripts/rebuild_oxigraph.py`. The public endpoint is SPARQL 1.1 Query only (no Update, no `SERVICE`, rate-limited). Docs live in [`ontology/README.md`](https://github.com/mrinaalr/CaseLinker/blob/main/ontology/README.md) and [`ontology/docs/SPARQL.md`](https://github.com/mrinaalr/CaseLinker/blob/main/ontology/docs/SPARQL.md).

Mapping and rebuild paths are faster. Location nodes carry readable place names in the graph viewer.

### Ontology & Graphs — [/patterns](https://caselinker.up.railway.app/patterns)

The explorer is rebuilt as the main graph workbench: CASE/UCO/CAC class lookup, platform and agency filters, case-ID / text search with Tab suggest, in-page SPARQL (and optional NL→SPARQL), press-release and PACER tabs, and Audit deep-links. Compare, Big Bang, Universe, and Analysis merge modes from Phase 2 are unchanged.

### PACER CASE/UCO graphs

[/lifecycle](https://caselinker.up.railway.app/lifecycle) still shows the **30** federal state machines and L* surface from Phase 2.

PACER filings are also modeled as CASE/UCO/CAC investigation graphs (**41 / 128 / 297**) under `ontology/PACER/`, loaded into Oxigraph (`urn:pacer:kg:…`), and available in the explorer. They were built with the [CASE/UCO SDK](https://github.com/vulnmaster/CASE-UCO-SDK). Query them through `/sparql` or the SDK MCP `execute_sparql_query` tool. CaseLinker’s own MCP remains the 37 read-only REST tools from Phase 2 (runtime updated to mcp 2).

### Provenance — Forest Savage

[Forest Savage](https://github.com/forest-savage1234) (`@forest-savage1234`) contributed additive provenance and paper-claim drift tooling. Review and merge trail:

1. [**#6** — additive provenance capture](https://github.com/mrinaalr/CaseLinker/pull/6) (document identity, scraper, ingest links)
2. [**#7** — snapshot manifests and `verify_paper` claim drift](https://github.com/mrinaalr/CaseLinker/pull/7)

Follow-ups on `main` after merge (sidecar paths, SQLite tests, default `verify_paper` behavior) stayed on that trail. Those two PRs are a clear window into how contributor work is reviewed here.

### Cleanup & speed

Lookup and merge caching, Oxigraph OOM mitigations, clustering/analysis cache paths, lifecycle UI cleanup, and AI-CSAM threshold tweaks. Same MCP tool count (**37**); transport stack refreshed.

### Crash Course — [/crash-course](https://caselinker.up.railway.app/crash-course)

Start here if you are new: a short deck plus a deeper path through ingest → extraction → CAC graphs → SPARQL → PACER → analysis, aimed at the live demo.

## Scope

Phase 2.5 keeps Phase 2’s research questions (Q1–Q3) and Affordance-Misuse-Harm framing. Lifecycle swimlanes stay at **30** cases. This release is platform work — speed, clarity, durability — not a new report series.

## Data & Ethics

- Records come from public, redacted sources (ICAC reports, NCMEC materials, DOJ CEOS and State AG press releases, federal PACER filings). No PII was processed.
- UMass Amherst HRPO Determination **#7668** — no private or identifiable information under 45 CFR 46.102(f)(1), (2).

## Citation

> Ramachandran, M. (2026). *CaseLinker: An Open-Source System for Cross-Case Analysis of Internet Crimes Against Children Reports* (Version 2.5) [Computer software]. https://github.com/mrinaalr/CaseLinker

Phase 2.5 DOI: [10.5281/zenodo.22803051](https://doi.org/10.5281/zenodo.22803051).

## Links

- **Live demo:** https://caselinker.up.railway.app/
- **Crash Course:** https://caselinker.up.railway.app/crash-course
- **Ontology & Graphs:** https://caselinker.up.railway.app/patterns
- **SPARQL:** https://caselinker.up.railway.app/sparql · `ontology/docs/SPARQL.md`
- **API docs:** https://caselinker.up.railway.app/docs
- **Docs:** `README.md`
- **Phase 2:** [10.5281/zenodo.21348119](https://doi.org/10.5281/zenodo.21348119)
- **Research site:** https://end-child-exploitation.com/
