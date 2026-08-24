#!/usr/bin/env python3
"""
Bridge between a source url-list and scrape_pdf.py that resolves justice.gov URLs
via the DOJ press-release API instead of scraping the (Akamai-gated) live page.

For each URL in the input file:
  - justice.gov -> query https://www.justice.gov/api/v1/press_releases.json,
    match the API record whose `url` slug equals the input URL's slug, strip the
    HTML `body` field into clean paragraphs, and emit a fully "resolved" record.
  - anything else -> pass the URL through unchanged for scrape_pdf.py's existing
    fetch/extract pipeline (no behavior change for state AG / other sources).

Output is a JSON list scrape_pdf.py consumes via --doj-file, so the final
merged PDF looks the same regardless of source:
  {"source_url": ..., "mode": "resolved", "title": ..., "byline": ...,
   "pub_date": "YYYY-MM-DD", "body": "...", "agency": ..., "uuid": ...}
  {"source_url": ..., "mode": "scrape"}

deps: pip install requests beautifulsoup4
usage:
    python3 scrape_doj.py --url-file sources/urls.txt --out sources/urls_resolved.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("pip install requests beautifulsoup4")

DEFAULT_URL_FILE = Path.cwd() / "sources" / "urls.txt"
DEFAULT_OUT_FILE = Path.cwd() / "sources" / "urls_resolved.json"

DOJ_API_URL = "https://www.justice.gov/api/v1/press_releases.json"
DOJ_API_PAGESIZE = 50
DOJ_API_MAX_PAGES = 6  # 6 * 50 = 300 candidate records per query, plenty for one title search
DOJ_API_MIN_DELAY = 0.3  # docs: 4 req/s max; stay well under that

DOJ_STOPWORDS = {
    "a", "an", "the", "of", "to", "in", "on", "at", "by", "for", "and", "or",
    "with", "from", "into", "his", "her", "its", "their", "s",
}

MIN_BODY_CHARS = 80


def load_urls(path: Path) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip().split("#", 1)[0].strip()
        if not line or not line.startswith("http"):
            continue
        key = line.rstrip("/")
        if key not in seen:
            seen.add(key)
            urls.append(line)
    return urls


def is_justice_gov_url(url: str) -> bool:
    netloc = urlparse(url).netloc.lower()
    return netloc in ("www.justice.gov", "justice.gov")


def _url_slug(url: str) -> str:
    return url.rstrip("/").split("/")[-1].lower()


def _slug_query_terms(slug: str, *, max_terms: int = 6) -> str:
    """Turn a URL slug into a substring query likely to appear in the article title."""
    words = [w for w in slug.split("-") if len(w) > 2 and w not in DOJ_STOPWORDS]
    return " ".join(words[:max_terms])


_last_doj_call = 0.0


def _doj_api_get(params: dict) -> dict:
    global _last_doj_call
    wait = DOJ_API_MIN_DELAY - (time.monotonic() - _last_doj_call)
    if wait > 0:
        time.sleep(wait)
    r = requests.get(DOJ_API_URL, params=params, timeout=30)
    _last_doj_call = time.monotonic()
    r.raise_for_status()
    return r.json()


def find_doj_record(url: str) -> dict | None:
    """Search the DOJ API for the record whose `url` field matches this URL's slug exactly."""
    target_slug = _url_slug(url)
    query = _slug_query_terms(target_slug)
    if not query:
        return None
    for page in range(DOJ_API_MAX_PAGES):
        data = _doj_api_get(
            {"parameters[title]": query, "pagesize": DOJ_API_PAGESIZE, "page": page}
        )
        results = data.get("results") or []
        for rec in results:
            if _url_slug(rec.get("url", "")) == target_slug:
                return rec
        total = int(data.get("metadata", {}).get("resultset", {}).get("count", 0))
        if (page + 1) * DOJ_API_PAGESIZE >= total or not results:
            break
    return None


def clean_doj_api_body(html_body: str) -> str:
    """
    DOJ API `body` is raw HTML (<p> blocks, &nbsp;, embedded <a>/<br>, and sometimes an
    addendum <table> of defendants/charges/status). Strip to clean paragraph-per-block
    text; each table row becomes its own block (pipe-joined cells) so it isn't dropped.
    """
    soup = BeautifulSoup(html_body or "", "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    blocks: list[str] = []
    for el in soup.find_all(["p", "tr"]):
        if el.name == "tr":
            if el.find_parent("tr"):
                continue
            cells = [
                re.sub(r"\s+", " ", c.get_text(" ", strip=True)).strip()
                for c in el.find_all(["td", "th"])
            ]
            cells = [c for c in cells if c]
            if cells:
                blocks.append(" | ".join(cells))
            continue
        if el.find_parent("table"):
            continue
        text = re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()
        if text:
            blocks.append(text)
    if not blocks:
        text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n", strip=True))
        return text.strip()
    return "\n\n".join(blocks)


def _epoch_to_date(raw: str | int | None) -> date | None:
    if raw is None or raw == "":
        return None
    try:
        return datetime.fromtimestamp(int(raw), tz=timezone.utc).date()
    except (ValueError, OSError):
        return None


def resolve_justice_gov_url(url: str) -> dict:
    rec = find_doj_record(url)
    if not rec:
        print(f"    [doj] no API match for {url}", file=sys.stderr)
        return {"source_url": url, "mode": "unresolved"}

    body = clean_doj_api_body(rec.get("body", ""))
    if len(body) < MIN_BODY_CHARS:
        print(f"    [doj] body too thin after clean: {url}", file=sys.stderr)
        return {"source_url": url, "mode": "unresolved"}

    pub_date = _epoch_to_date(rec.get("date"))
    components = rec.get("component") or []
    agency = components[0]["name"] if components and isinstance(components[0], dict) else ""

    return {
        "source_url": url,
        "mode": "resolved",
        "title": (rec.get("title") or "").strip(),
        "byline": pub_date.strftime("%B %d, %Y") if pub_date else "",
        "pub_date": pub_date.isoformat() if pub_date else None,
        "body": body,
        "agency": agency,
        "uuid": rec.get("uuid", ""),
    }


def build_records(urls: list[str]) -> list[dict]:
    records: list[dict] = []
    for i, url in enumerate(urls, start=1):
        print(f"  [{i}/{len(urls)}] {url}")
        if is_justice_gov_url(url):
            records.append(resolve_justice_gov_url(url))
        else:
            records.append({"source_url": url, "mode": "scrape"})
    return records


def main():
    ap = argparse.ArgumentParser(
        description="Resolve justice.gov URLs via the DOJ API; pass other URLs through unchanged.",
    )
    ap.add_argument("--url-file", type=Path, default=DEFAULT_URL_FILE)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT_FILE)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    if not args.url_file.is_file():
        sys.exit(f"URL file not found: {args.url_file}")

    urls = load_urls(args.url_file)
    if args.limit:
        urls = urls[: args.limit]

    print(f"\n{'='*55}")
    print(f"  URL file  : {args.url_file}")
    print(f"  Total URLs: {len(urls)}")
    print(f"  Output    : {args.out}")
    print(f"{'='*55}\n")

    records = build_records(urls)

    resolved = sum(1 for r in records if r["mode"] == "resolved")
    scrape = sum(1 for r in records if r["mode"] == "scrape")
    unresolved = sum(1 for r in records if r["mode"] == "unresolved")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(records, indent=2), encoding="utf-8")

    print(f"\n  Resolved (DOJ API): {resolved}  |  Pass-through (scrape): {scrape}  |  Unresolved: {unresolved}")
    print(f"  Wrote {args.out}\n")


if __name__ == "__main__":
    main()
