from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from caselinker.snapshots.manifest import (
    ComponentKind,
    ManifestError,
    build_manifest,
    canonical_json,
    sha256_bytes,
    verify_manifest,
    write_manifest,
)


def _write_fixture(root: Path) -> dict[ComponentKind, str]:
    paths: dict[ComponentKind, str] = {}
    for index, kind in enumerate(ComponentKind):
        if kind is ComponentKind.MODEL_BUNDLES:
            continue
        relative = f"fixture/{kind.value}.txt"
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{index}:{kind.value}\n", encoding="utf-8")
        paths[kind] = relative
    return paths


def _spec(paths: dict[ComponentKind, str]) -> dict[str, object]:
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
            components.append({"kind": kind.value, "paths": [paths[kind]]})
    return {
        "schema_version": "1.0",
        "snapshot_id": "snap_test_fixture",
        "recorded_at": "2026-08-15T00:00:00Z",
        "code_revision": "75df1d2f1cec02094f0f1b7df168a57c36c99528",
        "components": components,
    }


def _write_spec(root: Path, value: dict[str, object]) -> Path:
    path = root / "spec.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_build_is_deterministic_and_orders_components(tmp_path: Path) -> None:
    spec_path = _write_spec(tmp_path, _spec(_write_fixture(tmp_path)))

    first = build_manifest(root=tmp_path, spec_path=spec_path)
    second = build_manifest(root=tmp_path, spec_path=spec_path)

    assert first == second
    components = first["components"]
    assert isinstance(components, list)
    assert [component["kind"] for component in components] == sorted(
        kind.value for kind in ComponentKind
    )
    assert len(str(first["manifest_sha256"])) == 64


def test_manifest_verification_detects_changed_evidence(tmp_path: Path) -> None:
    paths = _write_fixture(tmp_path)
    manifest = build_manifest(root=tmp_path, spec_path=_write_spec(tmp_path, _spec(paths)))
    manifest_path = tmp_path / "snapshot.json"
    write_manifest(manifest_path, manifest)
    assert verify_manifest(root=tmp_path, manifest_path=manifest_path) == ()

    (tmp_path / paths[ComponentKind.ACCEPTED_ASSERTIONS]).write_text(
        "changed assertion ledger\n", encoding="utf-8"
    )

    findings = verify_manifest(root=tmp_path, manifest_path=manifest_path)
    assert any("accepted_assertions.txt: byte length" in finding for finding in findings)
    assert any("accepted_assertions.txt: sha256" in finding for finding in findings)


def test_manifest_verification_detects_tampering_with_manifest_metadata(tmp_path: Path) -> None:
    manifest = build_manifest(
        root=tmp_path,
        spec_path=_write_spec(tmp_path, _spec(_write_fixture(tmp_path))),
    )
    manifest["code_revision"] = "unreviewed"
    manifest_path = tmp_path / "snapshot.json"
    write_manifest(manifest_path, manifest)

    assert (
        "manifest_sha256 does not match"
        in verify_manifest(root=tmp_path, manifest_path=manifest_path)[0]
    )


def test_directory_input_expands_to_sorted_file_records(tmp_path: Path) -> None:
    paths = _write_fixture(tmp_path)
    directory = tmp_path / "fixture" / "code"
    directory.mkdir()
    (directory / "z.py").write_text("Z = 1\n", encoding="utf-8")
    (directory / "a.py").write_text("A = 1\n", encoding="utf-8")
    value = _spec(paths)
    for component in value["components"]:  # type: ignore[union-attr]
        if component["kind"] == ComponentKind.CODE.value:
            component["paths"] = ["fixture/code"]

    manifest = build_manifest(root=tmp_path, spec_path=_write_spec(tmp_path, value))
    components = manifest["components"]
    assert isinstance(components, list)
    code = next(component for component in components if component["kind"] == "code")
    assert [record["path"] for record in code["files"]] == [
        "fixture/code/a.py",
        "fixture/code/z.py",
    ]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.update({"surprise": True}), "unknown field"),
        (
            lambda value: value["components"].pop(),
            "missing required kind",
        ),
        (
            lambda value: value.update({"recorded_at": "2026-08-15T00:00:00-08:00"}),
            "ending in 'Z'",
        ),
    ],
)
def test_invalid_spec_is_rejected(tmp_path: Path, mutation: object, message: str) -> None:
    value = _spec(_write_fixture(tmp_path))
    assert callable(mutation)
    mutation(value)

    with pytest.raises(ManifestError, match=message):
        build_manifest(root=tmp_path, spec_path=_write_spec(tmp_path, value))


def test_path_traversal_is_rejected(tmp_path: Path) -> None:
    value = _spec(_write_fixture(tmp_path))
    components = value["components"]
    assert isinstance(components, list)
    components[0]["paths"] = ["../outside.txt"]

    with pytest.raises(ManifestError, match="repository-relative"):
        build_manifest(root=tmp_path, spec_path=_write_spec(tmp_path, value))


