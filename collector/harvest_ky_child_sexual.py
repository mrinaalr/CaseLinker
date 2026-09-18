#!/usr/bin/env python3
"""Harvest KY SP news URLs via WordPress REST (site is Next.js; HTML has no links)."""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

REPO = Path(__file__).resolve().parents[1]
API = "https://wp.kentuckystatepolice.ky.gov/wp-json/wp/v2/posts"
SEARCH = "child sexual"
PER_PAGE = 100


def wp_to_public_url(link: str, slug: str) -> str:
    p = urlparse(link)
    host = "www.kentuckystatepolice.ky.gov"
    path = p.path or f"/news/{slug}/"
    if not path.startswith("/news/"):
        path = f"/news/{slug}/"
    return f"https://{host}{path.rstrip('/')}/"


def harvest() -> list[str]:
    out: list[str] = []
    page = 1
    while True:
        r = requests.get(
            API,
            params={"search": SEARCH, "per_page": PER_PAGE, "page": page},
            timeout=60,
        )
        r.raise_for_status()
        posts = r.json()
        if not posts:
            break
        for p in posts:
            out.append(wp_to_public_url(p.get("link", ""), p.get("slug", "")))
        total_pages = int(r.headers.get("X-WP-TotalPages", 1))
        print(f"  page {page}/{total_pages}: +{len(posts)} (total {len(out)})", file=sys.stderr)
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.3)
    # dedupe preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for u in out:
        n = u.lower().rstrip("/")
        if n not in seen:
            seen.add(n)
            uniq.append(u)
    return uniq


def main() -> None:
    dest = REPO / "collector/state/ky_sp_child_sexual_harvest.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    urls = harvest()
    dest.write_text("\n".join(urls) + "\n", encoding="utf-8")
    print(f"Wrote {len(urls)} URLs -> {dest}")


if __name__ == "__main__":
    main()
