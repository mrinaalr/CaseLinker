#!/usr/bin/env python3
"""Deterministic, dependency-free checks for CaseLinker's authored source files."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

TEXT_SUFFIXES = frozenset(
    {
        ".css",
        ".html",
        ".js",
        ".json",
        ".md",
        ".py",
        ".sh",
        ".sql",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }
)
TEXT_FILENAMES = frozenset({"LICENSE", "Dockerfile", ".editorconfig", ".gitattributes"})
GENERATED_PREFIXES = (
    "ontology/graph_output/",
    "ontology/mcp_output/",
    "ontology/PACER/BULK_FOLDER/",
    "state_machines/graphs/",
)
MERGE_MARKER_PREFIXES = (b"<<<<<<< ", b">>>>>>> ")


@dataclass(frozen=True, slots=True)
class Finding:
    path: Path
    check: str
    detail: str

    def render(self, root: Path) -> str:
        try:
            display_path = self.path.relative_to(root)
        except ValueError:
            display_path = self.path
        return f"{display_path}: {self.check}: {self.detail}"


def tracked_paths(root: Path) -> list[Path]:
    """Return regular files tracked by the repository, in stable order."""
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    relative_paths = sorted(
        (Path(raw.decode("utf-8")) for raw in result.stdout.split(b"\0") if raw),
        key=lambda path: path.as_posix(),
    )
    return [root / path for path in relative_paths if (root / path).is_file()]


def is_authored_text(path: Path, root: Path) -> bool:
    relative = path.relative_to(root).as_posix()
    if relative.startswith(GENERATED_PREFIXES):
        return False
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in TEXT_FILENAMES


def validate_text(path: Path, data: bytes) -> list[Finding]:
    findings: list[Finding] = []
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return [Finding(path, "utf8", str(exc))]

    if "\ufffd" in text:
        findings.append(Finding(path, "utf8", "contains the Unicode replacement character"))
    if "\x00" in text:
        findings.append(Finding(path, "text", "contains a NUL byte"))

    for line_number, line in enumerate(data.splitlines(), start=1):
        marker = next(
            (prefix for prefix in MERGE_MARKER_PREFIXES if line.startswith(prefix)),
            b"=======" if line == b"=======" else None,
        )
        if marker is not None:
            findings.append(
                Finding(
                    path,
                    "merge-marker",
                    f"line {line_number} contains unresolved marker {marker.decode()!r}",
                )
            )
    return findings


def validate_python(path: Path, source: str) -> list[Finding]:
    try:
        compile(source, str(path), "exec", dont_inherit=True)
    except (SyntaxError, ValueError) as exc:
        if isinstance(exc, SyntaxError):
            line = f" line {exc.lineno}" if exc.lineno else ""
            detail = f"{exc.msg}{line}"
        else:
            detail = str(exc)
        return [Finding(path, "python-compile", detail)]
    return []


def check_paths(root: Path, paths: Iterable[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        if not is_authored_text(path, root):
            continue
        data = path.read_bytes()
        text_findings = validate_text(path, data)
        findings.extend(text_findings)
        if path.suffix == ".py" and not any(item.check == "utf8" for item in text_findings):
            findings.extend(validate_python(path, data.decode("utf-8")))
    return findings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Optional repository-relative files. Defaults to all tracked files.",
    )
    return parser


def main(argv: Sequence[str] | None = None, *, root: Path | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = root or Path(__file__).resolve().parents[2]
    paths = [root / path for path in args.paths] if args.paths else tracked_paths(root)
    missing = [path for path in paths if not path.is_file()]
    if missing:
        for path in missing:
            print(Finding(path, "path", "file does not exist").render(root), file=sys.stderr)
        return 2

    findings = check_paths(root, paths)
    if findings:
        for finding in findings:
            print(finding.render(root), file=sys.stderr)
        print(f"repository check failed with {len(findings)} finding(s)", file=sys.stderr)
        return 1

    print(f"repository check passed for {len(paths)} tracked file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
