"""
Provenance capture for CaseLinker (PR A).

Adopted domain values: document/version identity, URL canonicalization,
and content addressing. Tables live in CaseStorage.init_database() —
no migrations/ directory, no src/caselinker/ package.

This module is stdlib-only. Ingest and API behavior are unchanged when
no provenance sidecar or version rows exist.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Iterable, Mapping, Optional, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

DOCUMENT_ID_PATTERN: Final = re.compile(r"^doc_[a-z0-9][a-z0-9._-]{2,127}$")
VERSION_ID_PATTERN: Final = re.compile(r"^docv_[a-z0-9][a-z0-9._-]{2,127}$")
SOURCE_ID_PATTERN: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{1,127}$")
DOCUMENT_TYPE_PATTERN: Final = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
MIME_TYPE_PATTERN: Final = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*$"
)
SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")
TOKEN_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")

CANONICALIZATION_VERSION: Final = "urlcanon_v1"
SIDECAR_SCHEMA: Final = "caselinker.provenance.capture.v1"
SCRAPE_PARSER_NAME: Final = "scrape_pdf"
SCRAPE_PARSER_VERSION: Final = "v1"
JINA_PARSER_NAME: Final = "scrape_pdf.jina"
DEFAULT_DOCUMENT_TYPE: Final = "press_release"
JINA_DOCUMENT_TYPE: Final = "jina_reader_payload"

# Declared extractor tokens for extraction_runs (not a live ML probe).
PATTERN_LAYER_VERSION: Final = "pattern_processing"
DEFAULT_NER_BACKEND: Final = "stanza"
SEMANTIC_MODEL_NAME: Final = "all-MiniLM-L6-v2"
VICTIM_AGE_GATE_VERSION: Final = "v2"

SENSITIVE_QUERY_KEYS: Final = frozenset(
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
TRACKING_QUERY_KEYS: Final = frozenset(
    {
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "utm_campaign",
        "utm_content",
        "utm_medium",
        "utm_source",
        "utm_term",
    }
)
_DROP_QUERY_KEYS: Final = SENSITIVE_QUERY_KEYS | TRACKING_QUERY_KEYS


def utcnow() -> datetime:
    return datetime.now(UTC)


def canonical_utc(value: datetime) -> str:
    """Serialize a validated UTC timestamp without platform-dependent offsets."""
    _validate_utc(value, field="timestamp")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_canonical_utc(value: str) -> datetime:
    """Parse the timestamp representation stored by the document repository."""
    if not value.endswith("Z"):
        raise ValueError("stored timestamp must end in Z")
    parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    _validate_utc(parsed, field="stored timestamp")
    return parsed


def _validate_utc(value: datetime, *, field: str) -> None:
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise ValueError(f"{field} must be timezone-aware UTC")


def _validate_required_text(value: str, *, field: str, maximum: int) -> None:
    if not value or not value.strip() or value != value.strip():
        raise ValueError(f"{field} must be a non-empty trimmed string")
    if len(value) > maximum:
        raise ValueError(f"{field} must not exceed {maximum} characters")
    if any(ord(character) < 32 for character in value):
        raise ValueError(f"{field} must not contain control characters")


def _validate_optional_text(value: str | None, *, field: str, maximum: int) -> None:
    if value is not None:
        _validate_required_text(value, field=field, maximum=maximum)


def _validate_sha256(value: str, *, field: str) -> None:
    if SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


def _validate_url(value: str) -> None:
    _validate_required_text(value, field="canonical_url", maximum=2048)
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("canonical_url must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("canonical_url must not contain credentials")
    query_keys = {key.casefold() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    if query_keys & SENSITIVE_QUERY_KEYS:
        raise ValueError("canonical_url must not contain sensitive query parameters")
    if parsed.fragment:
        raise ValueError("canonical_url must not contain a fragment")


def canonicalize_url(url: str) -> str:
    """
    Normalize a public HTTP(S) URL for document identity.

    Lowercases scheme/host, drops default ports and fragments, strips a
    trailing slash (except ``/``), removes credentials, tracking, and
    sensitive query keys, and sorts remaining query parameters.
    """
    if not isinstance(url, str) or not url.strip():
        raise ValueError("url must be a non-empty string")
    parsed = urlsplit(url.strip())
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("url must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("url must not contain credentials")

    host = parsed.hostname.lower()
    port = parsed.port
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        netloc = f"{host}:{port}"
    else:
        netloc = host

    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    kept = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.casefold() not in _DROP_QUERY_KEYS
    ]
    kept.sort(key=lambda item: (item[0].casefold(), item[1]))
    query = urlencode(kept, doseq=True)
    canonical = urlunsplit((scheme, netloc, path, query, ""))
    _validate_url(canonical)
    return canonical


def source_id_for_url(url: str) -> str:
    """Stable lowercase source token from the URL host."""
    host = (urlsplit(url).hostname or "unknown").lower()
    if host.startswith("www."):
        host = host[4:]
    token = re.sub(r"[^a-z0-9._-]+", "-", host).strip("-._")
    if SOURCE_ID_PATTERN.fullmatch(token) is None:
        digest = hashlib.sha256(host.encode("utf-8")).hexdigest()[:12]
        token = f"source-{digest}"
    return token


def document_id_for(canonical_url: str) -> str:
    digest = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()
    return f"doc_{digest[:32]}"


def version_id_for(document_id: str, content_sha256: str) -> str:
    digest = hashlib.sha256(f"{document_id}:{content_sha256}".encode("utf-8")).hexdigest()
    return f"docv_{digest[:32]}"


def storage_key_for(content_sha256: str) -> str:
    _validate_sha256(content_sha256, field="content_sha256")
    return f"sha256/{content_sha256[:2]}/{content_sha256}"


def sha256_bytes(content: bytes) -> str:
    if not isinstance(content, (bytes, bytearray)):
        raise TypeError("content must be bytes")
    return hashlib.sha256(content).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_http_datetime(value: str | None) -> datetime | None:
    if not value or not str(value).strip():
        return None
    try:
        from email.utils import parsedate_to_datetime

        parsed = parsedate_to_datetime(str(value).strip())
    except (TypeError, ValueError, OverflowError, IndexError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def mime_type_from_header(content_type: str | None, *, fallback: str) -> str:
    raw = (content_type or "").split(";", 1)[0].strip()
    candidate = raw or fallback
    if MIME_TYPE_PATTERN.fullmatch(candidate) is None:
        return fallback
    return candidate


def date_to_utc_midnight(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        text = iso()
        parsed = datetime.fromisoformat(str(text))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    return None


@dataclass(frozen=True, slots=True)
class SourceDocument:
    """Stable identity for one public document across retrieved versions."""

    document_id: str
    source_id: str
    canonical_url: str
    canonicalization_version: str
    document_type: str
    recorded_at: datetime

    def __post_init__(self) -> None:
        if DOCUMENT_ID_PATTERN.fullmatch(self.document_id) is None:
            raise ValueError("document_id must be an opaque doc_ identifier")
        if SOURCE_ID_PATTERN.fullmatch(self.source_id) is None:
            raise ValueError("source_id must be a stable lowercase identifier")
        _validate_url(self.canonical_url)
        if TOKEN_PATTERN.fullmatch(self.canonicalization_version) is None:
            raise ValueError("canonicalization_version must be a stable token")
        if DOCUMENT_TYPE_PATTERN.fullmatch(self.document_type) is None:
            raise ValueError("document_type must be a lowercase snake_case token")
        _validate_utc(self.recorded_at, field="recorded_at")


@dataclass(frozen=True, slots=True)
class SourceDocumentVersion:
    """Immutable bytes and acquisition metadata for one retrieval."""

    version_id: str
    document_id: str
    content_sha256: str
    byte_length: int
    storage_key: str
    retrieved_at: datetime
    published_at: datetime | None
    recorded_at: datetime
    mime_type: str
    http_status: int
    http_etag: str | None
    http_last_modified: datetime | None
    parser_name: str
    parser_version: str
    normalized_text_sha256: str | None

    def __post_init__(self) -> None:
        if VERSION_ID_PATTERN.fullmatch(self.version_id) is None:
            raise ValueError("version_id must be an opaque docv_ identifier")
        if DOCUMENT_ID_PATTERN.fullmatch(self.document_id) is None:
            raise ValueError("document_id must be an opaque doc_ identifier")
        _validate_sha256(self.content_sha256, field="content_sha256")
        if (
            isinstance(self.byte_length, bool)
            or not isinstance(self.byte_length, int)
            or self.byte_length < 0
        ):
            raise ValueError("byte_length must be a non-negative integer")
        if self.storage_key != storage_key_for(self.content_sha256):
            raise ValueError("storage_key must be the canonical content-addressed key")
        _validate_utc(self.retrieved_at, field="retrieved_at")
        _validate_utc(self.recorded_at, field="recorded_at")
        if self.published_at is not None:
            _validate_utc(self.published_at, field="published_at")
        if MIME_TYPE_PATTERN.fullmatch(self.mime_type) is None:
            raise ValueError("mime_type must be a valid media type without parameters")
        if isinstance(self.http_status, bool) or self.http_status != 200:
            raise ValueError("http_status must be 200 for a complete retrieval")
        _validate_optional_text(self.http_etag, field="http_etag", maximum=1024)
        if self.http_last_modified is not None:
            _validate_utc(self.http_last_modified, field="http_last_modified")
        if TOKEN_PATTERN.fullmatch(self.parser_name) is None:
            raise ValueError("parser_name must be a stable token")
        if TOKEN_PATTERN.fullmatch(self.parser_version) is None:
            raise ValueError("parser_version must be a stable token")
        if self.normalized_text_sha256 is not None:
            _validate_sha256(self.normalized_text_sha256, field="normalized_text_sha256")

    @classmethod
    def capture(
        cls,
        *,
        version_id: str,
        document_id: str,
        content: bytes,
        retrieved_at: datetime,
        published_at: datetime | None,
        recorded_at: datetime,
        mime_type: str,
        http_status: int,
        http_etag: str | None,
        http_last_modified: datetime | None,
        parser_name: str,
        parser_version: str,
        normalized_text: str | None,
    ) -> "SourceDocumentVersion":
        """Create a version whose hashes and storage key are derived, never trusted."""
        content_sha256 = sha256_bytes(content)
        normalized_text_sha256 = (
            sha256_text(normalized_text) if normalized_text is not None else None
        )
        return cls(
            version_id=version_id,
            document_id=document_id,
            content_sha256=content_sha256,
            byte_length=len(content),
            storage_key=storage_key_for(content_sha256),
            retrieved_at=retrieved_at,
            published_at=published_at,
            recorded_at=recorded_at,
            mime_type=mime_type,
            http_status=http_status,
            http_etag=http_etag,
            http_last_modified=http_last_modified,
            parser_name=parser_name,
            parser_version=parser_version,
            normalized_text_sha256=normalized_text_sha256,
        )


@dataclass(frozen=True, slots=True)
class FetchedCapture:
    """One successful scraper fetch, before or after it is persisted."""

    url: str
    content: bytes
    retrieved_at: datetime
    mime_type: str
    http_status: int = 200
    http_etag: str | None = None
    http_last_modified: datetime | None = None
    published_at: datetime | None = None
    parser_name: str = SCRAPE_PARSER_NAME
    parser_version: str = SCRAPE_PARSER_VERSION
    normalized_text: str | None = None
    document_type: str = DEFAULT_DOCUMENT_TYPE

    def to_models(self) -> tuple[SourceDocument, SourceDocumentVersion]:
        canonical = canonicalize_url(self.url)
        recorded_at = utcnow()
        document_id = document_id_for(canonical)
        content_sha256 = sha256_bytes(self.content)
        document = SourceDocument(
            document_id=document_id,
            source_id=source_id_for_url(canonical),
            canonical_url=canonical,
            canonicalization_version=CANONICALIZATION_VERSION,
            document_type=self.document_type,
            recorded_at=recorded_at,
        )
        version = SourceDocumentVersion.capture(
            version_id=version_id_for(document_id, content_sha256),
            document_id=document_id,
            content=self.content,
            retrieved_at=self.retrieved_at,
            published_at=self.published_at,
            recorded_at=recorded_at,
            mime_type=self.mime_type,
            http_status=self.http_status,
            http_etag=self.http_etag,
            http_last_modified=self.http_last_modified,
            parser_name=self.parser_name,
            parser_version=self.parser_version,
            normalized_text=self.normalized_text,
        )
        return document, version

    def to_sidecar_row(self) -> dict[str, Any]:
        document, version = self.to_models()
        return {
            "original_url": self.url,
            "canonical_url": document.canonical_url,
            "source_id": document.source_id,
            "document_id": document.document_id,
            "document_type": document.document_type,
            "canonicalization_version": document.canonicalization_version,
            "version_id": version.version_id,
            "content_sha256": version.content_sha256,
            "byte_length": version.byte_length,
            "storage_key": version.storage_key,
            "retrieved_at": canonical_utc(version.retrieved_at),
            "published_at": canonical_utc(version.published_at) if version.published_at else None,
            "recorded_at": canonical_utc(version.recorded_at),
            "mime_type": version.mime_type,
            "http_status": version.http_status,
            "http_etag": version.http_etag,
            "http_last_modified": (
                canonical_utc(version.http_last_modified)
                if version.http_last_modified
                else None
            ),
            "parser_name": version.parser_name,
            "parser_version": version.parser_version,
            "normalized_text_sha256": version.normalized_text_sha256,
        }


def models_from_sidecar_row(row: Mapping[str, Any]) -> tuple[SourceDocument, SourceDocumentVersion]:
    """Rebuild domain values from a sidecar row (hashes already recorded)."""
    recorded_at = parse_canonical_utc(str(row["recorded_at"]))
    published_at = (
        parse_canonical_utc(str(row["published_at"])) if row.get("published_at") else None
    )
    last_modified = (
        parse_canonical_utc(str(row["http_last_modified"]))
        if row.get("http_last_modified")
        else None
    )
    document = SourceDocument(
        document_id=str(row["document_id"]),
        source_id=str(row["source_id"]),
        canonical_url=str(row["canonical_url"]),
        canonicalization_version=str(row.get("canonicalization_version") or CANONICALIZATION_VERSION),
        document_type=str(row.get("document_type") or DEFAULT_DOCUMENT_TYPE),
        recorded_at=recorded_at,
    )
    version = SourceDocumentVersion(
        version_id=str(row["version_id"]),
        document_id=str(row["document_id"]),
        content_sha256=str(row["content_sha256"]),
        byte_length=int(row["byte_length"]),
        storage_key=str(row["storage_key"]),
        retrieved_at=parse_canonical_utc(str(row["retrieved_at"])),
        published_at=published_at,
        recorded_at=recorded_at,
        mime_type=str(row["mime_type"]),
        http_status=int(row["http_status"]),
        http_etag=str(row["http_etag"]) if row.get("http_etag") else None,
        http_last_modified=last_modified,
        parser_name=str(row.get("parser_name") or SCRAPE_PARSER_NAME),
        parser_version=str(row.get("parser_version") or SCRAPE_PARSER_VERSION),
        normalized_text_sha256=(
            str(row["normalized_text_sha256"]) if row.get("normalized_text_sha256") else None
        ),
    )
    return document, version


def provenance_sidecar_path(pdf_path: str | Path) -> Path:
    path = Path(pdf_path)
    return path.with_name(f"{path.stem}.provenance.json")


def write_provenance_sidecar(pdf_path: str | Path, rows: Sequence[Mapping[str, Any]]) -> Path:
    sidecar = provenance_sidecar_path(pdf_path)
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": SIDECAR_SCHEMA,
        "generated_at": canonical_utc(utcnow()),
        "canonicalization_version": CANONICALIZATION_VERSION,
        "parser_name": SCRAPE_PARSER_NAME,
        "parser_version": SCRAPE_PARSER_VERSION,
        "documents": list(rows),
    }
    sidecar.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return sidecar


def load_provenance_sidecar(path: str | Path) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("provenance sidecar must be a JSON object")
    documents = data.get("documents")
    if not isinstance(documents, list):
        raise ValueError("provenance sidecar is missing documents[]")
    return [row for row in documents if isinstance(row, dict)]


def git_code_revision(repo_root: str | Path | None = None) -> str:
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def declared_extractor_versions() -> dict[str, str]:
    return {
        "pattern_layer_version": PATTERN_LAYER_VERSION,
        "ner_backend": DEFAULT_NER_BACKEND,
        "semantic_model": SEMANTIC_MODEL_NAME,
        "victim_age_gate_version": VICTIM_AGE_GATE_VERSION,
    }


def new_run_id() -> str:
    return f"run_{uuid.uuid4().hex}"


def _placeholder(dialect: str) -> str:
    return "?" if dialect == "sqlite" else "%s"


def apply_sqlite_provenance_schema(cursor: Any) -> None:
    """Create provenance tables, immutability triggers, and nullable case refs."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS source_documents (
            document_id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            canonical_url TEXT NOT NULL UNIQUE,
            canonicalization_version TEXT NOT NULL,
            document_type TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            CHECK (document_id GLOB 'doc_[a-z0-9]*'),
            CHECK (length(source_id) BETWEEN 2 AND 128),
            CHECK (length(canonical_url) BETWEEN 8 AND 2048),
            CHECK (length(canonicalization_version) BETWEEN 1 AND 128),
            CHECK (length(document_type) BETWEEN 2 AND 64),
            CHECK (recorded_at GLOB '*Z')
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_source_documents_source_id
        ON source_documents (source_id)
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS source_document_versions (
            version_id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            content_sha256 TEXT NOT NULL,
            byte_length INTEGER NOT NULL,
            storage_key TEXT NOT NULL,
            retrieved_at TEXT NOT NULL,
            published_at TEXT,
            recorded_at TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            http_status INTEGER NOT NULL,
            http_etag TEXT,
            http_last_modified TEXT,
            parser_name TEXT NOT NULL,
            parser_version TEXT NOT NULL,
            normalized_text_sha256 TEXT,
            FOREIGN KEY (document_id) REFERENCES source_documents(document_id),
            CHECK (version_id GLOB 'docv_[a-z0-9]*'),
            CHECK (length(content_sha256) = 64 AND content_sha256 NOT GLOB '*[^0-9a-f]*'),
            CHECK (byte_length >= 0),
            CHECK (storage_key = 'sha256/' || substr(content_sha256, 1, 2) || '/' || content_sha256),
            CHECK (retrieved_at GLOB '*Z'),
            CHECK (published_at IS NULL OR published_at GLOB '*Z'),
            CHECK (recorded_at GLOB '*Z'),
            CHECK (http_status = 200),
            CHECK (http_last_modified IS NULL OR http_last_modified GLOB '*Z')
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_source_document_versions_document_time
        ON source_document_versions (document_id, retrieved_at, version_id)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_source_document_versions_content_sha256
        ON source_document_versions (content_sha256)
        """
    )
    cursor.execute(
        """
        CREATE TRIGGER IF NOT EXISTS source_documents_immutable_update
        BEFORE UPDATE ON source_documents
        BEGIN
            SELECT RAISE(ABORT, 'source_documents rows are immutable');
        END
        """
    )
    cursor.execute(
        """
        CREATE TRIGGER IF NOT EXISTS source_documents_immutable_delete
        BEFORE DELETE ON source_documents
        BEGIN
            SELECT RAISE(ABORT, 'source_documents rows are immutable');
        END
        """
    )
    cursor.execute(
        """
        CREATE TRIGGER IF NOT EXISTS source_document_versions_immutable_update
        BEFORE UPDATE ON source_document_versions
        BEGIN
            SELECT RAISE(ABORT, 'source_document_versions rows are immutable');
        END
        """
    )
    cursor.execute(
        """
        CREATE TRIGGER IF NOT EXISTS source_document_versions_immutable_delete
        BEFORE DELETE ON source_document_versions
        BEGIN
            SELECT RAISE(ABORT, 'source_document_versions rows are immutable');
        END
        """
    )
    _create_extraction_runs(cursor)
    _add_case_provenance_columns_sqlite(cursor)


def apply_postgres_provenance_schema(cursor: Any) -> None:
    """Create provenance tables and nullable case refs for Railway Postgres.

    Rows are append-only: equivalent BEFORE UPDATE/DELETE triggers reject
    mutation of source_documents and source_document_versions. If a host
    cannot install those triggers, treat the tables as append-only by
    convention — CaseStorage only inserts.
    """
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS source_documents (
            document_id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            canonical_url TEXT NOT NULL UNIQUE,
            canonicalization_version TEXT NOT NULL,
            document_type TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_source_documents_source_id
        ON source_documents (source_id)
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS source_document_versions (
            version_id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL REFERENCES source_documents(document_id),
            content_sha256 TEXT NOT NULL,
            byte_length INTEGER NOT NULL,
            storage_key TEXT NOT NULL,
            retrieved_at TEXT NOT NULL,
            published_at TEXT,
            recorded_at TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            http_status INTEGER NOT NULL,
            http_etag TEXT,
            http_last_modified TEXT,
            parser_name TEXT NOT NULL,
            parser_version TEXT NOT NULL,
            normalized_text_sha256 TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_source_document_versions_document_time
        ON source_document_versions (document_id, retrieved_at, version_id)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_source_document_versions_content_sha256
        ON source_document_versions (content_sha256)
        """
    )
    cursor.execute(
        """
        CREATE OR REPLACE FUNCTION caselinker_append_only()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $fn$
        BEGIN
            RAISE EXCEPTION '% rows are append-only', TG_TABLE_NAME;
        END;
        $fn$
        """
    )
    cursor.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname = 'source_documents_immutable_update'
            ) THEN
                CREATE TRIGGER source_documents_immutable_update
                BEFORE UPDATE ON source_documents
                FOR EACH ROW EXECUTE PROCEDURE caselinker_append_only();
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname = 'source_documents_immutable_delete'
            ) THEN
                CREATE TRIGGER source_documents_immutable_delete
                BEFORE DELETE ON source_documents
                FOR EACH ROW EXECUTE PROCEDURE caselinker_append_only();
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname = 'source_document_versions_immutable_update'
            ) THEN
                CREATE TRIGGER source_document_versions_immutable_update
                BEFORE UPDATE ON source_document_versions
                FOR EACH ROW EXECUTE PROCEDURE caselinker_append_only();
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname = 'source_document_versions_immutable_delete'
            ) THEN
                CREATE TRIGGER source_document_versions_immutable_delete
                BEFORE DELETE ON source_document_versions
                FOR EACH ROW EXECUTE PROCEDURE caselinker_append_only();
            END IF;
        END $$;
        """
    )
    _create_extraction_runs(cursor)
    cursor.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='cases' AND column_name='document_version_id'
            ) THEN
                ALTER TABLE cases ADD COLUMN document_version_id TEXT;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='cases' AND column_name='extraction_run_id'
            ) THEN
                ALTER TABLE cases ADD COLUMN extraction_run_id TEXT;
            END IF;
        END $$;
        """
    )


