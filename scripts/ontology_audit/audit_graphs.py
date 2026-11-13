#!/usr/bin/env python3
"""Map every case with the current mapper and count what #57 measures.

  terms      classes / predicates / datatypes no pinned ontology declares
  grounding  nodes and edges the source does not support (#57 §4)
  shacl      full SHACL on a seeded sample, violations by bucket (#57 §6)

Reads cases from caselinker.db (``CASELINKER_DB`` overrides). Nothing is written
except the JSON report. Usage (repo root):

  python3 scripts/ontology_audit/audit_graphs.py terms --out terms.json
  python3 scripts/ontology_audit/audit_graphs.py grounding --out grounding.json
  python3 scripts/ontology_audit/audit_graphs.py shacl --sample 50 --seed 20261103 --out shacl.json
"""

from __future__ import annotations

import argparse
import collections
import json
import logging
import multiprocessing as mp
import os
import random
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "ontology"))

_MAPPER = None


def _init() -> None:
    global _MAPPER
    logging.disable(logging.WARNING)
    from features_to_cac import CaseToCAC

    _MAPPER = CaseToCAC()


def _db() -> Path:
    return Path(os.environ.get("CASELINKER_DB") or REPO / "caselinker.db")


def _case(case_id: str):
    from features_to_cac import CaseToCAC

    return CaseToCAC._load_from_local_sqlite(case_id)


def _terms(case_id: str):
    from term_resolution import undeclared_terms

    graph, _ = _MAPPER.map_case(_case(case_id))
    return {k: sorted(v) for k, v in undeclared_terms(graph).items()}


_CAC = "https://cacontology.projectvic.org#"
_LEGAL = "https://cacontology.projectvic.org/legal-outcomes#"
_PATTERNS = {
    "victim_roles_without_stated_victim": None,
    "participatesInEvent_edges": _CAC + "participatesInEvent",
    "usesChannel_edges": _CAC + "usesChannel",
    "hasRoleBeginPoint": _CAC + "hasRoleBeginPoint",
    "hasPhaseBeginPoint": _CAC + "hasPhaseBeginPoint",
    "hasProceedingBeginPoint": _LEGAL + "hasProceedingBeginPoint",
    "us-ncmec:supportedBy": "https://cacontology.projectvic.org/us/ncmec#supportedBy",
    "cac:usesMethod": _CAC + "usesMethod",
    "cac:producesArtifact": _CAC + "producesArtifact",
}


def _grounding(case_id: str):
    from rdflib import RDF, URIRef

    case = _case(case_id)
    graph, _ = _MAPPER.map_case(case)
    triples = {(s, p, o) for s, p, o, _c in graph.quads((None, None, None, None))}
    out = collections.Counter()
    for name, pred in _PATTERNS.items():
        if pred:
            out[name] = sum(1 for _s, p, _o in triples if str(p) == pred)
    events_with_links = {s for s, p, _o in triples if str(p) == _CAC + "usesChannel"} | {
        o for _s, p, o in triples if str(p) == _CAC + "participatesInEvent"
    }
    out["graphs_linking_several_events"] = int(len(events_with_links) > 1)
    vc = case.get("victim_count")
    victims = {s for s, p, o in triples if p == RDF.type and str(o) == _CAC + "VictimRole"}
    if victims and not (isinstance(vc, (int, float)) and vc > 0) and not case.get("relationship_to_victim"):
        out["victim_roles_without_stated_victim"] = len(victims)
    out["stub_ContentDataFacet"] = sum(
        1 for s, p, o in triples
        if p == RDF.type and str(o).endswith("/observable/ContentDataFacet")
        and not any(s2 == s and p2 != RDF.type for s2, p2, _o in triples)
    )
    out["charge_inferred_events"] = sum(1 for s in {s for s, _p, _o in triples} if "/offense-event/" in str(s))
    out["cybertip_reports"] = sum(1 for _s, p, o in triples if p == RDF.type and str(o).endswith("#NCMECCybertipReport"))
    out["triples"] = len(triples)
    return dict(out)


def _shacl(case_id: str):
    from features_to_cac import flatten_dataset
    from shacl_validation import full_validate

    graph, _ = _MAPPER.map_case(_case(case_id))
    return {b: dict(c) for b, c in full_validate(flatten_dataset(graph)).items()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("check", choices=("terms", "grounding", "shacl"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--sample", type=int, default=50, help="shacl: cases to sample")
    ap.add_argument("--seed", type=int, default=20261103, help="shacl: sample seed (#57 used 20261103)")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    ids = [r[0] for r in sqlite3.connect(str(_db())).execute("select id from cases order by id")]
    if args.check == "shacl":
        random.seed(args.seed)
        ids = random.sample(ids, args.sample)
    fn = {"terms": _terms, "grounding": _grounding, "shacl": _shacl}[args.check]
    with mp.Pool(args.workers, initializer=_init) as pool:
        results = dict(zip(ids, pool.map(fn, ids, chunksize=20)))

    if args.check == "terms":
        agg = collections.Counter(t for r in results.values() for v in r.values() for t in v)
        report = {"cases": len(ids), "graphs_with_undeclared": sum(1 for r in results.values() if any(r.values())),
                  "undeclared": dict(agg)}
    elif args.check == "grounding":
        total, graphs = collections.Counter(), collections.Counter()
        for r in results.values():
            total.update(r)
            graphs.update({k: 1 for k, v in r.items() if v})
        report = {"cases": len(ids), **{k: {"count": total[k], "graphs": graphs[k]} for k in sorted(total)}}
    else:
        buckets = {b: collections.Counter() for b in ("caselinker", "unstated", "upstream")}
        for r in results.values():
            for b, c in r.items():
                buckets[b].update(c)
        report = {"cases": len(ids), "seed": args.seed,
                  **{b: {"violations": sum(c.values()), "messages": dict(c.most_common())} for b, c in buckets.items()}}
    Path(args.out).write_text(json.dumps(report, indent=1))
    print(json.dumps({k: v if not isinstance(v, dict) or "count" in v or "violations" in v else len(v)
                      for k, v in report.items()}, indent=1)[:3000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
