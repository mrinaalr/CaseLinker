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
        "title": "Level 1. Which platforms do the records name, in how many cases?",
        "columns": ["platform", "cases", "mentions"],
        "sparql": PREFIXES + """SELECT ?platform (COUNT(DISTINCT ?g) AS ?cases) (COUNT(?obs) AS ?mentions) WHERE {
  GRAPH ?g { ?obs oa:motivatedBy oa:identifying ; oa:hasBody ?p . ?p core:name ?platform }
} GROUP BY ?platform ORDER BY DESC(?cases) DESC(?mentions) ?platform"""},
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
    "supported": {
        "title": "Level 3. Where does a record state that an act was done by means of a platform or feature?",
        "columns": ["case", "action", "relationship", "platform_or_class", "phrase", "standing"],
        "sparql": PREFIXES + """SELECT DISTINCT ?case ?action ?relationship ?what ?phrase ?standing WHERE {
  GRAPH ?og { ?obs oa:motivatedBy ?m ; oa:hasTarget ?span ; oa:hasBody ?body ; clt:sourceStatus ?standing .
              ?evidence oa:hasTarget ?span ; oa:hasBody ?rel . FILTER(?evidence != ?obs)
              OPTIONAL { ?obs clt:featureTerm ?phrase } OPTIONAL { ?body core:name ?name } }
  GRAPH ?rg { ?rel core:kindOfRelationship ?relationship ; core:source ?s ; core:target ?t }
  GRAPH ?eg { ?act clt:actionCode ?action } FILTER(?act IN (?s, ?t)) FILTER(STRENDS(STR(?eg), ":evidence"))
  FILTER(?body IN (?s, ?t) || BOUND(?phrase))
  BIND(COALESCE(?name, REPLACE(STR(?body), "^.*#", "")) AS ?what)
  BIND(REPLACE(REPLACE(STR(?og), "^urn:caselinker:pacer:", ""), ":observations$", "") AS ?case)
} ORDER BY ?case ?action ?what"""},
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
