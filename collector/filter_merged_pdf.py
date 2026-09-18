#!/usr/bin/env python3
"""
Filter a merged scrape PDF by URL noise patterns and body keywords; rebuild from ``tmp/`` cache.

Usage::
    python3 filter_merged_pdf.py \\
        --url-file sources/ice_child_urls.txt \\
        --merged ../../ICE_CHILD_ALL.pdf \\
        --tmp-dir ../../tmp \\
        --exclude-from patterns/ice_child_exclude.txt \\
        --write-url-file sources/ice_child_urls.txt
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

try:
    import pdfplumber
    from pypdf import PdfReader, PdfWriter
except ImportError:
    sys.exit("pip install pdfplumber pypdf")

# Child sexual exploitation / abuse material — not generic "sexual" or "exploitation"
_CHILD_EXPLOITATION = re.compile(
    r"(child\s+pornograph|child\s+sexual\s+abuse\s+material|child\s+sex\s+abuse|"
    r"\bcsam\b|child\s+exploitation|child\s+molest|"
    r"(possess|distribut|product|receiv)\w*\s+.{0,12}child|"
    r"entic\w+.{0,50}\bminor|solicit\w+.{0,50}\bminor|"
    r"sexual\s+abuse\s+of\s+(a\s+)?minor|"
    r"child\s+sex\s+traffick|internet\s+crimes\s+against\s+children|\bicac\b|"
    r"predator\s+sting|sex\s+with\s+(a\s+)?child|"
    r"record\w+\s+child\s+sexual|images?\s+of\s+child\s+porn|"
    r"exploiting\s+children|child\s+predator|child\s+sex\s+offen|"
    r"child\s+sex\s+crime|operation\s+predator|"
    r"sexual\s+abuse\s+of\s+(a\s+)?(child|minor)|"
    r"(?:child|minor).{0,40}sexual\s+abuse|"
    r"(?:child|minor).{0,40}\brape\b|\brape\b.{0,40}(?:child|minor)|"
    r"child\s+sexual\s+assault|sexual\s+assault.{0,30}(?:child|minor)|"
    r"child\s+abuse\s+material|production\s+of\s+csam|"
    r"entic\w+.{0,40}\bchild|meet.{0,25}\bchild.{0,40}sexual|"
    r"13-year-old\s+child|child\s+pornography|child\s+sexual\s+exploitation)",
    re.I,
)


def _article_id(url: str) -> str | None:
    m = re.search(r"/Article/(\d+)", url, re.I)
    return m.group(1) if m else None


_NCIS_NOISE = re.compile(
    r"(news\s+recap|k-9\s+program|esd\s+k-9|escaped\s+confinement|three\s+new\s+noses|"
    r"operation\s+home\s+for\s+the\s+holidays|missing\s+children\s+in\s+florida)",
    re.I,
)

_BODY_ROUNDUP_NOISE = re.compile(
    r"(enforcement\s+action\s+targeting|during\s+the\s+enforcement\s+action|"
    r"operation\s+no\s+safe\s+haven|fugitive\s+operations\s+teams|"
    r"\b\d+\s+criminal\s+aliens\b|\b\d+\s+illegal\s+aliens\b|"
    r"immigration\s+violators\s+across|sanctuary\s+calamity|"
    r"fy\s+20\d{2}\s+annual\s+report|body\s+worn\s+camera\s+pilot|"
    r"year\s+defined\s+by\s+results)",
    re.I,
)

_PDF_STUB_NOISE = re.compile(
    r"(requested\s+page\s+not\s+found|^search\s+results\s*$|about\s+\d+[,.]?\d*\s+results)",
    re.I | re.M,
)


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


def load_urls(path: Path) -> list[str]:
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            out.append(s.split("#", 1)[0])
    return out


def _cache_pdf(tmp_dir: Path, index: int, url: str) -> Path:
    h = hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:16]
    named = tmp_dir / f"{index:04d}_{h}.pdf"
    if named.is_file():
        return named
    # Scrape index may differ after URL list is trimmed; match by URL hash suffix.
    matches = sorted(tmp_dir.glob(f"*_{h}.pdf"))
    return matches[0] if matches else named


def _pdf_text(pdf_path: Path) -> str:
    parts: list[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser(description="Filter merged PDF by URL/body rules.")
    ap.add_argument("--url-file", type=Path, required=True)
    ap.add_argument("--merged", type=Path, required=True)
    ap.add_argument("--tmp-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--write-url-file", type=Path, default=None)
    ap.add_argument("--exclude-from", metavar="FILE")
    ap.add_argument("--header", default="", help="Comment line written to --write-url-file.")
    ap.add_argument("--skip-body-filter", action="store_true")
    args = ap.parse_args()

    noise = [x.lower() for x in _read_patterns(args.exclude_from)]

    def is_noise_url(url: str) -> bool:
        low = url.lower()
        return any(n in low for n in noise)

    def body_passes(text: str) -> bool:
        if args.skip_body_filter:
            return len((text or "").strip()) >= 80
        if not text or len(text.strip()) < 80:
            return False
        if _BODY_ROUNDUP_NOISE.search(text):
            return False
        if _NCIS_NOISE.search(text):
            return False
        if _PDF_STUB_NOISE.search(text):
            return False
        return bool(_CHILD_EXPLOITATION.search(text))

    urls = load_urls(args.url_file)
    kept_urls: list[str] = []
    kept_pdfs: list[Path] = []
    dropped_noise: list[str] = []
    dropped_kw: list[str] = []
    dropped_dup: list[str] = []
    missing: list[str] = []
    seen_article_ids: set[str] = set()

    for i, url in enumerate(urls, start=1):
        if is_noise_url(url):
            dropped_noise.append(url)
            continue
        aid = _article_id(url)
        if aid and aid in seen_article_ids:
            dropped_dup.append(url)
            continue
        cache = _cache_pdf(args.tmp_dir, i, url)
        if not cache.is_file() or cache.stat().st_size < 500:
            missing.append(url)
            continue
        if not body_passes(_pdf_text(cache)):
            dropped_kw.append(url)
            continue
        kept_urls.append(url)
        kept_pdfs.append(cache)
        if aid:
            seen_article_ids.add(aid)

    out_path = args.out or args.merged
    if not kept_pdfs:
        sys.exit("No articles passed filters; merged PDF not written.")

    writer = PdfWriter()
    for p in kept_pdfs:
        for page in PdfReader(str(p)).pages:
            writer.add_page(page)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        writer.write(f)

    if args.write_url_file:
        hdr = args.header or "Kept after filter"
        args.write_url_file.write_text(
            f"# {hdr}\n" + "\n".join(kept_urls) + "\n",
            encoding="utf-8",
        )

    print(f"Input URLs:       {len(urls)}")
    print(f"Kept:             {len(kept_urls)}")
    print(f"Dropped noise:    {len(dropped_noise)}")
    print(f"Dropped dup:      {len(dropped_dup)}")
    print(f"Dropped keywords: {len(dropped_kw)}")
    print(f"Missing cache:    {len(missing)}")
    print(f"Wrote -> {out_path}")


if __name__ == "__main__":
    main()
