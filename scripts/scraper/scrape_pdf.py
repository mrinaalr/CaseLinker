#!/usr/bin/env python3
"""
Fetch HTML pages from a URL list and build a merged PDF for CaseLinker ingestion.

Works with typical article / press-release markup (article, main, role=main,
common content class names). Title from ``og:title`` / ``twitter:title``, repeated-masthead ``<h1>``
heuristic, ``<title>`` (``|`` / en-dash splits), or URL slug; publication date from meta,
visible date fields, URL path segments, or the first Month D, YYYY dateline in body
text. Emits ``Publication date: YYYY-MM-DD`` before ``Source:`` for merged-PDF batching.

deps:  pip install requests beautifulsoup4 reportlab pypdf pdfplumber
usage:
    python3 scrape_pdf.py --url-file source_urls.txt --out-dir ./out --out-name batch.pdf
    python3 scrape_pdf.py --url-file source_urls.txt --limit 5
    python3 scrape_pdf.py --url-file urls.txt --jina-fallback   # hosts that return 403 to bots
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import re
import sys
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("pip install requests beautifulsoup4")

try:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate
    from reportlab.lib import colors
except ImportError:
    sys.exit("pip install reportlab")

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    sys.exit("pip install pypdf")

try:
    import pdfplumber
except ImportError:
    pdfplumber = None  # type: ignore[assignment]

DEFAULT_URL_FILE = Path.cwd() / "source_urls.txt"
DEFAULT_OUT_DIR = Path.cwd() / "scrape_output"
DEFAULT_OUT_NAME = "scraped_cases.pdf"
REQUEST_DELAY = 1.2
REQUEST_TIMEOUT = 30
JINA_READER_TIMEOUT = 90
MIN_BODY_CHARS = 80
# Drupal SPAs (e.g. troopers.ny.gov) often return only title+date in static HTML.
THIN_HTML_RETRY_CHARS = 400

_PROVENANCE_PATH = Path(__file__).resolve().parents[2] / "src" / "Storage Layer" / "provenance.py"
_provenance_spec = importlib.util.spec_from_file_location("caselinker_provenance", _PROVENANCE_PATH)
if _provenance_spec is None or _provenance_spec.loader is None:
    raise RuntimeError(f"Unable to load provenance support from {_PROVENANCE_PATH}")
provenance = importlib.util.module_from_spec(_provenance_spec)
_provenance_spec.loader.exec_module(provenance)


@dataclass(frozen=True)
class FetchedResource:
    content: bytes
    text: str
    retrieved_at: datetime
    status_code: int
    content_type: str | None
    etag: str | None
    last_modified: str | None
    final_url: str

# news.delaware.gov: breadcrumb lines vary — e.g.
#   ``Department of Justice Press Releases | Date Posted:``
#   ``Department of Justice | Date Posted:``
#   ``... Press Releases | Family | Date Posted:``
# Fusion sometimes emits the full breadcrumb + article twice.
_DE_DOJ_DATELINE_LINE_RE = re.compile(
    r"(?m)^[^\n]*Department\s+of\s+Justice[^\n]*\|\s*Date\s+Posted:\s*[^\n]*\s*$",
    re.I,
)


def _ordered_body_blocks_from_container(container) -> list[str]:
    """
    Document-order ``<p>`` and list blocks. Skips ``<p>`` inside lists; flattens
    ``<ul>``/``<ol>`` to numbered lines (matches merged ICAC PDF style).
    """
    blocks: list[str] = []
    for el in container.find_all(["p", "ul", "ol"]):
        if el.name == "p":
            if el.find_parent(["ul", "ol"]):
                continue
            t = el.get_text(" ", strip=True)
            if t:
                blocks.append(t)
        elif el.name in ("ul", "ol"):
            if el.find_parent(["ul", "ol"]):
                continue
            items = [
                li.get_text(" ", strip=True)
                for li in el.find_all("li", recursive=False)
                if li.get_text(strip=True)
            ]
            if items:
                blocks.append(" ".join(f"{i + 1}. {t}" for i, t in enumerate(items)))
    return blocks


def _collapse_consecutive_duplicate_paragraphs(paras: list[str]) -> list[str]:
    """Drop back-to-back duplicate ``<p>`` text (common when themes duplicate columns)."""
    out: list[str] = []
    prev_key: str | None = None
    for raw in paras:
        key = re.sub(r"\s+", " ", raw.strip())
        if len(key) < 30:
            continue
        if prev_key is not None and key == prev_key:
            continue
        out.append(raw.strip())
        prev_key = key
    return out


def _trim_news_delaware_duplicate_press_rail(body: str) -> str:
    """
    news.delaware.gov (Fusion / Avada) often emits the DOJ breadcrumb +
    ``Date Posted:`` line twice (possibly with ``| Family |`` etc. between crumbs).
    Subscribe widgets may sit between copies. Cut before the second breadcrumb line.
    """
    if not body:
        return body
    matches = list(_DE_DOJ_DATELINE_LINE_RE.finditer(body))
    if len(matches) < 2:
        return body
    second_start = matches[1].start()
    cut = body.rfind("\n\n", 0, second_start)
    if cut == -1:
        cut = body.rfind("\n", 0, second_start)
    if cut <= 0:
        return body[:second_start].rstrip()
    return body[:cut].rstrip()


def _dedupe_news_delaware_paragraph_blocks(body: str, *, min_chars: int = 120) -> str:
    """
    Drop repeated paragraph-sized blocks (normalized whitespace). Catches duplicated
    rails/columns where the second copy does not restart with the DOJ dateline line.
    """
    blocks = [b.strip() for b in re.split(r"\n\s*\n+", body.strip()) if b.strip()]
    if len(blocks) < 2:
        return body.strip()

    seen: set[str] = set()
    out: list[str] = []
    for b in blocks:
        if len(b) < min_chars:
            out.append(b)
            continue
        key = re.sub(r"\s+", " ", b.strip())
        if key in seen:
            continue
        seen.add(key)
        out.append(b)
    return "\n\n".join(out)


# Match batching._merged_news_dateline_year (month + day + year in prose).
_DATELINE_MDY_RE = re.compile(
    r"\b((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
    r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?))\s+"
    r"(\d{1,2}),?\s+((?:19|20)\d{2})\b",
    re.I,
)
_DOB_LINE_HINT_RE = re.compile(
    r"date\s+of\s+birth|\bd\.?\s*o\.?\s*b\.?\s*:|\bborn\b|birthdate|birth\s+date",
    re.I,
)

# Month token (regex capture group 1) -> calendar month number
_MONTH_TOKEN_TO_NUM: dict[str, int] = {}
for i, names in enumerate(
    (
        ("january", "jan"),
        ("february", "feb"),
        ("march", "mar"),
        ("april", "apr"),
        ("may",),
        ("june", "jun"),
        ("july", "jul"),
        ("august", "aug"),
        ("september", "sep", "sept"),
        ("october", "oct"),
        ("november", "nov"),
        ("december", "dec"),
    ),
    start=1,
):
    for n in names:
        _MONTH_TOKEN_TO_NUM[n] = i


def _parse_dateline_match(mon: str, day_s: str, year_s: str) -> date | None:
    tok = mon.lower().strip().rstrip(".")
    month = _MONTH_TOKEN_TO_NUM.get(tok)
    if not month:
        return None
    try:
        d_i, y_i = int(day_s), int(year_s)
        return date(y_i, month, d_i)
    except ValueError:
        return None


def _first_dateline_date_in_text(blob: str) -> date | None:
    """First Month D, YYYY in blob that is not near a DOB hint."""
    if not blob:
        return None
    head = blob[:12000]
    for m in _DATELINE_MDY_RE.finditer(head):
        pre = head[max(0, m.start() - 120) : m.start()]
        if _DOB_LINE_HINT_RE.search(pre):
            continue
        d = _parse_dateline_match(m.group(1), m.group(2), m.group(3))
        if d:
            return d
    return None


def _publication_date_from_meta(soup: BeautifulSoup) -> date | None:
    raw = _meta_content(soup, prop="article:published_time") or _meta_content(
        soup, name="article:published_time"
    )
    raw = raw or _meta_content(soup, prop="og:published_time")
    if raw:
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", raw.strip())
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass
    t = soup.find("time", attrs={"datetime": True})
    if t:
        dt = str(t.get("datetime", "")).strip()
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", dt)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass
    return None


def _publication_date_from_url_path(url: str) -> date | None:
    for pat in (
        r"/(\d{4})/(\d{2})/(\d{2})/",
        r"/(\d{4})/(\d{2})/(\d{2})-",
        r"/(\d{4})-(\d{2})-(\d{2})/",
    ):
        m = re.search(pat, url)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass
    return None


def _publication_date_from_visible_markup(soup: BeautifulSoup) -> date | None:
    """Drupal / news themes: date in header row, field, or meta without standard names."""
    for tag in soup.find_all(["time", "span", "div", "p", "h6", "h5", "h4", "small"]):
        cls = tag.get("class") or []
        cl = " ".join(str(c) for c in cls).lower()
        if any(k in cl for k in ("date", "published", "created", "submitted", "posted")):
            d = _first_dateline_date_in_text(tag.get_text(" ", strip=True))
            if d:
                return d
    return None


def resolve_publication_date(soup: BeautifulSoup, url: str, body: str) -> date | None:
    """
    Best-effort calendar date for the article. Used for ``Publication date: YYYY-MM-DD``
    before ``Source:`` so merged-PDF batching can assign case_id years.
    """
    for fn in (
        lambda: _publication_date_from_meta(soup),
        lambda: _publication_date_from_url_path(url),
        lambda: _publication_date_from_visible_markup(soup),
        lambda: _first_dateline_date_in_text(body),
        lambda: _first_dateline_date_in_text(soup.get_text(" ", strip=True)[:8000]),
    ):
        d = fn()
        if d:
            return d
    return None


def _default_headers(referer: str | None) -> dict[str, str]:
    ref = referer or "https://www.google.com/"
    return {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": ref,
        "DNT": "1",
    }


def _build_styles():
    base = getSampleStyleSheet()
    title_s = ParagraphStyle(
        "DocTitle",
        parent=base["Heading1"],
        fontSize=15,
        leading=19,
        spaceAfter=4,
        textColor=colors.HexColor("#1a1a1a"),
        fontName="Times-Bold",
    )
    meta_s = ParagraphStyle(
        "DocMeta",
        parent=base["Normal"],
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#555555"),
        fontName="Helvetica",
        spaceAfter=2,
    )
    source_s = ParagraphStyle(
        "DocSource",
        parent=base["Normal"],
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#0645ad"),
        fontName="Helvetica",
        spaceAfter=8,
    )
    body_s = ParagraphStyle(
        "DocBody",
        parent=base["Normal"],
        fontSize=10.5,
        leading=15,
        fontName="Times-Roman",
        textColor=colors.HexColor("#111111"),
        spaceAfter=7,
    )
    return title_s, meta_s, source_s, body_s


_TITLE_S, _META_S, _SOURCE_S, _BODY_S = _build_styles()


def esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


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


def fetch_resource(
    url: str,
    headers: dict[str, str],
    *,
    verify: bool = True,
    timeout: int = REQUEST_TIMEOUT,
) -> FetchedResource | None:
    try:
        retrieved_at = datetime.now(UTC)
        r = requests.get(
            url,
            headers=headers,
            timeout=timeout,
            allow_redirects=True,
            verify=verify,
        )
        r.raise_for_status()
        return FetchedResource(
            content=r.content,
            text=r.text,
            retrieved_at=retrieved_at,
            status_code=r.status_code,
            content_type=r.headers.get("Content-Type"),
            etag=r.headers.get("ETag"),
            last_modified=r.headers.get("Last-Modified"),
            final_url=r.url,
        )
    except Exception as e:
        print(f"    [fetch error] {e}", file=sys.stderr)
        return None


def fetch(url: str, headers: dict[str, str], *, verify: bool = True) -> str | None:
    resource = fetch_resource(url, headers, verify=verify)
    return resource.text if resource is not None else None


def fetch_bytes(url: str, headers: dict[str, str], *, verify: bool = True) -> bytes | None:
    resource = fetch_resource(
        url,
        {**headers, "Accept": "application/pdf,*/*;q=0.8"},
        verify=verify,
    )
    return resource.content if resource is not None else None


def _publication_date_from_filename(url: str) -> date | None:
    """Best-effort date from common city press-release PDF names."""
    slug = url.rstrip("/").split("/")[-1]
    stem = re.sub(r"\.pdf$", "", slug, flags=re.I)
    stem = re.sub(r"%20", " ", stem, flags=re.I)
    for pat, conv in (
        (r"^(\d{4})-(\d{2})-(\d{2})", lambda m: date(int(m[1]), int(m[2]), int(m[3]))),
        (r"^(\d{8})_", lambda m: _yyyymmdd(int(m[1]))),
        (r"^(\d{8})(?:_|$)", lambda m: _yyyymmdd(int(m[1]))),
        (r"^(\d{6})_", lambda m: _mmddyy(int(m[1]))),
        (r"^nr(\d{2})(\d{2})(\d{2})", lambda m: date(2000 + int(m[1]), int(m[2]), int(m[3]))),
        (r"^pr_(\d{2})-(\d{2})-(\d{2})", lambda m: date(2000 + int(m[3]), int(m[1]), int(m[2]))),
        (r"^(\d{4})/(\d{2})/(\d{2})", lambda m: date(int(m[1]), int(m[2]), int(m[3]))),
    ):
        m = re.search(pat, stem, re.I)
        if m:
            try:
                return conv(m)
            except ValueError:
                pass
    m = re.search(r"/(\d{4})-(\d{2})/", url)
    if m:
        try:
            return date(int(m[1]), int(m[2]), 1)
        except ValueError:
            pass
    return None


def _yyyymmdd(n: int) -> date:
    y, mo, d = n // 10000, (n // 100) % 100, n % 100
    return date(y, mo, d)


def _mmddyy(n: int) -> date:
    mo, d, y = n // 10000, (n // 100) % 100, n % 100
    return date(2000 + y if y < 100 else y, mo, d)


def _title_from_url(url: str) -> str:
    slug = url.rstrip("/").split("/")[-1]
    stem = re.sub(r"\.pdf$", "", slug, flags=re.I)
    stem = re.sub(r"%20", " ", stem)
    return stem.replace("-", " ").replace("_", " ").strip().title() or "Press release"


def _extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """
    Best-effort text from a native PDF. pdfplumber first; PyMuPDF when pdfplumber
    sees zero pages (common on older justice.gov archive press-release PDFs).
    """
    import io

    pages: list[str] = []
    if pdfplumber:
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                pages = [p.extract_text() or "" for p in pdf.pages]
        except Exception:
            pages = []
    body = "\n\n".join(p.strip() for p in pages if p.strip())
    if len(body) >= MIN_BODY_CHARS:
        return body.strip()
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        alt = "\n\n".join(page.get_text().strip() for page in doc if page.get_text().strip())
        if len(alt) >= MIN_BODY_CHARS:
            return alt.strip()
    except Exception:
        pass
    return body.strip()


def extract_from_native_pdf(pdf_bytes: bytes, url: str) -> tuple[str, str, str, date | None] | None:
    """Downloaded city PDF → title, byline, body, publication date."""
    if not pdfplumber:
        print("    [skip] pdfplumber not installed", file=sys.stderr)
        return None

    body = _extract_text_from_pdf_bytes(pdf_bytes)
    if len(body) < MIN_BODY_CHARS:
        return None
    title = _title_from_url(url)
    pub_date = _first_dateline_date_in_text(body) or _publication_date_from_filename(url)
    byline = format_display_byline(pub_date, None)
    return title, byline, body.strip(), pub_date


def fetch_via_jina_reader_resource(
    target_url: str, *, verify: bool = True, retries: int = 5
) -> FetchedResource | None:
    """Some hosts (e.g. mass.gov) block datacenter IPs; Jina Reader returns markdown + metadata."""
    jina_url = "https://r.jina.ai/" + target_url
    hdrs = {
        "User-Agent": _default_headers(None)["User-Agent"],
        "Accept": "text/plain,text/markdown;q=0.9,*/*;q=0.8",
    }
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            retrieved_at = datetime.now(UTC)
            r = requests.get(
                jina_url,
                headers=hdrs,
                timeout=JINA_READER_TIMEOUT,
                allow_redirects=True,
                verify=verify,
            )
            if r.status_code == 429:
                wait = min(60, 4 * (2**attempt))
                print(f"    [jina 429] waiting {wait}s …", file=sys.stderr)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return FetchedResource(
                content=r.content,
                text=r.text,
                retrieved_at=retrieved_at,
                status_code=r.status_code,
                content_type=r.headers.get("Content-Type"),
                etag=r.headers.get("ETag"),
                last_modified=r.headers.get("Last-Modified"),
                final_url=r.url,
            )
        except Exception as e:
            last_err = e
            if attempt + 1 < retries:
                time.sleep(min(30, 2 * (attempt + 1)))
    if last_err is not None:
        print(f"    [jina fetch error] {last_err}", file=sys.stderr)
    return None


def fetch_via_jina_reader(target_url: str, *, verify: bool = True, retries: int = 5) -> str | None:
    resource = fetch_via_jina_reader_resource(target_url, verify=verify, retries=retries)
    return resource.text if resource is not None else None


def _parse_jina_published_time(raw: str) -> date | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


# Mass.gov / Mayflower: Jina reader often prepends global nav + trust banner before the press lede.
_JINA_MASS_GOV_PRESS_LEDE = re.compile(
    r"(?m)^(?:[A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){0,5})\s+\u2014\s+\S.{25,}\s*$"
)


def _strip_jina_embedded_images(md: str) -> str:
    return re.sub(r"!\[[^\]]*\]\([^)]*\)\s*", "", md)


def _unwrap_jina_markdown_links(md: str) -> str:
    """Turn [label](url) into spaces around label so words do not glue (e.g. Barker[was](u)by)."""
    out = re.sub(r"\[([^\]]+)\]\([^)]+\)", r" \1 ", md)
    return re.sub(r"[ \t]{2,}", " ", out)


# WordPress.com / Jetpack sharedaddy (TBINewsroom and similar).
_WP_JETPACK_SHARE_BLOCK = re.compile(
    r"(?s)(?:\d+\.\s*)?"
    r"Share on X \(Opens in new window\)\s*X\s*"
    r"(?:\d+\.\s*)?Share on Facebook \(Opens in new window\)\s*Facebook\s*"
    r"(?:\d+\.\s*)?Share on\s*LinkedIn \(Opens in new window\)\s*LinkedIn\s*"
    r"(?:\d+\.\s*)?Email a link to a friend \(Opens in new window\)\s*Email\s*",
    re.I,
)


def _strip_wordpress_jetpack_share(body: str) -> str:
    """Remove Jetpack share rows that Jina inlines after the release body."""
    if not body:
        return body
    body = _WP_JETPACK_SHARE_BLOCK.sub("\n\n", body)
    kept: list[str] = []
    for line in body.splitlines():
        if re.search(
            r"Share on (?:X|Facebook|LinkedIn).+Opens in new window",
            line,
            re.I,
        ):
            remainder = _WP_JETPACK_SHARE_BLOCK.sub("", line).strip()
            if remainder and len(remainder) > 40:
                if not re.search(r"Opens in new window", remainder, re.I):
                    kept.append(remainder)
            continue
        kept.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def _trim_mass_gov_jina_preface(body: str) -> str:
    """Drop site chrome / duplicate H1 when Jina returns the full page shell."""
    m = _JINA_MASS_GOV_PRESS_LEDE.search(body)
    if m:
        return body[m.start() :].strip()
    return body


def _trim_mass_gov_jina_postface(body: str) -> str:
    """Remove repeated media blocks, feedback widgets, and global footer after the release."""
    m = re.search(r"(?m)^###\s*$", body)
    if m:
        return body[: m.end()].rstrip()
    m2 = re.search(r"(?m)^##\s*Help Us Improve Mass\.gov", body)
    if m2:
        return body[: m2.start()].strip()
    return body


def _trim_nmdoj_jina_preface(body: str) -> str:
    """WordPress/Elementor shell before City, NM dateline (bold, italic, or plain)."""
    # Torrez-era releases: long Elementor nav before "**Albuquerque, NM –**".
    m_abq = re.search(
        r"(?m)^\*\*(?:Albuquerque|Santa\s+Fe|Las\s+Cruces|Gallup|Roswell),?\s*NM\s*[\u2013\u2014\-]",
        body,
    )
    if m_abq:
        return body[m_abq.start() :].strip()
    patterns = (
        re.compile(
            r"(?m)^\*\*(?:[A-Z][^*\n]{0,140}),\s*NM\*\*\s*[\u2013\u2014\-]\s+\S",
        ),
        re.compile(
            r"(?m)^\*\*(?:[A-Z][^*\n]{0,140}),\s*NM\s*[\u2013\u2014\-]\*\*\s+\S",
        ),
        re.compile(
            r"(?m)^_(?:.+?),\s*NM_\s*[\u2013\u2014\-]\s+\S",
        ),
        re.compile(
            r"(?m)^(?:[A-Z]{2,}(?:\s+[A-Z]{2,})*)\s+[\u2014\u2013\-]\s+(?:Today|This|The|Attorney|Special|Octo|Immediately|A\s)",
        ),
        re.compile(
            r"(?m)^(?:[A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+)*)?,\s*NM\s*[\u2013\u2014\-]\s+\S",
        ),
    )
    best: re.Match[str] | None = None
    for pat in patterns:
        m = pat.search(body)
        if m and (best is None or m.start() < best.start()):
            best = m
    if best:
        return body[best.start() :].strip()
    return body


def _trim_nmdoj_jina_postface(body: str) -> str:
    """Clip Elementor sidebar (Most Viewed) and standard ### / # # # closers."""
    for pat in (
        r"(?m)^##\s*Most Viewed\b",
        r"(?m)^#\s*#\s*#\s*$",
        r"(?m)^###\s*$",
    ):
        m = re.search(pat, body)
        if m:
            return body[: m.start()].strip()
    return body


