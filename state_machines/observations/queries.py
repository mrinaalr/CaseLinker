"""Three SPARQL queries, one per level of evidence, over a release's named graphs.

    python -m state_machines.observations.queries <release_id>

They run against any store holding the release (``rebuild_oxigraph.py --pacer-release``); here
they run on the release files directly. The release report prints their results.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Dict, List

PREFIXES = """PREFIX oa: <http://www.w3.org/ns/oa#>
PREFIX core: <https://ontology.unifiedcyberontology.org/uco/core/>
PREFIX action: <https://ontology.unifiedcyberontology.org/uco/action/>
PREFIX clt: <https://w3id.org/caselinker/trajectory#>
"""

QUERIES: Dict[str, dict] = {
    "documented": {
        "title": "Level 1. Which listed platforms do the records name, in how many cases?",
        "columns": ["platform", "cases", "mentions"],
        "sparql": PREFIXES + """SELECT ?platform (COUNT(DISTINCT ?g) AS ?cases) (COUNT(?obs) AS ?mentions) WHERE {
  GRAPH ?g { ?obs oa:motivatedBy oa:identifying ; oa:hasBody ?p . ?p core:name ?platform }
  FILTER(STRSTARTS(STR(?p), "https://w3id.org/caselinker/resource/platform/"))
} GROUP BY ?platform ORDER BY DESC(?cases) DESC(?mentions) ?platform"""},
    "withheld": {
        "title": "Level 1. Which services does a record refer to by a placeholder, case by case? (A label means nothing outside its case.)",
        "columns": ["case", "label", "mentions"],
        "sparql": PREFIXES + """SELECT ?case ?label (COUNT(?obs) AS ?mentions) WHERE {
  GRAPH ?g { ?obs oa:motivatedBy oa:identifying ; oa:hasBody ?p . ?p core:name ?label }
  FILTER(!STRSTARTS(STR(?p), "https://w3id.org/caselinker/resource/platform/"))
  BIND(REPLACE(REPLACE(STR(?g), "^urn:caselinker:pacer:", ""), ":observations$", "") AS ?case)
} GROUP BY ?case ?label ORDER BY ?case ?label"""},
    "described": {
        "title": "Level 1. Which generic descriptions of an online service do the records use? (Not platforms; no use claimed.)",
        "columns": ["description", "cases", "mentions"],
        "sparql": PREFIXES + """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
