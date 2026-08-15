"""Storage-independent repository contract for immutable documents."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from caselinker.documents.models import SourceDocument, SourceDocumentVersion


class InsertOutcome(StrEnum):
    CREATED = "created"
    EXISTING = "existing"


class DocumentRepositoryError(RuntimeError):
    """Base error for document repository contract violations."""


class ImmutableConflictError(DocumentRepositoryError):
    """An immutable identity was reused with different content."""


class MissingDocumentError(DocumentRepositoryError):
    """A version referenced a document identity that does not exist."""


class DocumentRepository(Protocol):
    def add_document(self, document: SourceDocument) -> InsertOutcome: ...

    def get_document(self, document_id: str) -> SourceDocument | None: ...

    def add_version(self, version: SourceDocumentVersion) -> InsertOutcome: ...

    def get_version(self, version_id: str) -> SourceDocumentVersion | None: ...

    def list_versions(self, document_id: str) -> tuple[SourceDocumentVersion, ...]: ...
