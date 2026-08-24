"""Unit tests for the adopted snapshot manifest module (stdlib-only)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "scripts" / "verify" / "paper"
if str(PAPER) not in sys.path:
    sys.path.insert(0, str(PAPER))

from manifest import (  # noqa: E402
    ComponentKind,
    ManifestError,
    build_manifest,
    verify_manifest,
    write_manifest,
)


def _write_fixture(root: Path) -> dict[str, str]:
    paths: dict[str, str] = {}
    for index, kind in enumerate(ComponentKind):
        if kind is ComponentKind.MODEL_BUNDLES:
            continue
        relative = f"fixture/{kind.value}.txt"
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{index}:{kind.value}\n", encoding="utf-8", newline="\n")
        paths[kind.value] = relative
    return paths


def _spec(paths: dict[str, str]) -> dict[str, object]:
    components: list[dict[str, object]] = []
    for kind in ComponentKind:
        if kind is ComponentKind.MODEL_BUNDLES:
            components.append(
                {
                    "kind": kind.value,
                    "status": "not_applicable",
                    "reason": "The deterministic fixture does not use a statistical model.",
                }
            )
        else:
            components.append({"kind": kind.value, "paths": [paths[kind.value]]})
    return {
        "schema_version": "1.0",
        "snapshot_id": "snap_test_fixture",
        "recorded_at": "2026-08-15T00:00:00Z",
        "code_revision": "75df1d2f1cec02094f0f1b7df168a57c36c99528",
        "components": components,
    }


def _write_spec(root: Path, value: dict[str, object]) -> Path:
    path = root / "spec.json"
    path.write_text(json.dumps(value), encoding="utf-8", newline="\n")
    return path


class ManifestContractTests(unittest.TestCase):
    def test_build_is_deterministic_and_byte_stable_on_disk(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            spec_path = _write_spec(root, _spec(_write_fixture(root)))
            first = build_manifest(root=root, spec_path=spec_path)
            second = build_manifest(root=root, spec_path=spec_path)
            self.assertEqual(first, second)
            kinds = [component["kind"] for component in first["components"]]
            self.assertEqual(kinds, sorted(kind.value for kind in ComponentKind))
            self.assertEqual(len(str(first["manifest_sha256"])), 64)

            path = root / "manifest.json"
            write_manifest(path, first)
            write_manifest(path, second)
            self.assertEqual(path.read_bytes(), path.read_bytes())
            again = root / "manifest2.json"
            write_manifest(again, first)
            self.assertEqual(path.read_bytes(), again.read_bytes())
            self.assertEqual(verify_manifest(root=root, manifest_path=path), ())

    def test_verify_detects_changed_file_bytes(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            paths = _write_fixture(root)
            manifest = build_manifest(root=root, spec_path=_write_spec(root, _spec(paths)))
            path = root / "snapshot.json"
            write_manifest(path, manifest)
            (root / paths[ComponentKind.CORPUS.value]).write_text(
                "changed corpus\n", encoding="utf-8"
            )
            findings = verify_manifest(root=root, manifest_path=path)
            self.assertTrue(any("corpus.txt: byte length" in item for item in findings))
            self.assertTrue(any("corpus.txt: sha256" in item for item in findings))

    def test_unknown_spec_field_is_rejected(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            value = _spec(_write_fixture(root))
            value["surprise"] = True
            with self.assertRaises(ManifestError):
                build_manifest(root=root, spec_path=_write_spec(root, value))


if __name__ == "__main__":
    unittest.main()
