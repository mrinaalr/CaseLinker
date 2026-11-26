#!/usr/bin/env python3
"""Regenerate every AfH 2.0 Q1 output.

  run_all.py --export              refresh data/snapshot.sqlite from a CaseLinker DB (read-only), then build
  run_all.py --snapshot afh-2.0    download a frozen era snapshot (CaseLinker-Key), check its sha256, then build
  run_all.py                       build outputs/ and public/ from data/snapshot.sqlite
  run_all.py --public              build outputs/ (scratch, not shipped) from the shipped text-free numbers/public/ snapshot
  run_all.py --verify [--public]   rebuild into a temp dir and compare with the shipped numbers/build/
                                   (--public needs no caselinker.db: it reads numbers/public/ only)

The source DB defaults to ../CaseLinker/caselinker.db; set AFH_Q1_SOURCE_DB to override. --snapshot reads
CASELINKER_API_URL and CASELINKER_KEY. A --public build cannot write legacy_afh1_exemplars.json, which
resolves old case ids against release text.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from afhq1 import build, snapshot  # noqa: E402

ERAS = HERE / "snapshots.json"


def fetch_era(era: str) -> None:
    """Download a frozen snapshot from GET /api/snapshots/<era> and check it against snapshots.json."""
    eras = json.loads(ERAS.read_text(encoding="utf-8"))["eras"]
    if era not in eras:
        raise SystemExit(f"unknown era {era!r}; known: {sorted(eras) or 'none'}")
    base = os.environ.get("CASELINKER_API_URL", "").rstrip("/")
    key = os.environ.get("CASELINKER_KEY", "")
    if not base or not key:
        raise SystemExit("set CASELINKER_API_URL and CASELINKER_KEY to download a frozen snapshot")
    req = urllib.request.Request(f"{base}/api/snapshots/{era}", headers={"CaseLinker-Key": key})
    snapshot.DATA.mkdir(parents=True, exist_ok=True)
    tmp = snapshot.SNAPSHOT.with_suffix(".download")
    h = hashlib.sha256()
    with urllib.request.urlopen(req) as resp, tmp.open("wb") as f:
        for chunk in iter(lambda: resp.read(1 << 20), b""):
            h.update(chunk)
            f.write(chunk)
    if h.hexdigest() != eras[era]["sha256"]:
        tmp.unlink()
        raise SystemExit(f"{era}: sha256 {h.hexdigest()} != registered {eras[era]['sha256']}")
    tmp.replace(snapshot.SNAPSHOT)
    print(f"snapshot {era} sha256 ok")


def verify_against_shipped(shipped: Path, rebuilt: dict, skip=frozenset()) -> list:
    """Three-way check, file by file: the rebuilt output, the shipped file's actual bytes, and the hash
    recorded in the shipped RUN_IDENTITY.json must all agree, with no file missing or extra on either side."""
    recorded = json.loads((shipped / "RUN_IDENTITY.json").read_text())["outputs_sha256"]
    on_disk = {str(p.relative_to(shipped)): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(shipped.rglob("*")) if p.is_file() and p.name != "RUN_IDENTITY.json"
               and "latex" not in p.relative_to(shipped).parts}
    problems = []
    for k in sorted((set(recorded) | set(rebuilt) | set(on_disk)) - set(skip)):
        if k not in on_disk:
            problems.append(f"{k}: missing from the shipped build")
        elif k not in recorded:
            problems.append(f"{k}: shipped but not in RUN_IDENTITY.json")
        elif k not in rebuilt:
            problems.append(f"{k}: not produced by the rebuild")
        elif not (rebuilt[k] == on_disk[k] == recorded[k]):
            problems.append(f"{k}: rebuilt, shipped and recorded hashes disagree")
    return problems


def current_identity(public: bool) -> str:
    if public:
        return json.loads((snapshot.PUBLIC / "meta.json").read_text(encoding="utf-8"))["dataset_identity"]
    return snapshot.snapshot_meta(snapshot.connect())["dataset_identity"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export", action="store_true")
    ap.add_argument("--snapshot", metavar="ERA", help="download this frozen era snapshot first")
    ap.add_argument("--public", action="store_true", help="build from the committed text-free public/ snapshot")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--expect-identity", help="refuse to build unless the snapshot has this dataset identity")
    args = ap.parse_args(argv)
    if args.export and args.snapshot:
        raise SystemExit("--export and --snapshot both write data/snapshot.sqlite; pick one")
    if args.public and (args.export or args.snapshot):
        raise SystemExit("--public reads the committed public/ snapshot; drop --export/--snapshot")
    if args.export:
        ident = snapshot.export_snapshot()
        print(f"snapshot {ident['dataset_identity']} cases={ident['case_count']}")
    if args.snapshot:
        fetch_era(args.snapshot)
    committed = HERE / "numbers" / "build" / "RUN_IDENTITY.json"   # the shipped AfH 2.0 build
    if args.verify and not committed.is_file():
        print(f"{committed} missing: no committed outputs to verify against", file=sys.stderr)
        return 2
    have = current_identity(args.public)
    pinned = json.loads(committed.read_text())["dataset_identity"] if committed.is_file() else None
    want = args.expect_identity or (pinned if args.verify else None)
    if want and want != have:
        print(f"snapshot identity {have} != expected {want}; outputs would differ", file=sys.stderr)
        return 2
    if args.verify:
        with tempfile.TemporaryDirectory() as tmp:
            build.OUT = Path(tmp) / "outputs"
            build.PUBLIC = snapshot.PUBLIC if args.public else Path(tmp) / "public"
            ident = build.build(log=lambda *_: None, public=args.public)
        diff = verify_against_shipped(committed.parent, ident["outputs_sha256"],
                                      skip=set(build.TEXT_ONLY_OUTPUTS) if args.public else set())
        print("identical" if not diff else f"differs: {diff}")
        return 0 if not diff else 1
    ident = build.build(public=args.public)
    print(json.dumps({k: ident[k] for k in ("dataset_identity", "case_count", "git", "configs")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
