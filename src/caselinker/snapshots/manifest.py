"""Build and verify deterministic, content-addressed snapshot manifests."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Final

SCHEMA_VERSION: Final = "1.0"
SCHEMA_ID: Final = "https://caselinker.org/schemas/snapshot-manifest-v1.schema.json"
SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")
SNAPSHOT_ID_PATTERN: Final = re.compile(r"^snap_[a-z0-9][a-z0-9._-]{2,127}$")


class ManifestError(ValueError):
    """Raised when a snapshot specification or manifest violates its contract."""


class ComponentKind(StrEnum):
    """Inputs required to reproduce a CaseLinker analytical artifact."""

    CORPUS = "corpus"
    SOURCE_VERSIONS = "source_versions"
    ACCEPTED_ASSERTIONS = "accepted_assertions"
    CODE = "code"
    EXTRACTION_RULES = "extraction_rules"
    MODEL_BUNDLES = "model_bundles"
    ONTOLOGY = "ontology"
    SHAPES = "shapes"
    QUERY = "query"
    PARAMETERS = "parameters"
    OUTPUTS = "outputs"


class ComponentStatus(StrEnum):
    INCLUDED = "included"
    NOT_APPLICABLE = "not_applicable"


REQUIRED_KINDS: Final = frozenset(ComponentKind)
SPEC_KEYS: Final = frozenset(
    {"schema_version", "snapshot_id", "recorded_at", "code_revision", "components"}
)
COMPONENT_KEYS: Final = frozenset({"kind", "status", "paths", "reason"})
MANIFEST_KEYS: Final = frozenset(
    {
        "$schema",
        "schema_version",
        "snapshot_id",
        "recorded_at",
        "code_revision",
        "components",
        "manifest_sha256",
    }
)
SERIALIZED_COMPONENT_KEYS: Final = frozenset({"kind", "status", "files", "reason", "sha256"})
FILE_RECORD_KEYS: Final = frozenset({"path", "bytes", "sha256"})


@dataclass(frozen=True, slots=True)
class FileRecord:
    path: str
    bytes: int
    sha256: str

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path, "bytes": self.bytes, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class ComponentRecord:
    kind: ComponentKind
    status: ComponentStatus
    files: tuple[FileRecord, ...]
    reason: str | None
    sha256: str | None

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "kind": self.kind.value,
            "status": self.status.value,
            "files": [record.to_dict() for record in self.files],
        }
        if self.reason is not None:
            value["reason"] = self.reason
        if self.sha256 is not None:
            value["sha256"] = self.sha256
        return value


def canonical_json(value: object) -> bytes:
    """Return the canonical UTF-8 representation used for all manifest hashes."""
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _expect_mapping(value: object, *, location: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ManifestError(f"{location} must be a JSON object with string keys")
    return value


def _reject_unknown_keys(
    value: Mapping[str, object], allowed: frozenset[str], *, location: str
) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ManifestError(f"{location} contains unknown field(s): {', '.join(unknown)}")


def _required_string(value: Mapping[str, object], field: str, *, location: str) -> str:
    raw = value.get(field)
    if not isinstance(raw, str) or not raw.strip():
        raise ManifestError(f"{location}.{field} must be a non-empty string")
    return raw


def _validate_recorded_at(value: str) -> None:
    if not value.endswith("Z"):
        raise ManifestError("spec.recorded_at must be an ISO 8601 UTC timestamp ending in 'Z'")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise ManifestError("spec.recorded_at must be a valid ISO 8601 timestamp") from exc
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise ManifestError("spec.recorded_at must be UTC")


def _safe_relative_path(raw: object, *, location: str) -> PurePosixPath:
    if not isinstance(raw, str) or not raw:
        raise ManifestError(f"{location} must be a non-empty POSIX path string")
    if "\\" in raw:
        raise ManifestError(f"{location} must use POSIX '/' separators")
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts or raw != path.as_posix():
        raise ManifestError(f"{location} must be a normalized repository-relative path")
    return path


def _ensure_no_symlink(path: Path, root: Path) -> None:
    current = root
    for part in path.relative_to(root).parts:
        current /= part
        if current.is_symlink():
            raise ManifestError(f"snapshot inputs may not be symlinks: {current.relative_to(root)}")


def _expand_paths(root: Path, raw_paths: object, *, location: str) -> tuple[Path, ...]:
    if not isinstance(raw_paths, list) or not raw_paths:
        raise ManifestError(f"{location} must be a non-empty array")

    root = root.resolve(strict=True)
    expanded: dict[str, Path] = {}
    for index, raw in enumerate(raw_paths):
        relative = _safe_relative_path(raw, location=f"{location}[{index}]")
        candidate = root.joinpath(*relative.parts)
        _ensure_no_symlink(candidate, root)
        if not candidate.exists():
            raise ManifestError(f"snapshot input does not exist: {relative.as_posix()}")

        paths = [candidate]
        if candidate.is_dir():
            paths = sorted(
                (path for path in candidate.rglob("*") if path.is_file()),
                key=lambda path: path.relative_to(root).as_posix(),
            )
            if not paths:
                raise ManifestError(f"snapshot input directory is empty: {relative.as_posix()}")

        for path in paths:
            _ensure_no_symlink(path, root)
            if not path.is_file():
                raise ManifestError(
                    f"snapshot input is not a regular file: {path.relative_to(root)}"
                )
            display = path.relative_to(root).as_posix()
            expanded[display] = path

    return tuple(expanded[key] for key in sorted(expanded))


def _file_record(path: Path, root: Path) -> FileRecord:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    return FileRecord(path.relative_to(root).as_posix(), size, digest.hexdigest())


def _component_from_spec(value: object, *, root: Path, index: int) -> ComponentRecord:
    location = f"spec.components[{index}]"
    component = _expect_mapping(value, location=location)
    _reject_unknown_keys(component, COMPONENT_KEYS, location=location)
    raw_kind = _required_string(component, "kind", location=location)
    try:
        kind = ComponentKind(raw_kind)
    except ValueError as exc:
        raise ManifestError(f"{location}.kind is not recognized: {raw_kind}") from exc

    raw_status = component.get("status", ComponentStatus.INCLUDED.value)
    if not isinstance(raw_status, str):
        raise ManifestError(f"{location}.status must be included or not_applicable")
    try:
        status = ComponentStatus(raw_status)
    except ValueError as exc:
        raise ManifestError(f"{location}.status must be included or not_applicable") from exc

    if status is ComponentStatus.NOT_APPLICABLE:
        reason = _required_string(component, "reason", location=location)
        if "paths" in component:
            raise ManifestError(f"{location}.paths is forbidden when status is not_applicable")
        return ComponentRecord(kind, status, (), reason, None)

    if "reason" in component:
        raise ManifestError(f"{location}.reason is only valid when status is not_applicable")
    paths = _expand_paths(root, component.get("paths"), location=f"{location}.paths")
    files = tuple(_file_record(path, root) for path in paths)
    payload = {"kind": kind.value, "status": status.value, "files": [f.to_dict() for f in files]}
    return ComponentRecord(kind, status, files, None, sha256_bytes(canonical_json(payload)))


def _load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"could not read valid UTF-8 JSON from {path}: {exc}") from exc


def build_manifest(*, root: Path, spec_path: Path) -> dict[str, object]:
    """Build a deterministic manifest dictionary from a strict JSON specification."""
    root = root.resolve(strict=True)
    spec_path = spec_path.resolve(strict=True)
    spec = _expect_mapping(_load_json(spec_path), location="spec")
    _reject_unknown_keys(spec, SPEC_KEYS, location="spec")

    schema_version = _required_string(spec, "schema_version", location="spec")
    if schema_version != SCHEMA_VERSION:
        raise ManifestError(f"unsupported schema_version: {schema_version}")
    snapshot_id = _required_string(spec, "snapshot_id", location="spec")
    if SNAPSHOT_ID_PATTERN.fullmatch(snapshot_id) is None:
        raise ManifestError("spec.snapshot_id must match ^snap_[a-z0-9][a-z0-9._-]{2,127}$")
    recorded_at = _required_string(spec, "recorded_at", location="spec")
    _validate_recorded_at(recorded_at)
    code_revision = _required_string(spec, "code_revision", location="spec")

    raw_components = spec.get("components")
    if not isinstance(raw_components, list):
        raise ManifestError("spec.components must be an array")
    components = tuple(
        _component_from_spec(value, root=root, index=index)
        for index, value in enumerate(raw_components)
    )
    observed = [component.kind for component in components]
    duplicates = sorted({kind.value for kind in observed if observed.count(kind) > 1})
    if duplicates:
        raise ManifestError(f"spec.components contains duplicate kind(s): {', '.join(duplicates)}")
    missing = sorted(kind.value for kind in REQUIRED_KINDS - set(observed))
    if missing:
        raise ManifestError(f"spec.components is missing required kind(s): {', '.join(missing)}")

    ordered = sorted(components, key=lambda component: component.kind.value)
    payload: dict[str, object] = {
        "$schema": SCHEMA_ID,
        "schema_version": schema_version,
        "snapshot_id": snapshot_id,
        "recorded_at": recorded_at,
        "code_revision": code_revision,
        "components": [component.to_dict() for component in ordered],
    }
    payload["manifest_sha256"] = sha256_bytes(canonical_json(payload))
    return payload


def write_manifest(path: Path, manifest: Mapping[str, object]) -> None:
    """Atomically write a manifest using stable pretty-printed JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _serialized_contract_findings(manifest: Mapping[str, object]) -> tuple[str, ...]:
    findings: list[str] = []
    unknown = sorted(set(manifest) - MANIFEST_KEYS)
    missing_fields = sorted(MANIFEST_KEYS - set(manifest))
    if unknown:
        findings.append(f"manifest contains unknown field(s): {', '.join(unknown)}")
    if missing_fields:
        findings.append(f"manifest is missing field(s): {', '.join(missing_fields)}")
    if manifest.get("$schema") != SCHEMA_ID:
        findings.append("$schema is not the supported snapshot-manifest schema")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        findings.append("schema_version is not supported")

    snapshot_id = manifest.get("snapshot_id")
    if not isinstance(snapshot_id, str) or SNAPSHOT_ID_PATTERN.fullmatch(snapshot_id) is None:
        findings.append("snapshot_id does not match the required opaque identifier format")
    recorded_at = manifest.get("recorded_at")
    if not isinstance(recorded_at, str):
        findings.append("recorded_at must be a UTC timestamp string")
    else:
        try:
            _validate_recorded_at(recorded_at)
        except ManifestError as exc:
            findings.append(str(exc))
    code_revision = manifest.get("code_revision")
    if not isinstance(code_revision, str) or not code_revision.strip():
        findings.append("code_revision must be a non-empty string")
    manifest_hash = manifest.get("manifest_sha256")
    if not isinstance(manifest_hash, str) or SHA256_PATTERN.fullmatch(manifest_hash) is None:
        findings.append("manifest_sha256 must be a lowercase SHA-256 digest")

    components = manifest.get("components")
    if not isinstance(components, list):
        return tuple([*findings, "components must be an array"])

    observed_kinds: list[ComponentKind] = []
    for component_index, raw_component in enumerate(components):
        location = f"components[{component_index}]"
        if not isinstance(raw_component, Mapping):
            findings.append(f"{location} must be an object")
            continue
        component_unknown = sorted(set(raw_component) - SERIALIZED_COMPONENT_KEYS)
        if component_unknown:
            findings.append(f"{location} contains unknown field(s): {', '.join(component_unknown)}")

        raw_kind = raw_component.get("kind")
        try:
            kind = ComponentKind(raw_kind) if isinstance(raw_kind, str) else None
        except ValueError:
            kind = None
        if kind is None:
            findings.append(f"{location}.kind is not recognized")
        else:
            observed_kinds.append(kind)

        raw_status = raw_component.get("status")
        try:
            status = ComponentStatus(raw_status) if isinstance(raw_status, str) else None
        except ValueError:
            status = None
        if status is None:
            findings.append(f"{location}.status is not recognized")

        raw_files = raw_component.get("files")
        if not isinstance(raw_files, list):
            findings.append(f"{location}.files must be an array")
            continue
        if status is ComponentStatus.INCLUDED:
            if not raw_files:
                findings.append(f"{location}.files must not be empty when included")
            if "reason" in raw_component:
                findings.append(f"{location}.reason is forbidden when included")
            component_hash = raw_component.get("sha256")
            if (
                not isinstance(component_hash, str)
                or SHA256_PATTERN.fullmatch(component_hash) is None
            ):
                findings.append(f"{location}.sha256 must be a lowercase SHA-256 digest")
        elif status is ComponentStatus.NOT_APPLICABLE:
            reason = raw_component.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                findings.append(f"{location}.reason is required when not_applicable")
            if raw_files:
                findings.append(f"{location}.files must be empty when not_applicable")
            if "sha256" in raw_component:
                findings.append(f"{location}.sha256 is forbidden when not_applicable")

        observed_paths: set[str] = set()
        for file_index, raw_file in enumerate(raw_files):
            file_location = f"{location}.files[{file_index}]"
            if not isinstance(raw_file, Mapping):
                findings.append(f"{file_location} must be an object")
                continue
            file_unknown = sorted(set(raw_file) - FILE_RECORD_KEYS)
            file_missing = sorted(FILE_RECORD_KEYS - set(raw_file))
            if file_unknown:
                findings.append(
                    f"{file_location} contains unknown field(s): {', '.join(file_unknown)}"
                )
            if file_missing:
                findings.append(f"{file_location} is missing field(s): {', '.join(file_missing)}")
            try:
                relative = _safe_relative_path(raw_file.get("path"), location=file_location)
                normalized = relative.as_posix()
                if normalized in observed_paths:
                    findings.append(f"{file_location}.path duplicates {normalized}")
                observed_paths.add(normalized)
            except ManifestError as exc:
                findings.append(str(exc))
            byte_length = raw_file.get("bytes")
            if isinstance(byte_length, bool) or not isinstance(byte_length, int) or byte_length < 0:
                findings.append(f"{file_location}.bytes must be a non-negative integer")
            file_hash = raw_file.get("sha256")
            if not isinstance(file_hash, str) or SHA256_PATTERN.fullmatch(file_hash) is None:
                findings.append(f"{file_location}.sha256 must be a lowercase SHA-256 digest")

    duplicates = sorted({kind.value for kind in observed_kinds if observed_kinds.count(kind) > 1})
    if duplicates:
        findings.append(f"components contains duplicate kind(s): {', '.join(duplicates)}")
    missing_kinds = sorted(kind.value for kind in REQUIRED_KINDS - set(observed_kinds))
    if missing_kinds:
        findings.append(f"components is missing required kind(s): {', '.join(missing_kinds)}")
    return tuple(findings)


