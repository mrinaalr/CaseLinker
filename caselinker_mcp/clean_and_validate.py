"""Read-only duplicate audit: ingested cases traced back to source PDFs.

Opens ``caselinker.db`` with ``mode=ro`` and reads PDF bytes for text extraction.
Does not write sqlite, Postgres, or PDF files. Page removal lives in
``collector/remove_pdf_pages_by_text.py`` and the local-only MCP wrapper
``drop_collected_pdf_pages`` — this module never calls that write path.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

_REPO = Path(__file__).resolve().parent.parent
_DEFAULT_DB = _REPO / "caselinker.db"

# Placeholder links NCMEC used when a clipping had no article URL.
_FALLBACK_PATHS: dict[str, set[str]] = {
    "report.cybertip.org": {"", "/"},
    "gbi.georgia.gov": {"/submit-tips-online"},
    "justice.gov": {"/psc"},
    "missingkids.com": {"/home", "/"},
    "missingkids.org": {"/home", "/"},
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

# Headline on two pages is a second copy when the pages themselves match.
_PAGE_COPY_JACCARD = 0.72
# Two ingested rows are the same clipping when token overlap is this high.
_ROW_COPY_JACCARD = 0.85

_PAGE_CACHE: dict[str, list[str]] = {}


def compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def normalize_source_url(url: str) -> str:
    """Fold scheme, www, and a trailing slash so near-identical links group."""
    raw = re.sub(r"\s+", "", (url or "").strip())
    if not raw:
        return ""
    parsed = urlparse(raw)
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path or ""
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    scheme = "https" if parsed.scheme in {"http", "https"} else (parsed.scheme or "")
    return urlunparse((scheme, host, path.lower(), "", parsed.query, ""))


def _host_path(url: str) -> tuple[str, str]:
    raw = re.sub(r"\s+", "", (url or "").strip())
    parsed = urlparse(raw)
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = (parsed.path or "").rstrip("/").lower()
    return host, path


def url_kind(url: str) -> str:
    """``article``, ``fallback`` (generic landing page), or ``listing`` (index)."""
    host, path = _host_path(url)
    allowed = _FALLBACK_PATHS.get(host)
    if allowed is not None and path in {p.rstrip("/") for p in allowed}:
        return "fallback"
    blob = (url or "").lower()
    if any(marker in blob for marker in _LISTING_MARKERS):
        return "listing"
    return "article"


def headline_needle(case_text: str, *, min_chars: int = 28, take: int = 48) -> str:
    """Stable prefix of the clipping title, ignoring URL and boilerplate lines."""
    parts: list[str] = []
    for line in (case_text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        low = stripped.lower()
        if low.startswith(("http://", "https://", "source:", "www.")):
            continue
        parts.append(stripped)
        if len(" ".join(parts)) >= 40:
            break
    needle = compact(" ".join(parts))
    if len(needle) < min_chars:
        return ""
    return needle[:take]


def url_slug_needle(url: str, *, min_chars: int = 16) -> str:
    """Distinctive path slug. Short fallback paths return empty (they match too much)."""
    if url_kind(url) != "article":
        return ""
    parsed = urlparse(re.sub(r"\s+", "", (url or "").strip()))
    segments = [s for s in (parsed.path or "").split("/") if s and s not in {"news", "pr", "story", "article"}]
    slug = segments[-1] if segments else ""
    slug = re.sub(r"\.[a-z0-9]{2,4}$", "", slug, flags=re.I)
    needle = compact(slug)
    if len(needle) < min_chars and len(segments) >= 2:
        needle = compact(segments[-2] + segments[-1])
    if len(needle) < min_chars:
        return ""
    return needle[:80]


def token_jaccard(text_a: str, text_b: str) -> float:
    tokens_a = set(re.findall(r"[a-z0-9']+", (text_a or "").lower()))
    tokens_b = set(re.findall(r"[a-z0-9']+", (text_b or "").lower()))
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def pairwise_jaccard(texts: list[str]) -> tuple[float, float]:
    if len(texts) < 2:
        return 1.0, 1.0
    scores = [
        token_jaccard(texts[i], texts[j])
        for i in range(len(texts))
        for j in range(i + 1, len(texts))
    ]
    return min(scores), max(scores)


def body_compact(text: str) -> str:
    """Page text with standalone page numbers removed, for exact-copy grouping."""
    kept: list[str] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if re.fullmatch(r"\d{1,4}", stripped):
            continue
        if stripped:
            kept.append(stripped)
    return compact(" ".join(kept))


def judge_locations(
    *,
    url_class: str,
    n_cases: int,
    min_row_jaccard: float,
    max_row_jaccard: float,
    copies: list[dict[str, Any]],
) -> dict[str, Any]:
    """Turn PDF headline hits into a cut / keep verdict. ``copies`` are page hits.

    Each copy is ``{"pdf", "page", "page_jaccard"}`` where ``page_jaccard`` is the
    overlap with the earliest hit (1.0 for that earliest hit).
    """
    if url_class == "fallback":
        return {
            "verdict": "fallback_url",
            "cut_from_pdf": False,
            "reason": "Generic landing page stored as source_url, not a repeated article.",
        }
    if url_class == "listing":
        return {
            "verdict": "listing_page",
            "cut_from_pdf": False,
            "reason": "Index or category URL shared by many clippings.",
        }
    if n_cases < 2:
        return {
            "verdict": "unique",
            "cut_from_pdf": False,
            "reason": "Single ingested row.",
        }

    strong = [c for c in copies if c.get("page_jaccard", 1.0) >= _PAGE_COPY_JACCARD]
    weak = [c for c in copies if c.get("page_jaccard", 1.0) < _PAGE_COPY_JACCARD]
    # The earliest hit is the keeper; later strong hits are extra copies.
    extra = strong[1:]
    pdfs = {c["pdf"] for c in strong}
    all_pdfs = {c["pdf"] for c in copies}

    if len(strong) >= 2 and len(pdfs) == 1:
        return {
            "verdict": "same_pdf_twice",
            "cut_from_pdf": True,
            "drop_pages": [
                {"pdf": c["pdf"], "page": c["page"], "page_jaccard": round(c["page_jaccard"], 3)}
                for c in extra
            ],
            "keep_page": {"pdf": strong[0]["pdf"], "page": strong[0]["page"]},
            "reason": "Same headline is on more than one page of one PDF and those pages match.",
        }
    if len(strong) >= 2 and len(pdfs) >= 2:
        ncmec = [c for c in strong if "ncmec" in c["pdf"].lower()]
        other = [c for c in strong if "ncmec" not in c["pdf"].lower()]
        if ncmec and other:
            drop = ncmec
            keep = other[0]
            where = "ncmec_vs_other_source"
        else:
            # Year-vs-year NCMEC, or two non-NCMEC files. Keep the earliest filename/page.
            ordered = sorted(strong, key=lambda c: (c["pdf"], c["page"]))
            keep = ordered[0]
            drop = [c for c in ordered[1:]]
            where = "cross_pdf"
        return {
            "verdict": "cross_pdf",
            "cross_pdf_kind": where,
            "cut_from_pdf": True,
            "drop_pages": [
                {"pdf": c["pdf"], "page": c["page"], "page_jaccard": round(c.get("page_jaccard", 1), 3)}
                for c in drop
            ],
            "keep_page": {"pdf": keep["pdf"], "page": keep["page"]},
            "reason": "Same headline is in more than one PDF and the pages match.",
        }
    if not copies:
        return {
            "verdict": "not_found_in_pdf",
            "cut_from_pdf": False,
            "reason": "Headline was not found in the PDFs searched. No page listed to cut.",
        }
    if len(copies) >= 2 and len(all_pdfs) >= 2 and weak and not extra:
        return {
            "verdict": "cross_pdf_review",
            "cut_from_pdf": False,
            "headline_pages": [{"pdf": c["pdf"], "page": c["page"], "page_jaccard": c["page_jaccard"]} for c in copies],
            "reason": (
                "Headline shows up in more than one PDF, but the page text is only a partial match. "
                "Listed for review; not a cut candidate."
            ),
        }
    if copies and len(strong) < 2 and max_row_jaccard >= _ROW_COPY_JACCARD:
        return {
            "verdict": "pdf_once_rows_match",
            "cut_from_pdf": False,
            "reason": (
                "Ingested rows match each other, but the PDF shows that headline once. "
                "Cutting the page would remove the only copy."
            ),
        }
    if max_row_jaccard < 0.45:
        return {
            "verdict": "shared_url_different_stories",
            "cut_from_pdf": False,
            "reason": "Rows share a URL and little text. Typical of a URL assigned across a batching boundary.",
        }
    return {
        "verdict": "one_article_many_rows",
        "cut_from_pdf": False,
        "reason": (
            "One PDF location and partial text overlap. "
            "Typical of a multi-defendant sting or a multi-page clipping split into several case ids."
        ),
    }


def _connect_ro(db_path: Path) -> sqlite3.Connection:
    if not db_path.is_file():
        raise FileNotFoundError(f"sqlite database not found: {db_path}")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_case_rows(db_path: Path | None = None) -> list[dict[str, Any]]:
    path = Path(db_path) if db_path else _DEFAULT_DB
    conn = _connect_ro(path)
    try:
        found = conn.execute(
            """
            SELECT id, source, source_url,
                   json_extract(raw_data, '$.source_file') AS source_file,
                   json_extract(raw_data, '$.case_text') AS case_text
            FROM cases
            """
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "id": row["id"] or "",
            "source": row["source"] or "",
            "source_url": row["source_url"] or "",
            "source_file": row["source_file"] or "",
            "case_text": row["case_text"] or "",
        }
        for row in found
    ]


def _group_rows(rows: list[dict[str, Any]], *, match: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        url = (row.get("source_url") or "").strip()
        if not url:
            continue
        key = normalize_source_url(url) if match == "normalized" else url
        if key:
            grouped[key].append(row)
    return {key: value for key, value in grouped.items() if len(value) > 1}


def _summarize_group(key: str, members: list[dict[str, Any]], *, match: str) -> dict[str, Any]:
    sources = sorted({m["source"] for m in members})
    files = sorted({m["source_file"] for m in members if m["source_file"]})
    raw_url = members[0]["source_url"]
    kind = url_kind(raw_url)
    texts = [m["case_text"] for m in members]
    min_j, max_j = pairwise_jaccard(texts)
    relation = "cross_source" if len(sources) > 1 else "same_source"
    return {
        "match": match,
        "source_url": raw_url if match == "exact" else key,
        "url_kind": kind,
        "relation": relation,
        "case_count": len(members),
        "case_ids": [m["id"] for m in members],
        "sources": sources,
        "source_files": files,
        "min_row_jaccard": round(min_j, 3),
        "max_row_jaccard": round(max_j, 3),
        "ncmec": any(m["source"] == "NCMEC" or str(m["id"]).startswith("ncmec_") for m in members),
    }


def find_ingested_duplicates(
    *,
    db_path: str | None = None,
    source: str = "",
    match: str = "exact",
    limit: int = 0,
) -> dict[str, Any]:
    """Group ingested cases that share a source_url. Read-only. No PDF I/O."""
    if match not in {"exact", "normalized"}:
        return {"error": "match must be 'exact' or 'normalized'", "write": False}
    rows = load_case_rows(Path(db_path) if db_path else None)
    groups = [
        _summarize_group(key, members, match=match)
        for key, members in _group_rows(rows, match=match).items()
    ]
    if source:
        needle = source.strip().lower()
        groups = [
            g
            for g in groups
            if any(needle in s.lower() for s in g["sources"])
            or any(needle in i.lower() for i in g["case_ids"])
        ]
    groups.sort(key=lambda g: (-g["case_count"], g["source_url"]))
    shown = groups if limit <= 0 else groups[:limit]

    def _count(pred) -> int:
        return sum(1 for g in groups if pred(g))

    return {
        "write": False,
        "tool_kind": "READ",
        "mutated": False,
        "db": "sqlite-ro",
        "case_rows_scanned": len(rows),
        "match": match,
        "source_filter": source,
        "group_count": len(groups),
        "case_count": sum(g["case_count"] for g in groups),
        "cross_source_groups": _count(lambda g: g["relation"] == "cross_source"),
        "same_source_groups": _count(lambda g: g["relation"] == "same_source"),
        "ncmec_groups": _count(lambda g: g["ncmec"]),
        "fallback_groups": _count(lambda g: g["url_kind"] == "fallback"),
        "listing_groups": _count(lambda g: g["url_kind"] == "listing"),
        "article_groups": _count(lambda g: g["url_kind"] == "article"),
        "truncated": limit > 0 and len(groups) > limit,
        "groups": shown,
    }


def _pdf_path(repo: Path, source_file: str) -> Path | None:
    name = (source_file or "").strip()
    if not name:
        return None
    path = Path(name)
    if not path.is_absolute():
        path = repo / path
    try:
        resolved = path.resolve()
    except OSError:
        return None
    if not resolved.is_file():
        return None
    if not resolved.is_relative_to(repo.resolve()):
        return None
    return resolved


def ncmec_yearbook_paths(repo: Path | None = None) -> list[Path]:
    root = repo or _REPO
    found = sorted(root.glob("*NCMEC.pdf"))
    return [p for p in found if p.is_file() and re.search(r"\d{4}", p.name)]


def load_pdf_pages(pdf_path: Path) -> list[str]:
    """Extract each page's text. Cached for the process. Read-only."""
    key = str(pdf_path.resolve())
    cached = _PAGE_CACHE.get(key)
    if cached is not None:
        return cached
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    pages = [(page.extract_text() or "") for page in reader.pages]
    _PAGE_CACHE[key] = pages
    return pages


