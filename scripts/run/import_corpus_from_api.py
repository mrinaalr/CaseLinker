#!/usr/bin/env python3
"""
Pull the production corpus via trusted CaseLinker-Key and load local caselinker.db.

Usage (from repo root, venv active):
  export CASELINKER_KEY='your-trusted-key'
  python3 scripts/run/import_corpus_from_api.py

  # optional overrides
  CASELINKER_API_URL=https://caselinker.up.railway.app \\
  CASELINKER_DB=caselinker.db \\
  python3 scripts/run/import_corpus_from_api.py

Request a trusted key: mramachandra@umass.edu
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "Storage Layer"))

from storage import CaseStorage  # noqa: E402


def normalize(case: dict) -> dict:
    if not isinstance(case.get("date_range"), dict):
        case["date_range"] = {
            "start": case.get("date_start"),
            "end": case.get("date_end"),
        }
    vd = case.get("victim_demographics")
    cd = case.get("case_demographics")
    if not isinstance(cd, dict) and isinstance(vd, list) and vd:
        row = vd[0] if isinstance(vd[0], dict) else {}
        ar = row.get("age_range")
        if isinstance(ar, str):
            try:
                ar = json.loads(ar)
            except Exception:
                ar = None
        rebuilt = {}
        if isinstance(ar, dict) and ar.get("min") is not None:
            lo, hi = ar.get("min"), ar.get("max")
            rebuilt["ages"] = [lo] if hi == lo else [lo, hi]
            rebuilt["age_range"] = ar
        if row.get("region"):
            rebuilt["region"] = row["region"]
        if rebuilt:
            case["case_demographics"] = rebuilt
    return case


def main() -> int:
    key = (os.environ.get("CASELINKER_KEY") or "").strip()
    if not key:
        print(
            "Set CASELINKER_KEY to a trusted CaseLinker-Key.\n"
            "Request access: mramachandra@umass.edu",
            file=sys.stderr,
        )
        return 1

    try:
        import httpx
    except ImportError:
        print("httpx is required (pip install httpx / requirements.txt)", file=sys.stderr)
        return 1

    api_base = (os.environ.get("CASELINKER_API_URL") or "https://caselinker.up.railway.app").rstrip(
        "/"
    )
    db_path = Path(os.environ.get("CASELINKER_DB") or ROOT / "caselinker.db")
    url = f"{api_base}/api/cases"

    print(f"Downloading {url}?include_raw_data=true …")
    t0 = time.time()
    with httpx.Client(timeout=httpx.Timeout(600.0, connect=30.0), follow_redirects=True) as client:
        resp = client.get(
            url,
            params={"include_raw_data": "true"},
            headers={"CaseLinker-Key": key, "User-Agent": "CaseLinker-import_corpus_from_api"},
        )
    if resp.status_code != 200:
        print(f"HTTP {resp.status_code}: {resp.text[:400]}", file=sys.stderr)
        return 1

    cases = resp.json()
    if not isinstance(cases, list) or not cases:
        print("Empty or unexpected export payload", file=sys.stderr)
        return 1
    print(f"Downloaded {len(cases)} cases ({len(resp.content) / 1e6:.1f} MB) in {time.time() - t0:.1f}s")

    if db_path.exists():
        db_path.unlink()
        print(f"Removed existing {db_path}")

    storage = CaseStorage(str(db_path))
    stored = failed = 0
    t1 = time.time()
    for i, case in enumerate(cases, 1):
        try:
            if storage.store_case(normalize(case)):
                stored += 1
            else:
                failed += 1
        except Exception as exc:
            failed += 1
            if failed <= 5:
                print(f"store error {case.get('id')}: {exc}", file=sys.stderr)
        if i % 1000 == 0:
            print(f"  {i}/{len(cases)} stored={stored} failed={failed}")

    print(
        f"Done: stored={stored} failed={failed} "
        f"db={db_path} ({db_path.stat().st_size / 1e6:.1f} MB) "
        f"in {time.time() - t1:.1f}s"
    )
    print(f"Verify: python3 -c \"from pathlib import Path; import sys; "
          f"sys.path.insert(0, 'src/Storage Layer'); from storage import CaseStorage; "
          f"print(CaseStorage('{db_path}').get_case_count())\"")
    print("Then: python3 run/main.py")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
