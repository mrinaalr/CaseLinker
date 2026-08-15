from __future__ import annotations

import json
from pathlib import Path

from caselinker.snapshots.cli import main
from caselinker.snapshots.manifest import ComponentKind


def _write_cli_spec(tmp_path: Path) -> Path:
    fixture = tmp_path / "fixture.txt"
    fixture.write_text("policy-safe fixture\n", encoding="utf-8")
    components: list[dict[str, object]] = [
        {"kind": kind.value, "paths": ["fixture.txt"]} for kind in ComponentKind
    ]
    spec = {
        "schema_version": "1.0",
        "snapshot_id": "snap_cli_fixture",
        "recorded_at": "2026-08-15T00:00:00Z",
        "code_revision": "75df1d2f1cec02094f0f1b7df168a57c36c99528",
        "components": components,
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    return spec_path


def test_cli_builds_and_verifies_manifest(tmp_path: Path) -> None:
    spec_path = _write_cli_spec(tmp_path)
    output_path = tmp_path / "manifest.json"

    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "build",
                "--spec",
                str(spec_path),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    assert main(["--root", str(tmp_path), "verify", "--manifest", str(output_path)]) == 0
    assert output_path.is_file()


def test_cli_returns_failure_for_stale_manifest(tmp_path: Path, capsys: object) -> None:
    spec_path = _write_cli_spec(tmp_path)
    output_path = tmp_path / "manifest.json"
    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "build",
                "--spec",
                str(spec_path),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    (tmp_path / "fixture.txt").write_text("changed\n", encoding="utf-8")

    assert main(["--root", str(tmp_path), "verify", "--manifest", str(output_path)]) == 1


def test_cli_returns_usage_failure_for_invalid_spec(tmp_path: Path, capsys: object) -> None:
    spec_path = tmp_path / "invalid.json"
    spec_path.write_text("{}", encoding="utf-8")

    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "build",
                "--spec",
                str(spec_path),
                "--output",
                str(tmp_path / "manifest.json"),
            ]
        )
        == 2
    )
