#!/usr/bin/env python3
"""Regenerate every AfH 2.0 Q1 output.

  python ontology/platform_affordance_evidence/afh_manifest/run_all.py --export   # refresh the pinned snapshot from a CaseLinker DB (read-only)
  python ontology/platform_affordance_evidence/afh_manifest/run_all.py            # build outputs/ from the snapshot
  python ontology/platform_affordance_evidence/afh_manifest/run_all.py --verify   # rebuild into a temp dir and compare with outputs/

The source DB defaults to ../CaseLinker/caselinker.db; set AFH_Q1_SOURCE_DB to override.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from afhq1 import build, snapshot  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--expect-identity", help="refuse to build unless the snapshot has this dataset identity")
    args = ap.parse_args(argv)
    if args.export:
        ident = snapshot.export_snapshot()
        print(f"snapshot {ident['dataset_identity']} cases={ident['case_count']}")
    con = snapshot.connect()
    have = snapshot.snapshot_meta(con)["dataset_identity"]
    pinned = json.loads((HERE / "outputs" / "RUN_IDENTITY.json").read_text())["dataset_identity"] \
        if (HERE / "outputs" / "RUN_IDENTITY.json").is_file() else None
    want = args.expect_identity or (pinned if args.verify else None)
    if want and want != have:
        print(f"snapshot identity {have} != expected {want}; outputs would differ", file=sys.stderr)
        return 2
    if args.verify:
        committed = HERE / "outputs"
        with tempfile.TemporaryDirectory() as tmp:
            build.OUT = Path(tmp)
            ident = build.build(log=lambda *_: None)
        want_files = json.loads((committed / "RUN_IDENTITY.json").read_text())["outputs_sha256"]
        diff = sorted(k for k in set(want_files) | set(ident["outputs_sha256"])
                      if want_files.get(k) != ident["outputs_sha256"].get(k))
        print("identical" if not diff else f"differs: {diff}")
        return 0 if not diff else 1
    ident = build.build()
    print(json.dumps({k: ident[k] for k in ("dataset_identity", "case_count", "git", "configs")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
