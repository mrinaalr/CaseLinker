#!/usr/bin/env python3
"""Shared CaseLinker → JSON-LD/TTL graph generation (features_to_cac).

Writes a case graph and, by default, its provenance sidecar. Turtle is taken
from the mapped triples, not from a Dataset's empty default graph. When
DATABASE_URL is set, cases are read from Postgres. A ``done.txt`` in the
output directory lets a stopped run continue.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
ONTOLOGY = REPO_ROOT / "ontology"
DEFAULT_GRAPH_DIR = ONTOLOGY / "graph_output"
RESOURCE_IRI = "w3id.org/caselinker/resource"
# Hosts that must not be minted as CaseLinker names. The CAC ontology
# (cacontology.projectvic.org) is a different vocabulary and is allowed.
_REJECTED_IRIS = (
    ("caselinker.projectvic.org", "projectvic IRI"),
    ("caselinker.up.railway.app/resource", "railway resource IRI"),
    ("caselinker.up.railway.app/ns/provenance", "railway provenance IRI"),
)

sys.path.insert(0, str(ONTOLOGY))


def _open_export_storage(*, postgres_only: Optional[bool] = None) -> Tuple[Any, str]:
    """Postgres when DATABASE_URL is set, otherwise the local SQLite file.

    A local ``caselinker.db`` must not hide the production corpus while
    DATABASE_URL is set. Pass ``postgres_only=False`` to force SQLite.
    """
    from features_to_cac import CaseToCAC  # noqa: E402

    use_postgres = postgres_only if postgres_only is not None else bool(os.getenv("DATABASE_URL"))
    if use_postgres:
        storage = CaseToCAC._open_postgres()
        if storage is None:
            raise RuntimeError("DATABASE_URL is set but Postgres did not open")
        return storage, "postgres"
    storage = CaseToCAC._open_local_sqlite()
    if storage is None:
        raise FileNotFoundError("No local caselinker.db and DATABASE_URL is not set")
    return storage, "sqlite"


def _reject_bad_iris(text: str, case_id: str, kind: str) -> None:
    for needle, label in _REJECTED_IRIS:
        if needle in text:
            raise RuntimeError(f"{label} in {kind} for {case_id}")
    if RESOURCE_IRI not in text:
        raise RuntimeError(f"missing w3id resource IRI in {kind} for {case_id}")


def generate_graphs(
    ids: List[str],
    out_dir: Path,
    *,
    validate_shacl: bool = True,
    provenance: bool = True,
    resume: bool = True,
    postgres_only: Optional[bool] = None,
    storage: Any = None,
) -> Dict[str, Any]:
    from features_to_cac import CaseToCAC, flatten_dataset, _write_serialized  # noqa: E402
    from provenance_export import evidence_coverage, export_stored_case  # noqa: E402

    out_dir.mkdir(parents=True, exist_ok=True)
    done_path = out_dir / "done.txt"
    already = set()
    if resume and done_path.is_file():
        already = {line.strip() for line in done_path.read_text().splitlines() if line.strip()}
    if storage is None:
        storage, _source = _open_export_storage(postgres_only=postgres_only)
    mapper = CaseToCAC()

    generated: List[str] = []
    skipped: List[Dict[str, str]] = []
    failed: List[Dict[str, str]] = []
    no_provenance: List[str] = []
    shacl_ok: List[str] = []
    shacl_fail: List[Dict[str, Any]] = []
    # Cases whose age, sentence or CyberTip nodes lack a linked annotation (#73).
    # Reported, not fatal: an old resolution without winning ids links nothing.
    coverage_gaps: List[Dict[str, str]] = []

    for i, cid in enumerate(ids, 1):
        if cid in already:
            skipped.append({"case_id": cid, "reason": "already in done.txt"})
            continue
        try:
            case = storage.get_case(cid)
            if case is None:
                skipped.append({"case_id": cid, "reason": "not in DB"})
                continue

            graph, _warnings = mapper.map_case(case)
            conforms, shacl_report = True, ""
            if validate_shacl:
                conforms, shacl_report = mapper.validate(graph)
                if not conforms:
                    shacl_fail.append({"case_id": cid, "shacl_report": (shacl_report or "")[:4000]})
                    raise RuntimeError("case SHACL failed: " + (shacl_report or "")[:300])

            flat = flatten_dataset(graph)
            ttl_path = out_dir / f"{cid}.ttl"
            jsonld_path = out_dir / f"{cid}.jsonld"
            _write_serialized(flat, jsonld_path, "json-ld")
            _write_serialized(flat, ttl_path, "turtle")
            turtle = ttl_path.read_text()
            _reject_bad_iris(turtle, cid, "case graph")

            if provenance:
                prov = export_stored_case(cid, out_dir, storage, evidence_nodes=getattr(mapper, "evidence_nodes", None))
                if prov is None:
                    no_provenance.append(cid)
                    print(f"  NO_PROV {cid}", flush=True)
                else:
                    prov_text = Path(prov).read_text()
                    _reject_bad_iris(prov_text, cid, "provenance")
                    from rdflib import Graph as _Graph  # noqa: E402

                    covered, coverage_report = evidence_coverage(flat, _Graph().parse(data=prov_text, format="turtle"))
                    if not covered:
                        coverage_gaps.append({"case_id": cid, "report": coverage_report[:2000]})

            with done_path.open("a") as fh:
                fh.write(cid + "\n")
            already.add(cid)
            shacl_ok.append(cid)
            generated.append(cid)
        except Exception as exc:
            failed.append(
                {
                    "case_id": cid,
                    "reason": str(exc),
                    "traceback": traceback.format_exc()[-1500:],
                }
            )
            print(f"  FAIL {cid}: {exc}", file=sys.stderr)

        if i % 50 == 0:
            print(
                f"  [{i}/{len(ids)}] generated={len(generated)} "
                f"shacl_ok={len(shacl_ok)} fail={len(failed)}",
                flush=True,
            )

    return {
        "generated": generated,
        "skipped": skipped,
        "failed": failed,
        "no_provenance": no_provenance,
        "shacl_ok": shacl_ok,
        "shacl_fail": shacl_fail,
        "coverage_gaps": coverage_gaps,
        "out_dir": str(out_dir),
    }


def generate_graph_for_ids(case_ids: List[str]) -> Dict[str, Any]:
    """
    Build a merged in-memory CAC ontology graph for specific case IDs.

    Uses the same DB loaders and CaseToCAC mapper as the batch pipeline but
    does not write JSON-LD/TTL files or mutate the database.

    When a case is missing locally, falls back to GET /api/cases/{id} when
    CASELINKER_API_URL is set (aligns MCP stdio dev with the remote corpus).
    """
    import json
    import os

    import requests

    from features_to_cac import CaseToCAC, _load_case_with_fallback  # noqa: E402
    from graph_utils import flat_nodes_to_nodes_edges  # noqa: E402
    from merge_graph_cache import merge_case_into_store  # noqa: E402

    def _load_case(case_id: str) -> Tuple[Optional[Dict[str, Any]], str]:
        case, src = _load_case_with_fallback(case_id)
        if case is not None:
            return case, src
        api_url = os.getenv("CASELINKER_API_URL", "").strip().rstrip("/")
        if not api_url:
            return None, "missing"
        headers = {"Accept": "application/json"}
        key = os.getenv("CASELINKER_KEY", "").strip()
        if key:
            headers["CaseLinker-Key"] = key
        try:
            resp = requests.get(f"{api_url}/api/cases/{case_id}", headers=headers, timeout=30)
            if resp.status_code == 200:
                return resp.json(), "api"
        except requests.RequestException:
            pass
        return None, "missing"

    requested = [str(cid).strip() for cid in case_ids if cid and str(cid).strip()]
    mapper = CaseToCAC()
    store: Dict[str, Dict[str, Any]] = {}
    mapped: List[str] = []
    skipped: List[Dict[str, str]] = []

    for cid in requested:
        case, src = _load_case(cid)
        if case is None:
            skipped.append({"case_id": cid, "reason": "not in DB or API"})
            continue
        graph, _warnings = mapper.map_case(case)
        jsonld_str = graph.serialize(format="json-ld")
        doc = json.loads(jsonld_str)
        merge_case_into_store(store, cid, doc)
        mapped.append(cid)

    flat = list(store.values())
    for node in flat:
        node["_isShared"] = len(node.get("_cases") or []) > 1

    nodes, edges = flat_nodes_to_nodes_edges(flat)
    metadata = {
        "requested_count": len(requested),
        "cases_mapped": mapped,
        "skipped": skipped,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }
    return {"nodes": nodes, "edges": edges, "metadata": metadata, "flat_nodes": flat}


def load_all_case_ids(db_path: Optional[Path] = None, *, postgres_only: Optional[bool] = None) -> List[str]:
    """Case ids in storage order. Postgres when DATABASE_URL is set."""
    use_postgres = postgres_only if postgres_only is not None else bool(os.getenv("DATABASE_URL"))
    if use_postgres and db_path is None:
        from features_to_cac import CaseToCAC  # noqa: E402

        CaseToCAC._storage_layer_dir()
        from storage_postgres import get_connection, return_connection  # type: ignore

        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM cases ORDER BY id")
            return [row[0] for row in cursor.fetchall()]
        finally:
            return_connection(conn)
    import sqlite3

    db = db_path or (REPO_ROOT / "caselinker.db")
    if not db.is_file():
        raise FileNotFoundError(f"Database not found: {db}")
    conn = sqlite3.connect(str(db))
    try:
        return [r[0] for r in conn.execute("SELECT id FROM cases ORDER BY id").fetchall()]
    finally:
        conn.close()


def _load_dotenv() -> None:
    env = REPO_ROOT / ".env"
    if not env.is_file() or os.getenv("DATABASE_URL"):
        return
    for line in env.read_text().splitlines():
        if line.startswith("DATABASE_URL="):
            os.environ["DATABASE_URL"] = line.split("=", 1)[1].strip().strip('"').strip("'")
            return


def main(argv: Optional[List[str]] = None) -> int:
    """Export case graphs and provenance sidecars. Resumes from ``done.txt``."""
    import argparse

    _load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_GRAPH_DIR, help="output directory")
    parser.add_argument("--ids", nargs="*", help="case ids (default: every case in the database)")
    parser.add_argument("--sqlite", action="store_true", help="read caselinker.db even if DATABASE_URL is set")
    parser.add_argument("--no-provenance", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--no-shacl", action="store_true")
    args = parser.parse_args(argv)
    postgres_only = False if args.sqlite else None
    ids = args.ids or load_all_case_ids(postgres_only=postgres_only)
    print(f"Exporting {len(ids)} cases to {args.out}", flush=True)
    result = generate_graphs(
        ids,
        args.out,
        validate_shacl=not args.no_shacl,
        provenance=not args.no_provenance,
        resume=not args.no_resume,
        postgres_only=postgres_only,
    )
    print(
        f"DONE generated={len(result['generated'])} skipped={len(result['skipped'])} "
        f"fail={len(result['failed'])} no_provenance={len(result['no_provenance'])} "
        f"coverage_gaps={len(result['coverage_gaps'])}",
        flush=True,
    )
    for gap in result["coverage_gaps"][:20]:
        print(f"  COVERAGE {gap['case_id']}", flush=True)
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
