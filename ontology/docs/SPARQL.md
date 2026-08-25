# SPARQL API

Public SPARQL 1.1 Query endpoint over the CaseLinker CASE/UCO/CAC case graphs. Mapping, pools, and pipeline: [ontology/README.md](../README.md).

**Endpoint:** [`https://caselinker.up.railway.app/sparql`](https://caselinker.up.railway.app/sparql)  
**Protocol:** SPARQL 1.1 Query only (`SELECT`, `CONSTRUCT`, `ASK`, `DESCRIBE`)  
**OpenAPI:** [`/docs`](https://caselinker.up.railway.app/docs) (route `GET|POST /sparql`)  
**MCP:** [CASE/UCO SDK v1.25.0](https://github.com/vulnmaster/CASE-UCO-SDK/releases/tag/v1.25.0) `execute_sparql_query` defaults to this URL.

No `MCP_ACCESS_KEY`. SPARQL Update and `SERVICE` federation are rejected.

## Request formats

### GET

Query string parameter `query` (URL-encoded SPARQL). `update=` is rejected (`405`).

```bash
curl -sS -G 'https://caselinker.up.railway.app/sparql' \
  --data-urlencode 'query=ASK { ?s a <https://cacontology.projectvic.org#CACInvestigation> }' \
  -H 'Accept: application/sparql-results+json'
```

### POST

Two bodies are accepted:

| `Content-Type` | Body |
|---|---|
| `application/sparql-query` | Raw SPARQL (preferred) |
| `application/x-www-form-urlencoded` | Form field `query=` |

`application/sparql-update`, form field `update=`, and Update verbs in the query string are `405`.

```bash
curl -sS -X POST 'https://caselinker.up.railway.app/sparql' \
  -H 'Content-Type: application/sparql-query' \
  -H 'Accept: application/sparql-results+json' \
  --data-binary @- <<'SPARQL'
PREFIX cac: <https://cacontology.projectvic.org#>
ASK { ?s a cac:CACInvestigation }
SPARQL
```

## Content negotiation

`Accept` is forwarded to Oxigraph. If omitted, the proxy defaults to `application/sparql-results+json`.

| Query form | Typical `Accept` | Body |
|---|---|---|
| `SELECT` | `application/sparql-results+json` | `{ "head": { "vars": [...] }, "results": { "bindings": [...] } }` |
| `ASK` | `application/sparql-results+json` | `{ "boolean": true \| false }` |
| `CONSTRUCT` / `DESCRIBE` | `text/turtle` or `application/ld+json` | RDF graph |

W3C SPARQL Results XML (`application/sparql-results+xml`) is valid if the store accepts it.

## Named graphs and the default union

Each case is one named graph:

```
https://caselinker.up.railway.app/resource/case/{case_id}
```

Oxigraph runs with `--union-default-graph`. Triple patterns **without** `GRAPH` see the union of all case graphs. Use `GRAPH` to pin a case (or bind `?g`).

Instance IRIs use the same host:

| Kind | IRI |
|---|---|
| Case / named graph | `https://caselinker.up.railway.app/resource/case/{case_id}` |
| Platform | `https://caselinker.up.railway.app/resource/platform/{slug}` |
| Agency | `https://caselinker.up.railway.app/resource/agency/{slug}` |

`dcterms:identifier` on a `cac:CACInvestigation` is the CaseLinker `case_id` (e.g. `nj_ag_2017_001`).

## Namespaces

Graphs are CAC instance data on UCO identity/role/core types. CAC is the CASE-aligned investigation vocabulary ([CAC Ontology](https://github.com/Project-VIC-International/CAC-Ontology)).

```sparql
PREFIX cac:          <https://cacontology.projectvic.org#>
PREFIX cac-core:     <https://cacontology.projectvic.org/core#>
PREFIX cac-plat:     <https://cacontology.projectvic.org/platforms#>
PREFIX cac-legal:    <https://cacontology.projectvic.org/legal-outcomes#>
PREFIX cac-multi:    <https://cacontology.projectvic.org/multi-jurisdiction#>
PREFIX cac-detect:   <https://cacontology.projectvic.org/detection#>
PREFIX cac-tf:       <https://cacontology.projectvic.org/taskforce#>
PREFIX uco-core:     <https://ontology.unifiedcyberontology.org/uco/core/>
PREFIX uco-identity: <https://ontology.unifiedcyberontology.org/uco/identity/>
PREFIX uco-role:     <https://ontology.unifiedcyberontology.org/uco/role/>
PREFIX dcterms:      <http://purl.org/dc/terms/>
PREFIX rdfs:         <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd:          <http://www.w3.org/2001/XMLSchema#>
```

Other CAC modules appear when the mapped features need them (`grooming#`, `custodial#`, `sextortion#`, `production#`, `ai-csam#`, `us/ncmec#`, `usa-federal-law#`, `undercover#`). Bindings: [CASE/UCO SDK](https://github.com/vulnmaster/CASE-UCO-SDK) (`CASE_UCO_EXTENSIONS=cac`).

## Corpus metadata

| Fact | How to read it |
|---|---|
| Relational case count | `GET https://caselinker.up.railway.app/api/case-count` |
| Graph case count | `SELECT (COUNT(?s) AS ?n) WHERE { ?s a cac:CACInvestigation }` (expect **7,426**) |
| Named graphs | one per case; same count |
| Graph generation time | `dcterms:created` / `dcterms:modified` on the investigation (remap time, not offense date) |
| Public source | `dcterms:source` (press-release URL and/or source label) |
| Reload | wholesale `python3 scripts/rebuild_oxigraph.py` (not incremental) |

Platform/agency extra facts can vary by generation batch order ([issue #10](https://github.com/mrinaalr/CaseLinker/issues/10)).

## Limits

| Constraint | Value |
|---|---|
| Rate limit | **30 requests / minute / client IP** (same slowapi layer as `/api/technology-revolver`) |
| Default `LIMIT` | **1000** injected on outer `SELECT` / `CONSTRUCT` / `DESCRIBE` with no outer `LIMIT` (rdflib parse tree; inserted **before** a query-level `VALUES`) |
| Max outer `LIMIT` | **10,000** (larger is `400`, not rewritten) |
| `ASK` | no `LIMIT` injected |
| Store timeout | **32s** (`SPARQL_HTTP_TIMEOUT_S`) |

CORS is same-origin only (`https://caselinker.up.railway.app`, `http://localhost:8000`). curl, agents, and MCP do not use CORS. Off-origin browser UIs (YASGUI, etc.) are blocked unless listed in `SPARQL_CORS_ORIGINS`.

## Errors

FastAPI policy errors use `{"detail": "<message>"}`. Rate-limit uses `{"error": "..."}`. Oxigraph syntax/eval errors are forwarded with the store status and body.

| HTTP | When |
|---|---|
| `400` | Missing query, parse failure, `SERVICE`, outer `LIMIT` &gt; 10,000 |
| `405` | SPARQL Update (`INSERT`/`DELETE`/`LOAD`/`CLEAR`/`DROP`, `application/sparql-update`, `update=` parameter) |
| `429` | Rate limit. Body: `{"error":"Rate limit exceeded: 30 per 1 minute"}`. Retry in the current 60s window. (`X-RateLimit-*` / `Retry-After` are not emitted.) |
| `503` | Store unset, rebuild lock held, or Oxigraph unreachable. Rebuild message: `SPARQL store is being rebuilt. Retry shortly.` |
| `504` | Query exceeded 32s |

## Example queries

### Corpus size

```sparql
PREFIX cac: <https://cacontology.projectvic.org#>
SELECT (COUNT(?s) AS ?n) WHERE { ?s a cac:CACInvestigation }
```

### Platforms by case count

```sparql
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
```

### One case (named graph)

```sparql
SELECT ?s ?p ?o
WHERE {
  GRAPH <https://caselinker.up.railway.app/resource/case/nj_ag_2017_001> {
    ?s ?p ?o
  }
}
LIMIT 50
```

### Case id → investigation IRI

```sparql
PREFIX cac: <https://cacontology.projectvic.org#>
PREFIX dcterms: <http://purl.org/dc/terms/>
SELECT ?s ?source
WHERE {
  ?s a cac:CACInvestigation ;
     dcterms:identifier "nj_ag_2017_001" ;
     dcterms:source ?source .
}
```

### VALUES (limit is injected before VALUES, not after)

```sparql
SELECT ?s WHERE { ?s ?p ?o }
VALUES ?s { <https://caselinker.up.railway.app/resource/case/nj_ag_2017_001> }
```

### CONSTRUCT (ask for Turtle)

```bash
curl -sS -X POST 'https://caselinker.up.railway.app/sparql' \
  -H 'Content-Type: application/sparql-query' \
  -H 'Accept: text/turtle' \
  --data-binary @- <<'SPARQL'
PREFIX cac: <https://cacontology.projectvic.org#>
CONSTRUCT { ?s a cac:CACInvestigation }
WHERE { ?s a cac:CACInvestigation }
LIMIT 5
SPARQL
```

Live checks: `CASELINKER_SPARQL_LIVE=1 pytest tests/test_sparql_live.py -q`.
