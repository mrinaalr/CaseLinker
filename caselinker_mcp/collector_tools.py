"""MCP wrappers over ``collector`` for the press-release collector suite.

Two collection methods (same as PRESS_RELEASE_COLLECTION.md):

1. DOJ News API: discover by title term. Do not fetch justice.gov HTML (Akamai).
2. URL path: start from article URL(s) or a listing page.

WRITE tools create files under the repo (JSON url-lists, resolved records, PDFs).
They are registered only on local MCP (not Railway hosted). READ tools return
structured data only. Nothing here mutates CaseLinker sqlite.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Coroutine, TypeVar


def collector_disk_write_enabled() -> bool:
    """Same gate as ``caselinker_mcp.server.collector_disk_write_enabled``."""
    flag = os.getenv("MCP_COLLECTOR_WRITE", "").strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return True
    if flag in {"0", "false", "no", "off"}:
        return False
    if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_SERVICE_NAME"):
        return False
    return True


def _write_disabled_error() -> dict[str, Any]:
    return {
        "error": (
            "Collector WRITE tools are disabled on hosted MCP (Railway). "
            "Run local stdio MCP or set MCP_COLLECTOR_WRITE=1 on a machine you own."
        ),
        "write": True,
        "tool_kind": "WRITE",
        "collector_write_enabled": False,
    }

_T = TypeVar("_T")

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


def _run_async(coro: Coroutine[Any, Any, _T]) -> _T:
    """Run an async helper from sync collector code (incl. asyncio.to_thread)."""
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Already inside a running loop (rare for this module): isolate on a worker.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


# ---------------------------------------------------------------------------
# READ
# ---------------------------------------------------------------------------


def probe_press_url(url: str, *, jina_fallback: bool = True) -> dict[str, Any]:
    """READ: probe one press-release URL (no PDF write).

    justice.gov URLs resolve via the DOJ API (Akamai blocks live HTML).
    Other hosts use build_press_pdf extract (optional Jina fallback).
    """
    url = (url or "").strip()
    if not url.startswith("http"):
        return {"error": "url must be an http(s) URL", "write": False}

    resolve_mod = _load_module("resolve_press_urls_mcp", _COLLECTOR / "resolve_press_urls.py")
    if resolve_mod.is_justice_gov_url(url):
        rec = resolve_mod.resolve_justice_gov_url(url)
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

    pdf_mod = _load_module("build_press_pdf_mcp", _COLLECTOR / "build_press_pdf.py")

    ns = argparse.Namespace(
        referer=None,
        jina_fallback=jina_fallback,
        insecure=False,
    )
    resolved = pdf_mod.resolve_url_content(url, ns, verify_tls=True)
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
    """WRITE: run harvest_doj_press.py for a topic → resolved JSON under sources/ or out_dir."""
    if not collector_disk_write_enabled():
        return _write_disabled_error()
    title_term = (title_term or "").strip()
    if not title_term:
        return {"error": "title_term is required", "write": True}

    out = _ensure_out(out_dir) if out_dir else (_COLLECTOR / "sources")
    out.mkdir(parents=True, exist_ok=True)
    slug_s = _safe_slug(slug or f"doj_{title_term}")
    require = require_regex.strip() or re.escape(title_term.split()[0])

    cmd = [
        sys.executable,
        str(_COLLECTOR / "harvest_doj_press.py"),
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


def listing_fetch_argv(
    listing_url: str,
    out_file: Path,
    *,
    same_host: bool = True,
    path_prefix: str = "",
    require_any: str = "",
    exclude: str = "",
    google_cse: bool = False,
    cse_max_results: int = 0,
    url_template: str = "",
    page_range: str = "",
) -> list[str]:
    """CLI argv for fetch_source_urls.py. HTML page, paginated template, or Google CSE."""
    cmd = [sys.executable, str(_COLLECTOR / "fetch_source_urls.py")]
    template = (url_template or "").strip()
    pages = (page_range or "").strip()
    if google_cse:
        cmd.extend(["--google-cse-search-page", listing_url])
        if cse_max_results and int(cse_max_results) > 0:
            cmd.extend(["--cse-max-results", str(int(cse_max_results))])
    elif template:
        cmd.extend(["--url-template", template, "--page-range", pages or "0:0"])
    else:
        cmd.extend(["--url", listing_url])
    cmd.extend(["-o", str(out_file)])
    if same_host and not google_cse:
        cmd.append("--same-host")
    if path_prefix.strip():
        cmd.extend(["--path-prefix", path_prefix.strip()])
    for flag, blob in (("--require-any", require_any), ("--exclude", exclude)):
        for token in (blob or "").split(","):
            t = token.strip()
            if t:
                cmd.extend([flag, t])
    return cmd


def fetch_press_listing_urls(
    listing_url: str,
    *,
    out_name: str = "mcp_listing_urls.txt",
    same_host: bool = True,
    path_prefix: str = "",
    require_any: str = "",
    exclude: str = "",
    max_urls: int = 20,
    out_dir: str = "",
    google_cse: bool = False,
    cse_max_results: int = 0,
    url_template: str = "",
    page_range: str = "",
) -> dict[str, Any]:
    """WRITE: harvest article URLs from a listing, a {page} template, or a Google CSE page."""
    if not collector_disk_write_enabled():
        return _write_disabled_error()
    listing_url = (listing_url or "").strip()
    template = (url_template or "").strip()
    if google_cse or not template:
        if not listing_url.startswith("http"):
            return {"error": "listing_url must be http(s)", "write": True}
    elif "{page}" not in template and "{n}" not in template:
        return {"error": "url_template must contain {page} or {n}", "write": True}

    out = _ensure_out(out_dir)
    if out_name.endswith(".txt"):
        out_file = out / out_name
    else:
        out_file = out / f"{_safe_slug(out_name)}.txt"

    cmd = listing_fetch_argv(
        listing_url,
        out_file,
        same_host=same_host,
        path_prefix=path_prefix,
        require_any=require_any,
        exclude=exclude,
        google_cse=google_cse,
        cse_max_results=cse_max_results,
        url_template=template,
        page_range=page_range,
    )

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
        "method": "google_cse" if google_cse else ("url_template" if template else "url_listing_harvest"),
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
    """WRITE: resolve_press_urls router. justice.gov → API resolve; others → mode=scrape JSON."""
    if not collector_disk_write_enabled():
        return _write_disabled_error()
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

    resolve_mod = _load_module("resolve_press_urls_mcp", _COLLECTOR / "resolve_press_urls.py")
    records = resolve_mod.build_records(ordered)
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
    """WRITE: build_press_pdf.py → merged press-release PDF (doj-file or url-file)."""
    if not collector_disk_write_enabled():
        return _write_disabled_error()
    if not doj_file.strip() and not url_file.strip():
        return {"error": "Provide doj_file and/or url_file", "write": True}

    out = _ensure_out(out_dir)
    out_name_s = out_name if out_name.endswith(".pdf") else f"{_safe_slug(out_name)}.pdf"

    cmd = [
        sys.executable,
        str(_COLLECTOR / "build_press_pdf.py"),
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

    Convenience helper for A/B collection (API discovery vs URL-path router).
    """
    if not collector_disk_write_enabled():
        return _write_disabled_error()
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

    from caselinker_mcp.public_records import search_courtlistener

    cl_query = (rec.get("title") or title_term)[:120]
    try:
        court = _run_async(
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


def drop_collected_pdf_pages(
    pdf: str,
    pages: str,
    *,
    dry_run: bool = True,
    confirm_write: bool = False,
) -> dict[str, Any]:
    """Drop 1-based pages from a collected PDF.

    Prepared for source-level dedup (cut a repeated clipping out of an aggregate
    PDF, then re-ingest). Default is a preview: nothing is written unless
    ``dry_run`` is false AND ``confirm_write`` is true. A backup is written beside
    the PDF by ``collector/remove_pdf_pages_by_text.py`` on a real drop.

    Does not touch sqlite or Postgres.
    """
    will_write = (not dry_run) and bool(confirm_write)
    if will_write and not collector_disk_write_enabled():
        return _write_disabled_error()

    spec = (pages or "").strip()
    if not spec:
        return {
            "error": "pages is required, for example '365' or '12,15-17' (1-based).",
            "write": True,
            "tool_kind": "WRITE",
            "mutated": False,
        }

    raw = Path(pdf)
    path = raw if raw.is_absolute() else (_REPO / raw)
    try:
        resolved = path.resolve()
    except OSError as exc:
        return {"error": str(exc), "write": True, "mutated": False}
    repo = _REPO.resolve()
    if not resolved.is_relative_to(repo):
        return {
            "error": "pdf must stay inside the CaseLinker repo",
            "write": True,
            "mutated": False,
        }
    if resolved.suffix.lower() != ".pdf" or not resolved.is_file():
        return {"error": f"pdf not found: {resolved.name}", "write": True, "mutated": False}

    remover = _load_module("remove_pdf_pages_by_text_mcp", _COLLECTOR / "remove_pdf_pages_by_text.py")
    from pypdf import PdfReader

    reader = PdfReader(str(resolved))
    n_pages = len(reader.pages)
    try:
        drop = remover.parse_page_spec(spec, n_pages)
    except ValueError as exc:
        return {"error": f"could not parse pages: {exc}", "write": True, "mutated": False}

    preview: list[dict[str, Any]] = []
    for index in sorted(drop):
        text = reader.pages[index].extract_text() or ""
        preview.append({
            "page": index + 1,
            "snippet": re.sub(r"\s+", " ", text).strip()[:180],
        })

    base = {
        "write": True,
        "tool_kind": "WRITE",
        "pdf": resolved.name,
        "page_count": n_pages,
        "requested_pages": spec,
        "drop_pages": [index + 1 for index in sorted(drop)],
        "preview": preview,
        "dry_run": not will_write,
        "confirm_write": bool(confirm_write),
    }
    if not drop:
        return {**base, "mutated": False, "error": "no in-range pages matched"}
    if not will_write:
        return {
            **base,
            "mutated": False,
            "note": "Preview only. Pass dry_run=false and confirm_write=true to rewrite the PDF.",
        }

    before, after, _written_preview = remover.write_pdf_without_pages(
        resolved, drop, dry_run=False
    )
    backup = resolved.with_suffix(resolved.suffix + ".pre_remove_failures.bak")
    return {
        **base,
        "dry_run": False,
        "mutated": True,
        "pages_before": before,
        "pages_after": after,
        "backup": str(backup) if backup.is_file() else None,
    }