def _trim_sjpd_jina_body(body: str) -> str:
    """sjpd.org (CivicPlus/Granicus) via Jina: site chrome before FOR IMMEDIATE RELEASE; footer after release."""
    if not (body or "").strip():
        return body
    trimmed = body
    for pat in (
        r"(?m)^\*\*FOR IMMEDIATE RELEASE\*\*\s*$",
        r"(?m)^FOR IMMEDIATE RELEASE\s*$",
        r"(?m)^TYPE OF CRIME:",
        r"(?m)^##\s+(?:SJPD|Additional|Public Notification)[^\n]{8,220}\n+\s*Post Date:",
        r"(?m)^Post Date:\s*\d{1,2}/\d{1,2}/\d{4}",
    ):
        m = re.search(pat, trimmed)
        if m:
            trimmed = trimmed[m.start() :].strip()
            break
    # Drop duplicate page-title H1 when Jina leaves nav above the release block
    trimmed = re.sub(
        r"(?m)^#\s+[^|\n]{8,220}\|\s*News & Announcements\s*\|\s*San Jose Police Department, CA\s*$",
        "",
        trimmed,
    ).strip()
    end_markers = (
        r"Return to full list",
        r"(?m)^\s*Click to submit a tip anonymously",
        r"(?m)^\s*Archived News\s*:",
        r"(?m)^\s*Contact the Media Relations Unit",
        r"(?m)^\s*Older News:\s*\(Prior to",
        r"(?m)^\s*PRESS RELEASE, According to Cal Govt",
        r"(?m)\]\(https?://nextdoor\.com/",
        r"(?m)^\s*OUR MISSION:",
        r"(?m)^\s*E-Government Policy",
        r"(?m)^\s*Created By Granicus",
        r"(?m)^\s*###\s+Stay Connected",
        r"(?m)^\s*Powered by Translate",
        r"(?m)^Skip to Main Content",
        r"(?m)^\[Home\]\(",
        r"(?m)^Online Services\s*\+",
        r"(?m)^Join SJPD\s*$",
        r"(?m)^Phone Directory\b",
    )
    end_at: int | None = None
    for marker in end_markers:
        m = re.search(marker, trimmed)
        if m and m.start() > 400 and (end_at is None or m.start() < end_at):
            end_at = m.start()
    if end_at is not None:
        trimmed = trimmed[:end_at].strip()
    lines = []
    for line in trimmed.splitlines():
        s = line.strip()
        if not s:
            lines.append("")
            continue
        if re.match(r"^!\[[^\]]*\]\([^)]+\)\s*$", s):
            continue
        if re.match(r"^\[\]\(https?://", s):
            continue
        if s.startswith("*   [") or (s.startswith("+") and "[" in s):
            continue
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


