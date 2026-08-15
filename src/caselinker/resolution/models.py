"""Immutable process identity for canonical resolution runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from caselinker.assertions.models import TOKEN_PATTERN


@dataclass(frozen=True, slots=True)
class ResolutionRun:
    run_id: str
    code_revision: str
    created_at: datetime

    def __post_init__(self) -> None:
        if TOKEN_PATTERN.fullmatch(self.run_id) is None:
            raise ValueError("run_id must be a stable token")
        if (
            not self.code_revision
            or self.code_revision != self.code_revision.strip()
            or len(self.code_revision) > 128
            or any(ord(character) < 32 or ord(character) == 127 for character in self.code_revision)
        ):
            raise ValueError("code_revision must be non-empty, trimmed, and at most 128 characters")
        offset = self.created_at.utcoffset()
        if self.created_at.tzinfo is None or offset is None or offset.total_seconds() != 0:
            raise ValueError("created_at must be timezone-aware UTC")
