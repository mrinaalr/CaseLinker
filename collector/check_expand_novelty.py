#!/usr/bin/env python3
"""
Ensure expansion never double-dips: new scrape text must be mostly novel vs the
pre-expand PDF (and vs itself).

Checks (in order):
  1. Duplicate Source URLs within the merged PDF (hard fail)
  2. New cases (URLs not in baseline) vs baseline — URL / slug / exact body / near-dup body
  3. Optional --batch-pdf: validate a scrape batch before append

Usage::
    python3 collector/check_expand_novelty.py \\
        --pdf SCAG_ICAC_All.pdf --baseline SCAG_ICAC_All.pdf.pre_expand.bak --source "SCAG ICAC"

    python3 collector/check_expand_novelty.py \\
        --pdf KYSP_ICAC_All.pdf --baseline KYSP_ICAC_All.pdf.pre_expand.bak --source "KY SP"

    python3 collector/check_expand_novelty.py \\
        --batch-pdf collector/state/ky_sp/tmp/batch.pdf \\
        --baseline KYSP_ICAC_All.pdf.pre_expand.bak --source "KY SP"
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[1]
PROCESSING = REPO / "src" / "Processing Layer"

DEFAULT_NEAR_DUP = 0.88
MIN_NOVEL_RATE = 0.95


def _load_batching():
    sys.path.insert(0, str(PROCESSING))
    from batching import case_batching  # noqa: WPS433

    return case_batching


def _read_pdf_text(path: Path) -> str:
    try:
        import pdfplumber
    except ImportError:
        sys.exit("pip install pdfplumber")
    with pdfplumber.open(str(path)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def normalize_url(url: str) -> str:
    u = (url or "").strip().rstrip("/").lower()
    u = re.sub(r"^https?://(?:www\.)?", "https://www.", u)
    u = re.sub(r"\?.*$", "", u)
    u = re.sub(r"#.*$", "", u)
    return u


def slug_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/").split("/")[-1]
    return re.sub(r"\.html?$", "", path, flags=re.I).lower()


def extract_source_url(case_text: str, source: str = "") -> str:
    m = re.search(r"Source:\s*(https?://\S+)", case_text or "", re.I)
    if m:
        return m.group(1).rstrip(".,;)")
    lines = (case_text or "").splitlines()
    for i, ln in enumerate(lines):
        if re.match(r"^\s*Source:\s*$", ln, re.I) and i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            if nxt.lower().startswith("http"):
                return nxt.rstrip(".,;)")
    src = (source or "").upper()
    if "SCAG" in src:
        m = re.search(
            r"https?://(?:www\.)?scag\.gov/about-the-office/news/[a-z0-9\-]+/?",
            case_text or "",
            re.I,
        )
        if m:
            return m.group(0).rstrip("/") + "/"
    if "KY" in src:
        m = re.search(
            r"https?://(?:www\.)?kentuckystatepolice\.ky\.gov/news/[a-z0-9\-]+/?",
            case_text or "",
            re.I,
        )
        if m:
            return m.group(0).rstrip("/") + "/"
    m = re.search(r"https?://\S+/news/[a-z0-9\-]+/?", case_text or "", re.I)
    if m:
        return m.group(0).rstrip(".,;)")
    return ""


KY_ICAC_FOOTER_RE = re.compile(
    r"the kentucky internet crimes against children \(icac\) task force is comprised of.*",
    re.I | re.S,
)
SCAG_FOOTER_RE = re.compile(
    r"\* child sexual abuse material, or csam.*|for media inquiries please contact.*|"
    r"office address rembert dennis.*",
    re.I | re.S,
)


def merge_source_lines(text: str) -> str:
    """Match batching.py: join ``Source:`` line with URL on next line."""
    return re.sub(r"(?m)^(\s*Source:\s*)\n(\s*https?://\S+)", r"\1\2", text or "")


def strip_source_boilerplate(body: str, source: str) -> str:
    b = body
    if source.upper().startswith("KY"):
        b = KY_ICAC_FOOTER_RE.sub("", b)
    elif "SCAG" in source.upper():
        b = SCAG_FOOTER_RE.sub("", b)
    return b.strip()


def normalize_body(case_text: str, source: str = "") -> str:
    """Body fingerprint input: drop metadata lines and site chrome."""
    lines: list[str] = []
    for ln in (case_text or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        low = s.lower()
        if low.startswith(("source:", "publication date:", "http://", "https://")):
            continue
        if "kentucky state police" == low and len(s) < 40:
            continue
        if re.match(r"^(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d", low):
            continue
        if re.match(r"^[A-Z]{3,}\s+\d{1,2},\s+\d{4}$", s):
            continue
        if low.startswith("mailing address") or low.startswith("office address"):
            continue
        lines.append(s)
    body = re.sub(r"\s+", " ", " ".join(lines)).strip().lower()
    return strip_source_boilerplate(body, source)


def body_fingerprint(case_text: str, source: str = "") -> str:
    body = normalize_body(case_text, source)
    if len(body) < 40:
        body = normalize_body(case_text) or re.sub(r"\s+", " ", (case_text or "").lower())[:500]
    return hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()[:20]


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def weighted_jaccard(a: str, b: str) -> float:
    c1, c2 = Counter(tokenize(a)), Counter(tokenize(b))
    if not c1 and not c2:
        return 1.0
    if not c1 or not c2:
        return 0.0
    keys = set(c1) | set(c2)
    inter = sum(min(c1[t], c2[t]) for t in keys)
    union = sum(max(c1[t], c2[t]) for t in keys)
    return inter / union if union else 0.0


@dataclass
class CaseRec:
    case_id: str
    source_url: str
    url_norm: str
    slug: str
    body: str
    fingerprint: str
    headline: str
    is_expansion: bool = False


def url_from_batch(batch: dict, case_text: str = "", source: str = "") -> str:
    """Canonical URL from batching ``source_url``; parse ``case_text`` only if missing."""
    url = str(batch.get("source_url") or "").strip()
    if url:
        return url.rstrip(".,;)")
    return extract_source_url(case_text, source)


def cases_from_pdf(pdf_path: Path, source: str) -> list[CaseRec]:
    case_batching = _load_batching()
    text = merge_source_lines(_read_pdf_text(pdf_path))
    org = source.lower().replace(" ", "_").replace("-", "_")
    batches = case_batching(text, org_name=org, source=source, source_file=pdf_path.name)
    out: list[CaseRec] = []
    for b in batches:
        ct = b.get("case_text") or ""
        url = url_from_batch(b, ct, source)
        body = normalize_body(ct, source)
        headline = ""
        for ln in (ct or "").splitlines():
            s = ln.strip()
            if s and not s.lower().startswith(("source:", "publication", "http")) and len(s) > 18:
                headline = s[:120].lower()
                break
        out.append(
            CaseRec(
                case_id=str(b.get("case_id") or ""),
                source_url=url,
                url_norm=normalize_url(url) if url else "",
                slug=slug_from_url(url) if url else "",
                body=body,
                fingerprint=body_fingerprint(ct, source),
                headline=headline,
            )
        )
    return out


def all_source_urls_from_pdf(pdf_path: Path) -> list[str]:
    text = merge_source_lines(_read_pdf_text(pdf_path))
    return [u.rstrip(".,;)") for u in re.findall(r"Source:\s*(https?://\S+)", text, re.I)]


def attach_urls_to_cases(cases: list[CaseRec], urls: list[str]) -> None:
    """Fill missing url_norm by matching URL slug to case headline/body."""
    unused = list(urls)
    for c in cases:
        if c.url_norm:
            continue
        slug_hint = ""
        for ln in (c.headline or c.body).split():
            if len(ln) > 4:
                slug_hint = ln
                break
        best_url = ""
        best_score = 0
        for u in unused:
            sl = slug_from_url(u)
            score = 0
            if sl and sl in c.body:
                score += 10
            if sl and sl.replace("-", " ") in c.body:
                score += 8
            if c.headline and sl and sl.replace("-", " ")[:40] in c.headline.replace("-", " "):
                score += 5
            # token overlap
            sl_toks = set(sl.split("-")) - {"on", "and", "the", "with", "charges", "charge", "man", "woman"}
            body_toks = set(c.body.split())
            score += len(sl_toks & body_toks)
            if score > best_score:
                best_score, best_url = score, u
        if best_url and best_score >= 3:
            c.source_url = best_url
            c.url_norm = normalize_url(best_url)
            c.slug = slug_from_url(best_url)
            if best_url in unused:
                unused.remove(best_url)


def url_set_report(
    merged_pdf: Path,
    baseline_pdf: Path,
    new_urls_file: Path | None,
) -> tuple[set[str], set[str], set[str], list[tuple[str, list[str]]]]:
    merged_urls = [normalize_url(u) for u in all_source_urls_from_pdf(merged_pdf)]
    baseline_urls = {normalize_url(u) for u in all_source_urls_from_pdf(baseline_pdf)}
    merged_norm_list = merged_urls
    dup_in_merged: dict[str, list[str]] = defaultdict(list)
    for i, u in enumerate(merged_norm_list):
        dup_in_merged[u].append(str(i))
    duplicate_pairs = [(u, ids) for u, ids in dup_in_merged.items() if len(ids) > 1]
    expansion_urls = {u for u in merged_norm_list if u and u not in baseline_urls}
    if new_urls_file and new_urls_file.is_file():
        expected, _ = load_new_url_norms(new_urls_file)
        expansion_urls = expansion_urls  # compare below
    return baseline_urls, expansion_urls, set(merged_norm_list), duplicate_pairs


def load_new_url_norms(path: Path) -> tuple[set[str], set[str]]:
    norms: set[str] = set()
    slugs: set[str] = set()
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        norms.add(normalize_url(ln))
        slugs.add(slug_from_url(ln))
    return norms, slugs


def classify_expansion_cases(
    merged: list[CaseRec],
    baseline: list[CaseRec],
    *,
    expansion_url_norms: set[str] | None,
) -> tuple[list[CaseRec], list[CaseRec]]:
    """Return (expansion_cases, baseline_era_cases) from merged PDF."""
    baseline_fps = {c.fingerprint for c in baseline if c.fingerprint}

    expansion: list[CaseRec] = []
    prior: list[CaseRec] = []
    for c in merged:
        if expansion_url_norms is not None:
            is_new = bool(c.url_norm and c.url_norm in expansion_url_norms)
            if not is_new and c.slug:
                is_new = any(
                    slug_from_url(u) == c.slug for u in expansion_url_norms
                )
        else:
            baseline_urls = {x.url_norm for x in baseline if x.url_norm}
            is_new = bool(c.url_norm and c.url_norm not in baseline_urls)
            if not is_new and c.fingerprint not in baseline_fps:
                is_new = not c.url_norm
        c.is_expansion = is_new
        (expansion if is_new else prior).append(c)
    return expansion, prior


@dataclass
class NoveltyReport:
    merged_total: int = 0
    baseline_total: int = 0
    new_count: int = 0
    url_expansion_count: int = 0
    url_double_dip_count: int = 0
    harvest_missing_urls: int = 0
    duplicate_urls_in_merged: list[tuple[str, list[str]]] = field(default_factory=list)
    url_already_in_baseline: list[CaseRec] = field(default_factory=list)
    slug_already_in_baseline: list[CaseRec] = field(default_factory=list)
    exact_body_in_baseline: list[tuple[CaseRec, str]] = field(default_factory=list)
    near_dup_in_baseline: list[tuple[CaseRec, str, float]] = field(default_factory=list)
    near_dup_among_new: list[tuple[CaseRec, CaseRec, float]] = field(default_factory=list)
    novel_rate: float = 1.0
    ok: bool = True


def analyze(
    merged_cases: list[CaseRec],
    baseline_cases: list[CaseRec],
    *,
    expansion_cases: list[CaseRec],
    near_dup_threshold: float,
    min_novel_rate: float,
) -> NoveltyReport:
    rep = NoveltyReport(
        merged_total=len(merged_cases),
        baseline_total=len(baseline_cases),
        new_count=len(expansion_cases),
    )

    url_to_ids: dict[str, list[str]] = defaultdict(list)
    for c in merged_cases:
        if c.url_norm:
            url_to_ids[c.url_norm].append(c.case_id)
    if not rep.duplicate_urls_in_merged:
        rep.duplicate_urls_in_merged = [(u, ids) for u, ids in url_to_ids.items() if len(ids) > 1]

    baseline_urls = {c.url_norm for c in baseline_cases if c.url_norm}
    baseline_slugs = {c.slug for c in baseline_cases if c.slug}
    baseline_fps = {c.fingerprint: c.case_id for c in baseline_cases if c.fingerprint}
    baseline_by_headline: dict[str, list[CaseRec]] = defaultdict(list)
    for c in baseline_cases:
        if c.headline:
            baseline_by_headline[c.headline].append(c)

    # Double-dip: expansion case maps to baseline URL (body re-ingest of same article)
    for c in expansion_cases:
        if c.url_norm and c.url_norm in baseline_urls:
            rep.url_already_in_baseline.append(c)
        elif c.slug and c.slug in baseline_slugs and c.url_norm not in baseline_urls:
            rep.slug_already_in_baseline.append(c)

    for c in expansion_cases:
        if c.fingerprint in baseline_fps:
            # Only count as double-dip if a *different* baseline case shares body text
            # (ignore matching the same case_id label after re-batch)
            baseline_id = baseline_fps[c.fingerprint]
            if c.url_norm:
                baseline_match = next(
                    (b for b in baseline_cases if b.fingerprint == c.fingerprint and b.url_norm == c.url_norm),
                    None,
                )
                if baseline_match:
                    rep.exact_body_in_baseline.append((c, baseline_match.case_id))
            else:
                rep.exact_body_in_baseline.append((c, baseline_id))

    for c in expansion_cases:
        if c.fingerprint in baseline_fps:
            continue
        candidates: list[CaseRec] = []
        if c.headline and c.headline in baseline_by_headline:
            candidates = baseline_by_headline[c.headline]
        best_id, best_score = "", 0.0
        for b in candidates:
            score = weighted_jaccard(c.body, b.body)
            if score > best_score:
                best_score, best_id = score, b.case_id
        if best_score >= near_dup_threshold:
            rep.near_dup_in_baseline.append((c, best_id, best_score))

    for i, a in enumerate(expansion_cases):
        for b in expansion_cases[i + 1 :]:
            if a.url_norm and a.url_norm == b.url_norm:
                continue
            if a.fingerprint == b.fingerprint:
                rep.near_dup_among_new.append((a, b, 1.0))
                continue
            if a.headline and a.headline == b.headline:
                j = weighted_jaccard(a.body, b.body)
                if j >= near_dup_threshold:
                    rep.near_dup_among_new.append((a, b, j))

    double_dip = (
        len(rep.url_already_in_baseline)
        + len(rep.slug_already_in_baseline)
        + len(rep.exact_body_in_baseline)
        + len(rep.near_dup_in_baseline)
        + len(rep.duplicate_urls_in_merged)
    )
    truly_novel = rep.new_count - len(
        {c.case_id for c, _ in rep.exact_body_in_baseline}
        | {c.case_id for c, _, _ in rep.near_dup_in_baseline}
    )
    rep.novel_rate = truly_novel / rep.new_count if rep.new_count else 1.0
    rep.ok = (
        rep.url_double_dip_count == 0
        and not rep.duplicate_urls_in_merged
        and not rep.url_already_in_baseline
        and not rep.slug_already_in_baseline
        and not rep.exact_body_in_baseline
        and not rep.near_dup_in_baseline
        and rep.novel_rate >= min_novel_rate
        and rep.harvest_missing_urls == 0
    )
    return rep


def _print_report(rep: NoveltyReport, *, label: str, near_dup_threshold: float) -> None:
    print("=" * 72)
    print(f"EXPAND NOVELTY — {label}")
    print("=" * 72)
    print(f"Baseline cases:     {rep.baseline_total}")
    print(f"Merged cases:       {rep.merged_total}")
    print(f"Expansion slice:    {rep.new_count} cases ({rep.url_expansion_count} URLs in PDF)")
    print(f"URL double-dip (expansion URL already in baseline PDF): {rep.url_double_dip_count}")
    if rep.harvest_missing_urls:
        print(f"Harvest URLs missing from PDF: {rep.harvest_missing_urls}")
    print(f"Novel rate (expansion body vs baseline): {rep.novel_rate:.1%}  (min {MIN_NOVEL_RATE:.0%})")
    print()
    print()

    def _show(title: str, items: list, limit: int = 8) -> None:
        print(f"{title}: {len(items)}")
        for row in items[:limit]:
            print(f"  {row}")
        if len(items) > limit:
            print(f"  ... +{len(items) - limit} more")
        print()

    _show("FAIL duplicate Source URL in merged PDF (same URL, multiple cases)", rep.duplicate_urls_in_merged)
    _show("FAIL new case URL already in baseline (double-dip)", rep.url_already_in_baseline)
    _show("FAIL new slug already in baseline (URL variant)", rep.slug_already_in_baseline)
    _show("FAIL new case exact body already in baseline", rep.exact_body_in_baseline)
    _show(
        f"FAIL new case near-duplicate body (Jaccard >= {near_dup_threshold})",
        [(c.case_id, bid, f"{s:.3f}") for c, bid, s in rep.near_dup_in_baseline],
    )
    _show(
        "WARN near-duplicate among new-only cases",
        [(a.case_id, b.case_id, f"{s:.3f}") for a, b, s in rep.near_dup_among_new],
    )

    status = "PASS" if rep.ok else "FAIL"
    print(f"Overall: {status}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Check expansion PDF/batch is mostly novel.")
    ap.add_argument("--pdf", type=Path, help="Merged PDF after append")
    ap.add_argument("--batch-pdf", type=Path, help="Scrape batch only (pre-append check)")
    ap.add_argument("--baseline", type=Path, required=True, help="Pre-expand .bak or prior PDF")
    ap.add_argument("--source", required=True, help="Batching source key, e.g. 'KY SP'")
    ap.add_argument(
        "--new-urls-file",
        type=Path,
        help="URL list from harvest (defines expansion slice precisely)",
    )
    ap.add_argument("--near-dup", type=float, default=DEFAULT_NEAR_DUP, help="Jaccard threshold")
    ap.add_argument("--min-novel-rate", type=float, default=MIN_NOVEL_RATE)
    args = ap.parse_args()

    if not args.pdf and not args.batch_pdf:
        ap.error("Provide --pdf and/or --batch-pdf")
    baseline_path = args.baseline.expanduser().resolve()
    if not baseline_path.is_file():
        print(f"Baseline not found: {baseline_path}", file=sys.stderr)
        return 2

    source = args.source.strip()
    baseline_cases = cases_from_pdf(baseline_path, source)
    new_url_norms: set[str] | None = None
    new_slugs: set[str] | None = None
    if args.new_urls_file:
        nu_path = args.new_urls_file.expanduser().resolve()
        if not nu_path.is_file():
            print(f"new-urls-file not found: {nu_path}", file=sys.stderr)
            return 2
        new_url_norms, new_slugs = load_new_url_norms(nu_path)
    exit_code = 0

    def _run_check(pdf_path: Path, label: str) -> NoveltyReport:
        cases = cases_from_pdf(pdf_path, source)
        baseline_url_set, expansion_url_norms, _, dup_pairs = url_set_report(
            pdf_path, baseline_path, args.new_urls_file
        )
        url_double_dip = len(new_url_norms & baseline_url_set) if new_url_norms else 0
        harvest_missing = len(new_url_norms - expansion_url_norms) if new_url_norms else 0

        raw_urls = all_source_urls_from_pdf(pdf_path)
        attach_urls_to_cases(cases, raw_urls)
        expansion, _prior = classify_expansion_cases(
            cases, baseline_cases, expansion_url_norms=expansion_url_norms
        )
        if len(expansion) < max(1, len(expansion_url_norms)) * 0.85:
            print(
                f"  [warn] {len(expansion)} batched cases mapped for "
                f"{len(expansion_url_norms)} expansion URLs in {label}",
                file=sys.stderr,
            )

        out = analyze(
            cases,
            baseline_cases,
            expansion_cases=expansion,
            near_dup_threshold=args.near_dup,
            min_novel_rate=args.min_novel_rate,
        )
        out.url_expansion_count = len(expansion_url_norms)
        out.url_double_dip_count = url_double_dip
        out.harvest_missing_urls = harvest_missing
        out.duplicate_urls_in_merged = dup_pairs
        return out

    if args.batch_pdf:
        batch_path = args.batch_pdf.expanduser().resolve()
        if not batch_path.is_file():
            print(f"Batch PDF not found: {batch_path}", file=sys.stderr)
            return 2
        rep = _run_check(batch_path, f"batch {batch_path.name}")
        _print_report(rep, label=f"batch {batch_path.name}", near_dup_threshold=args.near_dup)
        if not rep.ok:
            exit_code = 1

    if args.pdf:
        pdf_path = args.pdf.expanduser().resolve()
        if not pdf_path.is_file():
            print(f"PDF not found: {pdf_path}", file=sys.stderr)
            return 2
        rep = _run_check(pdf_path, f"merged {pdf_path.name}")
        _print_report(rep, label=f"merged {pdf_path.name}", near_dup_threshold=args.near_dup)
        if not rep.ok:
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
