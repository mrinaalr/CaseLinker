"""Minimal provenance values shared by scraping, ingest, and storage.

The module is intentionally standard-library only. It identifies a public source
by canonical URL, identifies each retrieval by its exact bytes, and reads/writes
the capture sidecar emitted next to a merged scraper PDF.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

CAPTURE_SCHEMA_VERSION = "caselinker-capture-v1"
CANONICALIZATION_VERSION = "url-v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TRACKING_QUERY_KEYS = frozenset(
    {
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "ref_src",
    }
)
SENSITIVE_QUERY_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "auth",
        "authorization",
        "key",
        "password",
        "passwd",
        "sig",
        "signature",
        "token",
    }
)


def _canonical_utc(value: datetime | str) -> str:
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        parsed = value
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return (
        parsed.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def canonical_utc(value: datetime | str) -> str:
    """Serialize a timezone-aware timestamp in the database/manifest UTC form."""
    return _canonical_utc(value)


def _http_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return _canonical_utc(parsed)


def canonicalize_url(value: str) -> str:
    """Return a stable public HTTP(S) URL without fragments or tracking noise."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("source URL must be a non-empty string")
    parsed = urlsplit(value.strip())
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("source URL must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("source URL must not contain credentials")

    query: list[tuple[str, str]] = []
    for key, item in parse_qsl(parsed.query, keep_blank_values=True):
        folded = key.casefold()
        if folded in SENSITIVE_QUERY_KEYS:
            raise ValueError("source URL must not contain sensitive query parameters")
        if folded.startswith("utm_") or folded in TRACKING_QUERY_KEYS:
            continue
        query.append((key, item))
    query.sort()

    hostname = parsed.hostname.lower()
    port = parsed.port
    if port is not None and not (
        (scheme == "https" and port == 443) or (scheme == "http" and port == 80)
    ):
        hostname = f"{hostname}:{port}"
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((scheme, hostname, path, urlencode(query, doseq=True), ""))


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _identifier(prefix: str, value: str) -> str:
    return f"{prefix}{_digest(value.encode('utf-8'))[:32]}"


def _mime_type(value: str | None) -> str:
    media_type = (value or "application/octet-stream").split(";", 1)[0].strip().lower()
    if "/" not in media_type or any(character.isspace() for character in media_type):
        return "application/octet-stream"
    return media_type


def source_id_for_url(url: str) -> str:
    hostname = urlsplit(canonicalize_url(url)).hostname or "unknown"
    token = re.sub(r"[^a-z0-9]+", "_", hostname.casefold()).strip("_")
    return token[:128] or "unknown"


def build_capture_record(
    *,
    source_url: str,
    content: bytes,
    retrieved_at: datetime | str,
    mime_type: str | None,
    http_status: int,
    http_etag: str | None,
    http_last_modified: str | None,
    final_url: str,
    parser_name: str,
    parser_version: str,
    normalized_text: str | None,
    published_at: datetime | str | None = None,
) -> dict[str, Any]:
    """Derive a validated, content-addressed capture record from response bytes."""
    if not isinstance(content, bytes):
        raise TypeError("content must be bytes")
    if http_status != 200:
        raise ValueError("only complete HTTP 200 captures may be recorded")
    canonical_url = canonicalize_url(source_url)
    canonical_final_url = canonicalize_url(final_url)
    content_sha256 = _digest(content)
    retrieved_at_text = _canonical_utc(retrieved_at)
    document_id = _identifier("doc_", canonical_url)
    version_id = _identifier(
        "docv_", f"{document_id}:{content_sha256}:{retrieved_at_text}"
    )
    parser_name = str(parser_name).strip()
    parser_version = str(parser_version).strip()
    if not parser_name or not parser_version:
        raise ValueError("parser name and version are required")
    normalized_sha256 = (
        _digest(normalized_text.encode("utf-8"))
        if normalized_text is not None
        else None
    )
    media_type = _mime_type(mime_type)
    return {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "document_id": document_id,
        "version_id": version_id,
        "source_id": source_id_for_url(canonical_url),
        "canonical_url": canonical_url,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "document_type": "pdf" if media_type == "application/pdf" else "web_article",
        "content_sha256": content_sha256,
        "byte_length": len(content),
        "storage_key": f"sha256/{content_sha256[:2]}/{content_sha256}",
        "retrieved_at": retrieved_at_text,
        "published_at": _canonical_utc(published_at)
        if published_at is not None
        else None,
        "recorded_at": retrieved_at_text,
        "mime_type": media_type,
        "http_status": http_status,
        "http_etag": http_etag.strip()
        if isinstance(http_etag, str) and http_etag.strip()
        else None,
        "http_last_modified": _http_date(http_last_modified),
        "http_final_url": canonical_final_url,
        "parser_name": parser_name,
        "parser_version": parser_version,
        "normalized_text_sha256": normalized_sha256,
    }


def capture_manifest_path(pdf_path: str | Path) -> Path:
    path = Path(pdf_path)
    return path.with_name(path.name + ".provenance.json")


def _validate_record(record: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "document_id",
        "version_id",
        "source_id",
        "canonical_url",
        "canonicalization_version",
        "document_type",
        "content_sha256",
        "byte_length",
        "storage_key",
        "retrieved_at",
        "recorded_at",
        "mime_type",
        "http_status",
        "http_final_url",
        "parser_name",
        "parser_version",
    }
    missing = sorted(required - record.keys())
    if missing:
        raise ValueError(f"capture record missing fields: {', '.join(missing)}")
    if not SHA256_RE.fullmatch(str(record["content_sha256"])):
        raise ValueError("capture record has an invalid content SHA-256")
    canonical = canonicalize_url(str(record["canonical_url"]))
    if canonical != record["canonical_url"]:
        raise ValueError("capture record canonical_url is not canonical")
    if record["schema_version"] != CAPTURE_SCHEMA_VERSION:
        raise ValueError("unsupported capture record schema")
    if record["canonicalization_version"] != CANONICALIZATION_VERSION:
        raise ValueError("unsupported URL canonicalization version")
    expected_document_id = _identifier("doc_", canonical)
    if record["document_id"] != expected_document_id:
        raise ValueError("capture record document_id does not match canonical_url")
    retrieved_at = _canonical_utc(str(record["retrieved_at"]))
    if retrieved_at != record["retrieved_at"] or record["recorded_at"] != retrieved_at:
        raise ValueError("capture record timestamps are not canonical")
    expected_version_id = _identifier(
        "docv_", f"{expected_document_id}:{record['content_sha256']}:{retrieved_at}"
    )
    if record["version_id"] != expected_version_id:
        raise ValueError("capture record version_id does not match its retrieval")
    if record["source_id"] != source_id_for_url(canonical):
        raise ValueError("capture record source_id does not match canonical_url")
    if (
        isinstance(record["byte_length"], bool)
        or not isinstance(record["byte_length"], int)
        or record["byte_length"] < 0
    ):
        raise ValueError("capture record byte_length must be a non-negative integer")
    expected_storage_key = (
        f"sha256/{record['content_sha256'][:2]}/{record['content_sha256']}"
    )
    if record["storage_key"] != expected_storage_key:
        raise ValueError("capture record storage_key does not match content_sha256")
    if record["http_status"] != 200:
        raise ValueError("capture record HTTP status must be 200")
    final_url = canonicalize_url(str(record["http_final_url"]))
    if final_url != record["http_final_url"]:
        raise ValueError("capture record http_final_url is not canonical")
    return dict(record)


def write_capture_manifest(
    pdf_path: str | Path, records: Sequence[Mapping[str, Any]]
) -> Path:
    """Write the deterministic sidecar consumed by ingest."""
    normalized = [_validate_record(record) for record in records]
    normalized.sort(key=lambda item: (item["canonical_url"], item["version_id"]))
    payload = {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "records": normalized,
    }
    sidecar = capture_manifest_path(pdf_path)
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return sidecar


def load_capture_manifest(pdf_path: str | Path) -> list[dict[str, Any]]:
    sidecar = capture_manifest_path(pdf_path)
    if not sidecar.is_file():
        return []
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    if payload.get("schema_version") != CAPTURE_SCHEMA_VERSION:
        raise ValueError(f"unsupported capture manifest: {sidecar}")
    records = payload.get("records")
    if not isinstance(records, list):
        raise TypeError(f"capture manifest records must be a list: {sidecar}")
    return [_validate_record(record) for record in records]


def match_capture_for_url(
    records: Iterable[Mapping[str, Any]], source_url: str | None
) -> dict[str, Any] | None:
    if not source_url:
        return None
    try:
        canonical_url = canonicalize_url(source_url)
    except ValueError:
        return None
    matches = [
        record for record in records if record.get("canonical_url") == canonical_url
    ]
    if not matches:
        return None
    matches.sort(
        key=lambda item: (str(item.get("retrieved_at", "")), str(item["version_id"]))
    )
    return dict(matches[-1])


def persist_capture_bytes(
    root: str | Path, record: Mapping[str, Any], content: bytes
) -> Path:
    """Persist exact response bytes under the record's content-addressed storage key."""
    validated = _validate_record(record)
    if _digest(content) != validated["content_sha256"]:
        raise ValueError("capture bytes do not match capture record")
    destination = Path(root) / Path(str(validated["storage_key"]))
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if _digest(destination.read_bytes()) != validated["content_sha256"]:
            raise ValueError(f"content-addressed capture collision at {destination}")
        return destination
    destination.write_bytes(content)
    return destination


def get_code_revision(repo_root: str | Path) -> str:
    """Return the exact Git revision, with an explicit fallback outside a checkout."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(repo_root),
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    revision = result.stdout.strip().lower()
    return revision if re.fullmatch(r"[0-9a-f]{40,64}", revision) else "unknown"