def _pages_containing(pages: list[str], needle: str) -> list[int]:
    if not needle:
        return []
    hits: list[int] = []
    for index, text in enumerate(pages):
        if needle in compact(text):
            hits.append(index + 1)
    return hits


def _anchor_pages(
    headline_pages: dict[str, list[int]],
    slug_pages: dict[str, list[int]],
    page_text: dict[str, list[str]],
) -> dict[str, list[int]]:
    """Pages that are real copies of one article, not a shared press-release template.

    When the article URL slug is present, only pages that contain that slug (or a
    headline within two pages of it) count. Template headlines like "man arrested
    on child sexual abuse material charges" otherwise match dozens of unrelated
    clippings. With no slug, keep a second headline page only when the page text
    itself is almost the same.
    """
    if slug_pages:
        anchors: dict[str, list[int]] = defaultdict(list)
        for pdf_name, pages in slug_pages.items():
            headlines = headline_pages.get(pdf_name) or []
            for page in pages:
                if page in headlines:
                    chosen = page
                else:
                    near = [hit for hit in headlines if abs(hit - page) <= 2]
                    chosen = min(near, key=lambda hit: abs(hit - page)) if near else page
                if chosen not in anchors[pdf_name]:
                    anchors[pdf_name].append(chosen)
        return dict(anchors)

    rough = _copy_records(headline_pages, page_text)
    kept: dict[str, list[int]] = defaultdict(list)
    for copy in rough:
        if copy["page_jaccard"] < 0.92 and copy is not rough[0]:
            continue
        if copy["page"] not in kept[copy["pdf"]]:
            kept[copy["pdf"]].append(copy["page"])
    return dict(kept)


