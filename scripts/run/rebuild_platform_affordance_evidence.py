#!/usr/bin/env python3
"""Rebuild platform affordance evidence when the corpus identity changes.

The builder reads caselinker.db. This script compares that database to the
recorded corpus_case_count and extraction_run_fingerprint.

  python3 scripts/run/rebuild_platform_affordance_evidence.py --check
  python3 scripts/run/rebuild_platform_affordance_evidence.py --check --strict
  python3 scripts/run/rebuild_platform_affordance_evidence.py

--check prints the decision and the db_gaps gate and does not write.
--strict makes --check exit 1 when a rebuild is required or db_gaps is above
the warning threshold. Without --check, a rebuild decision runs the builder.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "run"
if str(RUN) not in sys.path:
    sys.path.insert(0, str(RUN))

from platform_affordance_evidence_freshness import (  # noqa: E402
    gap_gate,
    mismatched_inputs,
    read_live_identity,
    rebuild_decision,
    snapshot_freshness,
)

EVIDENCE = ROOT / "ontology" / "platform_affordance_evidence" / "platform_affordance_evidence.json"
DB = Path(os.environ.get("CASELINKER_DB", str(ROOT / "caselinker.db")))
BUILDER = ROOT / "ontology" / "platform_affordance_evidence" / "platform_affordance_evidence.py"


def refresh_platform_affordance_evidence(root: Path | None = None) -> dict:
    """Rebuild the snapshot from caselinker.db and report whether it is still stale.

    An MCP tool or agent can call this. It writes the evidence file when the
    recorded corpus count and extraction-run fingerprint do not match the
    database, then returns the freshness object for that file.
    """
    root = root or ROOT
    evidence = root / "ontology" / "platform_affordance_evidence" / "platform_affordance_evidence.json"
    database = Path(os.environ.get("CASELINKER_DB", str(root / "caselinker.db")))
    builder = root / "ontology" / "platform_affordance_evidence" / "platform_affordance_evidence.py"
    if not evidence.is_file():
        raise FileNotFoundError(evidence)
    if not database.is_file():
        raise FileNotFoundError(database)
    meta = json.loads(evidence.read_text(encoding="utf-8")).get("_meta") or {}
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as conn:
        live = read_live_identity(conn, root)
    decision = rebuild_decision(meta, live)
    rebuilt = False
    if decision == "rebuild":
        completed = subprocess.run([sys.executable, str(builder)], cwd=root,
                                   env={**os.environ, "CASELINKER_DB": str(database)})
        if completed.returncode != 0:
            raise RuntimeError(f"evidence builder exited {completed.returncode}")
        rebuilt = True
        meta = json.loads(evidence.read_text(encoding="utf-8")).get("_meta") or {}
        with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as conn:
            live = read_live_identity(conn, root)
    freshness = snapshot_freshness(meta, live)
    return {"decision": decision, "rebuilt": rebuilt, "freshness": freshness}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report only; do not rebuild")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="with --check, exit 1 when a rebuild is required or db_gaps warns",
    )
    args = parser.parse_args(argv)
    if not EVIDENCE.is_file():
        print(f"missing {EVIDENCE}", file=sys.stderr)
        return 1
    meta = json.loads(EVIDENCE.read_text(encoding="utf-8")).get("_meta") or {}
    gate = gap_gate(meta.get("db_gaps"))
    print(f"db_gaps={meta.get('db_gaps')} gate={gate}")
    if not DB.is_file():
        print("caselinker.db is absent; corpus identity was not compared", file=sys.stderr)
        return 1 if args.strict else 0
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as conn:
        live = read_live_identity(conn, ROOT)
    decision = rebuild_decision(meta, live)
    print(f"decision={decision} live_cases={None if live is None else live.get('case_count')}")
    if decision != "current":
        print("mismatched=" + ",".join(mismatched_inputs(meta, live)))
    if args.check:
        if args.strict and (decision != "current" or gate != "ok"):
            return 1
        return 0
    if decision == "current":
        print("snapshot identity matches; not rebuilding")
        return 0
    if decision == "unknown":
        print("corpus identity unavailable; not rebuilding", file=sys.stderr)
        return 1
    try:
        result = refresh_platform_affordance_evidence(ROOT)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    freshness = result["freshness"]
    print(
        f"rebuilt={result['rebuilt']} stale={freshness['stale']} "
        f"live_case_count={freshness['live_case_count']} coverage_pct={freshness['coverage_pct']}"
    )
    return 0 if freshness.get("stale") is False else 1


if __name__ == "__main__":
    raise SystemExit(main())
