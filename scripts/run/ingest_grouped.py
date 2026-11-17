#!/usr/bin/env python3
"""
Ingest PDFs one-by-one (or in small groups) inside ONE long-lived process.

Models (Stanza NER + MiniLM) load once on the first PDF and stay warm.

Usage (from repo root):
  python3 scripts/run/ingest_grouped.py --list /tmp/pdfs.txt --group-size 1
  python3 scripts/run/ingest_grouped.py --list /tmp/pdfs.txt --done-file ingest_done.txt

--done-file makes a bulk ingest resumable: each PDF is appended once its group is
stored, and PDFs already listed are skipped on the next run.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path


def _bootstrap_paths(repo_root: Path) -> None:
    pattern = repo_root / "src" / "Processing Layer" / "Pattern Processing Layer"
    processing = repo_root / "src" / "Processing Layer"
    ingestion = repo_root / "src" / "Ingestion Layer"
    storage = repo_root / "src" / "Storage Layer"
    src = repo_root / "src"
    for p in (pattern, processing, ingestion, storage, src):
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list",
        required=True,
        help="Text file with one absolute PDF path per line",
    )
    parser.add_argument(
        "--group-size",
        type=int,
        default=int(os.environ.get("INGEST_GROUP_SIZE", "1")),
        help="PDFs per run_pipeline call (default 1 = one-by-one, models stay warm)",
    )
    parser.add_argument(
        "--done-file",
        default=os.environ.get("INGEST_DONE_FILE", ""),
        help="Append each stored PDF here and skip PDFs already listed (resume after a crash)",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    _bootstrap_paths(repo_root)
    os.chdir(repo_root)

    list_path = Path(args.list)
    pdfs = [
        line.strip()
        for line in list_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not pdfs:
        print(f"No PDF paths in {list_path}", file=sys.stderr)
        return 1
    done_path = Path(args.done_file) if args.done_file else None
    if done_path and done_path.exists():
        done = {line.strip() for line in done_path.read_text(encoding="utf-8").splitlines() if line.strip()}
        skipped = [p for p in pdfs if p in done]
        pdfs = [p for p in pdfs if p not in done]
        if skipped:
            print(f"Resuming: {len(skipped)} PDF(s) already in {done_path}, {len(pdfs)} left", flush=True)
        if not pdfs:
            print("Nothing left to ingest.", flush=True)
            return 0

    group_size = max(1, args.group_size)
    print(
        f"Long-lived ingest: {len(pdfs)} PDF(s), {group_size} per pipeline call "
        f"(Stanza/MiniLM stay warm after first load)",
        flush=True,
    )

    from main import run_pipeline  # noqa: E402  (after path bootstrap)

    t_all = time.perf_counter()
    for start in range(0, len(pdfs), group_size):
        group = pdfs[start : start + group_size]
        n = start // group_size + 1
        total_groups = (len(pdfs) + group_size - 1) // group_size
        names = [Path(p).name for p in group]
        print(f"\n>>> [{n}/{total_groups}] {names}", flush=True)
        t0 = time.perf_counter()
        try:
            run_pipeline(group)
        except Exception as exc:
            print(f"!!! [{n}/{total_groups}] FAILED: {exc}", flush=True)
            import traceback
            traceback.print_exc()
            return 1
        print(
            f"<<< [{n}/{total_groups}] done in {time.perf_counter() - t0:.1f}s",
            flush=True,
        )
        if done_path:
            with done_path.open("a", encoding="utf-8") as handle:
                handle.writelines(f"{p}\n" for p in group)

    print(
        f"\n✓ All finished in one process ({time.perf_counter() - t_all:.1f}s wall)",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