def _copy_records(
    headline_pages: dict[str, list[int]],
    page_text: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """One record per headline hit, with Jaccard against the earliest hit's page text."""
    ordered: list[tuple[str, int]] = []
    for pdf_name in sorted(headline_pages):
        for page in sorted(set(headline_pages[pdf_name])):
            ordered.append((pdf_name, page))
    if not ordered:
        return []
    first_pdf, first_page = ordered[0]
    first_text = ""
    pages = page_text.get(first_pdf) or []
    if 1 <= first_page <= len(pages):
        first_text = pages[first_page - 1]
    copies: list[dict[str, Any]] = []
    for pdf_name, page in ordered:
        pages = page_text.get(pdf_name) or []
        text = pages[page - 1] if 1 <= page <= len(pages) else ""
        score = 1.0 if (pdf_name, page) == (first_pdf, first_page) else token_jaccard(first_text, text)
        copies.append({"pdf": pdf_name, "page": page, "page_jaccard": round(score, 3)})
    return copies


def _search_plan(repo: Path, members: list[dict[str, Any]]) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path | None) -> None:
        if path is None:
            return
        resolved = path.resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        paths.append(resolved)

    ncmec = any(m["source"] == "NCMEC" or "ncmec" in (m["source_file"] or "").lower() for m in members)
    for member in members:
        add(_pdf_path(repo, member["source_file"]))
    if ncmec:
        for path in ncmec_yearbook_paths(repo):
            add(path)
    return paths


