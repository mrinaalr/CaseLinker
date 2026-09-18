"""Free public-record helpers for MCP: DOJ News API + CourtListener RECAP.

No PACER fees. CourtListener docket-detail endpoints often require a free API
token; search + RECAP storage downloads for ``is_available`` documents do not.
"""

from __future__ import annotations

import os
from typing import Any
import httpx

DOJ_API_URL = "https://www.justice.gov/api/v1/press_releases.json"
COURTLISTENER_SEARCH = "https://www.courtlistener.com/api/rest/v4/search/"
COURTLISTENER_STORAGE = "https://storage.courtlistener.com"
USER_AGENT = "CaseLinker-MCP/1.0 (research; free public records)"
DEFAULT_TIMEOUT = 45.0


def _cl_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    token = (os.getenv("COURTLISTENER_API_TOKEN") or os.getenv("COURTLISTENER_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Token {token}"
    return headers


def _doj_headers() -> dict[str, str]:
    return {"Accept": "application/json", "User-Agent": USER_AGENT}


def _html_to_text(html: str) -> str:
    """Minimal body cleanup for DOJ API HTML (paragraphs + table rows)."""
    if not html:
        return ""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        # Fallback: crude strip
        import re

        text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
        text = re.sub(r"(?is)<br\s*/?>", "\n", text)
        text = re.sub(r"(?is)</p>", "\n", text)
        text = re.sub(r"(?is)</tr>", "\n", text)
        text = re.sub(r"(?is)<[^>]+>", " ", text)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"[ \t]+\n", "\n", text)
        return re.sub(r"\n{3,}", "\n\n", text).strip()

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    lines: list[str] = []
    for el in soup.find_all(["p", "tr"]):
        t = " ".join(el.stripped_strings)
        if t:
            lines.append(t)
    if not lines:
        t = soup.get_text("\n", strip=True)
        return t
    return "\n\n".join(lines)


async def search_doj_press_releases(
    title_term: str,
    *,
    page: int = 0,
    pagesize: int = 20,
    require_regex: str = "",
) -> dict[str, Any]:
    """Page the public DOJ News API by title substring (no API key)."""
    title_term = (title_term or "").strip()
    if not title_term:
        return {"error": "title_term is required"}
    pagesize = max(1, min(int(pagesize), 50))
    page = max(0, int(page))
    params = {
        "parameters[title]": title_term,
        "pagesize": pagesize,
        "page": page,
    }
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.get(DOJ_API_URL, params=params, headers=_doj_headers())
        resp.raise_for_status()
        payload = resp.json()

    results = payload.get("results") or payload.get("data") or []
    if not isinstance(results, list):
        results = []

    import re

    require_re = re.compile(require_regex, re.I) if require_regex.strip() else None
    records: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        body_html = item.get("body") or ""
        body = _html_to_text(body_html)
        if require_re and not (require_re.search(title) or require_re.search(body)):
            continue
        url = (
            item.get("url")
            or item.get("path")
            or item.get("alias")
            or ""
        )
        if url and not str(url).startswith("http"):
            url = f"https://www.justice.gov{url}"
        pub = item.get("date") or item.get("release_date") or item.get("created")
        if isinstance(pub, str) and "T" in pub:
            pub = pub.split("T", 1)[0]
        records.append(
            {
                "uuid": item.get("uuid") or item.get("id"),
                "title": title,
                "source_url": url,
                "pub_date": pub,
                "agency": item.get("component") or item.get("organization") or item.get("teaser"),
                "body_preview": body[:800],
                "body_chars": len(body),
                "mode": "resolved",
            }
        )

    return {
        "source": "DOJ News API",
        "cost": "free",
        "title_term": title_term,
        "page": page,
        "pagesize": pagesize,
        "api_result_count": payload.get("count") or payload.get("pager", {}).get("total_items"),
        "returned": len(records),
        "results": records,
        "note": (
            "justice.gov HTML pages are behind Akamai; use this API (or resolve_press_urls.py) "
            "instead of fetching article URLs directly."
        ),
    }


def _normalize_cl_result(item: dict[str, Any], *, search_type: str) -> dict[str, Any]:
    abs_url = item.get("docket_absolute_url") or item.get("absolute_url") or ""
    if abs_url and not str(abs_url).startswith("http"):
        abs_url = f"https://www.courtlistener.com{abs_url}"

    nested = item.get("recap_documents") or []
    free_nested: list[dict[str, Any]] = []
    for doc in nested if isinstance(nested, list) else []:
        if not isinstance(doc, dict):
            continue
        fp = doc.get("filepath_local") or doc.get("filepath_ia")
        available = bool(doc.get("is_available") or fp)
        free_nested.append(
            {
                "id": doc.get("id"),
                "description": doc.get("description") or doc.get("short_description"),
                "is_available": available,
                "filepath_local": doc.get("filepath_local"),
                "download_url": (
                    f"{COURTLISTENER_STORAGE}/{doc['filepath_local']}"
                    if doc.get("filepath_local")
                    else None
                ),
                "page_url": (
                    f"https://www.courtlistener.com{doc['absolute_url']}"
                    if doc.get("absolute_url") and not str(doc["absolute_url"]).startswith("http")
                    else doc.get("absolute_url")
                ),
            }
        )

    return {
        "search_type": search_type,
        "case_name": item.get("caseName") or item.get("caseNameFull") or item.get("case_name"),
        "docket_number": item.get("docketNumber") or item.get("docket_number"),
        "court": item.get("court"),
        "court_id": item.get("court_id"),
        "date_filed": item.get("dateFiled") or item.get("date_filed"),
        "docket_id": (
            item.get("docket_id")
            or (item.get("id") if search_type in ("r", "d") else None)
        ),
        "document_id": item.get("id") if search_type == "rd" else None,
        "description": item.get("description") or item.get("short_description"),
        "is_available": item.get("is_available"),
        "filepath_local": item.get("filepath_local"),
        "download_url": (
            f"{COURTLISTENER_STORAGE}/{item['filepath_local']}"
            if item.get("filepath_local") and item.get("is_available")
            else None
        ),
        "absolute_url": abs_url,
        "free_nested_documents": [d for d in free_nested if d.get("is_available")],
        "nested_document_count": len(free_nested),
    }


async def search_courtlistener(
    query: str,
    *,
    search_type: str = "r",
    free_only: bool = False,
    max_results: int = 10,
) -> dict[str, Any]:
    """Search CourtListener (case law / RECAP dockets / filings). Prefer type=r or rd for PACER/RECAP."""
    query = (query or "").strip()
    if not query:
        return {"error": "query is required"}
    search_type = (search_type or "r").strip().lower()
    if search_type not in {"o", "r", "rd", "d", "p", "oa"}:
        return {"error": "search_type must be one of: o, r, rd, d, p, oa"}
    max_results = max(1, min(int(max_results), 20))

    params = {"q": query, "type": search_type, "order_by": "score desc"}
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.get(COURTLISTENER_SEARCH, params=params, headers=_cl_headers())
        resp.raise_for_status()
        payload = resp.json()

    raw = payload.get("results") or []
    results: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        norm = _normalize_cl_result(item, search_type=search_type)
        if free_only:
            if search_type == "rd" and not (norm.get("is_available") and norm.get("filepath_local")):
                continue
            if search_type in {"r", "d"} and not norm.get("free_nested_documents"):
                continue
        results.append(norm)
        if len(results) >= max_results:
            break

    return {
        "source": "CourtListener / RECAP",
        "cost": "free (no PACER pull)",
        "query": query,
        "search_type": search_type,
        "free_only": free_only,
        "api_count": payload.get("count"),
        "returned": len(results),
        "results": results,
        "note": (
            "Only documents with is_available + filepath_local are downloadable at $0 via "
            f"{COURTLISTENER_STORAGE}/…. Docket-entry detail APIs may need COURTLISTENER_API_TOKEN "
            "(free signup). Never use this tool to purchase PACER pages."
        ),
    }


async def list_free_recap_documents(
    docket_id: int | str,
    *,
    max_results: int = 20,
) -> dict[str, Any]:
    """List RECAP filings for a docket that are free to download (is_available)."""
    try:
        did = int(str(docket_id).strip())
    except ValueError:
        return {"error": "docket_id must be an integer CourtListener docket id"}
    max_results = max(1, min(int(max_results), 50))

    params = {"q": f"docket_id:{did}", "type": "rd", "order_by": "score desc"}
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.get(COURTLISTENER_SEARCH, params=params, headers=_cl_headers())
        resp.raise_for_status()
        payload = resp.json()

    free: list[dict[str, Any]] = []
    unavailable = 0
    for item in payload.get("results") or []:
        if not isinstance(item, dict):
            continue
        if item.get("is_available") and item.get("filepath_local"):
            free.append(_normalize_cl_result(item, search_type="rd"))
        else:
            unavailable += 1
        if len(free) >= max_results:
            break

    return {
        "source": "CourtListener / RECAP",
        "cost": "free",
        "docket_id": did,
        "docket_url": f"https://www.courtlistener.com/docket/{did}/",
        "api_count": payload.get("count"),
        "free_returned": len(free),
        "unavailable_on_page": unavailable,
        "documents": free,
    }


async def resolve_free_recap_download(document_id: int | str) -> dict[str, Any]:
    """Resolve a CourtListener RECAP document id to a free storage URL when available."""
    try:
        doc_id = int(str(document_id).strip())
    except ValueError:
        return {"error": "document_id must be an integer"}

    # Search by id via type=rd; authenticated /api/rest/v4/recap-documents/{id}/ is preferred when token set
    token = (os.getenv("COURTLISTENER_API_TOKEN") or os.getenv("COURTLISTENER_TOKEN") or "").strip()
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        if token:
            resp = await client.get(
                f"https://www.courtlistener.com/api/rest/v4/recap-documents/{doc_id}/",
                headers=_cl_headers(),
            )
            if resp.status_code == 200:
                item = resp.json()
                fp = item.get("filepath_local")
                available = bool(item.get("is_available") and fp)
                return {
                    "source": "CourtListener / RECAP",
                    "cost": "free" if available else "not free via RECAP (would require PACER)",
                    "document_id": doc_id,
                    "is_available": available,
                    "description": item.get("description"),
                    "filepath_local": fp,
                    "download_url": f"{COURTLISTENER_STORAGE}/{fp}" if available else None,
                    "absolute_url": (
                        f"https://www.courtlistener.com{item['absolute_url']}"
                        if item.get("absolute_url") and not str(item["absolute_url"]).startswith("http")
                        else item.get("absolute_url")
                    ),
                }

        params = {"q": f"id:{doc_id}", "type": "rd"}
        resp = await client.get(COURTLISTENER_SEARCH, params=params, headers=_cl_headers())
        resp.raise_for_status()
        payload = resp.json()
        results = payload.get("results") or []
        if not results:
            # Fallback: quote-less id search often fails; try exact
            params = {"q": str(doc_id), "type": "rd"}
            resp = await client.get(COURTLISTENER_SEARCH, params=params, headers=_cl_headers())
            resp.raise_for_status()
            payload = resp.json()
            results = [
                r
                for r in (payload.get("results") or [])
                if isinstance(r, dict) and r.get("id") == doc_id
            ]

    if not results:
        return {
            "error": f"No RECAP document found for id={doc_id}",
            "hint": "Set COURTLISTENER_API_TOKEN for direct document lookup.",
        }

    item = results[0]
    norm = _normalize_cl_result(item, search_type="rd")
    available = bool(norm.get("is_available") and norm.get("filepath_local"))
    return {
        "source": "CourtListener / RECAP",
        "cost": "free" if available else "not free via RECAP (would require PACER)",
        "document_id": doc_id,
        "is_available": available,
        "description": norm.get("description"),
        "filepath_local": norm.get("filepath_local"),
        "download_url": norm.get("download_url"),
        "absolute_url": norm.get("absolute_url"),
        "case_name": norm.get("case_name"),
        "docket_id": norm.get("docket_id"),
    }

