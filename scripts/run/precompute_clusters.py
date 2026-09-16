#!/usr/bin/env python3
"""
Precompute automated-analysis / cluster-groups / technology-revolver slim rows
for the current corpus and persist to Postgres (+ optional Redis).

Run after bulk ingest with SKIP_PRECOMPUTE_CLUSTERS=1:

  # Prefer local sqlite for compute speed; write to Railway Postgres:
  unset SKIP_PRECOMPUTE_CLUSTERS
  export DATABASE_URL="$(railway variables --service Postgres --json | python3 -c '…PUBLIC_URL…')"
  export REDIS_URL="$(railway variables --service Redis --json | python3 -c '…PUBLIC_URL…')"
  python3 -u scripts/run/precompute_clusters.py --db caselinker.db

  # Or compute entirely against Railway (slower):
  python3 -u scripts/run/precompute_clusters.py
"""

from __future__ import annotations

import argparse
import gc
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Optional local sqlite for loading cases (writes still go to DATABASE_URL if set)",
    )
    ap.add_argument("--skip-revolver", action="store_true")
    args = ap.parse_args()

    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT / "src" / "Storage Layer"))
    sys.path.insert(0, str(ROOT / "src" / "Processing Layer"))
    sys.path.insert(0, str(ROOT / "src" / "Processing Layer" / "Pattern Processing Layer"))
    sys.path.insert(0, str(ROOT / "src" / "Clustering & Analysis Layer"))
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT / "run"))

    # Load cases: prefer --db sqlite, else Postgres via DATABASE_URL
    if args.db and args.db.is_file():
        from storage import CaseStorage as LocalStorage

        print(f"Loading cases from local sqlite {args.db}…", flush=True)
        local = LocalStorage(str(args.db))
        cases = local.get_all_cases(include_raw_data=False)
    else:
        if not os.environ.get("DATABASE_URL"):
            print("Set DATABASE_URL or pass --db caselinker.db", file=sys.stderr)
            return 1
        from storage_postgres import CaseStorage as PgStorage

        print("Loading cases from Postgres…", flush=True)
        cases = PgStorage().get_all_cases(include_raw_data=False)

    case_count = len(cases)
    print(f"loaded {case_count} cases", flush=True)
    if case_count == 0:
        return 1

    # Always persist to whatever DATABASE_URL points at (Railway).
    if not os.environ.get("DATABASE_URL"):
        print("DATABASE_URL required to persist slim payloads", file=sys.stderr)
        return 1
    from storage_postgres import CaseStorage as PgStorage

    pg = PgStorage()

    from analysis import run_automated_analysis

    t0 = time.perf_counter()
    print("Running automated analysis (clusters)…", flush=True)
    analysis = run_automated_analysis(cases)
    print(f"  analysis done in {time.perf_counter() - t0:.1f}s", flush=True)

    ok_aa = pg.store_automated_analysis_slim(analysis, case_count)
    ok_cg = pg.store_precomputed_clusters(analysis, case_count)
    print(f"  store automated_analysis_slim={ok_aa} cluster_groups_slim={ok_cg}", flush=True)

    # Redis warm (optional)
    try:
        from redis_cache import get_cache_key, set_cached

        result = {"success": True, "analysis": analysis, "cached": True, "source": "precompute_script"}
        set_cached(get_cache_key("automated-analysis", version=case_count), result, ttl=86400)
        # slim cluster-groups shape
        case_groups = analysis.get("case_groups") or []
        slim = []
        for g in case_groups:
            if not isinstance(g, dict):
                continue
            slim.append(
                {
                    "group_id": g.get("group_id"),
                    "size": g.get("size"),
                    "average_similarity": g.get("average_similarity"),
                    "min_similarity": g.get("min_similarity"),
                    "max_similarity": g.get("max_similarity"),
                    "case_ids": g.get("case_ids") or [],
                }
            )
        set_cached(
            get_cache_key("cluster-groups", version=case_count),
            {"success": True, "case_groups": slim, "cached": True, "source": "precompute_script"},
            ttl=86400,
        )
        print("  Redis warmed for automated-analysis + cluster-groups", flush=True)
    except Exception as e:
        print(f"  Redis warm skipped: {e}", flush=True)

    del cases
    gc.collect()

    if not args.skip_revolver:
        print("Computing technology revolver…", flush=True)
        # Import after path setup; needs app storage helpers
        try:
            # Minimal: call compute via importing functions from run.main is heavy
            # (starts FastAPI). Prefer direct pattern if available.
            import importlib.util

            # Load revolver compute without starting uvicorn: exec selected funcs
            # Use HTTP against local? No — import analysis-adjacent module.
            from pathlib import Path as P

            # Fall back: invoke via storage after hitting the same aggregate used in main
            # Importing run.main triggers app setup — acceptable for one-shot script.
            os.environ.setdefault("SKIP_STARTUP_WARMUP", "1")
            import main as app_main  # noqa: E402  (run/main.py via sys.path)

            t1 = time.perf_counter()
            payload = app_main._compute_technology_revolver_payload()
            print(f"  revolver done in {time.perf_counter() - t1:.1f}s", flush=True)
            ok_tr = pg.store_technology_revolver_slim(payload, case_count)
            print(f"  store technology_revolver_slim={ok_tr}", flush=True)
            try:
                from redis_cache import get_cache_key, set_cached

                ver = getattr(app_main, "_TECHNOLOGY_REVOLVER_SNIPPET_VER", 1)
                set_cached(
                    get_cache_key("technology-revolver", version=case_count, snippet_v=ver),
                    payload,
                    ttl=3600,
                )
                print("  Redis warmed for technology-revolver", flush=True)
            except Exception as e:
                print(f"  Redis revolver warm skipped: {e}", flush=True)
        except Exception as e:
            print(f"  technology revolver FAILED: {e}", flush=True)
            import traceback

            traceback.print_exc()

    print(f"DONE case_count={case_count}", flush=True)
    return 0 if (ok_aa and ok_cg) else 1


if __name__ == "__main__":
    raise SystemExit(main())