def verify_duplicate_pdf_pages(
    *,
    db_path: str | None = None,
    repo_root: str | None = None,
    case_ids: list[str] | None = None,
    source_url: str = "",
    source: str = "",
    match: str = "exact",
    max_groups: int = 8,
    include_listing: bool = False,
) -> dict[str, Any]:
    """Locate duplicate groups inside the source PDFs. Read-only.

    ``max_groups`` caps how many article groups are opened (0 means all).
    Listing and fallback URLs are classified without a recommendation to cut.
    """
    repo = Path(repo_root) if repo_root else _REPO
    rows = load_case_rows(Path(db_path) if db_path else None)
    grouped = _group_rows(rows, match=match)

    if source_url:
        want = source_url.strip()
        want_norm = normalize_source_url(want)
        grouped = {
            key: members
            for key, members in grouped.items()
            if key == want or key == want_norm or any(m["source_url"] == want for m in members)
        }
    if case_ids:
        wanted = {c.strip() for c in case_ids if c and c.strip()}
        grouped = {
            key: members
            for key, members in grouped.items()
            if any(m["id"] in wanted for m in members)
        }
    if source:
        needle = source.strip().lower()
        grouped = {
            key: members
            for key, members in grouped.items()
            if any(needle in (m["source"] or "").lower() or needle in (m["id"] or "").lower() for m in members)
        }

    summaries = [_summarize_group(key, members, match=match) for key, members in grouped.items()]
    summaries.sort(key=lambda g: (-int(g["ncmec"]), -g["case_count"], g["source_url"]))

    verified: list[dict[str, Any]] = []
    opened: list[str] = []
    for summary in summaries:
        if summary["url_kind"] == "listing" and not include_listing:
            verified.append({**summary, **judge_locations(
                url_class="listing",
                n_cases=summary["case_count"],
                min_row_jaccard=summary["min_row_jaccard"],
                max_row_jaccard=summary["max_row_jaccard"],
                copies=[],
            )})
            continue
        if max_groups > 0 and sum(1 for item in verified if item.get("pdf_checked")) >= max_groups:
            break
        members = _members_for_summary(grouped, summary, match=match)
        detail = _verify_members(repo, members, summary)
        if detail.get("pdf_checked"):
            for name in detail.get("pdfs_opened") or []:
                if name not in opened:
                    opened.append(name)
        verified.append(detail)

    cut = [item for item in verified if item.get("cut_from_pdf")]
    return {
        "write": False,
        "tool_kind": "READ",
        "mutated": False,
        "match": match,
        "groups_considered": len(summaries),
        "groups_returned": len(verified),
        "truncated": len(verified) < len(summaries),
        "cut_candidate_groups": len(cut),
        "verdict_counts": _verdict_counts(verified),
        "pdfs_opened": opened,
        "groups": verified,
    }


