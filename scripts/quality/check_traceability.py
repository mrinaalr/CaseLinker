#!/usr/bin/env python3
"""Validate the vNext milestone traceability manifest and governed paths."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Final

MANIFEST_PATH: Final = Path("docs/vnext/traceability.v1.json")
TOP_FIELDS: Final = {
    "schema_version",
    "upstream_baseline",
    "implementation_checkpoint",
    "milestones",
    "manifest_sha256",
}
MILESTONE_FIELDS: Final = {
    "id",
    "title",
    "status",
    "commits",
    "adrs",
    "implementation",
    "tests",
    "migrations",
}
PATH_FIELDS: Final = ("adrs", "implementation", "tests", "migrations")
SHA40: Final = re.compile(r"^[0-9a-f]{40}$")
SHA256: Final = re.compile(r"^[0-9a-f]{64}$")


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _mapping(value: object, *, location: str, findings: list[str]) -> Mapping[str, object] | None:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        findings.append(f"{location} must be an object with string keys")
        return None
    return value


def _safe_file(root: Path, raw: object, *, location: str, findings: list[str]) -> str | None:
    if not isinstance(raw, str) or not raw or "\\" in raw:
        findings.append(f"{location} must be a repository-relative POSIX path")
        return None
    relative = PurePosixPath(raw)
    if relative.is_absolute() or ".." in relative.parts or relative.as_posix() != raw:
        findings.append(f"{location} must be a normalized repository-relative path")
        return None
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            findings.append(f"{location} must not traverse a symbolic link: {raw}")
            return None
    if not current.is_file():
        findings.append(f"{location} does not identify a regular file: {raw}")
        return None
    return raw


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None


def validate_traceability(root: Path, value: object) -> tuple[str, ...]:
    findings: list[str] = []
    manifest = _mapping(value, location="manifest", findings=findings)
    if manifest is None:
        return tuple(findings)
    unknown = sorted(set(manifest) - TOP_FIELDS)
    missing = sorted(TOP_FIELDS - set(manifest))
    if unknown:
        findings.append(f"manifest has unknown fields: {', '.join(unknown)}")
    if missing:
        findings.append(f"manifest is missing fields: {', '.join(missing)}")
    if manifest.get("schema_version") != "1.0":
        findings.append("schema_version must equal 1.0")
    for field in ("upstream_baseline", "implementation_checkpoint"):
        raw = manifest.get(field)
        if not isinstance(raw, str) or SHA40.fullmatch(raw) is None:
            findings.append(f"{field} must be a full lowercase Git object ID")

    expected_hash = manifest.get("manifest_sha256")
    unhashed = dict(manifest)
    unhashed.pop("manifest_sha256", None)
    actual_hash = hashlib.sha256(_canonical_json(unhashed)).hexdigest()
    if not isinstance(expected_hash, str) or SHA256.fullmatch(expected_hash) is None:
        findings.append("manifest_sha256 must be a lowercase SHA-256 digest")
    elif expected_hash != actual_hash:
        findings.append("manifest_sha256 does not identify the canonical manifest")

    raw_milestones = manifest.get("milestones")
    if not isinstance(raw_milestones, list) or not raw_milestones:
        return tuple([*findings, "milestones must be a non-empty array"])
    expected_ids = [f"M{index:02d}" for index in range(1, len(raw_milestones) + 1)]
    observed_ids: list[object] = []
    ordered_commits: list[str] = []
    observed_commits: set[str] = set()
    observed_paths: dict[str, set[str]] = {field: set() for field in PATH_FIELDS}
    for index, raw_milestone in enumerate(raw_milestones):
        location = f"milestones[{index}]"
        milestone = _mapping(raw_milestone, location=location, findings=findings)
        if milestone is None:
            continue
        if set(milestone) != MILESTONE_FIELDS:
            findings.append(f"{location} fields do not match the v1 contract")
        observed_ids.append(milestone.get("id"))
        if milestone.get("status") != "implemented_proposal":
            findings.append(f"{location}.status must equal implemented_proposal")
        title = milestone.get("title")
        if not isinstance(title, str) or not title.strip():
            findings.append(f"{location}.title must be a non-empty string")
        commits = milestone.get("commits")
        if not isinstance(commits, list) or not commits:
            findings.append(f"{location}.commits must be a non-empty array")
        else:
            for commit in commits:
                if not isinstance(commit, str) or SHA40.fullmatch(commit) is None:
                    findings.append(f"{location}.commits contains an invalid Git object ID")
                elif commit in observed_commits:
                    findings.append(f"{location}.commits repeats {commit}")
                else:
                    observed_commits.add(commit)
                    ordered_commits.append(commit)
        for field in PATH_FIELDS:
            raw_paths = milestone.get(field)
            if not isinstance(raw_paths, list) or (field != "migrations" and not raw_paths):
                findings.append(f"{location}.{field} must be an appropriate path array")
                continue
            for path_index, raw_path in enumerate(raw_paths):
                path = _safe_file(
                    root,
                    raw_path,
                    location=f"{location}.{field}[{path_index}]",
                    findings=findings,
                )
                if path is None:
                    continue
                if path in observed_paths[field]:
                    findings.append(f"{location}.{field} repeats {path}")
                observed_paths[field].add(path)
    if observed_ids != expected_ids:
        findings.append("milestone IDs must be unique, ordered, and contiguous from M01")

    baseline = manifest.get("upstream_baseline")
    checkpoint = manifest.get("implementation_checkpoint")
    if isinstance(baseline, str) and isinstance(checkpoint, str):
        ancestry = _git(root, "merge-base", "--is-ancestor", baseline, checkpoint)
        history = _git(root, "rev-list", "--reverse", f"{baseline}..{checkpoint}")
        if ancestry is None or history is None:
            findings.append("Git is required to validate proposal history")
        elif ancestry.returncode != 0 or history.returncode != 0:
            findings.append("baseline and checkpoint must identify a valid ancestor range")
        elif tuple(ordered_commits) != tuple(history.stdout.splitlines()):
            findings.append("milestone commits must exactly cover the ordered proposal history")

    actual_adrs = {path.relative_to(root).as_posix() for path in (root / "docs/adr").glob("*.md")}
    if observed_paths["adrs"] != actual_adrs:
        findings.append("ADR traceability must cover every and only docs/adr/*.md file")
    actual_migrations = {
        path.relative_to(root).as_posix() for path in (root / "migrations/sqlite").glob("*.sql")
    }
    if observed_paths["migrations"] != actual_migrations:
        findings.append("migration traceability must cover every and only SQLite migration")
    return tuple(findings)


def main(argv: Sequence[str] | None = None) -> int:
    if argv:
        raise ValueError("check_traceability does not accept arguments")
    root = Path(__file__).resolve().parents[2]
    try:
        value = json.loads((root / MANIFEST_PATH).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"traceability manifest could not be loaded: {exc}")
        return 2
    findings = validate_traceability(root, value)
    if findings:
        for finding in findings:
            print(finding)
        return 1
    print(f"traceability check passed for {len(value['milestones'])} milestone(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
