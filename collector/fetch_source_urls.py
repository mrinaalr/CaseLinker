#!/usr/bin/env python3
"""
Collect http(s) links from one or more HTML pages.

Give a page URL (or a paginated URL template), resolve all anchor hrefs to
absolute URLs, optionally filter by host/path/substrings, and write a
deduplicated list for build_press_pdf.py.

Examples
--------
Single listing page::

    python3 fetch_source_urls.py --url https://example.org/reports \\
        --same-host --path-prefix /cases/ -o cases.txt

Drupal-style search (e.g. Vermont AG), stop when no results text appears::

    python3 fetch_source_urls.py \\
        --url-template 'https://ago.vermont.gov/search/node?keys=child&page={page}' \\
        --page-range 0:40 \\
        --same-host --path-prefix /blog/ \\
        --require-any-from patterns/vermont_icac_require.txt \\
        --exclude-from patterns/vermont_icac_exclude.txt \\
        --stop-if-text 'your search yielded no results' \\
        -o vermont_icac_urls.txt

Squarespace Universal site search **search page** URL (Anchorage PD, etc.).
The listing HTML only exposes a first slice; pagination uses GET
``/api/search/GeneralSearch?q=…&p=…``::

    python3 collector/fetch_source_urls.py \\
        --squarespace-search-page 'https://www.anchoragepolice.com/search?q=child' \\
        --path-prefix /news/ \\
        -o collector/anchorage_pd_child_search_urls.txt

deps: pip install requests beautifulsoup4

WordPress REST (sites whose HTML listing is empty / Next.js)::

    python3 collector/fetch_source_urls.py \\
        --wordpress-rest 'https://wp.kentuckystatepolice.ky.gov/wp-json/wp/v2/posts' \\
        --wp-search 'child sexual' \\
        --wp-public-host www.kentuckystatepolice.ky.gov \\
        --wp-path-prefix /news/ \\
        -o collector/state/ky_sp_urls.txt
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from urllib.parse import parse_qs, parse_qsl, quote, urlencode, urljoin, urlparse, urlunparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("pip install requests beautifulsoup4")

DEFAULT_DELAY = 1.2
DEFAULT_TIMEOUT = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/",
}


def _read_patterns(path: str | None) -> list[str]:
    if not path:
        return []
    lines: list[str] = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.strip()
            if s and not s.startswith("#"):
                lines.append(s)
    return lines


def fetch(
    url: str, timeout: int, *, verify: bool = True, retries: int = 4
) -> tuple[str | None, int]:
    last_status = 0
    for attempt in range(retries):
        try:
            r = requests.get(
                url,
                headers=HEADERS,
                timeout=timeout,
                allow_redirects=True,
                verify=verify,
            )
            if r.status_code == 429 and attempt + 1 < retries:
                wait = min(60, 5 * (2**attempt))
                print(f"  [429] waiting {wait}s …", file=sys.stderr)
                time.sleep(wait)
                continue
            return r.text, r.status_code
        except Exception as e:
            if attempt + 1 < retries:
                time.sleep(min(30, 2 * (attempt + 1)))
                continue
            print(f"  [error] {url}: {e}", file=sys.stderr)
            return None, 0
    return None, last_status


def _host(url: str) -> str:
    return urlparse(url).netloc.lower()


def _path(url: str) -> str:
    return urlparse(url).path or "/"


def collect_from_html(
    html: str,
    page_url: str,
    *,
    same_host: bool,
    extra_hosts: frozenset[str] | None,
    path_prefix: str | None,
    exclude_substrings: list[str],
    require_any_substrings: list[str],
    https_only: bool,
) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    base_host = _host(page_url)
    allowed: frozenset[str] | None = None
    if same_host:
        allowed = frozenset({base_host, *(extra_hosts or ())})
    path_prefix_l = path_prefix.lower() if path_prefix else None
    exclude_l = [p.lower() for p in exclude_substrings]
    require_l = [p.lower() for p in require_any_substrings]

    out: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        raw = a["href"].strip()
        if not raw or raw.startswith(("#", "mailto:", "javascript:")):
            continue
        abs_url = urljoin(page_url, raw)
        p = urlparse(abs_url)
        if https_only:
            if p.scheme != "https":
                continue
        elif p.scheme not in ("http", "https"):
            continue

        abs_url = abs_url.split("#", 1)[0]
        host = _host(abs_url)
        if allowed is not None and host not in allowed:
            continue
        if path_prefix_l and not _path(abs_url).lower().startswith(path_prefix_l):
            continue
        lower = abs_url.lower()
        if any(ex in lower for ex in exclude_l):
            continue
        if require_l and not any(req in lower for req in require_l):
            continue
        if abs_url not in seen:
            seen.add(abs_url)
            out.append(abs_url)
    return out


def _normalize_regex_extracted_url(raw: str) -> str | None:
    """Trim JSON/HTML junk from a URL substring (e.g. Search.gov embedded links)."""
    s = raw.strip()
    for sep in ("&quot;", "&quot", "\\u0026quot;", "%22", "\\", '"', "'", "<", ">"):
        if sep in s:
            s = s.split(sep)[0]
    s = re.sub(r"\)\S*$", "", s)
    s = s.strip().rstrip(".,);]}")
    if not s.startswith("http"):
        return None
    s = s.split("#", 1)[0]
    if len(s) > 500:
        s = s[:500]
    return s or None


def collect_from_regex(
    html: str,
    pattern: re.Pattern[str],
    *,
    path_prefix: str | None,
    exclude_substrings: list[str],
    require_any_substrings: list[str],
    https_only: bool,
) -> list[str]:
    """Find URL-shaped strings in raw HTML (e.g. JSON-LD / Search.gov results)."""
    path_prefix_l = path_prefix.lower() if path_prefix else None
    exclude_l = [p.lower() for p in exclude_substrings]
    require_l = [p.lower() for p in require_any_substrings]
    out: list[str] = []
    seen: set[str] = set()
    for m in pattern.finditer(html or ""):
        raw = m.group(0)
        abs_url = _normalize_regex_extracted_url(raw)
        if not abs_url:
            continue
        p = urlparse(abs_url)
        if https_only and p.scheme != "https":
            continue
        if not https_only and p.scheme not in ("http", "https"):
            continue
        if path_prefix_l and not _path(abs_url).lower().startswith(path_prefix_l):
            continue
        lower = abs_url.lower()
        if any(ex in lower for ex in exclude_l):
            continue
        if require_l and not any(req in lower for req in require_l):
            continue
        if abs_url not in seen:
            seen.add(abs_url)
            out.append(abs_url)
    return out


def parse_page_range(spec: str) -> range:
    """'0:29' -> inclusive 0..29 (step 1). '1:91:10' -> 1, 11, …, 91 (Delaware search start_rank)."""
    if ":" not in spec:
        raise argparse.ArgumentTypeError(
            "page-range must look like START:END or START:END:STEP (e.g. 0:29 or 1:91:10)"
        )
    parts = [p.strip() for p in spec.split(":")]
    if len(parts) == 2:
        start, end = int(parts[0]), int(parts[1])
        step = 1
    elif len(parts) == 3:
        start, end, step = int(parts[0]), int(parts[1]), int(parts[2])
        if step <= 0:
            raise argparse.ArgumentTypeError("STEP must be positive")
    else:
        raise argparse.ArgumentTypeError("page-range: use START:END or START:END:STEP")
    if end < start:
        raise argparse.ArgumentTypeError("END must be >= START")
    return range(start, end + 1, step)


def iter_page_urls(args: argparse.Namespace) -> list[str]:
    urls: list[str] = []
    for u in args.url or []:
        urls.append(u)
    if args.url_template:
        for n in args.page_range:
            urls.append(args.url_template.format(page=n, n=n))
    if not urls:
        raise SystemExit("Provide --url and/or --url-template with --page-range.")
    return urls


def _filter_abs_url(
    abs_url: str,
    *,
    path_prefix_l: str | None,
    exclude_l: list[str],
    require_l: list[str],
    https_only: bool,
) -> bool:
    """Return True if the URL passes path / substring / scheme filters."""
    abs_url = abs_url.split("#", 1)[0]
    p = urlparse(abs_url)
    if https_only:
        if p.scheme != "https":
            return False
    elif p.scheme not in ("http", "https"):
        return False
    if path_prefix_l and not _path(abs_url).lower().startswith(path_prefix_l):
        return False
    lower = abs_url.lower()
    if any(ex in lower for ex in exclude_l):
        return False
    if require_l and not any(req in lower for req in require_l):
        return False
    return True


def collect_squarespace_general_search_urls(
    search_page_url: str,
    *,
    timeout: int,
    verify: bool,
    delay: float,
    path_prefix: str | None,
    exclude_substrings: list[str],
    require_any_substrings: list[str],
    https_only: bool,
) -> list[str]:
    """
    Walk ``/api/search/GeneralSearch?q=…&p=…`` pages until no items remain.

    ``search_page_url`` must carry the query string Squarespace expects (typically ``q=``).
    """
    parsed = urlparse(search_page_url.strip())
    if not parsed.scheme or not parsed.netloc:
        raise SystemExit("--squarespace-search-page must be a full http(s) URL.")
    qs = parse_qs(parsed.query or "")
    q_vals = qs.get("q") or qs.get("query") or qs.get("keyword")
    if not q_vals or not q_vals[0].strip():
        raise SystemExit("--squarespace-search-page must include a non-empty ``q``, ``query``, or ``keyword`` param.")
    q_str = q_vals[0].strip()
    origin = f"{parsed.scheme}://{parsed.netloc}"
    path_prefix_l = path_prefix.lower() if path_prefix else None
    exclude_l = [x.lower() for x in exclude_substrings]
    require_l = [x.lower() for x in require_any_substrings]

    out: list[str] = []
    seen: set[str] = set()
    page_idx = 0
    last_total = 0

    while True:
        api = f"{origin}/api/search/GeneralSearch?q={quote(q_str)}&p={page_idx}"
        print(f"  [sqs] GET p={page_idx} ({api})", file=sys.stderr)
        body, status = fetch(api, timeout, verify=verify)
        if not body or status != 200:
            print(f"  [stop] HTTP {status}", file=sys.stderr)
            break
        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            print(f"  [stop] JSON decode: {e}", file=sys.stderr)
            break
        if data.get("serviceError"):
            print("  [stop] serviceError in JSON", file=sys.stderr)
            break
        items = data.get("items")
        if not isinstance(items, list):
            items = []
        tc = data.get("totalCount")
        if isinstance(tc, int):
            last_total = tc

        batch_n = 0
        for it in items:
            if not isinstance(it, dict):
                continue
            rel = it.get("itemUrl")
            if not rel or not isinstance(rel, str):
                continue
            rel = rel.strip()
            if not rel:
                continue
            abs_u = urljoin(origin + "/", rel.lstrip("/"))
            if abs_u not in seen and _filter_abs_url(
                abs_u,
                path_prefix_l=path_prefix_l,
                exclude_l=exclude_l,
                require_l=require_l,
                https_only=https_only,
            ):
                seen.add(abs_u)
                out.append(abs_u)
                batch_n += 1

        print(f"    -> raw items {len(items)}, new urls {batch_n}, total collected {len(out)}", file=sys.stderr)

        page_idx += 1
        if not items:
            break
        if last_total > 0 and len(out) >= last_total:
            break
        time.sleep(delay)

    return out


def _cse_host_patterns(netloc: str) -> tuple[re.Pattern[str], re.Pattern[str]]:
    host = netloc.lower().lstrip("www.")
    host_esc = re.escape(host)
    crumb = re.compile(rf"{host_esc}\s*›\s*([^\n]+)", re.I)
    abs_url = re.compile(rf"https?://(?:www\.)?{host_esc}[/\S]+", re.I)
    return crumb, abs_url


def _resolve_article_id_in_sitemap(path: str, sitemap_urls: list[str]) -> str | None:
    m = re.search(r"/Article/(\d+)", path, re.I)
    if not m:
        return None
    aid = m.group(1)
    hits = [u for u in sitemap_urls if f"/Article/{aid}/" in u or u.rstrip("/").endswith(f"/Article/{aid}")]
    if not hits:
        hits = [u for u in sitemap_urls if f"/{aid}/" in u]
    return sorted(hits, key=len)[0] if hits else None


def _load_sitemap_urls(sitemap_url: str, timeout: int, *, verify: bool) -> list[str]:
    body, status = fetch(sitemap_url, timeout, verify=verify)
    if not body or status != 200:
        return []
    return re.findall(r"<loc>([^<]+)</loc>", body)


def _resolve_cse_crumb_to_url(crumb: str, sitemap_urls: list[str]) -> str | None:
    """Map a Google CSE breadcrumb trail to a canonical press-release URL via sitemap."""
    crumb = crumb.strip().lower()
    if crumb.startswith("investigations"):
        return None
    if "behind-the-shades" in crumb:
        return None
    if "releases" not in crumb and "press" not in crumb and "newsroom" not in crumb:
        return None

    parts = [p.strip() for p in crumb.split("›")]
    for i, part in enumerate(parts):
        low = part.lower().rstrip(".")
        if low in ("local-media-release", "national-media-release"):
            slug = (parts[i + 1] if i + 1 < len(parts) else "").strip().rstrip(".")
            if slug and len(slug) >= 6:
                return f"https://www.cbp.gov/newsroom/{low}/{slug}"
    slug_prefix = ""
    year_month = ""

    if parts and re.fullmatch(r"\d{4}/\d{2}", parts[0]):
        year_month = parts[0]
        slug_prefix = (parts[1] if len(parts) > 1 else "").rstrip(".")
    else:
        for i, part in enumerate(parts):
            if part in ("press", "newsroom") and i + 2 < len(parts):
                if re.fullmatch(r"\d{4}/\d{2}", parts[i + 2]):
                    year_month = parts[i + 2]
                    slug_prefix = (parts[i + 3] if i + 3 < len(parts) else "").rstrip(".")
                    break
            if part == "releases" and i + 2 < len(parts):
                if re.fullmatch(r"\d{4}/\d{2}", parts[i + 1]):
                    year_month = parts[i + 1]
                    slug_prefix = (parts[i + 2] if i + 2 < len(parts) else "").rstrip(".")
                    break

    if not slug_prefix or len(slug_prefix) < 6:
        return None

    candidates = [
        u
        for u in sitemap_urls
        if slug_prefix in u.lower()
        and (not year_month or f"/{year_month}/" in u)
        and (
            "/press/releases/" in u
            or "/newsroom/releases/" in u
            or "/newsroom/national-media-release/" in u
            or "/newsroom/local-media-release/" in u
        )
    ]
    if not candidates:
        if "child" in crumb or "sexual" in crumb:
            last = (parts[-1] if parts else "").strip().rstrip(".")
            if len(last) >= 10:
                return f"https://www.cbp.gov/newsroom/local-media-release/{last}"
        return None
    return sorted(candidates, key=len)[0]


def _google_cse_page_url(search_page_url: str, page: int) -> str:
    """
    Set ``gsc.page`` for Google CSE listings.

    Jina Reader often ignores URL fragments, so CSE params are merged into the
    query string and the fragment is dropped.
    """
    u = search_page_url.strip()
    parsed = urlparse(u)
    qs = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if parsed.fragment and "=" in parsed.fragment:
        qs.update(parse_qsl(parsed.fragment.replace("&", "&"), keep_blank_values=True))
    qs["gsc.page"] = str(page)
    if "gsc.q" not in qs and "query" in qs:
        qs.setdefault("gsc.q", qs["query"].replace("+", " "))
    return urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, "", urlencode(qs, doseq=True), "")
    )


def _collect_cbp_cse_article_urls(body: str, origin: str) -> list[str]:
    """Resolve truncated CBP Google CSE hits (Jina markdown with ``...`` paths)."""
    cleaned = re.sub(r"\*+", "", body or "")
    out: list[str] = []
    seen: set[str] = set()

    def _add(url: str) -> None:
        u = url.split("#", 1)[0].rstrip("/")
        slug = u.rsplit("/", 1)[-1]
        if len(slug) < 20:
            return
        if u not in seen and "/newsroom/" in u:
            seen.add(u)
            out.append(u)

    for m in re.finditer(
        r"https?://(?:www\.)?cbp\.gov/newsroom/(local|national)-media-release/[a-z0-9\-]{20,}",
        cleaned,
        re.I,
    ):
        _add(m.group(0))

    for m in re.finditer(
        r"/newsroom/(local|national)-media-release/([a-z0-9][a-z0-9\-]{19,})",
        cleaned,
        re.I,
    ):
        _add(f"{origin}/newsroom/{m.group(1).lower()}/{m.group(2).lower()}")

    for m in re.finditer(
        r"newsroom\s*›\s*(local-media-release|national-media-release)\s*›\s*"
        r"([a-z0-9][a-z0-9\-]{5,})",
        cleaned,
        re.I,
    ):
        slug = m.group(2).lower().rstrip(".")
        prefix = slug[:40]
        expanded = re.findall(
            rf"(?:local|national)-media-release/({re.escape(prefix)}[a-z0-9\-]{{0,80}})",
            cleaned.lower(),
        )
        if expanded:
            slug = max(expanded, key=len).rstrip("-")
        _add(f"{origin}/newsroom/{m.group(1).lower()}/{slug}")

    for frag in re.findall(r"cbp\.gov/\.\.\.([^\s\)\]\"']+)", cleaned, re.I):
        frag = frag.rstrip(".").strip("/")
        if not frag:
            continue
        low = frag.lower()
        if "local..." in low:
            slug = re.sub(r".*local\.{3}/?", "", frag, flags=re.I).strip("/")
            if slug:
                _add(f"{origin}/newsroom/local-media-release/{slug}")
            continue
        if "national..." in low:
            slug = re.sub(r".*national\.{3}/?", "", frag, flags=re.I).strip("/")
            if slug:
                _add(f"{origin}/newsroom/national-media-release/{slug}")
            continue
        slug = frag.split("/")[-1]
        if len(slug) < 8:
            continue
        prefix = slug[:40]
        expanded = re.findall(
            rf"(?:local|national)-media-release/({re.escape(prefix)}[a-z0-9\-]{{0,80}})",
            cleaned.lower(),
        )
        if expanded:
            slug = max(expanded, key=len).rstrip("-")
        kind = "national-media-release"
        if not any(
            x in slug
            for x in (
                "illegal-alien",
                "national",
                "border-wide",
                "cbp-announces",
            )
        ):
            kind = "local-media-release"
        _add(f"{origin}/newsroom/{kind}/{slug}")

    return out


def collect_google_cse_search_urls(
    search_page_url: str,
    *,
    timeout: int,
    verify: bool,
    path_prefix: str | None,
    exclude_substrings: list[str],
    require_any_substrings: list[str],
    https_only: bool,
    sitemap_url: str | None,
    max_results: int | None,
) -> list[str]:
    """
    Harvest Google Programmable Search (CSE) results rendered on a listing page.

    Static HTML from the host usually omits CSE hits; this fetches via Jina Reader
  (``https://r.jina.ai/{search_page_url}``), parses breadcrumb trails and absolute
  links, and resolves truncated slugs against the site sitemap when provided.
    """
    parsed = urlparse(search_page_url.strip())
    if not parsed.scheme or not parsed.netloc:
        raise SystemExit("--google-cse-search-page must be a full http(s) URL.")

    fetch_url = _google_cse_page_url(search_page_url, 1)
    if re.search(r"gsc\.page=(\d+)", search_page_url, re.I):
        m_pg = re.search(r"gsc\.page=(\d+)", search_page_url, re.I)
        if m_pg:
            fetch_url = _google_cse_page_url(search_page_url, int(m_pg.group(1)))
    jina_url = "https://r.jina.ai/" + fetch_url
    print(f"  [cse] Jina GET {jina_url}", file=sys.stderr)
    body, status = fetch(jina_url, max(timeout, 60), verify=verify)
    if not body or status not in (200, 0):
        print(f"  [stop] Jina HTTP {status}", file=sys.stderr)
        return []

    body = re.sub(r"\*+", "", body)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    sitemap_urls: list[str] = []
    if sitemap_url:
        print(f"  [cse] sitemap {sitemap_url}", file=sys.stderr)
        sitemap_urls = _load_sitemap_urls(sitemap_url, timeout, verify=verify)

    path_prefix_l = path_prefix.lower() if path_prefix else None
    exclude_l = [x.lower() for x in exclude_substrings]
    require_l = [x.lower() for x in require_any_substrings]

    out: list[str] = []
    seen: set[str] = set()

    def _keep(abs_url: str) -> bool:
        low = abs_url.lower()
        if "/search?" in low or low.rstrip("/").endswith("/search"):
            return False
        return _filter_abs_url(
            abs_url,
            path_prefix_l=path_prefix_l,
            exclude_l=exclude_l,
            require_l=require_l,
            https_only=https_only,
        )

    crumb_re, abs_url_re = _cse_host_patterns(parsed.netloc)
    host_clean = parsed.netloc.lower().lstrip("www.")
    path_re = re.compile(
        rf"(?:https?://(?:www\.)?)?{re.escape(host_clean)}(/[^\s\)\]\"']+)",
        re.I,
    )

    for crumb in crumb_re.findall(body):
        resolved = _resolve_cse_crumb_to_url(crumb, sitemap_urls)
        if resolved and resolved not in seen and _keep(resolved):
            seen.add(resolved)
            out.append(resolved)
            if max_results and len(out) >= max_results:
                return out

    for raw in abs_url_re.findall(body):
        abs_u = _normalize_regex_extracted_url(raw)
        if not abs_u or abs_u in seen:
            continue
        if "..." in abs_u and sitemap_urls:
            path = urlparse(abs_u).path
            resolved = _resolve_article_id_in_sitemap(path, sitemap_urls)
            if resolved:
                abs_u = resolved
            else:
                continue
        elif sitemap_urls:
            slug = abs_u.rstrip("/").split("/")[-1]
            if len(slug) < 12:
                matches = [u for u in sitemap_urls if slug in u]
                if matches:
                    abs_u = sorted(matches, key=len)[0]
        if _keep(abs_u):
            seen.add(abs_u)
            out.append(abs_u)
            if max_results and len(out) >= max_results:
                return out

    for path_frag in path_re.findall(body):
        if "..." in path_frag:
            if sitemap_urls:
                resolved = _resolve_article_id_in_sitemap(path_frag, sitemap_urls)
                if resolved:
                    abs_u = resolved
                else:
                    continue
            else:
                continue
        else:
            abs_u = f"{origin}{path_frag.split('...')[0].rstrip('.')}"
        if abs_u not in seen and _keep(abs_u):
            seen.add(abs_u)
            out.append(abs_u)
            if max_results and len(out) >= max_results:
                return out

    if "cbp.gov" in parsed.netloc.lower():
        for abs_u in _collect_cbp_cse_article_urls(body, origin):
            if abs_u not in seen and _keep(abs_u):
                seen.add(abs_u)
                out.append(abs_u)
                if max_results and len(out) >= max_results:
                    return out

    return out


_ICE_RELEASE_PATH_RE = re.compile(
    r"www\.ice\.gov(/news/releases/[a-z0-9\-/]+)",
    re.I,
)


def _usa_host_path_re(host: str) -> re.Pattern[str]:
    """Match ``host`` plus a path segment in Jina search markdown (may truncate with ``...``)."""
    host_esc = re.escape(host.lower().lstrip("."))
    return re.compile(
        rf"(?:https?://)?(?:www\.)?{host_esc}(/[a-z0-9\-._%/]+)",
        re.I,
    )


def _load_ice_release_sitemap(timeout: int, *, verify: bool) -> list[str]:
    """All ``/news/releases/`` URLs from paginated ice.gov Drupal sitemap."""
    index_url = "https://www.ice.gov/sitemap.xml"
    body, status = fetch(index_url, timeout, verify=verify)
    if not body or status != 200:
        return []
    page_urls = re.findall(r"<loc>([^<]+sitemap\.xml\?page=\d+)</loc>", body)
    if not page_urls:
        page_urls = [index_url]
    releases: list[str] = []
    for page_sitemap in page_urls:
        chunk, st = fetch(page_sitemap, timeout, verify=verify)
        if chunk and st == 200:
            releases.extend(
                u for u in re.findall(r"<loc>([^<]+)</loc>", chunk) if "/news/releases/" in u
            )
        time.sleep(0.3)
    return releases


def _resolve_ice_release_path(path_fragment: str, sitemap_releases: list[str]) -> str | None:
    """Map truncated ``/news/releases/slug...`` from Jina to canonical ice.gov URL."""
    slug = path_fragment.split("...")[0].rstrip(".")
    if not slug.startswith("/news/releases/"):
        return None
    last = slug.rstrip("/").split("/")[-1]
    if len(last) < 10:
        return None
    hits = [u for u in sitemap_releases if last in u.rstrip("/").split("/")[-1]]
    if not hits:
        return None
    return sorted(hits, key=len)[0]


_USMS_PRESS_PATH_RE = re.compile(
    r"(?:https?://)?(?:www\.)?usmarshals\.gov(/news/press-release/[a-z0-9][a-z0-9\-]*)",
    re.I,
)


def _load_usmarshals_press_sitemap(timeout: int, *, verify: bool) -> list[str]:
    """All ``/news/press-release/`` URLs (direct XML, else Jina when CloudFront blocks)."""
    sm_url = "https://www.usmarshals.gov/sitemap.xml"
    body, status = fetch(sm_url, timeout, verify=verify)
    if body and status == 200:
        urls = [u for u in re.findall(r"<loc>([^<]+)</loc>", body) if "/news/press-release/" in u]
        if urls:
            return urls
    print("  [usa] usmarshals.gov sitemap blocked; loading via Jina…", file=sys.stderr)
    jbody, jstatus = fetch("https://r.jina.ai/" + sm_url, max(timeout, 90), verify=verify)
    if not jbody or jstatus not in (200, 0):
        return []
    paths = re.findall(
        r"https?://(?:www\.)?usmarshals\.gov(/news/press-release/[a-z0-9\-]+)",
        jbody,
        re.I,
    )
    return [f"https://www.usmarshals.gov{p}" for p in sorted(set(paths))]


def _resolve_usms_press_path(path_fragment: str, sitemap_releases: list[str]) -> str | None:
    """Map truncated ``/news/press-release/slug`` from Jina search to canonical URL via sitemap."""
    path_fragment = path_fragment.split("...")[0].rstrip(".")
    if not path_fragment.startswith("/news/press-release/"):
        return None
    slug = path_fragment.rstrip("/").split("/")[-1].rstrip("-.").lower()
    if len(slug) < 8:
        return None
    hits = [
        u
        for u in sitemap_releases
        if slug in u.rstrip("/").split("/")[-1] or u.rstrip("/").split("/")[-1].startswith(slug)
    ]
    if not hits:
        return None
    return max(hits, key=len)


def _usms_press_paths_from_usa_body(body: str) -> list[str]:
    """Collect ``/news/press-release/…`` path prefixes from a search.usa.gov Jina page (may truncate)."""
    paths: set[str] = set()
    for m in _USMS_PRESS_PATH_RE.finditer(body):
        raw = m.group(1)
        path = raw.split("...")[0].rstrip(".")
        if path.startswith("/news/press-release/"):
            paths.add(path)
    return sorted(paths)


def collect_usmarshals_usa_search_urls(
    affiliate: str,
    query: str,
    page_range: range,
    *,
    timeout: int,
    verify: bool,
    delay: float,
    exclude_substrings: list[str],
    require_any_substrings: list[str],
    sitemap_releases: list[str],
) -> list[str]:
    """
    Harvest USMS press releases from search.usa.gov via Jina.

    Jina truncates long result URLs with ``...``; resolve full URLs against the site sitemap.
    """
    exclude_l = [x.lower() for x in exclude_substrings]
    require_l = [x.lower() for x in require_any_substrings]
    out: list[str] = []
    seen: set[str] = set()

    for page in page_range:
        search_url = (
            f"https://search.usa.gov/search?affiliate={quote(affiliate)}"
            f"&query={quote(query)}&page={page}"
        )
        jina_url = "https://r.jina.ai/" + search_url
        print(f"  [usa] page {page} Jina GET", file=sys.stderr)
        body, status = fetch(jina_url, max(timeout, 60), verify=verify)
        if not body or status not in (200, 0):
            print(f"  [stop] page {page} HTTP {status}", file=sys.stderr)
            continue

        batch_n = 0
        for path in _usms_press_paths_from_usa_body(body):
            url = _resolve_usms_press_path(path, sitemap_releases)
            if not url:
                continue
            low = url.lower()
            if "/sites/default/" in low:
                continue
            if any(ex in low for ex in exclude_l):
                continue
            if require_l and not any(req in low for req in require_l):
                continue
            if url not in seen:
                seen.add(url)
                out.append(url)
                batch_n += 1

        print(f"    -> {batch_n} new (total {len(out)})", file=sys.stderr)
        if page != page_range[-1]:
            time.sleep(delay)

    return out


def collect_usa_search_urls(
    affiliate: str,
    query: str,
    page_range: range,
    *,
    host: str,
    timeout: int,
    verify: bool,
    delay: float,
    path_prefix: str | None,
    exclude_substrings: list[str],
    require_any_substrings: list[str],
    sitemap_releases: list[str] | None,
) -> list[str]:
    """
    Harvest ``search.usa.gov`` results via Jina Reader (CloudFront blocks bare curl).

    Parses paths on ``host`` (e.g. ``osi.af.mil``, ``ncis.navy.mil``). For ICE, pass
    ``host=ice.gov`` and ``sitemap_releases`` to resolve truncated Drupal slugs.
    """
    path_prefix_l = path_prefix.lower() if path_prefix else None
    exclude_l = [x.lower() for x in exclude_substrings]
    require_l = [x.lower() for x in require_any_substrings]
    host_clean = host.lower().lstrip(".")
    if host_clean.endswith("usmarshals.gov"):
        if not sitemap_releases:
            print("  [usa] loading usmarshals.gov press sitemap…", file=sys.stderr)
            sitemap_releases = _load_usmarshals_press_sitemap(timeout, verify=verify)
            print(f"  [usa] {len(sitemap_releases)} press-release URLs in sitemap", file=sys.stderr)
        if not sitemap_releases:
            print("  [error] USMS sitemap empty; cannot resolve truncated search URLs", file=sys.stderr)
            return []
        return collect_usmarshals_usa_search_urls(
            affiliate,
            query,
            page_range,
            timeout=timeout,
            verify=verify,
            delay=delay,
            exclude_substrings=exclude_substrings,
            require_any_substrings=require_any_substrings,
            sitemap_releases=sitemap_releases,
        )

    host_re = _usa_host_path_re(host_clean)
    use_ice = host_clean.endswith("ice.gov")
    out: list[str] = []
    seen: set[str] = set()

    for page in page_range:
        search_url = (
            f"https://search.usa.gov/search?affiliate={quote(affiliate)}"
            f"&query={quote(query)}&page={page}"
        )
        jina_url = "https://r.jina.ai/" + search_url
        print(f"  [usa] page {page} Jina GET", file=sys.stderr)
        body, status = fetch(jina_url, max(timeout, 60), verify=verify)
        if not body or status not in (200, 0):
            print(f"  [stop] page {page} HTTP {status}", file=sys.stderr)
            continue

        batch_n = 0
        patterns = [_ICE_RELEASE_PATH_RE] if use_ice else [host_re]
        for rx in patterns:
            for m in rx.finditer(body):
                path_frag = m.group(1)
                if use_ice and sitemap_releases:
                    abs_u = _resolve_ice_release_path(path_frag, sitemap_releases)
                elif use_ice:
                    slug = path_frag.split("...")[0].rstrip(".")
                    abs_u = f"https://www.ice.gov{slug}" if slug.startswith("/") else None
                else:
                    slug = path_frag.split("...")[0].rstrip(".")
                    if not slug.startswith("/"):
                        continue
                    abs_u = f"https://www.{host_clean}{slug}"
                if not abs_u:
                    continue
                if "..." in abs_u.split("#", 1)[0]:
                    path_part = urlparse(abs_u).path
                    if sitemap_releases:
                        resolved = _resolve_article_id_in_sitemap(
                            path_part, sitemap_releases
                        )
                        if resolved:
                            abs_u = resolved
                        else:
                            continue
                    else:
                        continue
                abs_u = abs_u.split("#", 1)[0]
                if urlparse(abs_u).scheme != "https":
                    continue
                lower = abs_u.lower()
                if path_prefix_l and not _path(abs_u).lower().startswith(path_prefix_l):
                    continue
                if any(ex in lower for ex in exclude_l):
                    continue
                if require_l and not any(req in lower for req in require_l):
                    continue
                if abs_u not in seen:
                    seen.add(abs_u)
                    out.append(abs_u)
                    batch_n += 1

        print(f"    -> {batch_n} new (total {len(out)})", file=sys.stderr)
        if page != page_range[-1]:
            time.sleep(delay)

    return out


def collect_google_cse_search_pages(
    search_page_url: str,
    page_range: range,
    *,
    timeout: int,
    verify: bool,
    delay: float,
    path_prefix: str | None,
    exclude_substrings: list[str],
    require_any_substrings: list[str],
    https_only: bool,
    sitemap_url: str | None,
    max_results: int | None,
) -> list[str]:
    """Walk ``gsc.page`` values and merge CSE harvest (order preserved, deduped)."""
    out: list[str] = []
    seen: set[str] = set()
    for page in page_range:
        page_url = _google_cse_page_url(search_page_url, page)
        print(f"  [cse] page {page}", file=sys.stderr)
        batch = collect_google_cse_search_urls(
            page_url,
            timeout=timeout,
            verify=verify,
            path_prefix=path_prefix,
            exclude_substrings=exclude_substrings,
            require_any_substrings=require_any_substrings,
            https_only=https_only,
            sitemap_url=sitemap_url,
            max_results=None,
        )
        new = 0
        for u in batch:
            if u not in seen:
                seen.add(u)
                out.append(u)
                new += 1
                if max_results and len(out) >= max_results:
                    return out
        print(f"    -> {new} new (total {len(out)})", file=sys.stderr)
        if page != page_range[-1]:
            time.sleep(delay)
    return out


def wp_rest_public_url(
    link: str,
    slug: str,
    *,
    public_host: str,
    path_prefix: str,
) -> str:
    """Map a WP REST ``link`` + ``slug`` to the public article URL."""
    prefix = path_prefix if path_prefix.startswith("/") else f"/{path_prefix}"
    if not prefix.endswith("/"):
        prefix = prefix + "/"
    p = urlparse(link or "")
    path = p.path or f"{prefix}{slug}/"
    if not path.startswith(prefix.rstrip("/")):
        path = f"{prefix}{slug.strip('/')}/"
    host = public_host.lower().lstrip(".")
    return f"https://{host}{path.rstrip('/')}/"


def collect_wordpress_rest_urls(
    api_url: str,
    *,
    search: str,
    public_host: str,
    path_prefix: str = "/news/",
    per_page: int = 100,
    timeout: int = DEFAULT_TIMEOUT,
    verify: bool = True,
    delay: float = 0.3,
    path_filter: str | None = None,
    exclude_substrings: list[str] | None = None,
    require_any_substrings: list[str] | None = None,
) -> list[str]:
    """Page a WP REST ``/wp/v2/posts`` (or similar) endpoint into public article URLs."""
    exclude_substrings = exclude_substrings or []
    require_any_substrings = require_any_substrings or []
    out: list[str] = []
    seen: set[str] = set()
    page = 1
    while True:
        try:
            r = requests.get(
                api_url,
                params={"search": search, "per_page": per_page, "page": page},
                headers={**HEADERS, "Accept": "application/json"},
                timeout=timeout,
                verify=verify,
            )
            r.raise_for_status()
        except Exception as e:
            print(f"  [wp-rest error] page {page}: {e}", file=sys.stderr)
            break
        posts = r.json()
        if not isinstance(posts, list) or not posts:
            break
        page_new = 0
        for post in posts:
            if not isinstance(post, dict):
                continue
            url = wp_rest_public_url(
                post.get("link") or "",
                post.get("slug") or "",
                public_host=public_host,
                path_prefix=path_prefix,
            )
            key = url.lower().rstrip("/")
            if key in seen:
                continue
            path = _path(url)
            if path_filter and not path.startswith(path_filter):
                continue
            low = url.lower()
            if any(x.lower() in low for x in exclude_substrings):
                continue
            if require_any_substrings and not any(x.lower() in low for x in require_any_substrings):
                continue
            seen.add(key)
            out.append(url)
            page_new += 1
        total_pages = int(r.headers.get("X-WP-TotalPages", page))
        print(
            f"  [wp-rest {page}/{total_pages}] +{page_new} (total {len(out)})",
            file=sys.stderr,
        )
        if page >= total_pages:
            break
        page += 1
        time.sleep(delay)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Collect links from HTML pages (optionally paginated)."
    )
    ap.add_argument("--url", action="append", default=[], help="A page to fetch (repeatable).")
    ap.add_argument(
        "--url-template",
        metavar="TEMPLATE",
        help="URL with {page} or {n} for pagination (use with --page-range).",
    )
    ap.add_argument(
        "--page-range",
        type=parse_page_range,
        metavar="START:END",
        help="Inclusive page numbers substituted into --url-template.",
    )
    ap.add_argument("-o", "--out", default="source_urls.txt", help="Output text file.")
    ap.add_argument("--same-host", action="store_true", help="Keep only links on the seed page's host.")
    ap.add_argument(
        "--also-host",
        action="append",
        default=[],
        metavar="HOST",
        help="Allow this host in addition to the page host (implies --same-host).",
    )
    ap.add_argument(
        "--path-prefix",
        metavar="PREFIX",
        help="Keep only URLs whose path starts with this (e.g. /blog/).",
    )
    ap.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="SUBSTR",
        help="Drop URLs containing this substring (case-insensitive). Repeatable.",
    )
    ap.add_argument(
        "--exclude-from",
        metavar="FILE",
        help="File with one exclude substring per line.",
    )
    ap.add_argument(
        "--require-any",
        action="append",
        default=[],
        metavar="SUBSTR",
        help="Keep only URLs that contain at least one of these (case-insensitive). "
        "If none given, no 'must match' filter.",
    )
    ap.add_argument(
        "--require-any-from",
        metavar="FILE",
        help="File with one required substring per line (any match keeps URL).",
    )
    ap.add_argument(
        "--stop-if-text",
        action="append",
        default=[],
        metavar="TEXT",
        help="If page HTML contains this (case-insensitive), stop pagination after this page.",
    )
    ap.add_argument(
        "--allow-http",
        action="store_true",
        help="Allow http:// links (default: https only).",
    )
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    ap.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS certificate verification (use only if the host has chain issues).",
    )
    ap.add_argument(
        "--max-consecutive-empty",
        type=int,
        default=2,
        metavar="N",
        help="Stop pagination after N pages in a row with no new URLs.",
    )
    ap.add_argument(
        "--raw-url-regex",
        action="append",
        default=[],
        metavar="PATTERN",
        help="Python regex scanned against raw HTML for URLs (e.g. Search.gov JSON). "
        "Repeatable. Use a pattern that matches full https URLs.",
    )
    ap.add_argument(
        "--squarespace-search-page",
        metavar="URL",
        help="Squarespace site search HTML page carrying q= (paginates GET /api/search/GeneralSearch). "
        "Do not combine with --url / --url-template.",
    )
    ap.add_argument(
        "--google-cse-search-page",
        metavar="URL",
        help="Google Programmable Search listing page (CSE widget; results via Jina Reader). "
        "Do not combine with --url / --url-template / --squarespace-search-page.",
    )
    ap.add_argument(
        "--cse-sitemap",
        metavar="URL",
        default=None,
        help="Site sitemap used to expand truncated CSE result slugs (e.g. https://www.example.gov/sitemap.xml).",
    )
    ap.add_argument(
        "--cse-max-results",
        type=int,
        default=None,
        metavar="N",
        help="Stop after N press-release URLs (use with --google-cse-search-page).",
    )
    ap.add_argument(
        "--cse-page-range",
        type=parse_page_range,
        metavar="START:END",
        help="Paginate Google CSE via gsc.page (e.g. 1:10 with --google-cse-search-page).",
    )
    ap.add_argument(
        "--usa-search",
        action="store_true",
        help="Harvest search.usa.gov (use with --usa-affiliate, --usa-query, --usa-page-range).",
    )
    ap.add_argument("--usa-affiliate", default="ice.gov", help="search.usa.gov affiliate id.")
    ap.add_argument(
        "--usa-host",
        default="ice.gov",
        help="Site hostname for path extraction (e.g. osi.af.mil, ncis.navy.mil, usmarshals.gov).",
    )
    ap.add_argument("--usa-query", default="child", help="search.usa.gov query string.")
    ap.add_argument(
        "--usa-page-range",
        type=parse_page_range,
        metavar="START:END",
        help="Inclusive search.usa.gov page numbers (e.g. 1:10).",
    )
    ap.add_argument(
        "--usa-sitemap",
        action="store_true",
        help="Resolve truncated slugs via site sitemap (ice.gov, usmarshals.gov press releases).",
    )
    ap.add_argument(
        "--wordpress-rest",
        metavar="API_URL",
        help="WordPress REST posts endpoint (e.g. https://wp.example.gov/wp-json/wp/v2/posts). "
        "Use when the public newsroom HTML has no links (Next.js shells).",
    )
    ap.add_argument(
        "--wp-search",
        default="",
        help="Search term for --wordpress-rest (WP ``search`` query param).",
    )
    ap.add_argument(
        "--wp-public-host",
        default="",
        help="Public hostname for rewritten article URLs (required with --wordpress-rest).",
    )
    ap.add_argument(
        "--wp-path-prefix",
        default="/news/",
        help="Public path prefix for rewritten article URLs (default /news/).",
    )
    ap.add_argument(
        "--wp-per-page",
        type=int,
        default=100,
        help="WP REST per_page (default 100).",
    )
    ap.add_argument(
        "--via-jina",
        action="store_true",
        help="Fetch listing pages through https://r.jina.ai/ (bot walls / JS shells). "
        "Applies to --url / --url-template HTML harvest only.",
    )
    args = ap.parse_args()

    if args.url_template and args.page_range is None:
        ap.error("--url-template requires --page-range START:END")

    if args.wordpress_rest:
        if not args.wp_public_host.strip():
            ap.error("--wordpress-rest requires --wp-public-host")
        if args.url or args.url_template or args.squarespace_search_page or args.google_cse_search_page or args.usa_search:
            ap.error("--wordpress-rest cannot be combined with other listing modes")

    if args.squarespace_search_page:
        if args.url or args.url_template:
            ap.error("--squarespace-search-page cannot be combined with --url / --url-template")

    if args.google_cse_search_page:
        if args.url or args.url_template or args.squarespace_search_page:
            ap.error(
                "--google-cse-search-page cannot be combined with --url, --url-template, "
                "or --squarespace-search-page"
            )

    if args.usa_search:
        if args.url or args.url_template or args.squarespace_search_page or args.google_cse_search_page:
            ap.error("--usa-search cannot be combined with other listing modes")
        if args.usa_page_range is None:
            ap.error("--usa-search requires --usa-page-range START:END")

    compiled_regexes: list[re.Pattern[str]] = []
    for pat in args.raw_url_regex or []:
        try:
            compiled_regexes.append(re.compile(pat))
        except re.error as e:
            ap.error(f"Invalid --raw-url-regex: {e}")

    exclude = list(args.exclude) + _read_patterns(args.exclude_from)
    require_any = list(args.require_any) + _read_patterns(args.require_any_from)
    https_only = not args.allow_http

    same_host = args.same_host or bool(args.also_host)
    extra_hosts: frozenset[str] | None = None
    if args.also_host:
        extra_hosts = frozenset(h.lower().lstrip(".") for h in args.also_host)

    verify_tls = not args.insecure
    if args.insecure:
        try:
            import urllib3

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass

    if args.wordpress_rest:
        all_urls = collect_wordpress_rest_urls(
            args.wordpress_rest,
            search=args.wp_search,
            public_host=args.wp_public_host,
            path_prefix=args.wp_path_prefix,
            per_page=max(1, int(args.wp_per_page)),
            timeout=args.timeout,
            verify=verify_tls,
            delay=args.delay,
            path_filter=args.path_prefix,
            exclude_substrings=exclude,
            require_any_substrings=require_any,
        )
        with open(args.out, "w", encoding="utf-8") as f:
            for u in all_urls:
                f.write(u + "\n")
        print(f"\nTotal URLs: {len(all_urls)}", file=sys.stderr)
        print(f"Saved -> {args.out}", file=sys.stderr)
        return

    if args.usa_search:
        sitemap_releases: list[str] | None = None
        if args.usa_sitemap:
            host = args.usa_host.lower().lstrip(".")
            if host.endswith("ice.gov"):
                print("  [usa] loading ice.gov release sitemap…", file=sys.stderr)
                sitemap_releases = _load_ice_release_sitemap(args.timeout, verify=verify_tls)
            elif host.endswith("usmarshals.gov"):
                sitemap_releases = _load_usmarshals_press_sitemap(args.timeout, verify=verify_tls)
            else:
                sm_url = f"https://www.{host}/sitemap.xml"
                print(f"  [usa] loading {sm_url}…", file=sys.stderr)
                sitemap_releases = _load_sitemap_urls(sm_url, args.timeout, verify=verify_tls)
            print(f"  [usa] {len(sitemap_releases)} URLs in sitemap", file=sys.stderr)
        all_urls = collect_usa_search_urls(
            args.usa_affiliate,
            args.usa_query,
            args.usa_page_range,
            host=args.usa_host,
            timeout=args.timeout,
            verify=verify_tls,
            delay=args.delay,
            path_prefix=args.path_prefix,
            exclude_substrings=exclude,
            require_any_substrings=require_any,
            sitemap_releases=sitemap_releases,
        )
        with open(args.out, "w", encoding="utf-8") as f:
            for u in all_urls:
                f.write(u + "\n")
        print(f"\nTotal URLs: {len(all_urls)}", file=sys.stderr)
        print(f"Saved -> {args.out}", file=sys.stderr)
        return

    if args.squarespace_search_page:
        all_urls = collect_squarespace_general_search_urls(
            args.squarespace_search_page,
            timeout=args.timeout,
            verify=verify_tls,
            delay=args.delay,
            path_prefix=args.path_prefix,
            exclude_substrings=exclude,
            require_any_substrings=require_any,
            https_only=https_only,
        )
        with open(args.out, "w", encoding="utf-8") as f:
            for u in all_urls:
                f.write(u + "\n")

        print(f"\nTotal URLs: {len(all_urls)}", file=sys.stderr)
        print(f"Saved -> {args.out}", file=sys.stderr)
        return

    if args.google_cse_search_page:
        sitemap = args.cse_sitemap
        if not sitemap:
            parsed_seed = urlparse(args.google_cse_search_page)
            if parsed_seed.scheme and parsed_seed.netloc:
                sitemap = f"{parsed_seed.scheme}://{parsed_seed.netloc}/sitemap.xml"
        if args.cse_page_range is not None:
            all_urls = collect_google_cse_search_pages(
                args.google_cse_search_page,
                args.cse_page_range,
                timeout=args.timeout,
                verify=verify_tls,
                delay=args.delay,
                path_prefix=args.path_prefix,
                exclude_substrings=exclude,
                require_any_substrings=require_any,
                https_only=https_only,
                sitemap_url=sitemap,
                max_results=args.cse_max_results,
            )
        else:
            all_urls = collect_google_cse_search_urls(
                args.google_cse_search_page,
                timeout=args.timeout,
                verify=verify_tls,
                path_prefix=args.path_prefix,
                exclude_substrings=exclude,
                require_any_substrings=require_any,
                https_only=https_only,
                sitemap_url=sitemap,
                max_results=args.cse_max_results,
            )
        with open(args.out, "w", encoding="utf-8") as f:
            for u in all_urls:
                f.write(u + "\n")

        print(f"\nTotal URLs: {len(all_urls)}", file=sys.stderr)
        print(f"Saved -> {args.out}", file=sys.stderr)
        return

    page_urls = iter_page_urls(args)
    all_urls = []
    seen_global: set[str] = set()
    consecutive_empty = 0
    stop_texts = [t.lower() for t in args.stop_if_text]

    for i, page_url in enumerate(page_urls):
        fetch_url = ("https://r.jina.ai/" + page_url) if args.via_jina else page_url
        print(f"  [{i + 1}/{len(page_urls)}] {fetch_url}", file=sys.stderr)
        html, status = fetch(fetch_url, args.timeout, verify=verify_tls)
        if status == 404 or not html:
            print(f"  [stop] HTTP {status}", file=sys.stderr)
            break
        lower_html = html.lower()
        if stop_texts and any(t in lower_html for t in stop_texts):
            print("  [stop] stop-if-text matched", file=sys.stderr)
            # still collect from this page first
            batch = collect_from_html(
                html,
                page_url,
                same_host=same_host,
                extra_hosts=extra_hosts,
                path_prefix=args.path_prefix,
                exclude_substrings=exclude,
                require_any_substrings=require_any,
                https_only=https_only,
            )
            for rx in compiled_regexes:
                batch.extend(
                    collect_from_regex(
                        html,
                        rx,
                        path_prefix=args.path_prefix,
                        exclude_substrings=exclude,
                        require_any_substrings=require_any,
                        https_only=https_only,
                    )
                )
            seen_b2: set[str] = set()
            batch = [u for u in batch if not (u in seen_b2 or seen_b2.add(u))]
            new = [u for u in batch if u not in seen_global]
            for u in new:
                seen_global.add(u)
            all_urls.extend(new)
            print(f"    -> {len(new)} new (total {len(all_urls)})", file=sys.stderr)
            break

        batch = collect_from_html(
            html,
            page_url,
            same_host=same_host,
            extra_hosts=extra_hosts,
            path_prefix=args.path_prefix,
            exclude_substrings=exclude,
            require_any_substrings=require_any,
            https_only=https_only,
        )
        for rx in compiled_regexes:
            batch.extend(
                collect_from_regex(
                    html,
                    rx,
                    path_prefix=args.path_prefix,
                    exclude_substrings=exclude,
                    require_any_substrings=require_any,
                    https_only=https_only,
                )
            )
        seen_batch: list[str] = []
        seen_b: set[str] = set()
        for u in batch:
            if u not in seen_b:
                seen_b.add(u)
                seen_batch.append(u)
        batch = seen_batch
        new = [u for u in batch if u not in seen_global]
        for u in new:
            seen_global.add(u)
        all_urls.extend(new)
        print(f"    -> {len(new)} new (total {len(all_urls)})", file=sys.stderr)

        if len(new) == 0:
            consecutive_empty += 1
            if consecutive_empty >= args.max_consecutive_empty:
                print(
                    f"  [stop] {args.max_consecutive_empty} consecutive pages with no new URLs",
                    file=sys.stderr,
                )
                break
        else:
            consecutive_empty = 0

        time.sleep(args.delay)

    with open(args.out, "w", encoding="utf-8") as f:
        for u in all_urls:
            f.write(u + "\n")

    print(f"\nTotal URLs: {len(all_urls)}", file=sys.stderr)
    print(f"Saved -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