def _members_for_summary(
    grouped: dict[str, list[dict[str, Any]]],
    summary: dict[str, Any],
    *,
    match: str,
) -> list[dict[str, Any]]:
    key = summary["source_url"] if match == "exact" else normalize_source_url(summary["source_url"])
    if key in grouped:
        return grouped[key]
    for members in grouped.values():
        if members and members[0]["source_url"] == summary["source_url"]:
            return members
    raise KeyError(summary["source_url"])


def _verify_members(repo: Path, members: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
    paths = _search_plan(repo, members)
    page_text: dict[str, list[str]] = {}
    missing = [m["source_file"] for m in members if m["source_file"] and _pdf_path(repo, m["source_file"]) is None]
    for path in paths:
        page_text[path.name] = load_pdf_pages(path)

    # One needle per distinct headline so URL-spill neighbors are not merged.
    needles: list[str] = []
    for member in members:
        needle = headline_needle(member["case_text"])
        if needle and needle not in needles:
            needles.append(needle)
    slug = url_slug_needle(members[0]["source_url"])

    headline_pages: dict[str, list[int]] = defaultdict(list)
    per_case: list[dict[str, Any]] = []
    for member in members:
        needle = headline_needle(member["case_text"])
        hits: dict[str, list[int]] = {}
        for pdf_name, pages in page_text.items():
            found = _pages_containing(pages, needle)
            if found:
                hits[pdf_name] = found
                for page in found:
                    if page not in headline_pages[pdf_name]:
                        headline_pages[pdf_name].append(page)
        per_case.append({
            "id": member["id"],
            "source": member["source"],
            "source_file": member["source_file"],
            "headline_pages": hits,
        })

    url_pages: dict[str, list[int]] = {}
    if slug:
        for pdf_name, pages in page_text.items():
            found = _pages_containing(pages, slug)
            if found:
                url_pages[pdf_name] = found

    anchors = _anchor_pages(dict(headline_pages), url_pages, page_text)
    copies = _copy_records(anchors, page_text)
    judgment = judge_locations(
        url_class=summary["url_kind"],
        n_cases=len(members),
        min_row_jaccard=summary["min_row_jaccard"],
        max_row_jaccard=summary["max_row_jaccard"],
        copies=copies,
    )
    return {
        **summary,
        **judgment,
        "pdf_checked": True,
        "pdfs_opened": [p.name for p in paths],
        "pdfs_missing": sorted(set(missing)),
        "headline_needles": len(needles),
        "url_slug_pages": url_pages,
        "headline_copies": copies,
        "cases": per_case,
    }


def _verdict_counts(groups: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for group in groups:
        counts[str(group.get("verdict") or "unknown")] += 1
    return dict(counts)


def scan_identical_pdf_pages(
    pdf_names: list[str] | None = None,
    *,
    repo_root: str | None = None,
    min_chars: int = 80,
) -> dict[str, Any]:
    """Group pages whose body text matches exactly inside each PDF. Read-only.

    Standalone page numbers are stripped first, so a repeated folio does not
    hide a repeated article. Default scope is the NCMEC yearbook PDFs.
    """
    repo = Path(repo_root) if repo_root else _REPO
    if pdf_names:
        paths = [p for name in pdf_names if (p := _pdf_path(repo, name))]
    else:
        paths = ncmec_yearbook_paths(repo)

    reports: list[dict[str, Any]] = []
    for path in paths:
        pages = load_pdf_pages(path)
        buckets: dict[str, list[int]] = defaultdict(list)
        for index, text in enumerate(pages):
            key = body_compact(text)
            if len(key) < min_chars:
                continue
            buckets[key].append(index + 1)
        duplicate_sets = [pages_i for pages_i in buckets.values() if len(pages_i) > 1]
        reports.append({
            "pdf": path.name,
            "page_count": len(pages),
            "identical_body_groups": len(duplicate_sets),
            "pages_in_those_groups": sum(len(g) for g in duplicate_sets),
            "groups": [
                {
                    "pages": group,
                    "drop_pages": group[1:],
                    "keep_page": group[0],
                    "preview": re.sub(r"\s+", " ", pages[group[0] - 1])[:180],
                }
                for group in duplicate_sets
            ],
        })
    return {
        "write": False,
        "tool_kind": "READ",
        "mutated": False,
        "pdfs": reports,
        "identical_body_groups": sum(item["identical_body_groups"] for item in reports),
    }


def clear_page_cache() -> None:
    _PAGE_CACHE.clear()


def audit_to_jsonable(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False)
