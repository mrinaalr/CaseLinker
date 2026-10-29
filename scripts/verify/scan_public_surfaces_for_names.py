#!/usr/bin/env python3
"""
Scan every outward CaseLinker surface for person names. Prints counts only.

People are read in memory, per case, from the local database (stored
``person_spans`` when present, otherwise the release's own cues), filtered to
names that do not read as places or agencies. The scan then looks for those
full names in:

- public API responses, called as an outside client (no key, not localhost)
- case graphs and provenance graphs under ``ontology/graph_output``
- structured stored fields (assertion extras, resolution finals, entity lists)

Research files that intentionally keep source excerpts are out of scope:
``scripts/verify/``, ``ontology/platform_affordance_evidence/``, ``ontology/PACER/``,
source text (``raw_data``), and stored admission excerpts (served masked).

Exit 1 when any in-scope surface holds a name. Never prints a name.

Usage:
  python3 scripts/verify/scan_public_surfaces_for_names.py --sqlite caselinker.db
  python3 scripts/verify/scan_public_surfaces_for_names.py --sqlite caselinker.db --cases all --graphs
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import random
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Set

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "src" / "Processing Layer" / "field_assertions"), str(REPO / "src" / "Storage Layer")]

import people_mask as PK  # noqa: E402


def case_people(db: sqlite3.Connection) -> Dict[str, Set[str]]:
    """case_id -> full names of people in that release (in memory only)."""
    out: Dict[str, Set[str]] = {}
    for cid, fj, rd in db.execute("SELECT id, extracted_features, raw_data FROM cases"):
        feats = json.loads(fj or "{}") or {}
        text = (json.loads(rd or "{}") or {}).get("case_text") or ""
        spans = PK.spans_for(feats, text)
        grounded = [g.get(k) for key in ("location_grounds", "agency_grounds") for g in feats.get(key) or []
                    if isinstance(g, dict) and g.get("status") == "grounded" for k in ("mention", "entity_name")]
        grounded += [x for x in (feats.get("agencies_involved") or []) if isinstance(x, str)]
        full, _ = PK.case_people(text, [text[a:b] for a, b in spans], grounded)
        full = {n for n in full if len(n.split()) >= 2 and len(n) >= 6}
        if full:
            out[cid] = full
    return out


def _pattern(names) -> "re.Pattern[str]":
    return re.compile("|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)))


def held_person_values(db: sqlite3.Connection, people: Dict[str, Set[str]]) -> Set[str]:
    """Entity values that are a person *in a case that stores them* (what aggregates could leak).

    A string that is a person in one release can be a town in another; aggregates
    (facets, location stats) are judged against the cases that hold each value.
    """
    out: Set[str] = set()
    for cid, fj in db.execute("SELECT id, extracted_features FROM cases"):
        names = people.get(cid)
        if not names:
            continue
        feats = json.loads(fj or "{}") or {}
        for key in ("locations", "organizations", "agencies_involved"):
            for v in feats.get(key) or []:
                if isinstance(v, str) and PK._norm_name(v) in names:
                    out.add(v)
    return out


def scan_api(db_path: str, people: Dict[str, Set[str]], case_ids, report: Counter,
             held: Set[str] = frozenset()) -> None:
    spec = importlib.util.spec_from_file_location("caselinker_scan_main", REPO / "run" / "main.py")
    main = importlib.util.module_from_spec(spec)
    sys.modules["caselinker_scan_main"] = main
    spec.loader.exec_module(main)
    from storage import CaseStorage
    from fastapi.testclient import TestClient

    main.storage = CaseStorage(db_path)
    main.REDIS_AVAILABLE = False
    public = TestClient(main.app, client=("203.0.113.9", 50000))
    every = _pattern(held) if held else None  # aggregates: values that are a person where stored

    def check(surface: str, body: str, names=None) -> None:
        pat = _pattern(names) if names else every
        report[f"api {surface}: responses"] += 1
        if pat is not None and pat.search(body):
            report[f"api {surface}: LEAK"] += 1

    for cid in case_ids:
        main._case_id_daily_counts.clear()
        names = people.get(cid)
        if not names:
            continue
        check("/api/cases/{id}", public.get(f"/api/cases/{cid}").text, names)
        main._case_id_daily_counts.clear()
        check("/api/cases/{id}/assertions", public.get(f"/api/cases/{cid}/assertions").text, names)
    for off in range(0, 5000, 500):
        main.limiter.reset()
        r = public.get("/api/assertions/disagreements", params={"limit": 500, "offset": off})
        items = r.json().get("items") if r.status_code == 200 else None
        if not items:
            break
        for item in items:  # each item belongs to one case: check that case's people
            names = people.get(item.get("case_id"))
            if names:
                check("/api/assertions/disagreements item", json.dumps(item), names)
    main.limiter.reset()
    r = public.get("/api/automated-analysis")
    if r.status_code == 200:  # triaged cases carry text: check each against its own case's people
        for item in ((r.json().get("analysis") or {}).get("triaged_cases") or []):
            names = people.get(item.get("id")) if isinstance(item, dict) else None
            if names:
                check("/api/automated-analysis triaged case", json.dumps(item), names)
    else:
        report[f"api /api/automated-analysis: not scanned (HTTP {r.status_code})"] += 1
    for path in ("/api/facet-distinct", "/api/facet-tree", "/api/location-stats", "/api/stats-detailed",
                 "/api/stats", "/api/tags", "/api/platform-affordance-evidence",
                 "/api/triage-eval", "/api/triage-model-corpus"):
        main.limiter.reset()
        r = public.get(path)
        if r.status_code == 200:
            check(path, r.text)
        else:
            report[f"api {path}: not scanned (HTTP {r.status_code})"] += 1


def scan_graphs(people: Dict[str, Set[str]], report: Counter) -> None:
    gdir = REPO / "ontology" / "graph_output"
    for cid, names in people.items():
        pat = _pattern(names)
        for ext in ("ttl", "provenance.ttl"):
            f = gdir / f"{cid}.{ext}"
            if f.exists():
                report[f"graph *.{ext}: files"] += 1
                if pat.search(f.read_text(encoding="utf-8", errors="ignore")):
                    report[f"graph *.{ext}: LEAK"] += 1


def scan_stored(db: sqlite3.Connection, people: Dict[str, Set[str]], report: Counter) -> None:
    for (ex,) in db.execute("SELECT extras_json FROM field_assertions WHERE extras_json LIKE '%entity%' OR extras_json LIKE '%sentence_subject%'"):
        extras = json.loads(ex or "{}") or {}
        raw = any(k in extras for k in ("defendant_entity", "sentence_subject")) or bool(
            PK._is_name(str(extras.get("entity") or "")) and len(str(extras.get("entity")).split()) >= 2)
        if raw:
            report["stored field_assertions extras: LEAK"] += 1
    n = db.execute("SELECT count(*) FROM field_resolutions WHERE final_json LIKE '%\"entity\"%'").fetchone()[0]
    if n:
        report["stored field_resolutions entity keys: LEAK"] += n
    keys = ("locations", "organizations", "agencies_involved", "location_grounds", "agency_grounds")
    for cid, fj in db.execute("SELECT id, extracted_features FROM cases"):
        names = people.get(cid)
        if not names:
            continue
        feats = json.loads(fj or "{}") or {}
        blob = json.dumps({k: feats.get(k) for k in keys} | {"ner": (feats.get("ml_features") or {}).get("ner_entities")})
        report["stored entity lists: cases"] += 1
        if _pattern(names).search(blob):
            report["stored entity lists: LEAK"] += 1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sqlite", required=True)
    ap.add_argument("--cases", default="500", help="number of cases to call per-case endpoints for, or 'all'")
    ap.add_argument("--graphs", action="store_true", help="also scan ontology/graph_output")
    ap.add_argument("--no-api", action="store_true")
    args = ap.parse_args()

    db = sqlite3.connect(args.sqlite)
    people = case_people(db)
    ids = sorted(people)
    if args.cases != "all":
        random.Random(20261029).shuffle(ids)
        ids = ids[: int(args.cases)]
    report: Counter = Counter()
    report["cases with named people"] = len(people)
    scan_stored(db, people, report)
    if not args.no_api:
        scan_api(args.sqlite, people, ids, report, held_person_values(db, people))
    if args.graphs:
        scan_graphs(people, report)
    for k in sorted(report):
        print(f"{report[k]:7}  {k}")
    leaks = sum(v for k, v in report.items() if k.endswith("LEAK"))
    print(f"\n{'FAIL' if leaks else 'PASS'}: {leaks} surfaces/items with a person name")
    sys.exit(1 if leaks else 0)


if __name__ == "__main__":
    main()
