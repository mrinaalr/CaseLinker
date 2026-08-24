#!/usr/bin/env python3
"""Verify paper claims → scripts/verify/paper/claims.md + paper_tested.md.

Optional snapshot modes (PR B):
  --snapshot [PATH]          emit a content-addressed manifest pinning corpus
                             state, code revision, and claim results
  --against-snapshot PATH    re-run claims and report attributed deltas
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

VERIFY_DIR = Path(__file__).resolve().parent
REPO_ROOT = VERIFY_DIR.parents[2]
sys.path.insert(0, str(VERIFY_DIR))

from claim_snapshot import (  # noqa: E402
    compare_against_snapshot,
    emit_claim_snapshot,
    format_drift_summary,
    git_code_revision,
    git_recorded_at,
    load_pinned_snapshot,
    pin_corpus,
    write_stable_json,
)
from claims_registry import build_claims  # noqa: E402
from paper import PAPER_URL, load_or_build_paper_text, verify_dir  # noqa: E402
from report import write_reports  # noqa: E402
from verifiers import build_context, verify_all  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify paper claims against CaseLinker")
    parser.add_argument("--db", type=Path, default=REPO_ROOT / "caselinker.db")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output dir (default: scripts/verify/paper/)",
    )
    parser.add_argument("--refresh-paper", action="store_true")
    parser.add_argument("--json", type=Path, default=None, help="Also write results.json")
    parser.add_argument(
        "--snapshot",
        nargs="?",
        const="",
        default=None,
        metavar="PATH",
        help=(
            "After verifying claims, emit a content-addressed snapshot manifest. "
            "Optional path (default: <out>/snapshot/manifest.json)."
        ),
    )
    parser.add_argument(
        "--against-snapshot",
        type=Path,
        default=None,
        metavar="MANIFEST",
        help="Re-run claim queries and report deltas against a pinned manifest.",
    )
    parser.add_argument(
        "--recorded-at",
        default=None,
        help="UTC timestamp ending in Z for --snapshot (default: git commit time).",
    )
    parser.add_argument(
        "--code-revision",
        default=None,
        help="Override git SHA recorded in the snapshot (tests / dirty trees).",
    )
    return parser.parse_args(argv)


def _write_results_json(path: Path, results: list[object]) -> None:
    payload = [
        {
            "claim_id": r.claim_id,
            "status": r.status,
            "observed": r.observed,
            "expected": r.expected,
            "source": r.source,
            "detail": r.detail,
            "notes": r.notes,
        }
        for r in results
    ]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    out_dir = args.out or verify_dir()
    paper_text, _ = load_or_build_paper_text(refresh=args.refresh_paper)

    claims = build_claims()
    ctx = build_context(db_path=args.db, paper_text=paper_text)
    results = verify_all(claims, ctx)

    claims_path, tested_path = write_reports(
        out_dir, claims, results, PAPER_URL, db_path=args.db
    )
    print(f"Wrote {claims_path}")
    print(f"Wrote {tested_path}")

    if args.json:
        _write_results_json(args.json, results)
        print(f"Wrote {args.json}")

    # Snapshot pin/compare is opt-in. Default verify_paper is today's path:
    # write the claim reports and stop. pin_corpus must not be a new
    # default-path failure mode.
    if args.snapshot is not None or args.against_snapshot is not None:
        code_revision = args.code_revision or git_code_revision(REPO_ROOT)
        conn = sqlite3.connect(str(args.db))
        try:
            corpus = pin_corpus(conn)
        finally:
            conn.close()

        if args.snapshot is not None:
            if args.snapshot:
                snapshot_dir = Path(args.snapshot).parent
            else:
                snapshot_dir = out_dir / "snapshot"
            recorded_at = args.recorded_at or git_recorded_at(REPO_ROOT)
            written = emit_claim_snapshot(
                snapshot_dir=snapshot_dir,
                corpus=corpus,
                results=results,
                code_revision=code_revision,
                recorded_at=recorded_at,
            )
            print(f"Wrote {written}")

        if args.against_snapshot is not None:
            pinned = load_pinned_snapshot(args.against_snapshot)
            report = compare_against_snapshot(
                pinned=pinned,
                live_corpus=corpus,
                live_results=results,
                live_code_revision=code_revision,
            )
            drift_path = out_dir / "claim-drift.json"
            write_stable_json(drift_path, report)
            print(f"Wrote {drift_path}")
            print(format_drift_summary(report))

    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    print("Summary:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 1 if counts.get("fail") else 0


if __name__ == "__main__":
    raise SystemExit(main())