_TROOPERS_MONTH = (
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
)
_TROOPERS_LEDE_RE = re.compile(
    r"(?m)^(?:On\s+"
    + _TROOPERS_MONTH
    + r"\s+\d{1,2},\s+\d{4},?\s+"
    r"(?:the\s+|members of the\s+)?(?:New York State Police|State Police)\b"
    r"|The New York State Police (?:announce|arrest|investigated|received|conducted)\b"
    r"|(?:On\s+"
    + _TROOPERS_MONTH
    + r"\s+\d{1,2},\s+\d{4},?\s+State Police in\b))",
    re.I,
)
_TROOPERS_NAV_MARKERS = (
    "Troop Locator",
    "School and Community Outreach",
    "Ticket Inquiries",
    "Crime Laboratory System",
)


def _troopers_body_ok(body: str) -> bool:
    """Reject site nav masquerading as a press release."""
    b = (body or "").strip()
    if len(b) < THIN_HTML_RETRY_CHARS:
        return False
    if any(m in b for m in _TROOPERS_NAV_MARKERS):
        return False
    if re.match(r"(?m)^#\s+New York State Police\s*$", b):
        return False
    return bool(_TROOPERS_LEDE_RE.search(b) or re.search(r"(?i)\b(?:arrested|indicted|charged)\b", b))


def _trim_troopers_jina_body(body: str) -> str:
    """
    troopers.ny.gov (NY Drupal) via Jina: global nav, NY.gov trust banner, translate
    widget, and recruiting copy wrap the actual press-release lede.
    """
    if not (body or "").strip():
        return body
    trimmed = body
    trimmed = re.sub(
        r"(?is)Skip to main content.*?Share sensitive information only on official, secure websites\.\s*",
        "\n",
        trimmed,
    )
    trimmed = re.sub(
        r"(?is)An official website of New York State\.\s*Here's how you know.*?secure websites\.\s*",
        "\n",
        trimmed,
    )
    trimmed = re.sub(
        r"(?is)We are now accepting applications for the NYS Trooper Entrance Exam!.*?(?=\n)",
        "\n",
        trimmed,
        count=1,
    )
    lede = _TROOPERS_LEDE_RE.search(trimmed)
    if not lede:
        return ""
    start = lede.start()
    window = trimmed[max(0, start - 900) : start]
    headlines = list(
        re.finditer(
            r"(?m)^#\s+(?!Accident Reports|Employment|Contact Us|New York State Police\b)[^\n|]{12,220}\s*$",
            window,
        )
    )
    if headlines:
        start = max(0, start - 900) + headlines[-1].start()
    trimmed = trimmed[start:].strip()
    end_at: int | None = None
    for marker in (
        r"(?m)^##\s+Contact Troop\b",
        r"(?m)^\*\*Troop [A-Z] Commander:\*\*",
        r"(?m)^Accident Reports\s*$",
        r"(?m)^TraCS\s*$",
        r"(?m)^Employment\s*$",
        r"(?m)^Become a Trooper\s*$",
        r"(?m)^Agencies\s*$",
        r"(?m)^Facebook\s*$",
        r"(?m)^Translate\s*$",
        r"(?m)^\[\]\(https?://troopers\.ny\.gov/news/",
        r"(?m)^Toggle navigation",
        r"(?m)^\s*Troopers\s*$",
    ):
        m = re.search(marker, trimmed)
        if m and m.start() > 200 and (end_at is None or m.start() < end_at):
            end_at = m.start()
    if end_at is not None:
        trimmed = trimmed[:end_at].strip()
    lines: list[str] = []
    for line in trimmed.splitlines():
        s = line.strip()
        if not s:
            lines.append("")
            continue
        if re.match(r"^\[\]\(https?://", s):
            continue
        if "Here's how you know" in s or s.startswith("Official websites use"):
            continue
        if re.match(
            r"^(Accident Reports|TraCS|Employment|Agencies|Contact Us|Troopers|Traffic|Firearms)$",
            s,
        ):
            break
        if re.match(r"^(Criminal Investigation|Specialty Units|Prevention and Preparedness)$", s):
            continue
        lines.append(re.sub(r"\s*\|\s*New York State Police\s*$", "", line))
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return out if _troopers_body_ok(out) else ""


_NJOAG_NAV_MARKERS = (
    "Recent Posts",
    "Divisions & Offices",
    "Meet Attorney General",
    "File a Complaint",
    "All Posts",
    "Grant Opportunities",
    "Public Records Request",
)


def _njoag_body_ok(body: str) -> bool:
    b = (body or "").strip()
    if len(b) < THIN_HTML_RETRY_CHARS:
        return False
    if sum(1 for m in _NJOAG_NAV_MARKERS if m in b) >= 2:
        return False
    return bool(
        re.search(r"(?m)^TRENTON\s*[\u2014\u2013\-]", b)
        or re.search(r"(?i)Attorney General .{0,80} announced", b)
        or re.search(r"(?i)\b(?:indicted|arrested|charged|convicted|sentenced)\b", b)
    )


_NJOAG_EXCLUDE_SLUG_RE = re.compile(
    r"(?:"
    r"sues-|"
    r"civil-rights|division-on-civil-rights|announce-final-decision|"
    r"state-board-of-medical-examiners-revokes|"
    r"board-of-nursing-permanently-revokes|"
    r"nj-board-of-nursing-temporarily-suspends-certification|"
    r"revocation-of-professional-licenses|"
    r"urges-congress|demands-immediate-action|demands-state-board|"
    r"deepfake|tells-tech-industry|"
    r"attorneys-general-are-calling|"
    r"leadership-transition|assumes-control-of-the|to-lead-the-office-of|"
    r"updates-how-forensic|"
    r"orders-sweeping-reforms|"
    r"establishes-task-force-to-investigate-alleg"
    r")",
    re.I,
)

_NJOAG_CONTAMINATION_TAIL_PATTERNS = (
    r"[\x0c\f]\s*\n[^\n]{15,220}\s*-\s*New Jersey Office of Attorney General",
    r"[\x0c\f]\s*\n(?:AG|Attorney General|Acting AG)[^\n]{15,220}\n[A-Z][a-z]+ \d{1,2}, \d{4}",
    r"[\x0c\f]\s*\n[A-Z][^\n]{20,200}\n[A-Z][a-z]+ \d{1,2}, \d{4}\s*$",
    r"[\x0c\f]\s*\n[A-Z][^\n]{20,200}\n[A-Z][a-z]+ \d{1,2}, \d{4}\s*\n",
    r"^Publication date: \d{4}-\d{2}-\d{2}\s*$",
    r"[\x0c\f]\s*[\u201c\"]Discord claims that safety is at the core",
    r"[\x0c\f]?\s*\nNew Jersey and Multistate Coalition ",
    r"[\x0c\f]\s*New Jersey and Multistate Coalition ",
    r"\n - New Jersey Office of Attorney\s*\nGeneral\s*$",
    r"[\x0c\f]?\s*\nAG Platkin Sues ",
    r"[\x0c\f]\s*AG Platkin Sues ",
    r"^AG Platkin Sues ",
    r"^[\u201c\"]Discord claims that safety is at the core",
    r"^[\u201c\"]By filing this lawsuit",
    r"^The lawsuit seeks a number of remedies",
    r"^As a result of the lawsuit, DOJ has now agreed",
    r"[\x0c\f]\s*As a result of the lawsuit, DOJ has now agreed",
    r"^The lawsuit, filed by the coalition on Tuesday",
    r"[\x0c\f]\s*The lawsuit, filed by the coalition on Tuesday",
    r"\n[A-Z][^\n]{20,180}\n[A-Z][a-z]+ \d{1,2}, \d{4}\s*$",
    r"[\x0c\f]?\s*\nAG Platkin Tells Tech ",
    r"^AG Platkin Tells Tech ",
    r"\nhttps://www\.njoag\.gov/",
    r"\nSource:\s*https://www\.njoag\.gov/",
    r"^Source:\s*https://www\.njoag\.gov/",
)


def is_njoag_icac_url(url: str) -> bool:
    """Drop lawsuits, license revocations, policy letters, and civil-rights releases."""
    path = urlparse(url or "").path.strip("/")
    if not path or path == "child-protection":
        return False
    slug = path.split("/")[-1]
    return not _NJOAG_EXCLUDE_SLUG_RE.search(slug)


def filter_njoag_icac_urls(urls: list[str]) -> list[str]:
    return [u for u in urls if is_njoag_icac_url(u)]


def extract_njoag_urls_from_merged_text(text: str) -> list[str]:
    """Rebuild full njoag.gov URLs from merged PDF text (handles wrapped Source: lines)."""
    urls: list[str] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        m = re.match(r"^Source:\s*(https://www\.njoag\.gov/\S*)", lines[i])
        if m:
            url = m.group(1).strip()
            j = i + 1
            while j < len(lines):
                nxt = lines[j].strip()
                if not nxt:
                    j += 1
                    continue
                if (
                    nxt.startswith("Source:")
                    or nxt.startswith("Office of")
                    or nxt.startswith("TRENTON")
                    or nxt.startswith("Media Inquiries")
                ):
                    break
                if re.match(r"^[-a-z0-9%]+/?$", nxt) or (
                    nxt.startswith("-") and " " not in nxt
                ):
                    url += nxt.lstrip("-") if nxt.startswith("-") else nxt
                    j += 1
                    continue
                break
            urls.append(url.rstrip("/").split()[0])
            i = j
            continue
        i += 1
    return sorted(set(urls))


def _cut_njoag_contamination(body: str, *, min_chars: int = 200) -> str:
    """Remove next-article bleed, site footers, and mid-merge press-release blocks."""
    if not body or len(body) < min_chars:
        return body
    text = body
    cut_at = len(text)

    m_tail = None
    for pat in _NJOAG_CONTAMINATION_TAIL_PATTERNS:
        m = re.search(pat, text[min_chars:], re.MULTILINE)
        if m and (m_tail is None or m.start() < m_tail.start()):
            m_tail = m
    if m_tail:
        cut_at = min(cut_at, min_chars + m_tail.start())

    trenton = list(re.finditer(r"(?m)^TRENTON\s*[\u2014\u2013\-]", text))
    if len(trenton) >= 2 and trenton[1].start() > min_chars:
        cut_at = min(cut_at, trenton[1].start())

    mastheads = list(
        re.finditer(r"(?m)^Office of (?:The )?Attorney General\s*[\u2013\-]", text)
    )
    if len(mastheads) >= 2 and mastheads[1].start() > min_chars:
        cut_at = min(cut_at, mastheads[1].start())

    if cut_at < len(text):
        text = text[:cut_at].rstrip()
    return text


def _strip_njoag_trailing_headline_bleed(text: str) -> str:
    """Drop orphan next-article title lines left after date/footer cuts."""
    bleed_prefixes = (
        "AG ",
        "Attorney General ",
        "Acting AG ",
        "Sussex County ",
        "Middlesex County ",
        "Passaic County ",
        "Two Officers ",
        "College Student ",
    )
    while text.strip():
        lines = text.rstrip().split("\n")
        last = lines[-1].strip()
        if not last or last.startswith("http"):
            break
        if re.match(r"^[A-Z][a-z]+ \d{1,2}, \d{4}$", last):
            text = "\n".join(lines[:-1]).rstrip()
            continue
        if (
            len(last) > 25
            and last[-1] not in ".!?;:"
            and "counsel" not in last.lower()
            and "Esq." not in last
            and any(last.startswith(p) for p in bleed_prefixes)
        ):
            text = "\n".join(lines[:-1]).rstrip()
            continue
        break
    return text


