"""SPARQL for a Search cohort: one row per case, with graph attributes.

Case graphs in the public store are named
``https://caselinker.up.railway.app/resource/case/{case_id}``.
Search already decided which cases are in the cohort (facet tags live in
the case database, not as a SPARQL pattern). This builder emits a SELECT
over those named graphs: source, platforms, agencies, phase, steps,
charges, and sentences.

Each attribute list is its own subquery so platforms do not cross-join
with agencies. The ``VALUES`` block sits inside ``WHERE``. The SPARQL
proxy only splices a default ``LIMIT`` in front of a query-level
``VALUES`` clause; an inline block plus an explicit ``LIMIT`` is left
alone. ``LIMIT`` equals the number of graphs in the query, one row each.
"""

from __future__ import annotations

import re
from string import Template
from typing import Any, Dict, Iterable, List, Optional

CASE_GRAPH_BASE = "https://caselinker.up.railway.app/resource/case/"
# Slugs used as case ids (nj_ag_2017_001, pacer_…). Reject anything that
# could break out of an IRI token.
CASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
# Keeps a root-of-tree cohort from emitting a multi-megabyte query.
MAX_COHORT_GRAPHS = 400
_LABEL_UNSAFE = re.compile(r"[^\w .,:;/+()'\"-]+", re.UNICODE)

_QUERY = Template(
    """$header
PREFIX cac: <https://cacontology.projectvic.org#>
PREFIX cac-legal: <https://cacontology.projectvic.org/legal-outcomes#>
PREFIX cac-multi: <https://cacontology.projectvic.org/multi-jurisdiction#>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?id ?sources ?platforms ?agencies ?phase ?steps ?charges ?sentences
WHERE {
  VALUES ?g { $values }
  GRAPH ?g {
    ?case a cac:CACInvestigation ;
          dcterms:identifier ?id .
    OPTIONAL {
      SELECT ?case (GROUP_CONCAT(DISTINCT STR(?raw); separator=" | ") AS ?sources)
      WHERE { ?case dcterms:source ?raw }
      GROUP BY ?case
    }
    OPTIONAL {
      SELECT ?case (GROUP_CONCAT(DISTINCT ?platform; separator=", ") AS ?platforms)
      WHERE {
        ?case cac:hasStep ?step .
        ?step cac:usesChannel ?node .
        OPTIONAL { ?node rdfs:label ?label }
        BIND(COALESCE(STR(?label), REPLACE(STR(?node), "^.*/", "")) AS ?platform)
      }
      GROUP BY ?case
    }
    OPTIONAL {
      SELECT ?case (GROUP_CONCAT(DISTINCT ?agency; separator=", ") AS ?agencies)
      WHERE {
        ?case cac-multi:involvesAgency ?node .
        OPTIONAL { ?node rdfs:label ?label }
        BIND(COALESCE(STR(?label), REPLACE(STR(?node), "^.*/", "")) AS ?agency)
      }
      GROUP BY ?case
    }
    OPTIONAL {
      SELECT ?case (GROUP_CONCAT(DISTINCT REPLACE(STR(?node), "^.*/", ""); separator=", ") AS ?phase)
      WHERE { ?case cac:currentPhase ?node }
      GROUP BY ?case
    }
    OPTIONAL {
      SELECT ?case (GROUP_CONCAT(DISTINCT REPLACE(STR(?node), "^.*resource/case/[^/]+/", ""); separator=", ") AS ?steps)
      WHERE { ?case cac:hasStep ?node }
      GROUP BY ?case
    }
    OPTIONAL {
      SELECT ?case (GROUP_CONCAT(DISTINCT ?charge; separator=", ") AS ?charges)
      WHERE {
        ?case cac:hasStep ?step .
        ?step cac-legal:hasCharge ?node .
        OPTIONAL { ?node rdfs:label ?label }
        BIND(COALESCE(STR(?label), REPLACE(STR(?node), "^.*/", "")) AS ?charge)
      }
      GROUP BY ?case
    }
    OPTIONAL {
      SELECT ?case (GROUP_CONCAT(DISTINCT ?sentence; separator=", ") AS ?sentences)
      WHERE {
        ?case cac:hasStep ?step .
        ?step cac-legal:resultsSentence ?node .
        OPTIONAL { ?node rdfs:label ?label }
        BIND(COALESCE(STR(?label), REPLACE(STR(?node), "^.*/", "")) AS ?sentence)
      }
      GROUP BY ?case
    }
  }
}
ORDER BY ?id
LIMIT $limit
"""
)


def normalize_case_ids(case_ids: Iterable[str]) -> List[str]:
    """Unique, sorted case ids that are safe to embed in an IRI."""
    seen = set()
    out: List[str] = []
    for raw in case_ids:
        cid = str(raw or "").strip()
        if not cid or cid in seen or CASE_ID_RE.fullmatch(cid) is None:
            continue
        seen.add(cid)
        out.append(cid)
    out.sort()
    return out


def _comment_label(label: Optional[str]) -> str:
    text = _LABEL_UNSAFE.sub(" ", str(label or ""))
    text = " ".join(text.split()).strip(" .")
    return (text[:80] or "Search cohort")


def build_cohort_case_query(
    case_ids: Iterable[str],
    label: Optional[str] = None,
    *,
    max_graphs: int = MAX_COHORT_GRAPHS,
) -> Dict[str, Any]:
    """Return one-row-per-case SPARQL restricted to the cohort's named graphs.

    ``included`` is how many graphs appear in ``VALUES``. ``truncated`` is
    true when valid ids were dropped to stay under ``max_graphs``. Invalid
    ids are omitted and do not count toward ``case_count``.
    """
    cap = max(1, int(max_graphs))
    ids = normalize_case_ids(case_ids)
    included = ids[:cap]
    title = _comment_label(label)
    if not included:
        return {
            "sparql": "",
            "case_count": 0,
            "included": 0,
            "truncated": False,
            "label": title,
        }
    n = len(included)
    lines = [
        f"# Search cohort: {title} ({n} {'case' if n == 1 else 'cases'})",
        "# One row per case. Attributes are the ones stored on that case graph.",
    ]
    if len(ids) > len(included):
        lines.append(
            f"# Capped at {len(included)} of {len(ids)} case ids, sorted."
        )
    values = " ".join(f"<{CASE_GRAPH_BASE}{cid}>" for cid in included)
    sparql = _QUERY.substitute(
        header="\n".join(lines),
        values=values,
        limit=len(included),
    )
    return {
        "sparql": sparql,
        "case_count": len(ids),
        "included": len(included),
        "truncated": len(ids) > len(included),
        "label": title,
    }
