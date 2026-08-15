"""Command-line interface for CaseLinker snapshot manifests."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from caselinker.snapshots.manifest import (
    ManifestError,
    build_manifest,
    verify_manifest,
    write_manifest,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build a deterministic snapshot manifest")
    build.add_argument("--spec", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)

    verify = subparsers.add_parser("verify", help="Verify a manifest and all referenced files")
    verify.add_argument("--manifest", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "build":
            manifest = build_manifest(root=args.root, spec_path=args.spec)
            write_manifest(args.output, manifest)
            print(f"wrote {args.output} ({manifest['manifest_sha256']})")
            return 0

        findings = verify_manifest(root=args.root, manifest_path=args.manifest)
        if findings:
            for finding in findings:
                print(finding, file=sys.stderr)
            print(f"verification failed with {len(findings)} finding(s)", file=sys.stderr)
            return 1
        print(f"verified {args.manifest}")
        return 0
    except ManifestError as exc:
        print(f"snapshot manifest error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