def _clean_njoag_scraped_body(body: str) -> str:
    """Final pass before PDF write: strip contamination Jina/HTML trim can miss."""
    if not (body or "").strip():
        return body
    text = re.sub(r"\r\n?", "\n", body).strip()
    text = re.sub(r"(?m)^Publication date: \d{4}-\d{2}-\d{2}\s*\n?", "", text)
    text = _cut_njoag_contamination(text)
    text = re.sub(r"[\x0c\f]+", "\n", text)
    text = re.sub(r"\n[A-Z][a-z]+ \d{1,2}, \d{4}\s*$", "", text)
    text = _strip_njoag_trailing_headline_bleed(text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


_SINCLAIR_BROADCAST_HOSTS = (
    "cbs12.com",
    "wpbf.com",
    "wptv.com",
    "cbsnews.com",
)


def _is_sinclair_broadcast_url(url: str) -> bool:
    host = urlparse(url or "").netloc.lower().removeprefix("www.")
    return any(host == h or host.endswith("." + h) for h in _SINCLAIR_BROADCAST_HOSTS)


_SOUTH_FLORIDA_NEWS_HOSTS = (
    "cbs12.com",
    "local10.com",
    "nbcmiami.com",
    "wsvn.com",
    "wpbf.com",
    "wptv.com",
    "cbsnews.com",
    "alachuachronicle.com",
    "gulfcoastnewsnow.com",
    "palmbeachpost.com",
    "fdle.state.fl.us",
    "dhs.gov",
    "coconutcreektalk.com",
    "coralspringstalk.com",
    "margatetalk.com",
    "tamaractalk.com",
    "kvia.com",
    "mbtimes.com.au",
)


def _is_south_florida_news_url(url: str) -> bool:
    host = urlparse(url or "").netloc.lower().removeprefix("www.")
    return any(host == h or host.endswith("." + h) for h in _SOUTH_FLORIDA_NEWS_HOSTS)


def _trim_south_florida_regional_news_body(body: str, url: str = "") -> str:
    """
    Regional ICAC news syndication (CBS12/Sinclair, Local10, NBC6, WSVN, etc.):
    drop site-wide breaking-news tickers, nav rails, footer CTAs, and duplicate bodies.
    """
    if not (body or "").strip():
        return body
    host = urlparse(url or "").netloc.lower().removeprefix("www.")
    trimmed = body.strip()
    if re.search(r"(?i)page not found|our apologies, the content you requested cannot be found", trimmed):
        return ""

    # Sinclair/CBS12 site-wide alert strip (e.g. F-15 airman rescue) before the dateline
    trimmed = re.sub(
        r"(?s)^(?:U\.S\. forces safely rescued.*?Friday\.\s*)+",
        "",
        trimmed,
        count=1,
    )
    trimmed = re.sub(
        r"(?m)^(?:U\.S\. forces safely rescued[^\n]{0,200}\n)+",
        "",
        trimmed,
    )

    # NBC6 streaming-channel chrome (full paragraph before the dateline, or inline in Jina rails)
    trimmed = re.sub(
        r"(?is)^You['\u2019]re watching the NBC6 South Florida News streaming channel.*?(?=\n\n[A-Z])",
        "",
        trimmed,
        count=1,
    )
    trimmed = re.sub(
        r"(?is)You['\u2019]re watching the NBC6 South Florida News streaming channel[^.\n]{0,800}\.",
        "",
        trimmed,
    )

    # CBS syndicated header line (keep article after it)
    trimmed = re.sub(
        r"(?m)^Updated on: [^\n]+ / CBS (?:Miami|Detroit|12)\s*\n?",
        "",
        trimmed,
        count=1,
    )

    # ICE.gov archive boilerplate when linked from SF ICAC index
    trimmed = re.sub(
        r"(?is)^In an effort to keep ICE\.gov current, the archive contains content from a previous.*?\.gov\s*\n+",
        "",
        trimmed,
        count=1,
    )

    start_at: int | None = None
    if host == "wsvn.com":
        m = re.search(r"(?m)^[A-Z][A-Z\s,\./\(\)]+\(WSVN\)\s", trimmed)
        if m:
            start_at = m.start()
    elif host.endswith("talk.com"):
        for pat in (
            r"(?m)^_By [A-Z][a-z]+ [A-Z][a-z]+_\s*$",
            r"(?m)^A Google cyber tip led to",
            r"(?m)^On (?:July|August|October|November|December|January|February|March|April|May|June)\s+\d",
        ):
            m = re.search(pat, trimmed)
            if m and (start_at is None or m.start() < start_at):
                start_at = m.start()
    elif host == "local10.com":
        m = re.search(r"(?m)^[A-Z][A-Za-z .'\-/]+, Fla\. — ", trimmed)
        if m:
            start_at = m.start()
    else:
        for pat in (
            r"(?m)^(?:Published: )?[A-Z][A-Za-z .'\-/]+, (?:Fla\.|Florida|FLA\.)\s",
            r"(?m)^[A-Z][A-Za-z .'\-/]+, (?:Fla\.|Florida|FLA\.)\s*(?:\([A-Z0-9]+\)|—|-)",
            r"(?m)^(?:Staff report\s+)?[A-Z][A-Za-z .'\-/]+, Fla\. – ",
            r"(?m)^Tags: [^\n]+(?:Fla\.|Florida)",
            r"(?m)^[A-Z][A-Z\s,\./\(\)]+(?:\(CBS12\)|\(WFOR\)|\(WSVN\)|\(WPLG\)|\(WPBF\)|\(WPTV\))\s*[—–-]",
            r"(?m)^(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\s*$",
            r"(?m)^By [A-Z][a-z]+ [A-Z][a-z]+\s",
            r"(?m)^[A-Z][A-Za-z .'\-/]+ — ",
        ):
            m = re.search(pat, trimmed)
            if m and (start_at is None or m.start() < start_at):
                start_at = m.start()
    if start_at is not None and start_at > 0:
        trimmed = trimmed[start_at:].strip()

    end_at: int | None = None
    for marker in (
        r"(?i)Find more ways to stay up to date with your latest local news",
        r"(?i)Sign up for our newsletter",
        r"(?i)Subscribe to our YouTube channel",
        r"(?i)Hidden predators in school",
        r"(?m)^## Related\b",
        r"(?m)^## Trending\b",
        r"(?m)^Today['\u2019]s Top Stories\b",
        r"(?m)^Page not found\b",
        r"(?i)Articles about arrests are based on reports from law enforcement agencies",
        r"(?m)^GAINESVILLE, Fla\. – .+\n\nGAINESVILLE, Fla\. – ",
        r"(?m)^Copyright 20\d{2} by WPLG",
        r"(?m)^_Copyright 20\d{2}",
        r"(?m)^### Around the Web\b",
        r"(?m)^Join our Newsletter\b",
        r"(?m)^#### Author Profile\b",
        r"(?i)Got News in (?:Margate|Coconut Creek|Coral Springs|Parkland|Tamarac)",
        r"(?m)^###### About The Author\b",
        r"(?m)^#### Marketplace\b",
        r"(?m)^Powered by\s*$",
        r"(?m)^BACK TO TOP\b",
        r"(?m)^Sunbeam Television Corporation\b",
    ):
        m = re.search(marker, trimmed)
        if m and m.start() > 200 and (end_at is None or m.start() < end_at):
            end_at = m.start()
    if end_at is not None:
        trimmed = trimmed[:end_at].strip()

    _junk_line = re.compile(
        r"(?i)^("
        r"share|"
        r"\d+ shares|"
        r"video \d+|"
        r"video player is loading|"
        r"play video|"
        r"play|"
        r"mute|"
        r"current time \d|"
        r"duration \d|"
        r"stream type live|"
        r"playback rate|"
        r"fullscreen cast to chromecast|"
        r"close modal dialog|"
        r"this is a modal window|"
        r"beginning of dialog window|"
        r"chapters|"
        r"descriptions|"
        r"captions|"
        r"quality levels|"
        r"native, selected|"
        r"cc1 captions|"
        r"audio track|"
        r"seek to live|"
        r"remaining time|"
        r"loaded: \d|"
        r"^\[\]\(https?://"
        r")$",
    )
    lines: list[str] = []
    for line in trimmed.splitlines():
        s = line.strip()
        if not s:
            lines.append("")
            continue
        if _junk_line.match(s):
            continue
        if re.match(r"(?i)^see also:", s):
            continue
        if re.search(r"(?m)(?:^|\s)\d+\.\s+\w", s) and len(re.findall(r"\d+\.\s+\w", s)) >= 3:
            continue
        if re.match(r"^\[\]\(https?://", s):
            continue
        if re.search(r"(?i)sellwild\.com|search by queryly|Advanced Search", s):
            break
        lines.append(line)
    trimmed = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()

    trimmed = _dedupe_news_delaware_paragraph_blocks(trimmed)
    trimmed = re.sub(r"\n{3,}", "\n\n", trimmed).strip()
    return trimmed


def _trim_njoag_body(body: str) -> str:
    """njoag.gov press releases: trim masthead metadata and Jina site chrome."""
    if not (body or "").strip():
        return body
    trimmed = body
    trimmed = re.sub(
        r"(?is)Skip to main content.*?Share sensitive information only on official, secure websites\.\s*",
        "\n",
        trimmed,
    )
    start_at: int | None = None
    for pat in (
        r"(?m)^TRENTON\s*[\u2014\u2013\-]\s*\*?\*?",
        r"(?m)^FOR IMMEDIATE RELEASE\s*$",
        r"(?m)^\*\*?FOR IMMEDIATE RELEASE\*\*?\s*$",
    ):
        m = re.search(pat, trimmed)
        if m and (start_at is None or m.start() < start_at):
            start_at = m.start()
    if start_at is not None and start_at > 0:
        trimmed = trimmed[start_at:].strip()
    else:
        m = re.search(
            r"(?m)^#\s+(?!Home|Divisions|About|Media)[^\n|]{20,240}\s*$",
            trimmed,
        )
        if m:
            trimmed = trimmed[m.start() :].strip()
    end_at: int | None = None
    for marker in (
        r"(?m)^Recent Posts\s*$",
        r"(?m)^Categories:\s*$",
        r"(?m)^All Posts\s*$",
        r"(?m)^Share on Facebook\s*$",
        r"(?m)^\*\*Related\*\*",
        r"(?m)^Divisions\s*$",
        r"(?m)^Initiatives\s*$",
        r"(?m)^Media Inquiries",
        r"(?m)^\[\]\(https?://www\.njoag\.gov/",
        r"[\x0c\f]\s*\n[^\n]{15,220}\s*-\s*New Jersey Office of Attorney General",
        r"(?m)^Publication date: \d{4}-\d{2}-\d{2}\s*$",
    ):
        m = re.search(marker, trimmed)
        if m and m.start() > 250 and (end_at is None or m.start() < end_at):
            end_at = m.start()
    if end_at is not None:
        trimmed = trimmed[:end_at].strip()
    trimmed = _cut_njoag_contamination(trimmed)
    lines: list[str] = []
    for line in trimmed.splitlines():
        s = line.strip()
        if not s:
            lines.append("")
            continue
        if re.match(r"^\[\]\(https?://", s):
            continue
        if s.startswith("by NJOAG Communications") or s.startswith("Media Inquiries"):
            continue
        if re.match(r"^(Divisions|About|Initiatives|Media|Home)\s*$", s):
            break
        lines.append(line)
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    out = _clean_njoag_scraped_body(out)
    return out if _njoag_body_ok(out) else ""


def _trim_ice_gov_jina_body(body: str) -> str:
    """
    ice.gov (USWDS/Drupal) via Jina: full site nav, mega-menu, and mobile footer
    precede the release dateline and article body.
    """
    if not (body or "").strip():
        return body
    trimmed = body
    start_patterns = (
        r"(?m)^[A-Z][a-z]+ \d{1,2}, \d{4} .{2,120}United States (?:Child Exploitation|Enforcement and Removal|Human Trafficking)\s*$",
        r"(?m)^[A-Z][A-Z\s,\.]{3,60} – ",
        r"(?m)^[A-Z][A-Z\s,\.]{3,60} - ",
        r"(?m)^\*\*FOR IMMEDIATE RELEASE\*\*\s*$",
        r"(?m)^FOR IMMEDIATE RELEASE\s*$",
        r"(?m)^#\s+[^|\n]{12,220}\|\s*ICE\s*$",
    )
    for pat in start_patterns:
        m = re.search(pat, trimmed)
        if m and m.start() > 0:
            trimmed = trimmed[m.start() :].strip()
            break
    # Drop duplicate article H1 when dateline start left a trailing title line
    trimmed = re.sub(
        r"(?m)^#\s+[^|\n]{12,220}\|\s*ICE\s*\n+",
        "",
        trimmed,
        count=1,
    ).strip()
    end_markers = (
        r"(?m)^Updated:\s*\d",
        r"(?m)^### Media Inquiries",
        r"(?m)^## ICE USWDS Footer",
        r"(?m)^\[Return to top\]",
        r"(?m)^You have been selected to participate",
        r"(?m)^## Mobile Menu",
        r"(?m)^## Main Navigation on Mobile",
        r"(?m)^\[Close menu\]",
        r"(?m)^Search Search\s*$",
        r"(?m)^\[AddToAny\]",
    )
    end_at: int | None = None
    for marker in end_markers:
        m = re.search(marker, trimmed)
        if m and m.start() > 350 and (end_at is None or m.start() < end_at):
            end_at = m.start()
    if end_at is not None:
        trimmed = trimmed[:end_at].strip()
    lines: list[str] = []
    for line in trimmed.splitlines():
        s = line.strip()
        if not s:
            lines.append("")
            continue
        if re.match(r"^!\[[^\]]*\]\([^)]+\)\s*$", s):
            continue
        if re.match(r"^\[\]\(https?://", s):
            continue
        if s.startswith("*   [") or (s.startswith("+") and "[" in s):
            continue
        if re.match(r"^#{1,6}\s+(About Us|Enforcement and Removal|Homeland Security|Newsroom)\s*$", s):
            continue
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _justice_pr_url_from_blob(blob: str) -> str | None:
    """NCIS press pages often only link to a USAO press release on justice.gov."""
    m = re.search(r"https://www\.justice\.gov/usao-[a-z]+/pr/[a-z0-9\-]+", blob or "", re.I)
    return m.group(0).rstrip(".,)>]") if m else None


def _ncis_doj_follow_url(
    page_url: str, body: str, *blobs: str | None
) -> str | None:
    """Return justice.gov PR URL when NCIS page is a shell or press-release stub."""
    if "ncis.navy.mil" not in (page_url or "").lower():
        return None
    doj_url: str | None = None
    for blob in blobs:
        if blob:
            doj_url = _justice_pr_url_from_blob(blob)
            if doj_url:
                break
    if not doj_url:
        return None
    b = (body or "").strip()
    if "/Press-Releases/" in page_url or len(b) < 400:
        return doj_url
    if re.search(
        r"Site Map\s*\|.*Privacy|Facebook X Email Share|Read the full DOJ",
        b,
        re.I,
    ):
        return doj_url
    return None


def _trim_justice_gov_jina_body(body: str) -> str:
    """USAO press releases on justice.gov: drop site chrome and related-articles rail."""
    if not (body or "").strip():
        return body
    trimmed = body
    start = None
    for pat in (
        r"(?m)^\*\*For Immediate Release\*\*",
        r"(?m)^[A-Z][A-Za-z .'-]+,\s+[A-Z]{2}\.?\s*–\s",
        r"(?m)^[A-Z][A-Za-z .'-]+,\s+[A-Z][a-z]+\s+–\s",
        r"(?m)^ALEXANDRIA,\s+Va\.\s*–",
    ):
        m = re.search(pat, trimmed)
        if m:
            start = m.start()
            break
    if start is not None and start > 0:
        trimmed = trimmed[start:].strip()
    for marker in (
        "\n## Related Content",
        "\n**Topic**",
        "\nInformation for Victims in Large Cases",
        "\nMain Menu",
        "\nWhy Justice ?",
        "\nSkip to main content",
        "\nAn official website of the United States government",
    ):
        j = trimmed.find(marker)
        if j > 200:
            trimmed = trimmed[:j].strip()
            break
    m = re.search(r"(?m)^Updated\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d", trimmed)
    if m and m.start() > 200:
        trimmed = trimmed[: m.start()].strip()
    return re.sub(r"\n{3,}", "\n\n", trimmed).strip()


def _trim_ncis_jina_body(body: str) -> str:
    """NCIS news articles: drop nav; keep quoted lede / dateline blocks."""
    if not (body or "").strip():
        return body
    trimmed = body
    for pat in (
        r'(?m)^_"',
        r"(?m)^[A-Z][a-z]+,\s+[A-Z]{2}\.\s*–",
        r"(?m)^\*\*[A-Z][a-z]+,\s+[A-Z]{2}\.\s*–",
        r"(?m)^[A-Z][a-z]+ \d{1,2}, \d{4}\s*$",
    ):
        m = re.search(pat, trimmed)
        if m and m.start() > 0:
            trimmed = trimmed[m.start() :].strip()
            break
    return re.sub(r"\n{3,}", "\n\n", trimmed).strip()


_CBP_NAV_MARKERS = re.compile(
    r"(?m)^(?:### Travel|Enter Search Term|Visa Waiver Program|Trusted Traveler|"
    r"Skip to main content|Countdown to America)",
    re.I,
)


def _cbp_release_body_score(text: str) -> int:
    """Prefer slices that look like a press release, not site chrome."""
    head = (text or "")[:900]
    if _CBP_NAV_MARKERS.search(head):
        return -10_000
    if "skip to main content" in head.lower():
        return -10_000
    score = min(len(text), 12_000)
    if re.search(r"child|sexual|predator|assault|csam|molest", text, re.I):
        score += 800
    if re.search(
        r"(?m)^[A-Z][A-Za-z .'-]+,\s+(?:[A-Z]{2}|[A-Za-z]+)\s*[-–—]",
        text,
    ):
        score += 400
    return score


def _cbp_slice_from_dateline(body: str, start: int) -> str:
    chunk = body[start:].strip()
    for marker in (
        "\nLast Modified:",
        "\nLast Updated:",
        "\n## Media Contacts",
        "\n### Media Contacts",
        "\nTopics",
        "\n### Media & Public",
        "\nSite Map",
        "\nCBP Seal",
        "\nEnter Search Term",
        "\n[Back to top]",
        "\nFollow the Director",
    ):
        j = chunk.find(marker)
        if j > 120:
            chunk = chunk[:j].strip()
            break
    return chunk


def _trim_cbp_jina_body(body: str) -> str:
    """CBP newsroom releases: pick best dateline block (nav often precedes article)."""
    if not (body or "").strip():
        return body
    candidates: list[str] = []
    for pat in (
        r"\*\*[A-Z][A-Za-z .'-]+,\s+[A-Za-z .'-]+\s*\*\*\s*[-–—]?\s*",
        r"\*\*[A-Z][A-Za-z .'-]{2,40}\*\*\s*[-–—]\s*",
        r"(?m)^\*\*[A-Z][A-Za-z .'-]+,\s+[A-Z]{2}\s*[-–—]\*\*",
        r"(?m)^[A-Z][A-Za-z .'-]+,\s+[A-Za-z .'-]+\s*[-–—]\s+",
        r"(?m)^[A-Z][A-Za-z .'-]+,\s+[A-Z]{2}\s*[-–—]\s+",
        r"(?m)^[A-Z][A-Z .'-]{3,40},\s+[A-Z]{2}\s*[-–—]\s+",
    ):
        for m in re.finditer(pat, body):
            candidates.append(_cbp_slice_from_dateline(body, m.start()))
    rel = re.search(
        r"(?m)^Release Date\s*\n+\w{3},\s+\d{1,2}/\d{1,2}/\d{4}\s*\n+",
        body,
    )
    if rel:
        candidates.append(_cbp_slice_from_dateline(body, rel.end()))
    if not candidates:
        m = re.search(
            r"(?m)^# [^\n]{12,}(?:child|sexual|predator|assault)[^\n]*\n+"
            r"(?:[^\n]*\n){0,8}?\*\*[A-Z]",
            body,
            re.I,
        )
        if m:
            tail = body[m.end() - 2 :]
            dm = re.search(
                r"\*\*[A-Z][A-Za-z .'-]+,\s+[A-Za-z .'-]+\s*\*\*\s*[-–—]?\s*",
                tail,
            )
            if dm:
                candidates.append(_cbp_slice_from_dateline(tail, dm.start()))
    if not candidates:
        return body
    best = max(candidates, key=_cbp_release_body_score)
    return re.sub(r"\n{3,}", "\n\n", best).strip()


def _cbp_body_ok(body: str) -> bool:
    if len((body or "").strip()) < MIN_BODY_CHARS:
        return False
    if _CBP_NAV_MARKERS.search(body[:1000]):
        return False
    if "skip to main content" in body[:500].lower():
        return False
    return bool(re.search(r"child|sexual|predator|assault|csam|molest", body, re.I))


_USMS_NAV_MARKERS = re.compile(
    r"(?m)^(?:## Office of Public Affairs|Usms\.mediadesk@|Skip to main content|"
    r"An official website of the United States government|Search Search\s*$)",
    re.I,
)


def _usms_slice_from_start(body: str, start: int) -> str:
    chunk = body[start:].strip()
    for marker in (
        "\n## Related",
        "\n### Related",
        "\nRelated Content",
        "\nMedia Contact",
        "\n## Media Contact",
        "\n[Back to top]",
        "\nAmerica's First Federal",
        "\nAn official website of the United States government",
        "\nusmarshals.gov is an official site",
    ):
        j = chunk.find(marker)
        if j > 120:
            chunk = chunk[:j].strip()
            break
    return chunk


def _usms_release_body_score(text: str) -> int:
    head = (text or "")[:900]
    if "skip to main content" in head.lower():
        return -10_000
    if re.search(r"(?m)^Search Search", head):
        return -10_000
    score = min(len(text), 10_000)
    if re.search(r"child|minor|kidnap|sexual|predator|exploitation|molest|abduct", text, re.I):
        score += 800
    if re.search(r"U\.?S\.? Marshals|Marshals Service", text, re.I):
        score += 200
    return score


def _trim_usmarshals_jina_body(body: str) -> str:
    """USMS press releases via Jina: keep dateline through body."""
    if not (body or "").strip():
        return body
    candidates: list[str] = []
    for pat in (
        r"\*\*[A-Z][A-Za-z .'-]+,\s*[A-Z]{2}\*\*\s*[-–—]\s*",
        r"(?m)^FOR IMMEDIATE RELEASE\s*$",
        r"(?m)^## For immediate release\s*$",
        r"(?m)^[A-Z][a-z .'-]+,\s+[A-Z]{2}\s*[-–—]\s",
        r"(?m)^[A-Z][A-Z .'-]{4,60},\s+[A-Z]{2}\s*[-–—]\s",
    ):
        for m in re.finditer(pat, body, re.I):
            candidates.append(_usms_slice_from_start(body, m.start()))
    if not candidates:
        return _trim_usmarshals_postface(body)
    best = max(candidates, key=_usms_release_body_score)
    dm = re.search(r"\*\*[A-Z][A-Za-z .'-]+,\s*[A-Z]{2}\*\*\s*[-–—]\s*", best)
    if not dm:
        dm = re.search(r"(?m)^[A-Z][a-z .'-]+,\s+[A-Z]{2}\s*[-–—]\s+", best)
    if dm:
        best = best[dm.start() :]
    return _trim_usmarshals_postface(re.sub(r"\n{3,}", "\n\n", best).strip())


def _trim_usmarshals_postface(body: str) -> str:
    """Drop USMS site footer, share row, and nav that Jina appends after release text."""
    if not (body or "").strip():
        return body
    end_markers = (
        r"(?m)^#{2,4}\s*$",
        r"(?m)^America['\u2019]s First Federal Law Enforcement Agency\s*$",
        r"(?m)^Email Facebook\b",
        r"(?m)^Back to top\s*$",
        r"(?m)^WHO WE ARE\s*$",
        r"(?m)^- \[x\]\s*$",
        r"(?m)^Search Search\s*$",
        r"(?m)^##\s+Related\b",
        r"(?m)^###\s+Related\b",
        r"(?m)^Related Content\s*$",
        r"(?m)^##\s+Media Contact\b",
        r"(?m)^Media Contact\s*$",
        r"(?m)^An official website of the United States government\b",
        r"(?m)^usmarshals\.gov is an official site\b",
        r"(?m)^\[Back to top\]",
    )
    end_at: int | None = None
    for marker in end_markers:
        m = re.search(marker, body)
        if m and m.start() > 200 and (end_at is None or m.start() < end_at):
            end_at = m.start()
    trimmed = body[:end_at].strip() if end_at is not None else body.strip()
    lines: list[str] = []
    for line in trimmed.splitlines():
        s = line.strip()
        if not s:
            lines.append("")
            continue
        if re.match(r"^[-*]\s*\[x\]\s*$", s):
            continue
        if s in {
            "Back to top",
            "WHO WE ARE",
            "About Us",
            "Leadership",
            "History",
            "Contact Us",
            "District Offices",
            "Headquarters",
            "Office of Professional Responsibility",
            "Business with U.S. Marshals",
        }:
            continue
        if re.match(r"^U\.?S\.? Marshals['\u2019]? Biographies$", s):
            continue
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _usms_body_ok(body: str) -> bool:
    """Reject nav shells and empty Jina pages; URL lists are already topic-filtered."""
    if len((body or "").strip()) < MIN_BODY_CHARS:
        return False
    if "skip to main content" in body[:500].lower():
        return False
    if re.search(r"(?m)^Search Search", body[:600]):
        return False
    if _USMS_NAV_MARKERS.search(body[:1200]):
        return False
    return bool(re.search(r"U\.?S\.?\s*Marshals|Marshals Service", body, re.I))


def _trim_dod_news_jina_body(body: str) -> str:
    """Trim DOD/USG news article chrome (OSI, NCIS, Marshals, CBP via Jina)."""
    if not (body or "").strip():
        return body
    trimmed = body
    for pat in (
        r"(?m)^\*\*FOR IMMEDIATE RELEASE\*\*\s*$",
        r"(?m)^FOR IMMEDIATE RELEASE\s*$",
        r"(?m)^[A-Z][a-z]+ \d{1,2}, \d{4}\s*$",
        r"(?m)^[A-Z][A-Z\s,\.]{4,80} – ",
        r"(?m)^[A-Z][A-Z\s,\.]{4,80} - ",
        r"(?m)^[A-Z][a-z].{20,200}\n\n[A-Z]",
    ):
        m = re.search(pat, trimmed)
        if m and m.start() > 0 and m.start() < 8000:
            trimmed = trimmed[m.start() :].strip()
            break
    trimmed = re.sub(r"(?m)^#\s+[^|\n]{10,220}\|\s*[^\n]+\s*\n+", "", trimmed, count=1).strip()
    end_markers = (
        r"(?m)^###\s+Related",
        r"(?m)^##\s+Related",
        r"(?m)^Related Articles",
        r"(?m)^Media (?:Contact|Inquiries)",
        r"(?m)^Subscribe to",
        r"(?m)^Connect with",
        r"(?m)^\[Return to top\]",
        r"(?m)^## Footer",
        r"(?m)^An official website of the United States government",
        r"(?m)^\[Close menu\]",
        r"(?m)^Search Search\s*$",
    )
    end_at: int | None = None
    for marker in end_markers:
        m = re.search(marker, trimmed)
        if m and m.start() > 300 and (end_at is None or m.start() < end_at):
            end_at = m.start()
    if end_at is not None:
        trimmed = trimmed[:end_at].strip()
    lines: list[str] = []
    for line in trimmed.splitlines():
        s = line.strip()
        if not s:
            lines.append("")
            continue
        if re.match(r"^!\[", s) or re.match(r"^\[\]\(https?://", s):
            continue
        if s.startswith("*   [") or (s.startswith("+") and "[" in s):
            continue
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _trim_ice_gov_html_container(soup: BeautifulSoup) -> BeautifulSoup | None:
    """Return a copy of the ICE release body node without breadcrumb/share chrome."""
    root = (
        soup.select_one(".nr-body")
        or soup.select_one(".views-field-nothing-3 .field-content")
        or soup.select_one(".field--name-body .field__item")
        or soup.select_one(".field--name-body")
        or soup.select_one("#main-content .node__content")
        or soup.select_one("#main-content")
    )
    if not root:
        return None
    fragment = BeautifulSoup(str(root), "html.parser")
    for sel in (
        ".breadcrumb",
        ".share",
        "nav",
        "aside",
        ".usa-breadcrumb",
        ".block-system-breadcrumb-block",
    ):
        for tag in fragment.select(sel):
            tag.decompose()
    return fragment


def _trim_lvmpd_jina_body(body: str) -> str:
    """lvmpd.com (Granicus) via Jina: global nav then press release under FOR IMMEDIATE RELEASE."""
    if not (body or "").strip():
        return body
    trimmed = body
    for pat in (
        r"(?m)^\*\*FOR IMMEDIATE RELEASE\*\*\s*$",
        r"(?m)^A multi-agency operation targeting child",
        r"(?m)^The Nevada Internet Crimes Against Children",
        r"(?m)^LAS VEGAS,?\s+Nevada",
    ):
        m = re.search(pat, trimmed)
        if m:
            trimmed = trimmed[m.start() :].strip()
            break
    for marker in (
        r"(?m)^Anyone who may have been a victim",
        r"(?m)^We would like to remind parents",
        r"(?m)^###\s+Stay Connected",
        r"(?m)^Created By Granicus",
        r"(?m)^Loading \.\.\.",
        r"(?m)^Office of Public Information\s*$",
        r"(?m)^Skip to Main Content",
        r"(?m)^\[Home\]\(",
        r"(?m)^Online Services\s*\+",
    ):
        m = re.search(marker, trimmed)
        if m and m.start() > 400:
            trimmed = trimmed[: m.start()].strip()
            break
    lines = []
    for line in trimmed.splitlines():
        s = line.strip()
        if not s:
            lines.append("")
            continue
        if re.match(r"^\[\]\(https?://", s):
            continue
        if re.match(r"^!\[", s):
            continue
        if s.startswith("*   [") or s.startswith("+") and "[" in s:
            continue
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _trim_cid_army_jina_body(body: str) -> str:
    """
    cid.army.mil via Jina returns DOD trust banner, global nav, sidebars, and footer.
    Keep the press-release lede through SHARE/related-stories markers.
    """
    if not (body or "").strip():
        return body
    trimmed = body
    # Drop duplicate breadcrumb H1 ("> Department of the Army Criminal Investigation Division > Article Display")
    trimmed = re.sub(
        r"(?m)^#\s+.+\>\s*Department of the Army Criminal Investigation Division\s*\>\s*Article Display\s*$",
        "",
        trimmed,
    )
    # Start at visible dateline or "News |" row above the article H1
    start = None
    for pat in (
        r"(?m)^News\s*\|\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)",
        r"(?m)^(?:QUANTICO|Quantico|KIRTLAND|Kirtland|FORT HOOD|Fort Hood)[^\n]{0,80}-\s+\S",
        r"(?m)^#\s+[A-Z][^\n]{12,120}$",
    ):
        m = re.search(pat, trimmed)
        if m and (start is None or m.start() < start):
            start = m.start()
    if start is not None and start > 0:
        trimmed = trimmed[start:].strip()
    # If nav chrome remains above dateline, cut from first release paragraph
    m = re.search(
        r"(?m)^(?:[A-Z][A-Za-z\s,\.'-]{2,50},\s*(?:Va\.|Texas|N\.M\.|Colo\.|Hawaii)\s*-\s+|\*\*Press Release\*\*\s*\n)",
        trimmed,
    )
    if m and m.start() > 200:
        trimmed = trimmed[m.start() :].strip()
    for marker in (
        r"(?m)^\s*SHARE\s*$",
        r"(?m)^\s*PRINT\s*$",
        r"(?m)^###\s+Stay Connected",
        r"(?m)^##\s+Related Stories",
        r"(?m)^##\s+Related Press Advisories",
        r"(?m)^Previous Story\s*$",
        r"(?m)^Next Story\s*$",
        r"(?m)^Department of War\s*$",
        r"(?m)^Thanks for sharing!",
        r"(?m)^AddToAny\s*$",
        r"(?m)^Hosted by Department of War",
        r"(?m)^An official website of the United States government",
        r"(?m)^Here's how you know",
        r"(?m)^Skip to main content",
        r"(?m)^Toggle navigation",
        r"(?m)^Search Army CID:",
    ):
        m = re.search(marker, trimmed)
        if m and m.start() > 300:
            trimmed = trimmed[: m.start()].strip()
            break
    # Drop markdown link-only lines and image alt stubs
    lines = []
    for line in trimmed.splitlines():
        s = line.strip()
        if not s:
            lines.append("")
            continue
        if re.match(r"^!\[[^\]]*\]\([^)]+\)\s*$", s):
            continue
        if re.match(r"^\[\]\(https?://www\.cid\.army\.mil", s):
            continue
        if s in (")", "Home", "About Us )", "Media Resources )", "Crime Prevention )", "Contact Us )"):
            continue
        if re.match(r"^[-\[\]()]+$", s):
            continue
        lines.append(line)
    trimmed = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return trimmed


def _trim_dps_iowa_jina_body(body: str) -> str:
    """Iowa DPS (Drupal) via Jina often includes site nav, search, and footer; keep the release body."""
    if not (body or "").strip():
        return body
    lines = body.splitlines()
    start = 0
    for i, line in enumerate(lines):
        s = line.strip()
        if re.match(
            r"^(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}",
            s,
        ):
            start = i
            break
        if re.match(r"^DES MOINES,?\s+Iowa", s, re.I):
            start = i
            break
    trimmed = "\n".join(lines[start:]).strip()
    for marker in (
        "\n## Footer\n",
        "\n### Footer\n",
        "Oran Pape State Office Building",
        "\n## Connect with",
        "\n### Connect",
        "Share feedback with us",
        "© 20",
        "Google Translate",
    ):
        j = trimmed.find(marker)
        if j > 200:
            trimmed = trimmed[:j].strip()
            break
    return trimmed


def extract_from_jina_reader(markdown_blob: str, original_url: str) -> tuple[str, str, str, date | None] | None:
    """
    Parse r.jina.ai plain-text response (Title / URL Source / Published Time / Markdown Content).

    Host-specific cleanup trims full-page chrome for mass.gov and nmdoj.gov press pages before PDF layout.
    """
    blob = markdown_blob.lstrip()
    if not blob.startswith("Title:") or "Markdown Content:" not in blob:
        return None
    lines = markdown_blob.splitlines()
    title = ""
    pub: date | None = None
    body_start: int | None = None
    for i, line in enumerate(lines):
        if line.startswith("Title:"):
            title = line.split(":", 1)[1].strip()
        elif line.startswith("Published Time:"):
            pub = _parse_jina_published_time(line.split(":", 1)[1])
        elif line.startswith("Markdown Content:"):
            body_start = i + 1
            break
    if body_start is None:
        return None
    body_raw = "\n\n".join(lines[body_start:]).strip()
    if "mass.gov" in (original_url or "").lower():
        body_raw = re.sub(r"^\s*#+\s*.+\|\s*Mass\.gov\s*$", "", body_raw, flags=re.MULTILINE)
    if "nmdoj.gov" in (original_url or "").lower():
        body_raw = re.sub(
            r"^\s*#+\s*.+\-\s*New Mexico Department of Justice\s*$",
            "",
            body_raw,
            flags=re.MULTILINE | re.IGNORECASE,
        )
    body_raw = _strip_jina_embedded_images(body_raw)
    body = _unwrap_jina_markdown_links(body_raw)
    if "nmdoj.gov" in (original_url or "").lower():
        body = _trim_nmdoj_jina_preface(body)
    if "cbp.gov" in (original_url or "").lower():
        body = _trim_cbp_jina_body(body)
    if "usmarshals.gov" in (original_url or "").lower():
        body = _trim_usmarshals_jina_body(body)
    body = re.sub(r"\*\*([^*]+)\*\*", r"\1", body)
    body = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", body)
    if "mass.gov" in (original_url or "").lower():
        body = _trim_mass_gov_jina_preface(body)
        body = _trim_mass_gov_jina_postface(body)
    if "nmdoj.gov" in (original_url or "").lower():
        body = _trim_nmdoj_jina_postface(body)
    if "dps.iowa.gov" in (original_url or "").lower():
        body = _trim_dps_iowa_jina_body(body)
    if "sjpd.org" in (original_url or "").lower():
        body = _trim_sjpd_jina_body(body)
        if "|" in title:
            title = title.split("|", 1)[0].strip()
    if "lvmpd.com" in (original_url or "").lower():
        body = _trim_lvmpd_jina_body(body)
        if title.lower().endswith("| news list") or "| las vegas" in title.lower():
            title = title.split("|", 1)[0].strip()
    if "ice.gov" in (original_url or "").lower():
        body = _trim_ice_gov_jina_body(body)
        if "|" in title:
            title = title.split("|", 1)[0].strip()
    if "justice.gov" in (original_url or "").lower():
        body = _trim_justice_gov_jina_body(body)
        if "|" in title:
            title = title.split("|", 1)[0].strip()
    if "cbp.gov" in (original_url or "").lower():
        if not _cbp_body_ok(body):
            return None
        if "|" in title:
            title = title.split("|", 1)[0].strip()
    elif "usmarshals.gov" in (original_url or "").lower():
        if not _usms_body_ok(body):
            return None
        if "|" in title:
            title = title.split("|", 1)[0].strip()
    elif any(
        h in (original_url or "").lower()
        for h in ("osi.af.mil", "ncis.navy.mil")
    ):
        body = _trim_dod_news_jina_body(body)
        if "ncis.navy.mil" in (original_url or "").lower():
            body = _trim_ncis_jina_body(body)
        if "|" in title:
            title = title.split("|", 1)[0].strip()
    if "cid.army.mil" in (original_url or "").lower():
        body = _trim_cid_army_jina_body(body)
        if title.lower().startswith("404") or "article display" in title.lower():
            m = re.search(r"(?m)^#\s+(.+)$", body)
            if m:
                title = re.sub(r"\s*>.*$", "", m.group(1)).strip()
    if "news.delaware.gov" in (original_url or "").lower():
        body = _trim_news_delaware_duplicate_press_rail(body)
        body = _dedupe_news_delaware_paragraph_blocks(body)
    if "tbinewsroom.com" in (original_url or "").lower():
        body = _strip_wordpress_jetpack_share(body)
    if "troopers.ny.gov" in (original_url or "").lower():
        body = _trim_troopers_jina_body(body)
        if not body:
            return None
    if "njoag.gov" in (original_url or "").lower():
        body = _trim_njoag_body(body)
        if not body:
            return None
    if _is_south_florida_news_url(original_url or ""):
        body = _trim_south_florida_regional_news_body(body, original_url or "")
        if not body or len(body) < MIN_BODY_CHARS:
            return None
    if len(body) < MIN_BODY_CHARS:
        return None
    byline = pub.strftime("%B %d, %Y") if pub else ""
    return title or "Untitled", byline, body, pub


def _meta_content(soup: BeautifulSoup, *, prop: str | None = None, name: str | None = None) -> str:
    for sel, val in (("property", prop), ("name", name)):
        if not val:
            continue
        tag = soup.find("meta", attrs={sel: val})
        if tag and tag.get("content"):
            return str(tag["content"]).strip()
    return ""


def format_display_byline(pub_date: date | None, soup: BeautifulSoup | None) -> str:
    """Optional human date under the title (omit if we only have ISO publication line)."""
    if pub_date:
        return pub_date.strftime("%B %d, %Y")
    if soup is None:
        return ""
    raw = _meta_content(soup, prop="article:published_time") or _meta_content(
        soup, name="article:published_time"
    )
    raw = raw or _meta_content(soup, prop="og:published_time")
    if raw and len(raw) <= 120:
        return raw.strip()
    return ""


def _trim_ncsbi_news_body(raw: str) -> str:
    """
    ncsbi.gov press releases live in ``.NewsBody`` (div/font, rarely ``<p>``).
    Drop contact/masthead lines before the dateline lede.
    """
    text = re.sub(r"\r\n?", "\n", (raw or "").strip())
    if not text:
        return ""
    # Dateline may split across lines: "Raleigh, NC\\n– On Thursday..."
    text = re.sub(
        r"(?m)^([A-Za-z .'-]+,\s*NC)\s*\n\s*([\u2013\u2014\-]\s+)",
        r"\1 \2",
        text,
    )
    start = None
    for pat in (
        r"(?m)^\([A-Z][^\n]{3,120}\)\s*--\s+\S",
        r"(?m)^Raleigh,\s*NC\s*[\u2013\u2014\-]\s+\S",
        r"(?m)^[A-Z][A-Za-z .'-]+,\s*NC\s*[\u2013\u2014\-]\s+\S",
        r"(?m)^MEDIA ADVISORY\b",
        r"(?m)^FOR IMMEDIATE RELEASE\b",
    ):
        m = re.search(pat, text)
        if m and (start is None or m.start() < start):
            start = m.start()
    if start is not None:
        text = text[start:].strip()
    for marker in (
        "\nInvestigations\n",
        "\n© North Carolina",
        "\nDirector R.E.",
        "\nCrime Statistics",
    ):
        j = text.find(marker)
        if j > 120:
            text = text[:j].strip()
            break
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _extract_ncsbi_gov(soup: BeautifulSoup, url: str) -> tuple[str, str, str, date | None] | None:
    """North Carolina SBI news releases (``.NewsBody`` / ``.newsItemDetail``)."""
    title = ""
    if soup.title:
        raw = soup.title.get_text(strip=True)
        if raw.lower().startswith("ncsbi - "):
            title = raw[8:].strip()
        elif " - " in raw:
            title = raw.split(" - ", 1)[-1].strip()
        else:
            title = raw
    og = _meta_content(soup, prop="og:title") or _meta_content(soup, name="twitter:title")
    if og and len(og.strip()) >= 8:
        title = og.strip()

    node = soup.select_one(".NewsBody") or soup.select_one(".newsItemDetail")
    if not node:
        return None
    body = _trim_ncsbi_news_body(node.get_text("\n", strip=True))
    if len(body) < MIN_BODY_CHARS:
        return None
    pub_date = _first_dateline_date_in_text(body) or _first_dateline_date_in_text(
        node.get_text(" ", strip=True)
    )
    byline = format_display_byline(pub_date, soup)
    if not title:
        title = _title_from_url(url)
    return title.strip(), byline.strip(), body.strip(), pub_date


def _html_headline_title(soup: BeautifulSoup) -> str:
    """
    Prefer social meta (og/twitter): many WordPress/Avada pages repeat the site name in the
    first ``<h1>`` and put the article headline only in ``og:title`` / ``<title>``.

    If meta is missing, resolve ``<h1>``: when several leading ``h1``s share the same masthead
    text and the last ``h1`` differs (common on dojmt.gov), use the last one.
    """

    og = _meta_content(soup, prop="og:title") or _meta_content(soup, name="twitter:title")
    if og and len(og.strip()) >= 4:
        return og.strip()

    h1_texts = [h.get_text(" ", strip=True) for h in soup.find_all("h1") if h.get_text(strip=True)]
    if h1_texts:
        if (
            len(h1_texts) >= 2
            and h1_texts[0]
            and all(h == h1_texts[0] for h in h1_texts[:-1])
            and h1_texts[-1] != h1_texts[0]
        ):
            return h1_texts[-1]
        return h1_texts[0]

    if soup.title:
        raw = soup.title.get_text(strip=True)
        head = raw.split("|", 1)[0].strip()
        for sep in (" \u2013 ", " \u2014 ", " - "):  # en dash, em dash, spaced hyphen
            if sep in head:
                left, right = head.split(sep, 1)
                if len(left.strip()) >= 8 and len(right.strip()) >= 8:
                    return left.strip()
        return head
    return ""


def extract(html: str, url: str) -> tuple[str, str, str, date | None] | None:
    netloc = urlparse(url).netloc.lower()

    # ncsbi.gov puts release text inside a <form>; extract before form decompose below.
    if netloc in ("www.ncsbi.gov", "ncsbi.gov"):
        ncsbi = _extract_ncsbi_gov(BeautifulSoup(html, "html.parser"), url)
        if ncsbi:
            return ncsbi

    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(
        ["script", "style", "noscript", "iframe", "nav", "footer", "aside", "form", "button"]
    ):
        tag.decompose()

    netloc = urlparse(url).netloc.lower()

    title = _html_headline_title(soup).strip()
    if netloc == "www.fresnosheriff.org" or netloc == "fresnosheriff.org":
        if title.lower() in ("media relations",) or len(title) < 25:
            h2 = soup.select_one(".item-page h2") or soup.select_one(".com-content-article h2")
            if h2:
                title = h2.get_text(" ", strip=True)
            elif soup.title:
                raw = soup.title.get_text(strip=True)
                if " - " in raw:
                    title = raw.rsplit(" - ", 1)[-1].strip()
    if not title:
        slug = url.rstrip("/").split("/")[-1]
        title = slug.replace("-", " ").replace("_", " ").title()

    container = None
    if netloc == "news.delaware.gov":
        container = soup.select_one(".fusion-post-content") or soup.select_one(".post-content")
    elif netloc in ("www.fresnosheriff.org", "fresnosheriff.org"):
        container = (
            soup.select_one(".com-content-article.item-page")
            or soup.select_one(".item-page")
        )
    elif netloc in ("www.osceolasheriff.org", "osceolasheriff.org"):
        container = (
            soup.select_one(".l-main .entry-content")
            or soup.select_one(".entry-content")
            or soup.select_one(".l-main")
        )
    elif netloc == "dps.iowa.gov":
        container = (
            soup.select_one(".field--name-field-news__body .field__item")
            or soup.select_one(".field--name-field-news__body")
            or soup.select_one("div.node__content.news__inner.text-editor-content")
            or soup.select_one("div.node__content.news__inner")
        )
    elif netloc in ("www.lvmpd.com", "lvmpd.com"):
        container = (
            soup.select_one(".content.main-content")
            or soup.select_one("#pagebody")
            or soup.select_one("article")
            or soup.select_one(".fr-view")
        )
    elif netloc in ("www.sjpd.org", "sjpd.org"):
        container = (
            soup.select_one(".content.main-content")
            or soup.select_one("#pagebody")
            or soup.select_one("article")
            or soup.select_one(".fr-view")
        )
    elif netloc in ("riag.ri.gov", "www.riag.ri.gov"):
        container = (
            soup.select_one("article.press-release")
            or soup.select_one("article")
            or soup.select_one(".field--name-body")
            or soup.select_one("main")
        )
    elif netloc in ("www.njoag.gov", "njoag.gov"):
        container = (
            soup.select_one("article.type-post")
            or soup.select_one("article.post")
            or soup.select_one(".entry-content")
            or soup.select_one("article")
            or soup.select_one("main")
        )
    elif netloc in ("www.myfloridalegal.com", "myfloridalegal.com"):
        container = (
            soup.select_one("article.node--type-news-release")
            or soup.select_one("article")
            or soup.select_one(".field--name-body")
            or soup.select_one("main")
        )
    elif netloc in ("www.secretservice.gov", "secretservice.gov"):
        h1 = soup.select_one("h1")
        if h1:
            h1_text = h1.get_text(" ", strip=True)
            if h1_text and h1_text.lower() not in ("search this site",):
                title = h1_text
        container = (
            soup.select_one("article")
            or soup.select_one("main")
            or soup.select_one('[role="main"]')
        )
    elif netloc in ("www.ice.gov", "ice.gov"):
        og = _meta_content(soup, prop="og:title") or _meta_content(soup, name="twitter:title")
        if og:
            title = og.split("|", 1)[0].strip()
        if not title or title.lower() in ("ice", "newsroom"):
            h1 = soup.select_one("#main-content h1") or soup.select_one("main h1")
            if h1:
                title = h1.get_text(" ", strip=True)
        ice_root = _trim_ice_gov_html_container(soup)
        container = ice_root if ice_root is not None else (
            soup.select_one(".nr-body")
            or soup.select_one(".field--name-body .field__item")
            or soup.select_one("#main-content")
        )
    elif netloc in ("www.osi.af.mil", "osi.af.mil"):
        container = (
            soup.select_one(".article-body")
            or soup.select_one(".body-text")
            or soup.select_one("article")
            or soup.select_one("main")
        )
    elif netloc in ("www.ncis.navy.mil", "ncis.navy.mil"):
        container = (
            soup.select_one(".article-text")
            or soup.select_one(".body-text")
            or soup.select_one("article")
            or soup.select_one("main")
        )
    elif netloc in ("www.usmarshals.gov", "usmarshals.gov"):
        container = (
            soup.select_one(".field--name-body")
            or soup.select_one("article")
            or soup.select_one("main")
        )
    elif netloc in ("www.cbp.gov", "cbp.gov"):
        container = (
            soup.select_one(".field--name-body .field__item")
            or soup.select_one(".field--name-body")
            or soup.select_one("article")
            or soup.select_one("main")
        )
    elif _is_sinclair_broadcast_url(url):
        # Sinclair Next.js pages: generic ``*content*`` regex hits empty Expandable_content first.
        container = (
            soup.select_one('[class*="mainContent"]')
            or soup.select_one('[class*="contentColumnContainer"]')
            or soup.select_one('[class*="StoryPage"]')
        )

    if container is None:
        container = (
            soup.find("article")
            or soup.find("main")
            or soup.find(attrs={"role": "main"})
            or soup.find(class_=re.compile(r"content|body|field-body|article-body|post-body", re.I))
            or soup.body
        )
    if not container:
        return None

    paras = _ordered_body_blocks_from_container(container)
    paras = _collapse_consecutive_duplicate_paragraphs(paras)
    body = "\n\n".join(p for p in paras if len(p) > 30)
    if len(body) < MIN_BODY_CHARS:
        body = container.get_text("\n", strip=True)
    if len(body) < MIN_BODY_CHARS:
        return None

    if netloc == "news.delaware.gov":
        body = _trim_news_delaware_duplicate_press_rail(body)
        body = _dedupe_news_delaware_paragraph_blocks(body)

    if netloc in ("www.usmarshals.gov", "usmarshals.gov"):
        body = _trim_usmarshals_postface(body)

    if netloc in ("tbinewsroom.com", "www.tbinewsroom.com"):
        body = _strip_wordpress_jetpack_share(body)

    if netloc in ("troopers.ny.gov", "www.troopers.ny.gov"):
        if len(body) < THIN_HTML_RETRY_CHARS:
            return None

    if netloc in ("www.njoag.gov", "njoag.gov"):
        body = _trim_njoag_body(body)
        if not body:
            return None

    if _is_south_florida_news_url(url):
        body = _trim_south_florida_regional_news_body(body, url)
        if not body or len(body) < MIN_BODY_CHARS:
            return None

    pub_date = resolve_publication_date(soup, url, body)
    byline = format_display_byline(pub_date, soup)

    return title.strip(), byline.strip(), body.strip(), pub_date


def write_pdf(
    out_path: Path,
    title: str,
    byline: str,
    body: str,
    url: str,
    pub_date: date | None,
) -> bool:
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=LETTER,
        leftMargin=0.9 * inch,
        rightMargin=0.9 * inch,
        topMargin=0.85 * inch,
        bottomMargin=0.85 * inch,
    )
    story = [Paragraph(esc(title), _TITLE_S)]
    if byline:
        story.append(Paragraph(esc(byline), _META_S))
    if pub_date:
        story.append(
            Paragraph(esc(f"Publication date: {pub_date.isoformat()}"), _META_S)
        )
    story.append(Paragraph(f"Source: {esc(url)}", _SOURCE_S))
    story.append(
        HRFlowable(
            width="100%",
            thickness=0.5,
            color=colors.HexColor("#cccccc"),
            spaceAfter=8,
        )
    )
    for block in re.split(r"\n\s*\n+", body):
        block = block.strip()
        if block:
            story.append(Paragraph(esc(block), _BODY_S))
    try:
        doc.build(story)
        return True
    except Exception as e:
        print(f"    [pdf error] {e}", file=sys.stderr)
        return False