def verify_manifest(*, root: Path, manifest_path: Path) -> tuple[str, ...]:
    """Return deterministic findings for a manifest and its referenced files."""
    root = root.resolve(strict=True)
    manifest = _expect_mapping(_load_json(manifest_path), location="manifest")
    findings = list(_serialized_contract_findings(manifest))
    expected_manifest_hash = manifest.get("manifest_sha256")
    unhashed = dict(manifest)
    unhashed.pop("manifest_sha256", None)
    actual_manifest_hash = sha256_bytes(canonical_json(unhashed))
    if expected_manifest_hash != actual_manifest_hash:
        findings.append("manifest_sha256 does not match the canonical manifest payload")

    components = manifest.get("components")
    if not isinstance(components, list):
        return tuple([*findings, "components must be an array"])

    for component_index, raw_component in enumerate(components):
        location = f"components[{component_index}]"
        if not isinstance(raw_component, Mapping):
            findings.append(f"{location} must be an object")
            continue
        if raw_component.get("status") != ComponentStatus.INCLUDED.value:
            continue
        raw_files = raw_component.get("files")
        if not isinstance(raw_files, list):
            findings.append(f"{location}.files must be an array")
            continue
        for file_index, raw_file in enumerate(raw_files):
            file_location = f"{location}.files[{file_index}]"
            if not isinstance(raw_file, Mapping):
                findings.append(f"{file_location} must be an object")
                continue
            try:
                relative = _safe_relative_path(raw_file.get("path"), location=file_location)
                path = root.joinpath(*relative.parts)
                _ensure_no_symlink(path, root)
                if not path.is_file():
                    findings.append(f"{relative.as_posix()}: referenced file is missing")
                    continue
                observed = _file_record(path, root)
            except ManifestError as exc:
                findings.append(str(exc))
                continue
            if raw_file.get("bytes") != observed.bytes:
                findings.append(f"{observed.path}: byte length does not match manifest")
            if raw_file.get("sha256") != observed.sha256:
                findings.append(f"{observed.path}: sha256 does not match manifest")

        component_without_hash = {
            key: value for key, value in raw_component.items() if key != "sha256"
        }
        expected_component_hash = raw_component.get("sha256")
        actual_component_hash = sha256_bytes(canonical_json(component_without_hash))
        if expected_component_hash != actual_component_hash:
            findings.append(f"{location}.sha256 does not match its canonical component payload")
    return tuple(findings)