def test_symlink_input_is_rejected(tmp_path: Path) -> None:
    paths = _write_fixture(tmp_path)
    target = tmp_path / paths[ComponentKind.CORPUS]
    link = tmp_path / "fixture" / "corpus-link.txt"
    link.symlink_to(target)
    value = _spec(paths)
    components = value["components"]
    assert isinstance(components, list)
    components[0]["paths"] = ["fixture/corpus-link.txt"]

    with pytest.raises(ManifestError, match="symlinks"):
        build_manifest(root=tmp_path, spec_path=_write_spec(tmp_path, value))


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("schema_version", "2.0", "unsupported schema_version"),
        ("snapshot_id", "bad", "snapshot_id must match"),
        ("recorded_at", "not-a-dateZ", "valid ISO 8601"),
        ("code_revision", "", "non-empty string"),
        ("components", {}, "components must be an array"),
    ],
)
def test_invalid_top_level_contract_is_rejected(
    tmp_path: Path, field: str, replacement: object, message: str
) -> None:
    value = _spec(_write_fixture(tmp_path))
    value[field] = replacement

    with pytest.raises(ManifestError, match=message):
        build_manifest(root=tmp_path, spec_path=_write_spec(tmp_path, value))


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ({"kind": "unknown", "paths": ["fixture/corpus.txt"]}, "kind is not recognized"),
        (
            {"kind": "corpus", "status": 1, "paths": ["fixture/corpus.txt"]},
            "status must be",
        ),
        (
            {"kind": "corpus", "status": "future", "paths": ["fixture/corpus.txt"]},
            "status must be",
        ),
        (
            {"kind": "corpus", "status": "not_applicable", "reason": "unused", "paths": []},
            "paths is forbidden",
        ),
        (
            {"kind": "corpus", "paths": ["fixture/corpus.txt"], "reason": "unexpected"},
            "reason is only valid",
        ),
        ({"kind": "corpus", "paths": []}, "non-empty array"),
        ({"kind": "corpus", "paths": ["fixture/missing.txt"]}, "does not exist"),
        ({"kind": "corpus", "paths": ["fixture\\corpus.txt"]}, "POSIX"),
        ({"kind": "corpus", "paths": [None]}, "POSIX path string"),
    ],
)
def test_invalid_component_contract_is_rejected(
    tmp_path: Path, replacement: dict[str, object], message: str
) -> None:
    value = _spec(_write_fixture(tmp_path))
    components = value["components"]
    assert isinstance(components, list)
    components[0] = replacement

    with pytest.raises(ManifestError, match=message):
        build_manifest(root=tmp_path, spec_path=_write_spec(tmp_path, value))


def test_duplicate_component_kind_is_rejected(tmp_path: Path) -> None:
    value = _spec(_write_fixture(tmp_path))
    components = value["components"]
    assert isinstance(components, list)
    components.append(dict(components[0]))

    with pytest.raises(ManifestError, match="duplicate kind"):
        build_manifest(root=tmp_path, spec_path=_write_spec(tmp_path, value))


def test_empty_directory_input_is_rejected(tmp_path: Path) -> None:
    paths = _write_fixture(tmp_path)
    (tmp_path / "empty").mkdir()
    value = _spec(paths)
    components = value["components"]
    assert isinstance(components, list)
    components[0]["paths"] = ["empty"]

    with pytest.raises(ManifestError, match="directory is empty"):
        build_manifest(root=tmp_path, spec_path=_write_spec(tmp_path, value))


def test_invalid_json_is_rejected(tmp_path: Path) -> None:
    spec_path = tmp_path / "spec.json"
    spec_path.write_text("{", encoding="utf-8")

    with pytest.raises(ManifestError, match="valid UTF-8 JSON"):
        build_manifest(root=tmp_path, spec_path=spec_path)


def test_non_object_spec_is_rejected(tmp_path: Path) -> None:
    spec_path = tmp_path / "spec.json"
    spec_path.write_text("[]", encoding="utf-8")

    with pytest.raises(ManifestError, match="spec must be a JSON object"):
        build_manifest(root=tmp_path, spec_path=spec_path)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda manifest: manifest.update({"components": {}}), "components must be an array"),
        (lambda manifest: manifest.update({"components": ["bad"]}), "must be an object"),
        (
            lambda manifest: manifest.update({"components": [{"status": "included", "files": {}}]}),
            "files must be an array",
        ),
        (
            lambda manifest: manifest.update(
                {"components": [{"status": "included", "files": ["bad"]}]}
            ),
            r"files\[0\] must be an object",
        ),
        (
            lambda manifest: manifest.update(
                {"components": [{"status": "included", "files": [{"path": "fixture/missing.txt"}]}]}
            ),
            "referenced file is missing",
        ),
        (
            lambda manifest: manifest.update(
                {"components": [{"status": "included", "files": [{"path": "../bad"}]}]}
            ),
            "repository-relative",
        ),
    ],
)
def test_verifier_reports_malformed_records(tmp_path: Path, mutation: object, message: str) -> None:
    manifest = build_manifest(
        root=tmp_path,
        spec_path=_write_spec(tmp_path, _spec(_write_fixture(tmp_path))),
    )
    assert callable(mutation)
    mutation(manifest)
    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest_path, manifest)

    assert any(
        re.search(message, finding)
        for finding in verify_manifest(root=tmp_path, manifest_path=manifest_path)
    )