def merge(pdf_paths: list[Path], out_path: Path) -> bool:
    writer = PdfWriter()
    merged = 0
    for p in pdf_paths:
        try:
            for page in PdfReader(str(p)).pages:
                writer.add_page(page)
            merged += 1
        except Exception as e:
            print(f"  [merge warn] skip {p.name}: {e}", file=sys.stderr)
    if not merged:
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        writer.write(f)
    return True


def _per_url_cache_pdf(tmp_dir: Path, index: int, url: str) -> Path:
    """
    Per-URL cache filename under tmp_dir (index prefix keeps merge order).
    Avoids reusing slot ``0001.pdf`` from a different url-file (e.g. Anchorage vs Oregon).
    """
    h = hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:16]
    return tmp_dir / f"{index:04d}_{h}.pdf"


def _capture_success(
    *,
    out_dir: Path,
    per_url_pdf: Path,
    source_url: str,
    resource: FetchedResource,
    parser_name: str,
    normalized_text: str,
    published_at: date | None,
) -> dict | None:
    """Persist exact fetched bytes and the per-article ingest sidecar."""
    published_timestamp = (
        datetime(published_at.year, published_at.month, published_at.day, tzinfo=UTC)
        if published_at is not None
        else None
    )
    try:
        record = provenance.build_capture_record(
            source_url=source_url,
            content=resource.content,
            retrieved_at=resource.retrieved_at,
            mime_type=resource.content_type,
            http_status=resource.status_code,
            http_etag=resource.etag,
            http_last_modified=resource.last_modified,
            final_url=resource.final_url,
            parser_name=parser_name,
            parser_version="1",
            normalized_text=normalized_text,
            published_at=published_timestamp,
        )
        provenance.persist_capture_bytes(out_dir / "provenance", record, resource.content)
        provenance.write_capture_manifest(per_url_pdf, [record])
        return record
    except (OSError, TypeError, ValueError) as exc:
        print(f"    [provenance error] {exc}", file=sys.stderr)
        return None