def _create_extraction_runs(cursor: Any) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS extraction_runs (
            run_id TEXT PRIMARY KEY,
            code_revision TEXT,
            started_at TEXT NOT NULL,
            pattern_layer_version TEXT,
            ner_backend TEXT,
            semantic_model TEXT,
            victim_age_gate_version TEXT,
            source_files TEXT
        )
        """
    )


def _add_case_provenance_columns_sqlite(cursor: Any) -> None:
    for column in ("document_version_id", "extraction_run_id"):
        try:
            cursor.execute(f"ALTER TABLE cases ADD COLUMN {column} TEXT")
        except Exception:
            pass


def persist_document(cursor: Any, document: SourceDocument, *, dialect: str = "sqlite") -> str:
    """Insert a source_documents row. Identical existing row is a no-op."""
    ph = _placeholder(dialect)
    cursor.execute(
        f"SELECT document_id, source_id, canonical_url, canonicalization_version, "
        f"document_type, recorded_at FROM source_documents WHERE document_id = {ph}",
        (document.document_id,),
    )
    existing = cursor.fetchone()
    if existing:
        return document.document_id
    cursor.execute(
        f"""
        INSERT INTO source_documents (
            document_id, source_id, canonical_url, canonicalization_version,
            document_type, recorded_at
        ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """,
        (
            document.document_id,
            document.source_id,
            document.canonical_url,
            document.canonicalization_version,
            document.document_type,
            canonical_utc(document.recorded_at),
        ),
    )
    return document.document_id


def persist_version(cursor: Any, version: SourceDocumentVersion, *, dialect: str = "sqlite") -> str:
    """Insert a source_document_versions row. Identical existing row is a no-op."""
    ph = _placeholder(dialect)
    cursor.execute(
        f"SELECT version_id FROM source_document_versions WHERE version_id = {ph}",
        (version.version_id,),
    )
    if cursor.fetchone():
        return version.version_id
    cursor.execute(
        f"""
        INSERT INTO source_document_versions (
            version_id, document_id, content_sha256, byte_length, storage_key,
            retrieved_at, published_at, recorded_at, mime_type, http_status,
            http_etag, http_last_modified, parser_name, parser_version,
            normalized_text_sha256
        ) VALUES (
            {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph},
            {ph}, {ph}, {ph}, {ph}, {ph}
        )
        """,
        (
            version.version_id,
            version.document_id,
            version.content_sha256,
            version.byte_length,
            version.storage_key,
            canonical_utc(version.retrieved_at),
            canonical_utc(version.published_at) if version.published_at else None,
            canonical_utc(version.recorded_at),
            version.mime_type,
            version.http_status,
            version.http_etag,
            canonical_utc(version.http_last_modified) if version.http_last_modified else None,
            version.parser_name,
            version.parser_version,
            version.normalized_text_sha256,
        ),
    )
    return version.version_id


def persist_models(
    cursor: Any,
    document: SourceDocument,
    version: SourceDocumentVersion,
    *,
    dialect: str = "sqlite",
) -> tuple[str, str]:
    persist_document(cursor, document, dialect=dialect)
    persist_version(cursor, version, dialect=dialect)
    return document.document_id, version.version_id


def persist_sidecar_rows(
    cursor: Any,
    rows: Iterable[Mapping[str, Any]],
    *,
    dialect: str = "sqlite",
) -> list[str]:
    version_ids: list[str] = []
    for row in rows:
        document, version = models_from_sidecar_row(row)
        persist_models(cursor, document, version, dialect=dialect)
        version_ids.append(version.version_id)
    return version_ids


def latest_version_id_for_url(cursor: Any, url: str, *, dialect: str = "sqlite") -> Optional[str]:
    try:
        canonical = canonicalize_url(url)
    except ValueError:
        return None
    ph = _placeholder(dialect)
    cursor.execute(
        f"""
        SELECT v.version_id
        FROM source_document_versions v
        JOIN source_documents d ON d.document_id = v.document_id
        WHERE d.canonical_url = {ph}
        ORDER BY v.retrieved_at DESC, v.version_id DESC
        LIMIT 1
        """,
        (canonical,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    return row[0] if not isinstance(row, dict) else row.get("version_id")


def insert_extraction_run(
    cursor: Any,
    *,
    run_id: str,
    code_revision: str,
    started_at: datetime,
    pattern_layer_version: str,
    ner_backend: str,
    semantic_model: str,
    victim_age_gate_version: str,
    source_files: Sequence[str],
    dialect: str = "sqlite",
) -> str:
    ph = _placeholder(dialect)
    cursor.execute(
        f"""
        INSERT INTO extraction_runs (
            run_id, code_revision, started_at, pattern_layer_version,
            ner_backend, semantic_model, victim_age_gate_version, source_files
        ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """,
        (
            run_id,
            code_revision,
            canonical_utc(started_at),
            pattern_layer_version,
            ner_backend,
            semantic_model,
            victim_age_gate_version,
            json.dumps(list(source_files)),
        ),
    )
    return run_id


def resolve_case_source_url(case: Mapping[str, Any]) -> Optional[str]:
    url = case.get("source_url")
    if isinstance(url, str) and url.strip():
        return url.strip()
    raw = case.get("raw_data")
    if isinstance(raw, dict):
        raw_url = raw.get("source_url")
        if isinstance(raw_url, str) and raw_url.strip():
            return raw_url.strip()
    return None


def case_source_files(cases: Sequence[Mapping[str, Any]]) -> list[str]:
    files: list[str] = []
    seen: set[str] = set()
    for case in cases:
        raw = case.get("raw_data") if isinstance(case.get("raw_data"), dict) else {}
        candidate = case.get("source_file") or (raw.get("source_file") if raw else None)
        if isinstance(candidate, str) and candidate.strip() and candidate not in seen:
            seen.add(candidate)
            files.append(candidate)
    return files


def discover_sidecars(source_files: Sequence[str]) -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    for source in source_files:
        path = Path(source)
        for candidate in (
            provenance_sidecar_path(path),
            path.with_name(f"{path.name}.provenance.json"),
        ):
            resolved = candidate if candidate.is_absolute() else Path(candidate)
            if resolved.is_file() and resolved.resolve() not in seen:
                seen.add(resolved.resolve())
                found.append(resolved)
    return found


def attach_ingest_provenance(
    storage: Any,
    cases: Sequence[dict[str, Any]],
    *,
    repo_root: str | Path | None = None,
    extractor_versions: Mapping[str, str] | None = None,
) -> Optional[str]:
    """
    Import any scrape sidecars, record one extraction_run, and set nullable
    document_version_id / extraction_run_id on each case dict.

    Returns the run_id, or None if recording the run failed. Missing sidecars
    leave document_version_id unset (legacy NULL).
    """
    source_files = case_source_files(cases)
    for sidecar in discover_sidecars(source_files):
        try:
            storage.import_provenance_sidecar(sidecar)
        except Exception as exc:
            print(f"⚠️  Provenance sidecar skipped ({sidecar}): {exc}")

    versions = dict(declared_extractor_versions())
    if extractor_versions:
        versions.update(extractor_versions)
    try:
        run_id = storage.record_extraction_run(
            code_revision=git_code_revision(repo_root),
            started_at=utcnow(),
            source_files=source_files,
            **versions,
        )
    except Exception as exc:
        print(f"⚠️  extraction_runs record skipped: {exc}")
        return None

    for case in cases:
        case["extraction_run_id"] = run_id
        url = resolve_case_source_url(case)
        if not url:
            continue
        try:
            version_id = storage.get_document_version_id_for_url(url)
        except Exception:
            version_id = None
        if version_id:
            case["document_version_id"] = version_id
    return run_id
