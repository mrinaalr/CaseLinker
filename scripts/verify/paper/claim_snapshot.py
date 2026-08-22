"""Pin paper-claim runs to a content-addressed snapshot manifest.

Used by ``verify_paper.py --snapshot`` / ``--against-snapshot``. Manifests
are on-disk artifacts (not DB state). Document-version hashes are recorded
and used for source-change attribution only when those columns/tables exist
(PR A). This module does not import capture code.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from manifest import (
    ComponentKind,
    SCHEMA_VERSION,
    build_manifest,
    canonical_json,
    sha256_bytes,
    write_manifest,
)

CORPUS_PIN_SCHEMA = "caselinker.claim_corpus_pin.v1"
DRIFT_SCHEMA = "caselinker.claim_drift.v1"
VOLATILE_CASE_COLUMNS = frozenset({"created_at", "updated_at"})

HELD_COMPONENT_REASONS: dict[ComponentKind, str] = {
    ComponentKind.ACCEPTED_ASSERTIONS: (
        "No per-assertion ledger in this slice; cases are pinned as corpus rows."
    ),
    ComponentKind.EXTRACTION_RULES: (
        "Extractor versions are not a claim-snapshot input; see PR A extraction_runs."
    ),
    ComponentKind.MODEL_BUNDLES: "Paper claim verify does not load ML bundles.",
    ComponentKind.ONTOLOGY: "Ontology graphs are not pinned by claim snapshots.",
    ComponentKind.SHAPES: "SHACL shapes are not pinned by claim snapshots.",
    ComponentKind.QUERY: "Claims are verified in-process, not via a stored query file.",
    ComponentKind.PARAMETERS: "No additional analysis parameters beyond the corpus pin.",
}


def git_code_revision(repo_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def git_recorded_at(repo_root: Path) -> str:
    """UTC timestamp from the current HEAD commit — stable across repeat runs."""
    try:
        raw = subprocess.check_output(
            ["git", "log", "-1", "--format=%cI"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OSError, subprocess.CalledProcessError, ValueError):
        return "1970-01-01T00:00:00Z"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def _jsonable(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float, str)):
        return value
    return str(value)


def _source_version_rows(conn: sqlite3.Connection) -> list[dict[str, Any]] | None:
    """Return version-hash rows when PR A tables exist; otherwise None."""
    if not _table_exists(conn, "source_document_versions"):
        return None
    version_cols = set(_columns(conn, "source_document_versions"))
    if "content_sha256" not in version_cols:
        return None

    case_cols = set(_columns(conn, "cases")) if _table_exists(conn, "cases") else set()
    if "document_version_id" in case_cols:
        rows = conn.execute(
            """
            SELECT c.id, c.document_version_id, v.content_sha256
            FROM cases c
            LEFT JOIN source_document_versions v
              ON v.version_id = c.document_version_id
            ORDER BY c.id
            """
        ).fetchall()
        return [
            {
                "case_id": case_id,
                "document_version_id": version_id,
                "content_sha256": digest,
            }
            for case_id, version_id, digest in rows
        ]

    select_cols = [
        col
        for col in ("version_id", "document_id", "content_sha256")
        if col in version_cols
    ]
    quoted = ", ".join(select_cols)
    order = "version_id" if "version_id" in version_cols else select_cols[0]
    rows = conn.execute(
        f"SELECT {quoted} FROM source_document_versions ORDER BY {order}"
    ).fetchall()
    return [dict(zip(select_cols, row)) for row in rows]


def pin_source_versions(conn: sqlite3.Connection) -> dict[str, Any] | None:
    rows = _source_version_rows(conn)
    if rows is None:
        return None
    return {
        "available": True,
        "digest": sha256_bytes(canonical_json(rows)),
        "rows": rows,
    }


def pin_corpus(conn: sqlite3.Connection) -> dict[str, Any]:
    """Case count + content digest over case rows, plus version hashes if present."""
    if not _table_exists(conn, "cases"):
        raise ValueError("database has no cases table")
    cols = _columns(conn, "cases")
    digest_cols = [col for col in cols if col not in VOLATILE_CASE_COLUMNS]
    if "id" not in digest_cols:
        raise ValueError("cases table has no id column")
    quoted = ", ".join(digest_cols)
    rows = conn.execute(f"SELECT {quoted} FROM cases ORDER BY id").fetchall()
    hasher = hashlib.sha256()
    case_ids: list[str] = []
    id_index = digest_cols.index("id")
    for row in rows:
        record = {digest_cols[i]: _jsonable(row[i]) for i in range(len(digest_cols))}
        hasher.update(canonical_json(record))
        hasher.update(b"\n")
        case_ids.append(str(row[id_index]))
    source_versions = pin_source_versions(conn)
    return {
        "schema": CORPUS_PIN_SCHEMA,
        "case_count": len(case_ids),
        "case_ids": case_ids,
        "content_digest": hasher.hexdigest(),
        "source_versions": source_versions,
    }


def results_payload(results: Iterable[Any]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for result in results:
        payload.append(
            {
                "claim_id": result.claim_id,
                "detail": result.detail,
                "expected": result.expected,
                "notes": list(result.notes),
                "observed": result.observed,
                "source": result.source,
                "status": result.status,
            }
        )
    payload.sort(key=lambda item: item["claim_id"])
    return payload


def snapshot_id_for(corpus_digest: str, code_revision: str) -> str:
    token = sha256_bytes(f"{corpus_digest}:{code_revision}".encode("utf-8"))[:16]
    return f"snap_claim_{token}"


def write_stable_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.write_text(serialized, encoding="utf-8", newline="\n")


def _component_specs(
    *,
    include_source_versions: bool,
) -> list[dict[str, object]]:
    components: list[dict[str, object]] = [
        {"kind": ComponentKind.CORPUS.value, "paths": ["corpus.json"]},
        {"kind": ComponentKind.CODE.value, "paths": ["code_revision.txt"]},
        {"kind": ComponentKind.OUTPUTS.value, "paths": ["results.json"]},
    ]
    if include_source_versions:
        components.append(
            {"kind": ComponentKind.SOURCE_VERSIONS.value, "paths": ["source_versions.json"]}
        )
    else:
        components.append(
            {
                "kind": ComponentKind.SOURCE_VERSIONS.value,
                "status": "not_applicable",
                "reason": (
                    "Document-version hashes are absent; source-change attribution "
                    "is skipped until those hashes exist (PR A)."
                ),
            }
        )
    for kind, reason in HELD_COMPONENT_REASONS.items():
        components.append(
            {"kind": kind.value, "status": "not_applicable", "reason": reason}
        )
    return components


def emit_claim_snapshot(
    *,
    snapshot_dir: Path,
    corpus: Mapping[str, Any],
    results: Sequence[Any],
    code_revision: str,
    recorded_at: str,
) -> Path:
    """Write pin files and a content-addressed manifest. Repeat runs are byte-stable."""
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    source_versions = corpus.get("source_versions")
    include_source = isinstance(source_versions, Mapping) and bool(
        source_versions.get("available")
    )

    write_stable_json(snapshot_dir / "corpus.json", dict(corpus))
    write_stable_json(snapshot_dir / "results.json", results_payload(results))
    (snapshot_dir / "code_revision.txt").write_text(
        f"{code_revision}\n", encoding="utf-8", newline="\n"
    )
    if include_source:
        write_stable_json(snapshot_dir / "source_versions.json", source_versions)

    snap_id = snapshot_id_for(str(corpus["content_digest"]), code_revision)
    spec = {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": snap_id,
        "recorded_at": recorded_at,
        "code_revision": code_revision,
        "components": _component_specs(include_source_versions=include_source),
    }
    spec_path = snapshot_dir / "spec.json"
    write_stable_json(spec_path, spec)
    manifest = build_manifest(root=snapshot_dir, spec_path=spec_path)
    manifest_path = snapshot_dir / "manifest.json"
    write_manifest(manifest_path, manifest)
    return manifest_path


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_pinned_snapshot(manifest_path: Path) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    root = manifest_path.parent
    corpus = _load_json(root / "corpus.json")
    results = _load_json(root / "results.json")
    return {
        "manifest": manifest,
        "root": root,
        "corpus": corpus,
        "results": results,
        "code_revision": manifest.get("code_revision"),
        "snapshot_id": manifest.get("snapshot_id"),
    }


def _result_index(payload: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {str(item["claim_id"]): item for item in payload}


def _result_changed(pinned: Mapping[str, Any], live: Mapping[str, Any]) -> bool:
    keys = ("status", "observed", "expected", "detail")
    return any(pinned.get(key) != live.get(key) for key in keys)


def source_versions_changed(pinned: Any, live: Any) -> bool:
    """True only when both sides have document-version hashes and they differ."""
    if not isinstance(pinned, Mapping) or not isinstance(live, Mapping):
        return False
    if not pinned.get("available") or not live.get("available"):
        return False
    return pinned.get("digest") != live.get("digest")


def attribute_causes(
    *,
    new_case_ids: Sequence[str],
    code_revision_changed: bool,
    source_changed: bool,
) -> list[str]:
    causes: list[str] = []
    if new_case_ids:
        causes.append("corpus_growth")
    if code_revision_changed:
        causes.append("extraction_change")
    if source_changed:
        causes.append("source_change")
    if not causes:
        causes.append("unattributed")
    return causes


def compare_against_snapshot(
    *,
    pinned: Mapping[str, Any],
    live_corpus: Mapping[str, Any],
    live_results: Sequence[Any],
    live_code_revision: str,
) -> dict[str, Any]:
    pinned_corpus = pinned["corpus"]
    pinned_ids = [str(item) for item in pinned_corpus.get("case_ids") or []]
    live_ids = [str(item) for item in live_corpus.get("case_ids") or []]
    pinned_set = set(pinned_ids)
    live_set = set(live_ids)
    new_case_ids = [case_id for case_id in live_ids if case_id not in pinned_set]
    removed_case_ids = [case_id for case_id in pinned_ids if case_id not in live_set]
    code_changed = str(pinned.get("code_revision") or "") != live_code_revision
    source_changed = source_versions_changed(
        pinned_corpus.get("source_versions"),
        live_corpus.get("source_versions"),
    )
    causes = attribute_causes(
        new_case_ids=new_case_ids,
        code_revision_changed=code_changed,
        source_changed=source_changed,
    )

    live_payload = results_payload(live_results)
    pinned_index = _result_index(pinned["results"])
    live_index = _result_index(live_payload)
    deltas: list[dict[str, Any]] = []
    for claim_id in sorted(set(pinned_index) | set(live_index)):
        before = pinned_index.get(claim_id)
        after = live_index.get(claim_id)
        if before is None or after is None or _result_changed(before, after):
            deltas.append(
                {
                    "claim_id": claim_id,
                    "pinned": before,
                    "live": after,
                    "attribution": list(causes),
                }
            )

    return {
        "schema": DRIFT_SCHEMA,
        "pinned_snapshot_id": pinned.get("snapshot_id"),
        "pinned_code_revision": pinned.get("code_revision"),
        "live_code_revision": live_code_revision,
        "pinned_case_count": pinned_corpus.get("case_count"),
        "live_case_count": live_corpus.get("case_count"),
        "new_case_ids": new_case_ids,
        "removed_case_ids": removed_case_ids,
        "corpus_digest_changed": pinned_corpus.get("content_digest")
        != live_corpus.get("content_digest"),
        "source_versions_available": bool(
            isinstance(live_corpus.get("source_versions"), Mapping)
            and live_corpus["source_versions"].get("available")
        ),
        "source_versions_changed": source_changed,
        "deltas": deltas,
    }


def format_drift_summary(report: Mapping[str, Any]) -> str:
    lines = [
        "Claim drift vs snapshot "
        f"{report.get('pinned_snapshot_id')}: "
        f"{len(report.get('deltas') or [])} delta(s)",
        f"  pinned cases={report.get('pinned_case_count')} "
        f"live cases={report.get('live_case_count')}",
        f"  new_case_ids={list(report.get('new_case_ids') or [])}",
        f"  extraction_change="
        f"{report.get('pinned_code_revision') != report.get('live_code_revision')}",
        f"  source_versions_available={report.get('source_versions_available')} "
        f"source_change={report.get('source_versions_changed')}",
    ]
    for delta in report.get("deltas") or []:
        claim_id = delta.get("claim_id")
        attribution = ", ".join(delta.get("attribution") or [])
        pinned = (delta.get("pinned") or {}).get("observed")
        live = (delta.get("live") or {}).get("observed")
        lines.append(f"  {claim_id}: {pinned!r} → {live!r} [{attribution}]")
    return "\n".join(lines)