def main():
    ap = argparse.ArgumentParser(
        description="Scrape HTML URLs from a list into one merged PDF.",
    )
    ap.add_argument("--url-file", type=Path, default=DEFAULT_URL_FILE)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--out-name", default=DEFAULT_OUT_NAME)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--delay", type=float, default=REQUEST_DELAY)
    ap.add_argument(
        "--referer",
        default=None,
        help="HTTP Referer header (default: origin of each URL).",
    )
    ap.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS certificate verification (use only if the host has chain issues).",
    )
    ap.add_argument(
        "--jina-fallback",
        action="store_true",
        help="If direct HTML fetch fails (e.g. 403), retry via https://r.jina.ai/ reader markdown.",
    )
    ap.add_argument(
        "--filter-njoag",
        action="store_true",
        help="Drop njoag.gov URLs that are lawsuits, license actions, policy letters, or civil-rights releases.",
    )
    args = ap.parse_args()

    verify_tls = not args.insecure
    if args.insecure:
        try:
            import urllib3

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass

    if not args.url_file.is_file():
        sys.exit(f"URL file not found: {args.url_file}")

    all_urls = load_urls(args.url_file)
    if args.filter_njoag:
        before = len(all_urls)
        all_urls = filter_njoag_icac_urls(all_urls)
        print(f"  NJ filter  : {before} -> {len(all_urls)} URLs")
    urls = all_urls[: args.limit] if args.limit else all_urls

    print(f"\n{'='*55}")
    print(f"  URL file  : {args.url_file}")
    print(f"  Total URLs: {len(all_urls)}  |  processing: {len(urls)}")
    print(f"  Output    : {args.out_dir / args.out_name}")
    print(f"{'='*55}\n")

    tmp_dir = args.out_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    successes: list[Path] = []
    failures: list[str] = []
    captures: list[dict] = []

    for i, url in enumerate(urls, start=1):
        slug = url.rstrip("/").split("/")[-1][:65]
        print(f"  [{i}/{len(urls)}] {slug}")

        out_pdf = _per_url_cache_pdf(tmp_dir, i, url)
        if out_pdf.exists() and out_pdf.stat().st_size > 500:
            try:
                cached_captures = provenance.load_capture_manifest(out_pdf)
            except (OSError, TypeError, ValueError) as exc:
                cached_captures = []
                print(f"    [cache provenance invalid] {exc}", file=sys.stderr)
            if cached_captures:
                print("    [cached]")
                successes.append(out_pdf)
                captures.extend(cached_captures)
                continue
            print("    [cache missing provenance; refetching]")

        parsed = urlparse(url)
        ref = args.referer or f"{parsed.scheme}://{parsed.netloc}/"
        hdrs = _default_headers(referer=ref)
        path_lower = parsed.path.lower()
        if path_lower.endswith(".pdf"):
            resource = fetch_resource(
                url,
                {**hdrs, "Accept": "application/pdf,*/*;q=0.8"},
                verify=verify_tls,
            )
            if resource is None:
                failures.append(url)
                time.sleep(args.delay)
                continue
            raw = resource.content
            result = extract_from_native_pdf(raw, url)
            if not result:
                print("    [FAILED] native PDF: body too thin")
                failures.append(url)
                time.sleep(args.delay)
                continue
            title, byline, body, pub_date = result
            if "njoag.gov" in url.lower():
                body = _clean_njoag_scraped_body(body)
                if not body or len(body) < MIN_BODY_CHARS:
                    print("    [FAILED] njoag: body too thin after clean")
                    failures.append(url)
                    time.sleep(args.delay)
                    continue
            ok = write_pdf(out_pdf, title, byline, body, url, pub_date)
            if ok:
                kb = out_pdf.stat().st_size // 1024
                print(f"    [ok pdf] {kb} KB - {title[:65]}")
                successes.append(out_pdf)
                record = _capture_success(
                    out_dir=args.out_dir,
                    per_url_pdf=out_pdf,
                    source_url=url,
                    resource=resource,
                    parser_name="native-pdf",
                    normalized_text="\n".join((title, byline, body)),
                    published_at=pub_date,
                )
                if record is not None:
                    captures.append(record)
            else:
                failures.append(url)
            time.sleep(args.delay)
            continue

        use_jina_first = args.jina_fallback and (
            "cbp.gov" in url.lower()
            or "usmarshals.gov" in url.lower()
            or "troopers.ny.gov" in url.lower()
        )
        if use_jina_first:
            if "cbp.gov" in url.lower():
                tag = "cbp"
            elif "usmarshals.gov" in url.lower():
                tag = "usms"
            else:
                tag = "nysp"
            print(f"    [{tag}] r.jina.ai reader ...")
            resource = fetch_via_jina_reader_resource(url, verify=verify_tls)
            html = resource.text if resource is not None else None
            capture_parser = "jina-reader"
        else:
            resource = fetch_resource(url, hdrs, verify=verify_tls)
            html = resource.text if resource is not None else None
            capture_parser = "case-linker-html"
            if not html and args.jina_fallback:
                print("    [fallback] r.jina.ai reader ...")
                resource = fetch_via_jina_reader_resource(url, verify=verify_tls)
                html = resource.text if resource is not None else None
                capture_parser = "jina-reader"
        if not html:
            failures.append(url)
            time.sleep(args.delay)
            continue

        is_jina = html.lstrip().startswith("Title:") and "Markdown Content:" in html
        html_j: str | None = None
        if is_jina:
            result = extract_from_jina_reader(html, url)
        else:
            result = extract(html, url)
        body_len = len(((result[2] if result else "") or "").strip())
        needs_jina = (
            args.jina_fallback
            and not is_jina
            and (
                not result
                or (
                    "troopers.ny.gov" in url.lower()
                    and body_len < THIN_HTML_RETRY_CHARS
                )
                or (
                    "njoag.gov" in url.lower()
                    and (
                        body_len < THIN_HTML_RETRY_CHARS
                        or not _njoag_body_ok((result[2] if result else "") or "")
                    )
                )
            )
        )
        if needs_jina:
            print("    [fallback] r.jina.ai reader (thin or empty extract) ...")
            jina_resource = fetch_via_jina_reader_resource(url, verify=verify_tls)
            html_j = jina_resource.text if jina_resource is not None else None
            if html_j:
                resource = jina_resource
                capture_parser = "jina-reader"
                is_j2 = html_j.lstrip().startswith("Title:") and "Markdown Content:" in html_j
                if is_j2:
                    result = extract_from_jina_reader(html_j, url)
                else:
                    result = extract(html_j, url)
        body_so_far = ((result[2] if result else "") or "").strip()
        doj_url = (
            _ncis_doj_follow_url(url, body_so_far, html, html_j)
            if args.jina_fallback
            else None
        )
        if doj_url:
            print(f"    [ncis] follow DOJ release …")
            doj_blob = fetch_via_jina_reader(doj_url, verify=verify_tls)
            if doj_blob:
                if doj_blob.lstrip().startswith("Title:"):
                    doj_result = extract_from_jina_reader(doj_blob, doj_url)
                else:
                    doj_result = extract(doj_blob, doj_url)
                if doj_result and (
                    not result or len(doj_result[2]) > len((result[2] if result else "") or "")
                ):
                    result = doj_result
        if not result:
            print("    [FAILED] extract: body too thin")
            failures.append(url)
            time.sleep(args.delay)
            continue

        title, byline, body, pub_date = result
        if "njoag.gov" in url.lower():
            body = _clean_njoag_scraped_body(body)
            if not body or len(body) < MIN_BODY_CHARS:
                print("    [FAILED] njoag: body too thin after clean")
                failures.append(url)
                time.sleep(args.delay)
                continue
        ok = write_pdf(out_pdf, title, byline, body, url, pub_date)

        if ok:
            kb = out_pdf.stat().st_size // 1024
            print(f"    [ok] {kb} KB - {title[:65]}")
            successes.append(out_pdf)
            if resource is not None:
                record = _capture_success(
                    out_dir=args.out_dir,
                    per_url_pdf=out_pdf,
                    source_url=url,
                    resource=resource,
                    parser_name=capture_parser,
                    normalized_text="\n".join((title, byline, body)),
                    published_at=pub_date,
                )
                if record is not None:
                    captures.append(record)
        else:
            failures.append(url)

        time.sleep(args.delay)

    print(f"\n  Succeeded: {len(successes)}  |  Failed: {len(failures)}")

    if not successes:
        sys.exit("No PDFs to merge.")

    out_pdf = args.out_dir / args.out_name
    print(f"\nMerging {len(successes)} PDFs -> {out_pdf} ...")
    if merge(successes, out_pdf):
        mb = out_pdf.stat().st_size / 1024 / 1024
        print(f"-> {out_pdf}  ({mb:.2f} MB)\n")
        sidecar = provenance.write_capture_manifest(out_pdf, captures)
        print(f"-> {sidecar}  ({len(captures)} source versions)\n")
    else:
        sys.exit("Merge failed.")

    if failures:
        print(f"\nFailed URLs ({len(failures)}):")
        for u in failures:
            print(f"  {u}")


if __name__ == "__main__":
    main()
