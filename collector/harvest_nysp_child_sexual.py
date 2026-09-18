#!/usr/bin/env python3
"""Harvest troopers.ny.gov /news URLs from NY State Google CSE (child sexual inurl)."""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse

import requests

SEARCH_BASE = (
    "https://search.its.ny.gov/search/search.html?"
    + urlencode(
        {
            "btnG": "Search",
            "client": "default_frontend",
            "output": "xml_no_dtd",
            "proxystylesheet": "default_frontend",
            "ulang": "en",
            "sort": "date:D:L:d1",
            "entqr": "3",
            "entqrm": "0",
            "wc": "200",
            "wc_mc": "1",
            "oe": "UTF-8",
            "ie": "UTF-8",
            "ud": "1",
            "site": "default_collection",
            "q": "child sexual inurl:troopers.ny.gov",
        }
    )
)

_TROOPERS_RE = re.compile(
    r"https?://(?:www\.)?troopers\.ny\.gov(/news/[a-z0-9\-]+)",
    re.I,
)


def _clean_troopers_url(raw: str) -> str | None:
    s = raw.strip().rstrip(".,;)")
    if "](" in s:
        s = s.split("](", 1)[0]
    if not s.startswith("http"):
        return None
    m = _TROOPERS_RE.search(s)
    if not m:
        return None
    path = m.group(1).rstrip("/").lower()
    if len(path) < 12 or path == "/news":
        return None
    return f"https://troopers.ny.gov{path}"


def _urls_from_jina_body(text: str, seen: set[str], out: list[str]) -> int:
    page_new = 0
    for m in re.finditer(r"https?://(?:www\.)?troopers\.ny\.gov/news/[a-z0-9\-]+", text, re.I):
        u = _clean_troopers_url(m.group(0))
        if u and u not in seen:
            seen.add(u)
            out.append(u)
            page_new += 1
    return page_new


def harvest_cse(*, max_pages: int, delay: float, seen: set[str], out: list[str]) -> None:
    """NY State search (Jina); CSE pagination often repeats — kept for overlap with newsroom."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; CaseLinker/1.0)"}
    for page in range(1, max_pages + 1):
        search_url = f"{SEARCH_BASE}&gsc.page={page}"
        jina = "https://r.jina.ai/" + search_url
        print(f"  [cse {page}] …", file=sys.stderr)
        try:
            r = requests.get(jina, headers=headers, timeout=90)
        except Exception as e:
            print(f"  [cse error] {e}", file=sys.stderr)
            break
        if r.status_code != 200:
            break
        n = _urls_from_jina_body(r.text, seen, out)
        print(f"    -> {n} new (total {len(out)})", file=sys.stderr)
        if n == 0 and page > 1:
            break
        time.sleep(delay)


def harvest_newsroom(*, max_pages: int, delay: float, seen: set[str], out: list[str]) -> None:
    """Drupal newsroom keyword=child sexual (primary harvest; paginate with &page=N)."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; CaseLinker/1.0)"}
    empty_streak = 0
    for page in range(0, max_pages):
        base = "https://troopers.ny.gov/nysp-newsroom?keyword=child%20sexual"
        if page:
            base += f"&page={page}"
        jina = "https://r.jina.ai/" + base
        print(f"  [newsroom {page}] …", file=sys.stderr)
        try:
            r = requests.get(jina, headers=headers, timeout=90)
        except Exception as e:
            print(f"  [newsroom error] {e}", file=sys.stderr)
            break
        if r.status_code != 200:
            break
        n = _urls_from_jina_body(r.text, seen, out)
        print(f"    -> {n} new (total {len(out)})", file=sys.stderr)
        if n == 0:
            empty_streak += 1
            if empty_streak >= 2:
                break
        else:
            empty_streak = 0
        time.sleep(delay)


def harvest(*, max_pages: int, delay: float) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    harvest_cse(max_pages=min(5, max_pages), delay=delay, seen=seen, out=out)
    harvest_newsroom(max_pages=max_pages, delay=delay, seen=seen, out=out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--max-pages", type=int, default=50)
    ap.add_argument("--delay", type=float, default=1.2)
    args = ap.parse_args()

    urls = harvest(max_pages=args.max_pages, delay=args.delay)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(urls) + ("\n" if urls else ""), encoding="utf-8")
    print(f"Total URLs: {len(urls)}", file=sys.stderr)
    print(f"Saved -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
