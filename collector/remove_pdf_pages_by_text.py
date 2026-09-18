#!/usr/bin/env python3
"""Drop pages from a merged PDF by text match and/or exact-page dedupe.

Modes:
  --exclude REGEX     Drop pages matching any regex (default: drop ALL matches).
  --keep-first        With --exclude: keep the first matching page per pattern;
                      drop only the 2nd+ hits (and optional following pages).
  --follow-pages N    With --keep-first/--exclude: also drop N pages after each
                      dropped match (for multi-page articles whose title is only
                      on the first page of the copy).
  --dedupe-exact-text Drop pages whose normalized full-page text was already seen
                      earlier in the PDF (keeps first copy only).
  --pages 3,7-9       Drop explicit 1-based page numbers / ranges.

Usage::
    python3 remove_pdf_pages_by_text.py --pdf FOO.pdf --exclude 'some title' --keep-first
    python3 remove_pdf_pages_by_text.py --pdf FOO.pdf --dedupe-exact-text
    python3 remove_pdf_pages_by_text.py --pdf FOO.pdf --pages 12,15-17
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

try:
    import pdfplumber
    from pypdf import PdfReader, PdfWriter
except ImportError:
    sys.exit("pip install pdfplumber pypdf")


def normalize_page_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def parse_page_spec(spec: str, n_pages: int) -> set[int]:
    """Parse '3,7-9' (1-based, inclusive) into 0-based page indices."""
    out: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a), int(b)
            for p in range(start, end + 1):
                if 1 <= p <= n_pages:
                    out.add(p - 1)
        else:
            p = int(part)
            if 1 <= p <= n_pages:
                out.add(p - 1)
    return out


def load_page_texts(pdf_path: Path) -> list[str]:
    texts: list[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            texts.append(page.extract_text() or "")
    return texts


def pages_matching_exclude(
    page_texts: list[str],
    patterns: list[re.Pattern[str]],
    *,
    keep_first: bool,
    follow_pages: int,
) -> set[int]:
    """
    Return 0-based page indices to drop for --exclude patterns.

    keep_first=False: every matching page (plus follow_pages after each).
    keep_first=True: per pattern, keep the first match; drop 2nd+ matches
    (each with follow_pages after).
    """
    drop: set[int] = set()
    n = len(page_texts)
    for pat in patterns:
        hits = [i for i, text in enumerate(page_texts) if pat.search(text)]
        to_cut = hits[1:] if keep_first else hits
        for i in to_cut:
            for j in range(i, min(n, i + 1 + max(0, follow_pages))):
                drop.add(j)
    return drop


def pages_exact_text_duplicates(page_texts: list[str], *, min_chars: int = 80) -> set[int]:
    """Drop 2nd+ pages whose normalized text equals an earlier page."""
    drop: set[int] = set()
    seen: dict[str, int] = {}
    for i, text in enumerate(page_texts):
        key = normalize_page_text(text)
        if len(key) < min_chars:
            continue
        if key in seen:
            drop.add(i)
        else:
            seen[key] = i
    return drop


def write_pdf_without_pages(
    pdf_path: Path,
    drop: set[int],
    *,
    dry_run: bool,
    backup_suffix: str = ".pre_remove_failures.bak",
) -> tuple[int, int, list[tuple[int, str]]]:
    """Apply page drops. Returns (before, after, dropped_preview)."""
    reader = PdfReader(str(pdf_path))
    page_texts = load_page_texts(pdf_path)
    dropped_preview = [
        (i, (page_texts[i][:120] if i < len(page_texts) else "").replace("\n", " "))
        for i in sorted(drop)
    ]
    keep = [i for i in range(len(reader.pages)) if i not in drop]
    before, after = len(reader.pages), len(keep)
    if dry_run or not drop:
        return before, after, dropped_preview

    bak = pdf_path.with_suffix(pdf_path.suffix + backup_suffix)
    if not bak.exists():
        shutil.copy2(pdf_path, bak)

    writer = PdfWriter()
    for i in keep:
        writer.add_page(reader.pages[i])
    with open(pdf_path, "wb") as f:
        writer.write(f)
    return before, after, dropped_preview


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Drop PDF pages by regex / exact-text dedupe / page list (page-cut only)."
    )
    ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Regex; page dropped if it matches (repeatable).",
    )
    ap.add_argument(
        "--keep-first",
        action="store_true",
        help="With --exclude: keep the first match per pattern; drop only later matches.",
    )
    ap.add_argument(
        "--follow-pages",
        type=int,
        default=0,
        help="Also drop this many pages after each excluded match (multi-page articles).",
    )
    ap.add_argument(
        "--dedupe-exact-text",
        action="store_true",
        help="Drop pages whose normalized text duplicates an earlier page (keep first).",
    )
    ap.add_argument(
        "--pages",
        type=str,
        default="",
        help="Comma-separated 1-based pages/ranges to drop, e.g. '3,7-9'.",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.exclude and not args.dedupe_exact_text and not args.pages:
        ap.error("Provide --exclude and/or --dedupe-exact-text and/or --pages")

    pdf_path = args.pdf.resolve()
    if not pdf_path.is_file():
        sys.exit(f"missing pdf: {pdf_path}")

    reader = PdfReader(str(pdf_path))
    n_pages = len(reader.pages)
    page_texts = load_page_texts(pdf_path)

    drop: set[int] = set()
    if args.pages:
        drop |= parse_page_spec(args.pages, n_pages)
    if args.exclude:
        patterns = [re.compile(p, re.I | re.S) for p in args.exclude]
        drop |= pages_matching_exclude(
            page_texts,
            patterns,
            keep_first=args.keep_first,
            follow_pages=args.follow_pages,
        )
    if args.dedupe_exact_text:
        drop |= pages_exact_text_duplicates(page_texts)

    before, after, preview = write_pdf_without_pages(
        pdf_path, drop, dry_run=args.dry_run
    )
    mode = "DRY-RUN " if args.dry_run else ""
    print(f"{mode}{pdf_path.name}: {before} pages -> keep {after}, drop {len(drop)}")
    for idx, snip in preview[:20]:
        print(f"  drop page {idx + 1}: {snip}…")
    if len(preview) > 20:
        print(f"  … +{len(preview) - 20} more")
    if not args.dry_run and drop:
        bak = pdf_path.with_suffix(pdf_path.suffix + ".pre_remove_failures.bak")
        print(f"Wrote {pdf_path} ({after} pages). Backup: {bak}")


if __name__ == "__main__":
    main()
