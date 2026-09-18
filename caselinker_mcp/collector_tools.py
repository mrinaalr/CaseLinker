"""MCP wrappers over ``collector`` for the press-release collector suite.

Two collection methods (same as PRESS_RELEASE_COLLECTION.md):

1. DOJ News API: discover by title term. Do not fetch justice.gov HTML (Akamai).
2. URL path: start from article URL(s) or a listing page.

WRITE tools create files under the repo (JSON url-lists, resolved records, PDFs).
READ tools return structured data only. Nothing here mutates CaseLinker sqlite.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parent.parent
# On-disk path: repo-root collector/.
_COLLECTOR = _REPO / "collector"
_DEFAULT_OUT = _REPO / "collector_output" / "mcp_collect"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _safe_slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", (text or "case").strip())[:80]
    return s.strip("_") or "case"


def _ensure_out(out_dir: str | Path | None) -> Path:
    path = Path(out_dir) if out_dir else _DEFAULT_OUT
    if not path.is_absolute():
        path = _REPO / path
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# READ
# ---------------------------------------------------------------------------


def probe_press_url(url: str, *, jina_fallback: bool = True) -> dict[str, Any]:
    """READ: probe one press-release URL (no PDF write).

    justice.gov URLs resolve via the DOJ API (Akamai blocks live HTML).
    Other hosts use scrape_pdf extract (optional Jina fallback).
    """
    url = (url or "").strip()
    if not url.startswith("http"):
        return {"error": "url must be an http(s) URL", "write": False}

    scrape_doj = _load_module("scrape_doj_mcp", _COLLECTOR / "scrape_doj.py")
    if scrape_doj.is_justice_gov_url(url):
        rec = scrape_doj.resolve_justice_gov_url(url)
        return {
            "write": False,
            "method": "doj_api_resolve",
            "source_url": url,
            "mode": rec.get("mode"),
            "title": rec.get("title"),
            "pub_date": rec.get("pub_date"),
            "agency": rec.get("agency"),
            "body_chars": len(rec.get("body") or ""),
            "body_preview": (rec.get("body") or "")[:600],
            "note": "justice.gov must use DOJ API. Live HTML hits Akamai.",
        }

    scrape_pdf = _load_module("scrape_pdf_mcp", _COLLECTOR / "scrape_pdf.py")
    import argparse

    ns = argparse.Namespace(
        referer=None,
        jina_fallback=jina_fallback,
        insecure=False,
    )
    resolved = scrape_pdf.resolve_url_content(url, ns, verify_tls=True)
    if not resolved:
        return {
            "write": False,
            "method": "html_extract",
            "source_url": url,
            "ok": False,
            "error": "extract failed (thin body, fetch error, or bot wall)",
            "hint": "Retry with jina_fallback=true, or check host extractor.",
        }
    (title, byline, body, pub_date), _fetch = resolved
    return {
        "write": False,
        "method": "html_extract",
        "source_url": url,
        "ok": True,
        "title": title,
        "byline": byline,
        "pub_date": pub_date.isoformat() if pub_date else None,
        "body_chars": len(body or ""),
        "body_preview": (body or "")[:600],
    }


# ---------------------------------------------------------------------------
# WRITE: DOJ API discovery
# ---------------------------------------------------------------------------


def harvest_doj_press_topic(
    title_term: str,
    *,
    require_regex: str = "",
    max_keep: int = 1,
    limit_pages: int = 1,
    slug: str = "",
    keep_early: bool = True,
    out_dir: str = "",
) -> dict[str, Any]:
    """WRITE: run harvest_doj_psc.py for a topic → resolved JSON under sources/ or out_dir."""
    title_term = (title_term or "").strip()
    if not title_term:
        return {"error": "title_term is required", "write": True}

    out = _ensure_out(out_dir) if out_dir else (_COLLECTOR / "sources")
    out.mkdir(parents=True, exist_ok=True)
    slug_s = _safe_slug(slug or f"doj_{title_term}")
    require = require_regex.strip() or re.escape(title_term.split()[0])

    cmd = [
        sys.executable,
        str(_COLLECTOR / "harvest_doj_psc.py"),
        "--slug",
        slug_s,
        "--skip-cac",
        "--title-term",
        title_term,
        "--require",
        require,
        "--max-keep",
        str(max(1, int(max_keep))),
        "--limit-pages",
        str(max(1, int(limit_pages))),
        "--out-dir",
        str(out),
    ]
    if keep_early:
        cmd.append("--keep-early")

    proc = subprocess.run(
        cmd,
        cwd=str(_COLLECTOR),
        capture_output=True,
        text=True,
        timeout=180,
    )
    novel = out / f"{slug_s}_resolved_novel.json"
    resolved = out / f"{slug_s}_resolved.json"
    urls = out / f"{slug_s}_urls.txt"
    records: list[dict[str, Any]] = []
    target = novel if novel.is_file() else resolved
    if target.is_file():
        try:
            records = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            records = []

    return {
        "write": True,
        "tool_kind": "WRITE",
        "method": "doj_api_harvest",
        "ok": proc.returncode == 0 and bool(records),
        "exit_code": proc.returncode,
        "slug": slug_s,
        "resolved_json": str(target) if target.is_file() else None,
        "url_file": str(urls) if urls.is_file() else None,
        "kept": len(records),
        "records": [
            {
                "title": r.get("title"),
                "source_url": r.get("source_url"),
                "pub_date": r.get("pub_date"),
                "agency": r.get("agency"),
                "body_chars": len(r.get("body") or ""),
            }
            for r in records[: max(1, int(max_keep))]
        ],
        "stderr_tail": (proc.stderr or "")[-1200:],
        "stdout_tail": (proc.stdout or "")[-800:],
    }


# ---------------------------------------------------------------------------
# WRITE: URL path
# ---------------------------------------------------------------------------


def fetch_press_listing_urls(
    listing_url: str,
    *,
    out_name: str = "mcp_listing_urls.txt",
    same_host: bool = True,
    path_prefix: str = "",
    require_any: str = "",
    max_urls: int = 20,
    out_dir: str = "",
) -> dict[str, Any]:
    """WRITE: harvest article URLs from one listing/search page → url-file."""
    listing_url = (listing_url or "").strip()
    if not listing_url.startswith("http"):
        return {"error": "listing_url must be http(s)", "write": True}

    out = _ensure_out(out_dir)
    if out_name.endswith(".txt"):
        out_file = out / out_name
    else:
        out_file = out / f"{_safe_slug(out_name)}.txt"

    cmd = [
        sys.executable,
        str(_COLLECTOR / "fetch_source_urls.py"),
        "--url",
        listing_url,
        "-o",
        str(out_file),
    ]
    if same_host:
        cmd.append("--same-host")
    if path_prefix.strip():
        cmd.extend(["--path-prefix", path_prefix.strip()])
    for token in (require_any or "").split(","):
        t = token.strip()
        if t:
            cmd.extend(["--require-any", t])

    proc = subprocess.run(
        cmd,
        cwd=str(_COLLECTOR),
        capture_output=True,
        text=True,
        timeout=120,
    )
    urls: list[str] = []
    if out_file.is_file():
        urls = [
            ln.strip()
            for ln in out_file.read_text(encoding="utf-8").splitlines()
            if ln.strip().startswith("http")
        ]
    if max_urls and len(urls) > max_urls:
        urls = urls[: max(1, int(max_urls))]
        out_file.write_text("\n".join(urls) + "\n", encoding="utf-8")

    return {
        "write": True,
        "tool_kind": "WRITE",
        "method": "url_listing_harvest",
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "listing_url": listing_url,
        "url_file": str(out_file),
        "url_count": len(urls),
        "urls": urls[:50],
        "stderr_tail": (proc.stderr or "")[-800:],
    }


def resolve_press_urls(
    urls: list[str] | None = None,
    *,
    url_file: str = "",
    out_name: str = "mcp_urls_resolved.json",
    out_dir: str = "",
    limit: int = 0,
) -> dict[str, Any]:
    """WRITE: scrape_doj router. justice.gov → API resolve; others → mode=scrape JSON."""
    out = _ensure_out(out_dir)
    collected: list[str] = []
    if url_file.strip():
        p = Path(url_file.strip())
        if not p.is_absolute():
            p = _REPO / p
        if not p.is_file():
            return {"error": f"url_file not found: {p}", "write": True}
        collected = [
            ln.strip()
            for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip().startswith("http")
        ]
    if urls:
        collected.extend(u.strip() for u in urls if (u or "").strip().startswith("http"))
    # dedupe preserve order
    seen: set[str] = set()
    ordered: list[str] = []
    for u in collected:
        if u not in seen:
            seen.add(u)
            ordered.append(u)
    if limit and limit > 0:
        ordered = ordered[: int(limit)]
    if not ordered:
        return {"error": "Provide urls[] and/or url_file with http(s) lines", "write": True}

    scrape_doj = _load_module("scrape_doj_mcp", _COLLECTOR / "scrape_doj.py")
    records = scrape_doj.build_records(ordered)
    out_path = out / (out_name if out_name.endswith(".json") else f"{_safe_slug(out_name)}.json")
    out_path.write_text(json.dumps(records, indent=2), encoding="utf-8")

    return {
        "write": True,
        "tool_kind": "WRITE",
        "method": "url_path_resolve",
        "ok": True,
        "resolved_json": str(out_path),
        "count": len(records),
        "resolved": sum(1 for r in records if r.get("mode") == "resolved"),
        "scrape": sum(1 for r in records if r.get("mode") == "scrape"),
        "unresolved": sum(1 for r in records if r.get("mode") == "unresolved"),
        "records": [
            {
                "source_url": r.get("source_url"),
                "mode": r.get("mode"),
                "title": r.get("title"),
                "pub_date": r.get("pub_date"),
            }
            for r in records
        ],
    }


def build_press_pdf(
    *,
    doj_file: str = "",
    url_file: str = "",
    out_name: str = "MCP_PRESS.pdf",
    out_dir: str = "",
    limit: int = 1,
    jina_fallback: bool = True,
    insecure: bool = False,
) -> dict[str, Any]:
    """WRITE: scrape_pdf.py → merged press-release PDF (doj-file or url-file)."""
    if not doj_file.strip() and not url_file.strip():
        return {"error": "Provide doj_file and/or url_file", "write": True}

    out = _ensure_out(out_dir)
    out_name_s = out_name if out_name.endswith(".pdf") else f"{_safe_slug(out_name)}.pdf"

    cmd = [
        sys.executable,
        str(_COLLECTOR / "scrape_pdf.py"),
        "--out-dir",
        str(out),
        "--out-name",
        out_name_s,
        "--limit",
        str(max(1, int(limit))),
    ]
    if doj_file.strip():
        p = Path(doj_file.strip())
        if not p.is_absolute():
            p = _REPO / p
        if not p.is_file():
            return {"error": f"doj_file not found: {p}", "write": True}
        cmd.extend(["--doj-file", str(p)])
    else:
        p = Path(url_file.strip())
        if not p.is_absolute():
            p = _REPO / p
        if not p.is_file():
            return {"error": f"url_file not found: {p}", "write": True}
        cmd.extend(["--url-file", str(p)])
    if jina_fallback:
        cmd.append("--jina-fallback")
    if insecure:
        cmd.append("--insecure")

    proc = subprocess.run(
        cmd,
        cwd=str(_COLLECTOR),
        capture_output=True,
        text=True,
        timeout=300,
    )
    pdf_path = out / out_name_s
    return {
        "write": True,
        "tool_kind": "WRITE",
        "method": "build_press_pdf",
        "ok": proc.returncode == 0 and pdf_path.is_file(),
        "exit_code": proc.returncode,
        "pdf_path": str(pdf_path) if pdf_path.is_file() else None,
        "pdf_bytes": pdf_path.stat().st_size if pdf_path.is_file() else 0,
        "stdout_tail": (proc.stdout or "")[-1000:],
        "stderr_tail": (proc.stderr or "")[-600:],
    }


def collect_case_dual_path(
    title_term: str,
    *,
    topic_slug: str = "",
    require_regex: str = "",
    out_dir: str = "",
) -> dict[str, Any]:
    """WRITE helper: one topic → DOJ harvest PDF + same URL via url-path resolve PDF.

    Intern/agent convenience for A/B collection (API discovery vs URL-path router).
    """
    slug = _safe_slug(topic_slug or title_term)
    out = _ensure_out(out_dir or f"collector_output/mcp_collect/{slug}")

    harvest = harvest_doj_press_topic(
        title_term,
        require_regex=require_regex or title_term,
        max_keep=1,
        limit_pages=2,
        slug=f"doj_{slug}",
        keep_early=True,
        out_dir=str(out),
    )
    if not harvest.get("ok") or not harvest.get("records"):
        return {
            "write": True,
            "ok": False,
            "topic": title_term,
            "slug": slug,
            "harvest": harvest,
            "error": "DOJ harvest returned no records",
        }

    rec = harvest["records"][0]
    source_url = rec.get("source_url") or ""
    resolved_json = harvest.get("resolved_json")

    pdf_a = build_press_pdf(
        doj_file=resolved_json or "",
        out_name=f"{slug}_via_doj_api.pdf",
        out_dir=str(out),
        limit=1,
    )

    # URL path: same URL → resolve_press_urls → PDF
    url_list = out / f"{slug}_same_case_url.txt"
    url_list.write_text(source_url + "\n", encoding="utf-8")
    resolved_b = resolve_press_urls(
        url_file=str(url_list),
        out_name=f"{slug}_via_url_resolved.json",
        out_dir=str(out),
        limit=1,
    )
    pdf_b = build_press_pdf(
        doj_file=resolved_b.get("resolved_json") or "",
        out_name=f"{slug}_via_url_path.pdf",
        out_dir=str(out),
        limit=1,
    )

    import asyncio

    from caselinker_mcp.public_records import search_courtlistener

    cl_query = (rec.get("title") or title_term)[:120]
    try:
        court = asyncio.run(
            search_courtlistener(cl_query, search_type="r", free_only=True, max_results=3)
        )
    except Exception as exc:  # noqa: BLE001  surface in packet, don't fail dual collect
        court = {"error": str(exc)}

    return {
        "write": True,
        "tool_kind": "WRITE",
        "ok": bool(pdf_a.get("ok") and pdf_b.get("ok")),
        "topic": title_term,
        "slug": slug,
        "case": rec,
        "path_a_doj_api": pdf_a,
        "path_b_url_path": pdf_b,
        "url_resolve": resolved_b,
        "out_dir": str(out),
        "courtlistener": court,
    }
