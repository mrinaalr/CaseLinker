"""Processing gate: refuse an obvious duplicate case before it is written.

An obvious duplicate is a new case id whose canonical article URL is already
held by a different source. The existing row stays; the new row is not written.

This does not clean source PDFs. Same-source repeats (a yearbook pasting one
clipping twice, or several defendants in one article) are left alone. Those
are found with ``find_ingested_duplicates`` / ``verify_duplicate_pdf_pages``
and removed from the PDF, not collapsed here.

Placeholder URLs (tip forms, newsroom indexes) are not article identity, so
they never count as a duplicate.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

_STORAGE = Path(__file__).resolve().parents[1] / "Storage Layer"
if str(_STORAGE) not in sys.path:
    sys.path.append(str(_STORAGE))

from provenance import canonicalize_url, resolve_case_source_url  # noqa: E402


# Hosts are compared after stripping a leading www. Paths have no trailing slash.
_PLACEHOLDER_PATHS: dict[str, set[str]] = {
    "report.cybertip.org": {""},
    "gbi.georgia.gov": {"/submit-tips-online"},
    "justice.gov": {"/psc"},
    "missingkids.com": {"/home", ""},
    "missingkids.org": {"/home", ""},
}

_LISTING_MARKERS = (
    "/category/",
    "showall=true",
    "/search/results",
    "/search?",
    "/cases-and-arrests",
    "/news/categories/",
    "news-releases#",
    "/cybertipline/cybertiplinedata",
)


def _collapse_ws(url: str) -> str:
    return re.sub(r"\s+", "", (url or "").strip())


def article_url_key(url: str | None) -> str | None:
    """Canonical article URL, or None when the value cannot identify one article."""
    raw = _collapse_ws(url or "")
    if not raw:
        return None
    try:
        canonical = canonicalize_url(raw)
    except ValueError:
        return None
    parsed = urlsplit(canonical)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = (parsed.path or "").rstrip("/").lower()
    if path in _PLACEHOLDER_PATHS.get(host, set()):
        return None
    blob = canonical.lower()
    if any(marker in blob for marker in _LISTING_MARKERS):
        return None
    return canonical


def _case_source(case: Mapping[str, Any]) -> str:
    return str(case.get("source") or "").strip()


def drop_obvious_duplicate_cases(
    incoming: Sequence[Mapping[str, Any]],
    existing: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep rows that are not an obvious cross-source duplicate.

    Returns ``(kept, skipped)``. A skipped row names ``duplicate_of_case_id``
    and is not written. Re-ingest of an id already stored is kept, so that
    row can refresh. Same-source rows that share a URL are kept.
    """
    holders: dict[str, list[dict[str, str]]] = defaultdict(list)

    def _add(case_id: str, source: str, key: str) -> None:
        bucket = holders[key]
        if any(row["id"] == case_id for row in bucket):
            return
        bucket.append({"id": case_id, "source": source})

    for row in existing:
        key = article_url_key(row.get("source_url"))
        case_id = str(row.get("id") or "").strip()
        if key and case_id:
            _add(case_id, _case_source(row), key)

    kept: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for case in incoming:
        payload = dict(case)
        key = article_url_key(resolve_case_source_url(payload))
        case_id = str(payload.get("id") or "").strip()
        source = _case_source(payload)
        if not key:
            kept.append(payload)
            continue
        bucket = holders.get(key) or []
        if any(row["id"] == case_id for row in bucket):
            kept.append(payload)
            continue
        other = next((row for row in bucket if row["source"].casefold() != source.casefold()), None)
        if other is not None:
            skipped.append({
                "id": case_id,
                "source": source,
                "source_url": key,
                "duplicate_of_case_id": other["id"],
                "duplicate_of_source": other["source"],
            })
            continue
        kept.append(payload)
        if case_id:
            _add(case_id, source, key)
    return kept, skipped
