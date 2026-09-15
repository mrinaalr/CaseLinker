#!/usr/bin/env python3
"""
Harvest Project Safe Childhood prosecutions from the public DOJ press-release API.

PSC has no dedicated API. justice.gov/psc/press-room is a curated listing (~12
items/page, pager claims ~1768 pages) but pages after 0 return HTTP 403, so the
listing cannot be crawled. The DOJ News API only filters by title/date (topic,
component, and body parameters are ignored). This harvester therefore:

  1. Pages title-substring queries for CAC prosecution phrasing
  2. Keeps records whose title or body mentions ``Project Safe Childhood``
  3. Drops grants / rollups / prevention / speeches
  4. Keeps the richest public stage (sentencing > plea/conviction) so arrest
     and indictment write-ups of the same matter do not inflate the count
  5. Requires the existing verify_cac.py gate
  6. Emits scrape_pdf.py --doj-file resolved records

No API key. Self-throttles under the documented 4 req/s cap.

usage:
    python3 harvest_doj_psc.py
    python3 harvest_doj_psc.py --limit-pages 2   # smoke
    python3 harvest_doj_psc.py --max-keep 0      # no cap (older than the last 2,200)

    # Same pipeline, different topic (CAC gate off — that filter is ICAC-specific):
    python3 harvest_doj_psc.py --slug doj_fentanyl --skip-cac \\
        --require 'fentanyl|methamphetamine' --title-term fentanyl --max-keep 2200
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

DOJ_API_URL = "https://www.justice.gov/api/v1/press_releases.json"
PAGESIZE = 50
MIN_DELAY = 0.32
MIN_BODY_CHARS = 80

TITLE_TERMS = (
    "child pornography",
    "child sexual abuse material",
    "child exploitation",
    "child sexual",
    "CSAM",
    "enticement of a minor",
    "coercion and enticement",
    "child sex trafficking",
    "sex trafficking of a child",
    "sex trafficking of a minor",
    "illicit sexual conduct",
    "obscene visual",
    "sextortion",
    "traveling to engage",
    "production of child",
    "receiving child",
    "distributing child",
    "possessing child",
    "possession of child",
)

EXISTING_DOJ_PDFS = (
    REPO / "DOJ_CEOS_All.pdf",
    REPO / "DOJ_ARCHIVES_All.pdf",
    REPO / "DOJ_AI_CSAM_All.pdf",
    REPO / "DOJ_SAFE_CHILDHOOD.pdf",
    REPO / "DOJ_SAFE_CHILDHOOD_All.pdf",
)

PSC_RE = re.compile(r"\bProject\s+Safe\s+Childhood\b", re.I)

# Program / money / awareness — not a single prosecution write-up.
NOISE_RE = re.compile(
    r"""
    \b(?:grant|grants|awarded|funding|cooperative\s+agreement)\b
    | \b(?:awareness|prevention\s+month|national\s+strategy)\b
    | \b(?:encourages?\s+schools|partner\s+with\s+doj)\b
    | \b(?:quarterly\s+update|releases?\s+update\s+on|prosecut(?:es|ing)\s+\d+)
    | \b(?:child\s+exploitation\s+cases\s+prosecuted\s+under)\b
    | \b(?:statement\s+of\s+(?:the\s+)?attorney\s+general)\b
    | \b(?:remarks|keynote|op-?ed)\b
    """,
    re.I | re.VERBOSE,
)

SENTENCED_RE = re.compile(r"\bsentenc", re.I)
PLEA_RE = re.compile(r"\bplead|\bpleads|\bpleaded|\bguilty|\bconvict", re.I)
EARLY_RE = re.compile(r"\barrest|\bindict|\bcharg(?:ed|es)\b", re.I)


def _load_scrape_doj():
    spec = importlib.util.spec_from_file_location("scrape_doj", HERE / "scrape_doj.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_verify_cac():
    spec = importlib.util.spec_from_file_location(
        "verify_cac", REPO / "scripts" / "verify" / "verify_cac.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _normalize_url(url: str) -> str:
    u = (url or "").strip().rstrip("/").lower()
    u = re.sub(r"^https?://(?:www\.)?", "https://www.", u)
    u = re.sub(r"\?.*$", "", u)
    u = re.sub(r"#.*$", "", u)
    return u


_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)


def _urls_from_pdf_bytes(path: Path) -> set[str]:
    """Fast URL scrape from PDF byte strings (no full text extract)."""
    try:
        raw = path.read_bytes()
    except OSError:
        return set()
    text = raw.decode("latin-1", errors="ignore")
    out: set[str] = set()
    for m in _URL_RE.findall(text):
        cleaned = m.rstrip(".,;)]>")
        if "justice.gov" in cleaned.lower() or cleaned.lower().startswith("http"):
            out.add(_normalize_url(cleaned))
    return out


def existing_doj_urls(extra: list[Path] | None = None) -> set[str]:
    urls: set[str] = set()
    paths = list(EXISTING_DOJ_PDFS)
    if extra:
        paths.extend(extra)
    seen_paths: set[Path] = set()
    for path in paths:
        path = path.resolve()
        if path in seen_paths or not path.is_file():
            continue
        seen_paths.add(path)
        found = {u for u in _urls_from_pdf_bytes(path) if "justice.gov" in u}
        print(f"  baseline {path.name}: {len(found)} justice.gov URLs", file=sys.stderr)
        urls |= found
    return urls


def justice_gov_in_other_corpus_pdfs() -> dict[str, int]:
    """How many justice.gov URLs already sit in AG / ICAC merged PDFs."""
    hits: dict[str, int] = {}
    for path in sorted(REPO.glob("*_All.pdf")):
        if path.name.startswith("DOJ_"):
            continue
        found = {u for u in _urls_from_pdf_bytes(path) if "justice.gov" in u}
        if found:
            hits[path.name] = len(found)
    return hits


def classify_stage(title: str) -> str:
    if SENTENCED_RE.search(title):
        return "sentenced"
    if PLEA_RE.search(title):
        return "plea_or_convicted"
    if EARLY_RE.search(title):
        return "early"
    return "other"


_last_call = 0.0


def api_get(params: dict) -> dict:
    global _last_call
    wait = MIN_DELAY - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    r = requests.get(DOJ_API_URL, params=params, timeout=45)
    _last_call = time.monotonic()
    r.raise_for_status()
    return r.json()


def page_term(term: str, *, limit_pages: int | None) -> list[dict]:
    out: list[dict] = []
    page = 0
    while True:
        data = api_get(
            {
                "parameters[title]": term,
                "pagesize": PAGESIZE,
                "page": page,
                "sort": "date",
                "direction": "DESC",
            }
        )
        results = data.get("results") or []
        total = int(data.get("metadata", {}).get("resultset", {}).get("count") or 0)
        out.extend(results)
        print(
            f"    [{term}] page {page} +{len(results)} (have {len(out)}/{total})",
            file=sys.stderr,
        )
        if not results:
            break
        if (page + 1) * PAGESIZE >= total:
            break
        page += 1
        if limit_pages is not None and page >= limit_pages:
            break
    return out


def canonical_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    if raw.startswith("//"):
        raw = "https:" + raw
    elif raw.startswith("/"):
        raw = "https://www.justice.gov" + raw
    parsed = urlparse(raw)
    if parsed.netloc in ("justice.gov",):
        raw = raw.replace("://justice.gov", "://www.justice.gov", 1)
    return raw


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Page the DOJ News API by title terms, filter, emit scrape_pdf.py --doj-file JSON. "
            "Defaults are the Project Safe Childhood recipe; override --title-term/--require/--skip-cac "
            "for any other DOJ topic (drugs, fraud, …)."
        )
    )
    ap.add_argument("--limit-pages", type=int, default=None, help="Max pages per title term (smoke).")
    ap.add_argument(
        "--keep-early",
        action="store_true",
        help="Also keep arrest/indictment titles (default: sentencing + plea/conviction only).",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=HERE / "sources",
    )
    ap.add_argument(
        "--max-keep",
        type=int,
        default=2200,
        help="Stop after this many kept records (newest first). 0 = no cap.",
    )
    ap.add_argument(
        "--title-term",
        action="append",
        dest="title_terms",
        help="Title substring to page (repeatable). Default: built-in CAC prosecution phrasing.",
    )
    ap.add_argument(
        "--require",
        default=None,
        help="Regex that title or body must match. Default: Project Safe Childhood.",
    )
    ap.add_argument(
        "--skip-cac",
        action="store_true",
        help="Do not run verify_cac.py (required for non-ICAC topics: drugs, fraud, …).",
    )
    ap.add_argument(
        "--slug",
        default="doj_psc",
        help="Output filename prefix (doj_psc_resolved_novel.json, …).",
    )
    ap.add_argument(
        "--source",
        default="DOJ SAFE CHILDHOOD",
        help="Source label stored on CAC-gate probe records (ingest uses the PDF filename).",
    )
    ap.add_argument(
        "--baseline-pdf",
        action="append",
        type=Path,
        default=[],
        help="Extra merged PDF to treat as already-seen justice.gov URLs (repeatable).",
    )
    ap.add_argument(
        "--until",
        default=None,
        help="Keep records with pub_date strictly before this YYYY-MM-DD (e.g. 2010-01-01).",
    )
    ap.add_argument(
        "--direction",
        choices=("ASC", "DESC"),
        default=None,
        help="API date sort. Default DESC; ASC when --until is set so old years are first.",
    )
    args = ap.parse_args()

    scrape_doj = _load_scrape_doj()
    verify_cac = None if args.skip_cac else _load_verify_cac()
    require_re = re.compile(args.require, re.I) if args.require else PSC_RE
    title_terms = tuple(args.title_terms) if args.title_terms else TITLE_TERMS
    sort_dir = args.direction or ("ASC" if args.until else "DESC")
    until_s = args.until

    args.out_dir.mkdir(parents=True, exist_ok=True)
    print("Loading existing DOJ PDF URLs for novelty…", file=sys.stderr)
    seen_urls = existing_doj_urls(args.baseline_pdf)
    print(f"  baseline unique justice.gov URLs: {len(seen_urls)}", file=sys.stderr)
    other_hits = justice_gov_in_other_corpus_pdfs()
    if other_hits:
        print(f"  justice.gov already in non-DOJ PDFs: {other_hits}", file=sys.stderr)
    else:
        print("  justice.gov URLs in AG/ICAC PDFs: 0", file=sys.stderr)

    seen_uuid: set[str] = set()
    kept: list[dict] = []
    stats = Counter()
    hit_cap = False

    def consider(rec: dict) -> bool:
        """Return True if we should stop (hit max-keep)."""
        uid = rec.get("uuid") or ""
        if not uid:
            stats["no_uuid"] += 1
            return False
        if uid in seen_uuid:
            stats["dup_uuid"] += 1
            return False
        seen_uuid.add(uid)
        stats["unique_uuid"] += 1

        title = (rec.get("title") or "").strip()
        raw_body = rec.get("body") or ""
        url = canonical_url(rec.get("url") or "")
        pub_date = scrape_doj._epoch_to_date(rec.get("date"))
        if until_s:
            if not pub_date or pub_date.isoformat() >= until_s:
                stats["drop_until"] += 1
                return False
        blob = f"{title}\n{raw_body}"
        if not require_re.search(blob):
            stats["drop_no_require"] += 1
            return False
        if NOISE_RE.search(title) or NOISE_RE.search(raw_body[:800]):
            if NOISE_RE.search(title) or classify_stage(title) in {"early", "other"}:
                stats["drop_noise"] += 1
                return False
        stage = classify_stage(title)
        if stage == "early" and not args.keep_early:
            stats["drop_early_stage"] += 1
            return False
        if stage == "other":
            stats["drop_other_stage"] += 1
            return False
        body = scrape_doj.clean_doj_api_body(raw_body)
        if len(body) < MIN_BODY_CHARS:
            stats["drop_thin_body"] += 1
            return False
        if not url:
            stats["drop_no_url"] += 1
            return False
        if verify_cac is not None:
            cac_case = {
                "id": uid,
                "source": args.source,
                "source_url": url,
                "case_text": f"{title}\n{body}",
            }
            if not verify_cac.is_cac_case(cac_case):
                stats["drop_cac"] += 1
                return False
        norm = _normalize_url(url)
        novel = norm not in seen_urls
        if not novel:
            stats["already_in_doj_pdf"] += 1
        components = rec.get("component") or []
        agency = ""
        if components and isinstance(components[0], dict):
            agency = components[0].get("name") or ""
        kept.append(
            {
                "source_url": url,
                "mode": "resolved",
                "title": title,
                "byline": pub_date.strftime("%B %d, %Y") if pub_date else "",
                "pub_date": pub_date.isoformat() if pub_date else None,
                "body": body,
                "agency": agency,
                "uuid": uid,
                "stage": stage,
                "novel_vs_doj_pdfs": novel,
            }
        )
        stats[f"keep_{stage}"] += 1
        if args.max_keep and len(kept) >= args.max_keep:
            return True
        return False

    for term in title_terms:
        print(f"\n=== title term: {term} (kept {len(kept)}) ===", file=sys.stderr)
        page = 0
        while True:
            try:
                data = api_get(
                    {
                        "parameters[title]": term,
                        "pagesize": PAGESIZE,
                        "page": page,
                        "sort": "date",
                        "direction": sort_dir,
                    }
                )
            except Exception as exc:
                print(f"  FAILED {term} page {page}: {exc}", file=sys.stderr)
                stats[f"api_fail:{term}"] += 1
                break
            results = data.get("results") or []
            total = int(data.get("metadata", {}).get("resultset", {}).get("count") or 0)
            stats["api_records"] += len(results)
            print(
                f"    [{term}] page {page} +{len(results)} scanned={stats['api_records']} kept={len(kept)}/{total}",
                file=sys.stderr,
            )
            page_past_until = 0
            for rec in results:
                if consider(rec):
                    hit_cap = True
                    break
                if until_s:
                    pd = scrape_doj._epoch_to_date(rec.get("date"))
                    if pd and pd.isoformat() >= until_s:
                        page_past_until += 1
            if hit_cap or not results:
                break
            if until_s and sort_dir == "ASC" and results and page_past_until == len(results):
                print(f"    [{term}] reached --until {until_s}; next term.", file=sys.stderr)
                break
            if (page + 1) * PAGESIZE >= total:
                break
            page += 1
            if args.limit_pages is not None and page >= args.limit_pages:
                break
        if hit_cap:
            print(f"\nHit --max-keep {args.max_keep}; stopping.", file=sys.stderr)
            break

    kept.sort(key=lambda r: (r.get("pub_date") or "", r["title"]), reverse=True)
    novel = [r for r in kept if r["novel_vs_doj_pdfs"]]

    resolved_path = args.out_dir / f"{args.slug}_resolved.json"
    urls_path = args.out_dir / f"{args.slug}_urls.txt"
    novel_path = args.out_dir / f"{args.slug}_resolved_novel.json"
    summary_path = args.out_dir / f"{args.slug}_harvest_summary.json"

    resolved_path.write_text(json.dumps(kept, indent=2), encoding="utf-8")
    novel_path.write_text(json.dumps(novel, indent=2), encoding="utf-8")
    urls_path.write_text("\n".join(r["source_url"] for r in kept) + "\n", encoding="utf-8")

    years = Counter((r.get("pub_date") or "unknown")[:4] for r in kept)
    summary = {
        "stats": dict(stats),
        "kept_total": len(kept),
        "kept_novel_vs_existing_doj_pdfs": len(novel),
        "already_in_doj_pdfs": stats["already_in_doj_pdf"],
        "baseline_doj_pdf_urls": len(seen_urls),
        "justice_gov_in_ag_icac_pdfs": other_hits,
        "hit_max_keep": hit_cap,
        "max_keep": args.max_keep,
        "slug": args.slug,
        "skip_cac": args.skip_cac,
        "require": args.require or r"\bProject\s+Safe\s+Childhood\b",
        "title_terms": list(title_terms),
        "by_stage": {
            "sentenced": stats["keep_sentenced"],
            "plea_or_convicted": stats["keep_plea_or_convicted"],
        },
        "by_year": dict(sorted(years.items())),
        "resolved_json": str(resolved_path),
        "novel_json": str(novel_path),
        "url_file": str(urls_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\n======== DOJ harvest ========")
    print(json.dumps(summary, indent=2))
    print(f"Wrote {resolved_path}")
    print(f"Wrote {novel_path}")
    print(f"Wrote {urls_path}")


if __name__ == "__main__":
    main()
