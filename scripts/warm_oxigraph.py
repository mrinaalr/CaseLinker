#!/usr/bin/env python3
"""Wake Oxigraph before a demo so the first SPARQL query is not a cold start.

The web service polls the store and returns when it answers, or a
machine-readable waking payload if it is still opening.

  python3 scripts/warm_oxigraph.py
  python3 scripts/warm_oxigraph.py --url https://caselinker.up.railway.app

Exit 0 when the store is awake, 1 when it is still waking.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default=os.environ.get("CASELINKER_API_URL", "https://caselinker.up.railway.app"),
        help="CaseLinker origin (default: CASELINKER_API_URL or production)",
    )
    args = parser.parse_args(argv)
    endpoint = args.url.rstrip("/") + "/api/oxigraph/warm"
    req = urllib.request.Request(
        endpoint,
        data=b"{}",
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=70) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        status = exc.code
    except urllib.error.URLError as exc:
        print(f"warm request failed: {exc.reason}", file=sys.stderr)
        return 1

    try:
        body = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        print(raw[:500], file=sys.stderr)
        return 1

    print(json.dumps(body, indent=2))
    if status == 200 and body.get("status") == "awake":
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