def test_verifier_reports_component_hash_tampering(tmp_path: Path) -> None:
    manifest = build_manifest(
        root=tmp_path,
        spec_path=_write_spec(tmp_path, _spec(_write_fixture(tmp_path))),
    )
    components = manifest["components"]
    assert isinstance(components, list)
    components[0]["sha256"] = "0" * 64
    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest_path, manifest)

    findings = verify_manifest(root=tmp_path, manifest_path=manifest_path)
    assert any("canonical component payload" in finding for finding in findings)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("unknown_root", "manifest contains unknown field"),
        ("missing_root", "manifest is missing field"),
        ("schema", r"\$schema is not the supported"),
        ("version", "schema_version is not supported"),
        ("snapshot_id", "snapshot_id does not match"),
        ("recorded_type", "recorded_at must be a UTC"),
        ("recorded_value", "ending in 'Z'"),
        ("code_revision", "code_revision must be a non-empty"),
        ("component_unknown", "contains unknown field"),
        ("component_kind", "kind is not recognized"),
        ("component_status", "status is not recognized"),
        ("included_files", "files must not be empty"),
        ("included_reason", "reason is forbidden when included"),
        ("included_hash", "sha256 must be a lowercase"),
        ("not_applicable_reason", "reason is required"),
        ("not_applicable_files", "files must be empty"),
        ("not_applicable_hash", "sha256 is forbidden"),
        ("file_unknown", "contains unknown field"),
        ("file_missing", "is missing field"),
        ("file_duplicate", "path duplicates"),
        ("file_bytes", "bytes must be a non-negative"),
        ("file_hash", "sha256 must be a lowercase"),
        ("duplicate_kind", "components contains duplicate kind"),
        ("missing_kind", "components is missing required kind"),
    ],
)
def test_verifier_enforces_serialized_contract(tmp_path: Path, case: str, message: str) -> None:
    manifest = build_manifest(
        root=tmp_path,
        spec_path=_write_spec(tmp_path, _spec(_write_fixture(tmp_path))),
    )
    components = manifest["components"]
    assert isinstance(components, list)
    included = next(component for component in components if component["status"] == "included")
    not_applicable = next(
        component for component in components if component["status"] == "not_applicable"
    )
    files = included["files"]
    assert isinstance(files, list)
    file_record = files[0]

    if case == "unknown_root":
        manifest["unexpected"] = True
    elif case == "missing_root":
        manifest.pop("code_revision")
    elif case == "schema":
        manifest["$schema"] = "https://example.invalid/schema"
    elif case == "version":
        manifest["schema_version"] = "2.0"
    elif case == "snapshot_id":
        manifest["snapshot_id"] = "bad"
    elif case == "recorded_type":
        manifest["recorded_at"] = 1
    elif case == "recorded_value":
        manifest["recorded_at"] = "2026-08-15"
    elif case == "code_revision":
        manifest["code_revision"] = ""
    elif case == "component_unknown":
        included["unexpected"] = True
    elif case == "component_kind":
        included["kind"] = "unknown"
    elif case == "component_status":
        included["status"] = "unknown"
    elif case == "included_files":
        included["files"] = []
    elif case == "included_reason":
        included["reason"] = "unexpected"
    elif case == "included_hash":
        included["sha256"] = "bad"
    elif case == "not_applicable_reason":
        not_applicable["reason"] = ""
    elif case == "not_applicable_files":
        not_applicable["files"] = [dict(file_record)]
    elif case == "not_applicable_hash":
        not_applicable["sha256"] = "0" * 64
    elif case == "file_unknown":
        file_record["unexpected"] = True
    elif case == "file_missing":
        file_record.pop("bytes")
    elif case == "file_duplicate":
        files.append(dict(file_record))
    elif case == "file_bytes":
        file_record["bytes"] = -1
    elif case == "file_hash":
        file_record["sha256"] = "bad"
    elif case == "duplicate_kind":
        components.append(dict(included))
    elif case == "missing_kind":
        components.remove(included)
    else:  # pragma: no cover - the parameter table is exhaustive
        raise AssertionError(case)

    unhashed = dict(manifest)
    unhashed.pop("manifest_sha256", None)
    manifest["manifest_sha256"] = sha256_bytes(canonical_json(unhashed))
    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest_path, manifest)

    assert any(
        re.search(message, finding)
        for finding in verify_manifest(root=tmp_path, manifest_path=manifest_path)
    )