SELECT ?description (COUNT(DISTINCT ?g) AS ?cases) (COUNT(?obs) AS ?mentions) WHERE {
  GRAPH ?g { ?obs oa:motivatedBy oa:describing ; oa:hasBody ?b . ?b rdf:value ?description }
} GROUP BY ?description ORDER BY DESC(?cases) DESC(?mentions) ?description"""},
    "features": {
        "title": "Level 1. Which feature phrases do the records state, under which CAC class?",
        "columns": ["class", "phrase", "cases", "mentions"],
        "sparql": PREFIXES + """SELECT ?class ?phrase (COUNT(DISTINCT ?g) AS ?cases) (COUNT(?obs) AS ?mentions) WHERE {
  GRAPH ?g { ?obs oa:motivatedBy oa:classifying ; oa:hasBody ?c ; clt:featureTerm ?phrase }
  BIND(REPLACE(STR(?c), "^.*#", "") AS ?class)
} GROUP BY ?class ?phrase ORDER BY ?class DESC(?mentions) ?phrase"""},
    "reconstructed": {
        "title": "Level 2. Which acts did both coders agree on?",
        "columns": ["action", "cases", "acts"],
        "sparql": PREFIXES + """SELECT ?action (COUNT(DISTINCT ?g) AS ?cases) (COUNT(?act) AS ?acts) WHERE {
  GRAPH ?g { ?act a action:Action ; clt:actionCode ?action ; clt:reviewStatus "agreed" }
  FILTER(STRENDS(STR(?g), ":evidence"))
} GROUP BY ?action ORDER BY DESC(?acts) ?action"""},
    "disputed": {
        "title": "Between levels 1 and 3. Where does a sentence state a platform or feature as a means while the two coders dispute the act? (No act is published there.)",
        "columns": ["case", "platform_or_class", "phrase", "standing", "observations"],
        "sparql": PREFIXES + """SELECT ?case ?what ?phrase ?standing (COUNT(DISTINCT ?obs) AS ?observations) WHERE {
  GRAPH ?og { ?obs clt:reviewStatus "disputed" ; oa:hasBody ?body ; oa:hasTarget ?span ; clt:sourceStatus ?standing .
              OPTIONAL { ?obs clt:featureTerm ?phrase } OPTIONAL { ?body core:name ?name } }
  BIND(COALESCE(?name, REPLACE(STR(?body), "^.*#", "")) AS ?what)
  BIND(REPLACE(REPLACE(STR(?og), "^urn:caselinker:pacer:", ""), ":observations$", "") AS ?case)
} GROUP BY ?case ?what ?phrase ?standing ORDER BY ?case ?what"""},
    "supported": {
        "title": "Level 3. Where does a record state that an act was done by means of a platform or feature?",
        "columns": ["case", "act", "action", "relationship", "platform_or_class", "phrase", "standing"],
        # The relationship and the act live in the same case's own graphs (node IRIs are case-scoped), so ?rg and ?eg are
        # bound from ?og instead of ranging over every graph in the store; the unbound form timed out on the live store.
        "sparql": PREFIXES + """SELECT DISTINCT ?case ?event ?action ?relationship ?what ?phrase ?standing WHERE {
  GRAPH ?og { ?obs oa:motivatedBy ?m ; oa:hasTarget ?span ; oa:hasBody ?body ; clt:sourceStatus ?standing .
              ?evidence oa:hasTarget ?span ; oa:hasBody ?rel . FILTER(?evidence != ?obs) FILTER(?m != oa:describing)
              OPTIONAL { ?obs clt:featureTerm ?phrase } OPTIONAL { ?body core:name ?name } }
  FILTER(STRSTARTS(STR(?og), "urn:caselinker:pacer:") && STRENDS(STR(?og), ":observations"))
  BIND(REPLACE(STR(?og), ":observations$", "") AS ?base)
  BIND(IRI(CONCAT(?base, ":evidence")) AS ?eg)
  VALUES ?part { ":evidence" ":observations" }
  BIND(IRI(CONCAT(?base, ?part)) AS ?rg)
  GRAPH ?rg { ?rel core:kindOfRelationship ?relationship ; core:source ?s ; core:target ?t }
  GRAPH ?eg { ?act clt:actionCode ?action } FILTER(?act IN (?s, ?t))
  FILTER(?body IN (?s, ?t) || (BOUND(?phrase) && EXISTS { GRAPH ?any { ?s a ?body } }))
  BIND(COALESCE(?name, REPLACE(STR(?body), "^.*#", "")) AS ?what)
  BIND(REPLACE(REPLACE(STR(?og), "^urn:caselinker:pacer:", ""), ":observations$", "") AS ?case)
  BIND(REPLACE(STR(?act), "^.*[/#:-](e[0-9]+)$", "$1") AS ?event)
} ORDER BY ?case ?event ?what"""},
}


def run(release_id: str, data_root: Path = None) -> Dict[str, List[List[str]]]:
    """Each query's rows over the release's graphs (evidence, trajectories and observations)."""
    import rdflib
    from state_machines.graphs.release import DATA, nquads
    with tempfile.TemporaryDirectory() as tmp:
        ds = rdflib.Dataset()
        ds.parse(nquads(release_id, data_root=data_root or DATA, out=Path(tmp) / "all.nq"), format="nquads")
        return {name: [["" if v is None else str(v) for v in row] for row in ds.query(q["sparql"])] for name, q in QUERIES.items()}


if __name__ == "__main__":
    for name, rows in run(sys.argv[1]).items():
        print(f"\n== {QUERIES[name]['title']}\n" + " | ".join(QUERIES[name]["columns"]))
        for row in rows:
            print(" | ".join(row))
