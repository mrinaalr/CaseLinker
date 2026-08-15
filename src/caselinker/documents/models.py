"""Pure domain values for stable documents and immutable retrieved versions."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Self
from urllib.parse import parse_qsl, urlsplit

DOCUMENT_ID_PATTERN: Final = re.compile(r"^doc_[a-z0-9][a-z0-9._-]{2,127}$")
VERSION_ID_PATTERN: Final = re.compile(r"^docv_[a-z0-9][a-z0-9._-]{2,127}$")
SOURCE_ID_PATTERN: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{1,127}$")
DOCUMENT_TYPE_PATTERN: Final = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
MIME_TYPE_PATTERN: Final = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*$"
)
SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")
TOKEN_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
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


def _validate_optional_text(value: str | None, *, field: str, maximum: int) -> None:
    if value is not None:
        _validate_required_text(value, field=field, maximum=maximum)


def _validate_sha256(value: str, *, field: str) -> None:
    if SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


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
        expected_storage_key = self.storage_key_for(self.content_sha256)
        if self.storage_key != expected_storage_key:
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

    @staticmethod
    def storage_key_for(content_sha256: str) -> str:
        _validate_sha256(content_sha256, field="content_sha256")
        return f"sha256/{content_sha256[:2]}/{content_sha256}"

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
    ) -> Self:
        """Create a version whose hashes and storage key are derived, never trusted."""
        content_sha256 = hashlib.sha256(content).hexdigest()
        normalized_text_sha256 = (
            hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
            if normalized_text is not None
            else None
        )
        return cls(
            version_id=version_id,
            document_id=document_id,
            content_sha256=content_sha256,
            byte_length=len(content),
            storage_key=cls.storage_key_for(content_sha256),
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
