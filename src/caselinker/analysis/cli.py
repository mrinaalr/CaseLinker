"""Build Evidence Packs and execute Claim CI from pinned repository inputs."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

from caselinker.analysis.claim_ci import ClaimCiEvaluator, ClaimExpectation
from caselinker.analysis.pipeline import (
    ClaimPipeline,
    ClaimPipelineError,
    resolve_repository_input,
)
from caselinker.snapshots.manifest import canonical_json


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _load_expectation(path: Path) -> ClaimExpectation:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClaimPipelineError("expectation is not valid UTF-8 JSON") from exc
    if not isinstance(raw, Mapping) or not all(isinstance(key, str) for key in raw):
        raise ClaimPipelineError("expectation must be a JSON object")
    try:
        return ClaimExpectation.from_dict(raw)
    except ValueError as exc:
        raise ClaimPipelineError(f"expectation is invalid: {exc}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build a canonical Evidence Pack")
    build.add_argument("--spec", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)

    check = subparsers.add_parser("check", help="Regenerate and evaluate a Claim CI contract")
    check.add_argument("--spec", type=Path, required=True)
    check.add_argument("--expectation", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = ClaimPipeline().run(root=args.root, spec_path=args.spec)
        if args.command == "build":
            _write_atomic(args.output, result.evidence_pack.canonical_json)
            print(f"wrote {args.output} ({result.evidence_pack.pack_id})")
            return 0

        expectation_path = resolve_repository_input(
            args.root, args.expectation, field="claim expectation"
        )
        expectation = _load_expectation(expectation_path)
        report = ClaimCiEvaluator().evaluate(
            expectation=expectation,
            claim=result.claim,
            evidence_pack=result.evidence_pack,
        )
        print(canonical_json(report.to_dict()).decode("utf-8"))
        return 0 if report.passed else 1
    except (ClaimPipelineError, OSError, ValueError) as exc:
        print(f"claim pipeline error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
