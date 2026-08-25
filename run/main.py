"""
FastAPI Backend for CaseLinker
Provides API endpoints for visualization frontend
"""

from fastapi import FastAPI, Request, Query, HTTPException
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional, Tuple
import sys
import json
import os
import re
import hashlib
import logging
import threading
import time
import gc
import asyncio
import httpx
import requests
from datetime import datetime
from pathlib import Path
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RUN_DIR = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_RUN_DIR) not in sys.path:
    sys.path.insert(0, str(_RUN_DIR))
sys.path.insert(0, str(_REPO_ROOT / "src" / "Storage Layer"))
sys.path.insert(0, str(_REPO_ROOT / "src" / "Clustering & Analysis Layer"))
sys.path.insert(0, str(_REPO_ROOT / "src" / "Visualization Layer"))
# Processing Layer only — not Pattern Processing Layer (would shadow processing.py wrapper).
sys.path.insert(0, str(_REPO_ROOT / "src" / "Processing Layer"))
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "run"))

# Load .env from repo root and run/ (optional) so GROQ_API_KEY, GEMINI_API_KEY, DATABASE_URL, etc. work locally without export.
try:
    from dotenv import load_dotenv

    _run_dir = Path(__file__).resolve().parent
    _repo_root = _run_dir.parent
    load_dotenv(_repo_root / ".env", override=False)
    load_dotenv(_run_dir / ".env", override=False)
except ImportError:
    pass

# Partner API keys for exempting GET /api/cases/{case_id} from the public daily export cap.
_trusted_raw = set(os.environ.get("CASELINKER_TRUSTED_KEYS", "").split(",")) - {""}
CASELINKER_TRUSTED_KEYS: set = {k.strip() for k in _trusted_raw if k.strip()}

# Use PostgreSQL if DATABASE_URL is set, otherwise use SQLite
if os.getenv("DATABASE_URL"):
    try:
        from storage_postgres import CaseStorage
        print("✅ Using PostgreSQL database")
    except ImportError:
        print("⚠️  PostgreSQL storage not available, falling back to SQLite")
        from storage import CaseStorage
else:
    from storage import CaseStorage
    print("✅ Using SQLite database (local development)")
from facet_tree import (
    DEFAULT_FACET_ORDER,
    ERA_PERIOD_BUCKETS,
    build_facet_tree,
    cohort_members_for_path,
    count_nodes,
    distinct_field_values,
    enrich_cases_with_era_period,
    facet_order_subset,
    filter_cases_by_constraints,
    infer_case_year,
    max_tree_depth,
)
from case_storage_utils import investigation_types_for_case
from analysis import tag_threader, return_tagged_cases, run_automated_analysis
# Import Redis cache helper
try:
    from redis_cache import (
        REDIS_AVAILABLE, 
        get_cached, 
        set_cached, 
        get_cache_key,
        clear_all_cache
    )
except ImportError:
    # Fallback if redis_cache module not found
    REDIS_AVAILABLE = False
    def get_cached(key):
        return None
    def set_cached(key, value, ttl=3600):
        return False
    def get_cache_key(endpoint, **kwargs):
        return f"caselinker:{endpoint}"

from sparql_proxy import SparqlRejected, prepare_sparql_query, sparql_cors_allow_origin
from sparql_rebuild_lock import rebuild_in_progress

_mcp_streamable_enabled = False


@asynccontextmanager
async def _app_lifespan(application: FastAPI):
    """FastAPI lifespan — starts Streamable HTTP session manager when MCP is mounted."""
    cm = None
    if _mcp_streamable_enabled:
        from caselinker_mcp.server import get_mcp_streamable_session_manager

        mgr = get_mcp_streamable_session_manager()
        cm = mgr.run()
        await cm.__aenter__()
        application.state.mcp_streamable_cm = cm
    yield
    if cm is not None:
        await cm.__aexit__(None, None, None)


app = FastAPI(title="CaseLinker API", lifespan=_app_lifespan)

# Trust Railway / reverse-proxy X-Forwarded-* headers for scheme and client IP.
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

# Rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Compress large ontology merged payloads (e.g. Big Bang merged graph).
app.add_middleware(GZipMiddleware, minimum_size=1000)


class _SparqlCorsMiddleware(BaseHTTPMiddleware):
    """Overwrite CORSMiddleware's * for /sparql only.

    Same-origin CaseLinker UI does not need CORS. Agents/curl/MCP ignore it.
    Off-origin browser pages (any site, or YASGUI) cannot fire visitor-browser
    queries unless listed in SPARQL_CORS_ORIGINS.
    """

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path.rstrip("/") != "/sparql":
            return response
        allowed = sparql_cors_allow_origin(request.headers.get("origin"))
        if allowed:
            response.headers["Access-Control-Allow-Origin"] = allowed
            response.headers["Vary"] = "Origin"
        else:
            # Starlette MutableHeaders has no pop(); delete keys that CORSMiddleware set.
            for key in ("access-control-allow-origin", "access-control-allow-credentials"):
                if key in response.headers:
                    del response.headers[key]
        return response


app.add_middleware(_SparqlCorsMiddleware)

# Structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def read_utf8_text_file(path: Path) -> str:
    """
    Read a file as UTF-8 for HTML/JSON served from disk.

    Editors and paste sources often insert Windows-1252 punctuation (em dash 0x97, closing
    quote 0x9d, etc.) into files that are otherwise UTF-8, which makes strict decoding fail
    and previously caused 500s on routes like /tech-landscape. We decode strictly first, then
    fall back to replacement so the site stays up; check logs and re-save the file as UTF-8.
    """
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        logger.warning(
            "Invalid UTF-8 in %s (%d bytes); decoding with errors=replace. "
            "Re-save as UTF-8 (avoid CP1252 smart quotes pasted into UTF-8 files).",
            path,
            len(raw),
        )
        return raw.decode("utf-8", errors="replace")


def _is_local_request(request: Request) -> bool:
    """Treat localhost traffic as internal for local development."""
    host = request.client.host if request.client else ""
    return host in {"127.0.0.1", "::1", "localhost"}


_BULK_CASES_FORBIDDEN_DETAIL = (
    "Bulk corpus export is restricted to local usage and access holders. "
    "To request full access to the corpus, please email mramachandra@umass.edu for the API key."
)

_LIFECYCLE_API_FORBIDDEN_DETAIL = (
    "Lifecycle data export is restricted to local usage and trusted API key holders. "
    "The /lifecycle visualization is public; programmatic access to GET /api/lifecycle/* "
    "requires a CaseLinker-Key listed in CASELINKER_TRUSTED_KEYS. "
    "Email mramachandra@umass.edu to request a key."
)


_CASE_ID_DAILY_LIMIT = 20
_CASE_ID_DAILY_LIMIT_DETAIL = (
    "Daily case id export limit reached (20/day). CaseLinker is open research! "
    "If you're building on this data or need bulk access, please email mramachandra@umass.edu "
    "to request a free API key for api/cases. Case id export resets at midnight UTC."
)
_case_id_daily_counts: Dict[str, int] = {}
_case_id_daily_lock = threading.Lock()


def _has_trusted_case_export_key(request: Request) -> bool:
    """True when CaseLinker-Key matches a non-empty entry in CASELINKER_TRUSTED_KEYS."""
    if not CASELINKER_TRUSTED_KEYS:
        return False
    provided = (request.headers.get("CaseLinker-Key") or "").strip()
    return bool(provided) and provided in CASELINKER_TRUSTED_KEYS


def _has_bulk_corpus_access(request: Request) -> bool:
    """Localhost or trusted partner key (bulk export and unsanitized single-case payloads)."""
    return _is_local_request(request) or _has_trusted_case_export_key(request)


def _enforce_case_id_daily_limit(request: Request) -> None:
    """
    Per-IP daily cap on GET /api/cases/{case_id} (midnight UTC reset).
    Exempt: localhost and CaseLinker-Key in CASELINKER_TRUSTED_KEYS.
    """
    if _is_local_request(request) or _has_trusted_case_export_key(request):
        return

    client_ip = request.headers.get("X-Forwarded-For", request.client.host).split(",")[0].strip()
    day = datetime.utcnow().strftime("%Y-%m-%d")
    bucket = f"{client_ip}|{day}"

    with _case_id_daily_lock:
        stale = [k for k in _case_id_daily_counts if not k.endswith(f"|{day}")]
        for k in stale:
            _case_id_daily_counts.pop(k, None)

        count = _case_id_daily_counts.get(bucket, 0)
        if count >= _CASE_ID_DAILY_LIMIT:
            raise HTTPException(status_code=429, detail=_CASE_ID_DAILY_LIMIT_DETAIL)
        _case_id_daily_counts[bucket] = count + 1


_LLM_DAILY_LIMIT = 50
_LLM_DAILY_LIMIT_DETAIL = (
    "Daily LLM chat limit reached (50/day). Resets at midnight UTC. "
    "For higher limits, email mramachandra@umass.edu."
)
_llm_daily_counts: Dict[str, int] = {}
_llm_daily_lock = threading.Lock()


def _enforce_llm_daily_limit(request: Request) -> None:
    """Per-IP daily cap on POST /api/llm/chat (midnight UTC). Exempt: localhost and CaseLinker-Key."""
    if _is_local_request(request) or _has_trusted_case_export_key(request):
        return

    client_ip = request.headers.get("X-Forwarded-For", request.client.host).split(",")[0].strip()
    day = datetime.utcnow().strftime("%Y-%m-%d")
    bucket = f"{client_ip}|{day}"

    with _llm_daily_lock:
        stale = [k for k in _llm_daily_counts if not k.endswith(f"|{day}")]
        for k in stale:
            _llm_daily_counts.pop(k, None)

        count = _llm_daily_counts.get(bucket, 0)
        if count >= _LLM_DAILY_LIMIT:
            raise HTTPException(status_code=429, detail=_LLM_DAILY_LIMIT_DETAIL)
        _llm_daily_counts[bucket] = count + 1


def _sanitize_case_for_public(case: Dict[str, Any]) -> Dict[str, Any]:
    """Remove raw narrative material from public case payloads."""
    case.pop("raw_data", None)
    extracted = case.get("extracted_features")
    if isinstance(extracted, dict):
        extracted.pop("raw_data", None)
        extracted.pop("case_text", None)
    return case


def _sanitize_tagged_cases_response(request: Request, out: Dict[str, Any]) -> Dict[str, Any]:
    """Strip raw_data from tagged-case payloads for callers without bulk corpus access."""
    if _has_bulk_corpus_access(request):
        return out
    return {
        "cases": [
            _sanitize_case_for_public(dict(c))
            for c in out.get("cases", [])
            if isinstance(c, dict)
        ],
    }


def _extract_case_text_value(case: Dict[str, Any]) -> str:
    """Best-effort extraction of case narrative text from a case payload."""
    direct = case.get("case_text")
    if isinstance(direct, str) and direct.strip():
        return direct

    raw_data = case.get("raw_data")
    if isinstance(raw_data, dict):
        text = raw_data.get("case_text")
        if isinstance(text, str) and text.strip():
            return text
    elif isinstance(raw_data, str) and raw_data.strip():
        try:
            parsed = json.loads(raw_data)
            if isinstance(parsed, dict):
                text = parsed.get("case_text")
                if isinstance(text, str) and text.strip():
                    return text
        except Exception:
            pass
    return ""


def _attach_case_text_to_automated_analysis(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure triaged cases include `case_text` for public automated-analysis UI.
    Keeps `raw_data` out of response while preserving quick modal rendering.
    """
    if not isinstance(analysis, dict):
        return analysis

    triaged = analysis.get("triaged_cases")
    if not isinstance(triaged, list) or not triaged:
        return analysis

    ids = []
    for c in triaged:
        if isinstance(c, dict):
            cid = c.get("id")
            if isinstance(cid, str) and cid:
                ids.append(cid)
    ids = list(dict.fromkeys(ids))
    if not ids:
        return analysis

    full_cases = storage.get_cases_by_ids(ids, include_raw_data=True) or []
    text_by_id: Dict[str, str] = {}
    for fc in full_cases:
        if not isinstance(fc, dict):
            continue
        cid = fc.get("id")
        if not isinstance(cid, str) or not cid:
            continue
        text = _extract_case_text_value(fc)
        if text:
            text_by_id[cid] = text

    for c in triaged:
        if not isinstance(c, dict):
            continue
        cid = c.get("id")
        if not isinstance(cid, str) or not cid:
            continue
        if not c.get("case_text"):
            case_text = text_by_id.get(cid, "")
            if case_text:
                c["case_text"] = case_text
        # Never expose raw_data via this endpoint.
        c.pop("raw_data", None)

    return analysis


def _case_summary_slim(case: Dict[str, Any]) -> Dict[str, Any]:
    """Slim case shape for chunk/by-ids summary APIs (no narratives/raw blobs)."""
    out = {
        "id": case.get("id"),
        "source": case.get("source"),
        "source_url": case.get("source_url"),
        "date_start": case.get("date_start"),
        "date_end": case.get("date_end"),
        "date_range": case.get("date_range"),
        "victim_count": case.get("victim_count"),
        "perpetrator_count": case.get("perpetrator_count"),
        "relationship_to_victim": case.get("relationship_to_victim"),
        "platforms_used": case.get("platforms_used"),
        "severity_indicators": case.get("severity_indicators"),
        "case_topics": case.get("case_topics"),
        "tags": case.get("tags"),
        "investigation_type": case.get("investigation_type"),
        "investigation_types": investigation_types_for_case(case),
        "agencies_involved": case.get("agencies_involved"),
        "organizations": case.get("organizations"),
        # Needed by visualization/visualization.html Previous Perpetrator chart and stats (slim API otherwise omits it).
        "perpetrator_registered_sex_offender": case.get("perpetrator_registered_sex_offender"),
    }
    return out


class CaseIdsBody(BaseModel):
    """Up to 500 case ids per request for batched summaries (no raw narratives)."""

    ids: List[str] = Field(..., min_length=1)


class LlmChatBody(BaseModel):
    """Public LLM assistant: natural language plus optional read-only SQL on ``cases``."""

    question: str = Field(..., min_length=1, max_length=12000)
    model: Optional[str] = Field(None, max_length=128)
    provider: Optional[str] = Field(None, max_length=32)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    logger.info(
        f"{request.method} {request.url.path}",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "process_time": round(process_time, 3),
            "client_ip": request.client.host if request.client else None
        }
    )
    
    return response

# Initialize storage
if os.getenv("DATABASE_URL"):
    # PostgreSQL - use DATABASE_URL directly
    storage = CaseStorage()
    db_path = None  # PostgreSQL doesn't use file path
else:
    # SQLite - use file path
    try:
        from config import DATABASE_PATH
    except ImportError:
        DATABASE_PATH = "caselinker.db"
    
    # Fix path for Railway - Procfile runs from 'run/' directory, so go up one level
    if Path(__file__).parent.name == 'run':
        db_path = Path(__file__).parent.parent / DATABASE_PATH
    else:
        db_path = Path(DATABASE_PATH)
    
    storage = CaseStorage(str(db_path))

# --- NL LLM (Groq + read-only ``cases`` SELECT) --------------------------------

_GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
_GEMINI_CHAT_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
_NL_DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
_NL_DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"
_NL_MAX_SQL_LEN = 4000
_NL_MAX_TOOL_ROUNDS = 8
_NL_MAX_ROWS_TO_MODEL = 12
_NL_MAX_CELL_CHARS = 220
_NL_MAX_TOOL_JSON_CHARS = 9000
_NL_FORBIDDEN_SQL_SNIPPETS = ("--", "/*", "*/")
_NL_FORBIDDEN_KEYWORDS = (
    "insert ",
    "update ",
    "delete ",
    "drop ",
    "alter ",
    "create ",
    "truncate ",
    "attach ",
    "detach ",
    "pragma ",
    "vacuum ",
    "replace ",
    "grant ",
    "revoke ",
    "copy ",
    "call ",
    "execute ",
    "merge ",
    "upsert ",
    "into outfile",
    "load_file",
    "xp_cmdshell",
    "pg_sleep",
    "benchmark(",
    "waitfor delay",
)
_NL_FORBIDDEN_IDENTIFIERS = (
    "sqlite_master",
    "sqlite_temp",
    "sqlite_schema",
    "information_schema",
    "pg_catalog",
    "pg_roles",
    "pg_user",
    "pg_shadow",
    "pg_authid",
    "pg_stat_activity",
    "victim_demographics",
    "perpetrator_demographics",
    "prosecution_outcomes",
    "precomputed_clusters",
    "cluster_groups_slim",
    "technology_revolver_slim",
    "dblink",
    "lo_import",
    "lo_export",
)


def _nl_pick_groq_model(provider: Optional[str], override: Optional[str]) -> str:
    o = (override or "").strip()
    if o and re.match(r"^[\w.\-]{1,128}$", o):
        return o
    _ = provider
    return _NL_DEFAULT_GROQ_MODEL


def _nl_reload_dotenv_for_llm() -> None:
    """Re-read ``.env`` so keys added without restarting the server are visible (override=False)."""
    try:
        from dotenv import load_dotenv

        run_dir = Path(__file__).resolve().parent
        root = run_dir.parent
        for p in (root / ".env", run_dir / ".env"):
            if p.is_file():
                load_dotenv(p, override=False)
    except ImportError:
        pass


def _nl_strip_api_key_value(v: str) -> str:
    s = (v or "").strip().strip("\ufeff")
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1].strip()
    return s


def _nl_gemini_dotenv_merged() -> Dict[str, Any]:
    """Read ``.env`` files directly so values are found even when ``os.environ`` has an empty placeholder."""
    try:
        from dotenv import dotenv_values
    except ImportError:
        return {}
    run_dir = Path(__file__).resolve().parent
    root = run_dir.parent
    merged: Dict[str, Any] = {}
    for p in (root / ".env", run_dir / ".env"):
        if not p.is_file():
            continue
        d = dotenv_values(str(p))
        if not isinstance(d, dict):
            continue
        for kk, vv in d.items():
            if kk is None:
                continue
            key = str(kk).strip().lstrip("\ufeff")
            if vv is None:
                continue
            s = str(vv).strip()
            if s:
                merged[key] = vv
    return merged


def _nl_resolve_gemini_api_key() -> str:
    """Resolve Gemini / Google AI Studio key from env and from ``.env`` files (file wins over empty env)."""
    _nl_reload_dotenv_for_llm()
    names = (
        "GEMINI_API_KEY",
        "CASELINKER_GEMINI_API_KEY",
        "GOOGLE_GENERATIVE_AI_API_KEY",
        "gemini_api_key",
        "GEMINI_KEY",
        "GOOGLE_API_KEY",
    )
    file_vals = _nl_gemini_dotenv_merged()
    for k in names:
        v = _nl_strip_api_key_value(os.getenv(k, ""))
        if not v:
            v = _nl_strip_api_key_value(str(file_vals.get(k) or ""))
        if v and not (v.startswith("${") and v.endswith("}")):
            return v
    return ""


def _nl_pick_gemini_model(override: Optional[str]) -> str:
    o = (override or "").strip()
    if o and o.lower().startswith("gemini") and re.match(r"^[\w.\-]{1,128}$", o):
        # Incomplete placeholders (e.g. "gemini", "gemini-") are not valid model ids on Google.
        if re.fullmatch(r"(?i)gemini-?", o):
            pass
        else:
            return o
    env_m = (os.getenv("CASELINKER_GEMINI_MODEL") or os.getenv("GEMINI_MODEL") or "").strip()
    if env_m and re.match(r"^[\w.\-]{1,128}$", env_m):
        return env_m
    return _NL_DEFAULT_GEMINI_MODEL


def _nl_validate_select_sql(sql: str) -> str:
    s = (sql or "").strip()
    if not s:
        raise ValueError("Empty SQL")
    if len(s) > _NL_MAX_SQL_LEN:
        raise ValueError("SQL exceeds maximum length")
    for bad in _NL_FORBIDDEN_SQL_SNIPPETS:
        if bad in s:
            raise ValueError("SQL comments are not allowed")
    core = s.rstrip().rstrip(";")
    if ";" in core:
        raise ValueError("Multiple SQL statements are not allowed")
    s = core
    if not re.match(r"(?is)^\s*select\s+", s):
        raise ValueError("Only a single SELECT statement is allowed")
    low = s.lower()
    for kw in _NL_FORBIDDEN_KEYWORDS:
        if kw in low:
            raise ValueError(f"Disallowed SQL keyword or construct: {kw.strip()!r}")
    for ident in _NL_FORBIDDEN_IDENTIFIERS:
        if re.search(rf"(?i)\b{re.escape(ident)}\b", s):
            raise ValueError(f"Disallowed identifier: {ident}")
    if not re.search(r"(?is)\bfrom\s+cases\b", s):
        raise ValueError("Query must read from the cases table (FROM cases)")
    if re.search(r"(?is)\binto\s+", s):
        raise ValueError("SELECT INTO is not allowed")
    return _nl_ensure_outer_limit(s, cap=100)


def _nl_ensure_outer_limit(sql: str, cap: int) -> str:
    t = sql.strip().rstrip(";")
    m = re.search(r"\blimit\s+(\d+)\s*$", t, flags=re.I)
    if m:
        n = int(m.group(1))
        if n > cap:
            t = re.sub(r"\blimit\s+\d+\s*$", f" LIMIT {cap}", t, count=1, flags=re.I)
        return t
    return t + f" LIMIT {cap}"


def _nl_sanitize_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows[:_NL_MAX_ROWS_TO_MODEL]:
        d: Dict[str, Any] = {}
        for k, v in r.items():
            if k == "raw_data":
                d[k] = "[omitted]"
                continue
            if isinstance(v, str) and len(v) > _NL_MAX_CELL_CHARS:
                v = v[:_NL_MAX_CELL_CHARS] + "..."
            d[k] = v
        out.append(d)
    return out


def _nl_json_tool_content(tool_payload: Dict[str, Any]) -> str:
    """Keep tool messages under Groq TPM limits (on-demand tier is tight)."""
    s = json.dumps(tool_payload, default=str)
    if len(s) <= _NL_MAX_TOOL_JSON_CHARS:
        return s
    rows = tool_payload.get("rows")
    if isinstance(rows, list) and rows:
        n = len(rows)
        for keep in (8, 5, 3, 1):
            slim = {
                **{k: v for k, v in tool_payload.items() if k != "rows"},
                "rows": rows[:keep],
                "_truncated": True,
                "_note": f"Showing {keep} of {n} rows to fit token limits; use COUNT or narrower SELECT.",
            }
            s = json.dumps(slim, default=str)
            if len(s) <= _NL_MAX_TOOL_JSON_CHARS:
                return s
    return json.dumps(
        {
            "error": "Tool result too large for the model context; use COUNT(*), fewer columns, or a narrower WHERE.",
            "_truncated": True,
        },
        default=str,
    )


def _nl_execute_cases_select(sql: str, *, use_postgres: bool, sqlite_path: str) -> List[Dict[str, Any]]:
    validated = _nl_validate_select_sql(sql)
    if use_postgres:
        from psycopg2.extras import RealDictCursor

        from storage_postgres import get_connection, return_connection

        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute(validated)
            rows = cur.fetchall() or []
            return [dict(x) for x in rows]
        finally:
            try:
                cur.close()
            finally:
                return_connection(conn)

    import sqlite3

    path = Path(sqlite_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"SQLite database not found: {path}")
    conn = sqlite3.connect(str(path), timeout=15.0)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(validated)
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _nl_tool_schema() -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "query_cases_database",
                "description": (
                    "One read-only SELECT on `cases` for counts/filters/aggregates. "
                    "Never guess counts. JSON-ish columns are TEXT: use LIKE/ILIKE."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sql": {
                            "type": "string",
                            "description": "Single SELECT, FROM cases only.",
                        }
                    },
                    "required": ["sql"],
                },
            },
        }
    ]


def _nl_system_prompt(dialect_label: str) -> str:
    return f"""CaseLinker assistant (journalists, law enforcement, researchers). Database: {dialect_label}.

Answer directly in plain language; avoid repetitive disclaimers unless the user asks for legal advice.
For any count, filter, or aggregate from stored cases, call query_cases_database once with a single SELECT on table cases only. Never invent numbers.

Table cases (TEXT unless noted): id, source, source_url, date_start, date_end, victim_count (int), perpetrator_count (int), relationship_to_victim, platforms_used, severity_indicators, case_topics, tags, notes, raw_data, extracted_features. JSON arrays live as text—use LIKE or ILIKE (Postgres). Prefer COUNT(*) or narrow columns; avoid SELECT *; raw narrative is omitted from tool results.

Tool SQL: one SELECT, must include FROM cases; no comments or multi-statement; server adds LIMIT 100.

After tool results, summarize briefly. If SQL fails, suggest a simpler query."""


def _nl_openai_compatible_chat(
    *,
    chat_url: str,
    api_key: str,
    model: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]],
    timeout: float,
    log_label: str,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 2048,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    r = requests.post(
        chat_url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=timeout,
    )
    if not r.ok:
        logger.warning("%s HTTP %s: %s", log_label, r.status_code, r.text[:500])
    r.raise_for_status()
    return r.json()


def _nl_message_from_response(data: Dict[str, Any]) -> Dict[str, Any]:
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("LLM returned no choices")
    return choices[0].get("message") or {}


def nl_llm(
    question: str,
    *,
    provider: Optional[str],
    model_override: Optional[str],
    api_key: str,
    timeout_per_request: float = 90.0,
) -> Dict[str, Any]:
    """
    Chat with function-calling (validated read-only SELECT on ``cases`` only).

    **Groq** (default): leave the model field empty or set a Groq model id.

    **Gemini**: set the model field to a string starting with ``gemini`` (e.g. ``gemini-`` or
    ``gemini-2.5-flash`` for a specific id). Requires ``GEMINI_API_KEY`` / ``gemini_api_key`` /
    ``GOOGLE_API_KEY`` on the server. No automatic fallback between providers.
    """
    use_pg = bool(os.getenv("DATABASE_URL"))
    dialect_label = "postgresql" if use_pg else "sqlite"
    mo = (model_override or "").strip()
    use_gemini = bool(mo and mo.lower().startswith("gemini"))

    if use_gemini:
        gemini_key = _nl_resolve_gemini_api_key()
        if not gemini_key:
            raise RuntimeError(
                "Gemini is selected (model field starts with gemini) but no Gemini API key was found. "
                "Set one of: GEMINI_API_KEY, CASELINKER_GEMINI_API_KEY, GOOGLE_GENERATIVE_AI_API_KEY, "
                "gemini_api_key, GEMINI_KEY, or GOOGLE_API_KEY in the project root `.env` "
                "(same directory as `run/`) or in the process environment, then try again. "
                "If you just edited `.env`, restart the server if the key still is not picked up."
            )
        gemini_model = _nl_pick_gemini_model(model_override)
        groq_model = _NL_DEFAULT_GROQ_MODEL
    else:
        gemini_key = ""
        gemini_model = _NL_DEFAULT_GEMINI_MODEL
        groq_model = _nl_pick_groq_model(provider, model_override)

    def _sql_executor(sql: str) -> List[Dict[str, Any]]:
        sp = str(db_path) if db_path is not None else ""
        return _nl_execute_cases_select(sql, use_postgres=use_pg, sqlite_path=sp)

    def _invoke_llm(msgs: List[Dict[str, Any]], tls: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
        if use_gemini:
            return _nl_openai_compatible_chat(
                chat_url=_GEMINI_CHAT_URL,
                api_key=gemini_key,
                model=gemini_model,
                messages=msgs,
                tools=tls,
                timeout=timeout_per_request,
                log_label="Gemini",
            )
        return _nl_openai_compatible_chat(
            chat_url=_GROQ_CHAT_URL,
            api_key=api_key,
            model=groq_model,
            messages=msgs,
            tools=tls,
            timeout=timeout_per_request,
            log_label="Groq",
        )

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": _nl_system_prompt(dialect_label)},
        {"role": "user", "content": question},
    ]
    tools = _nl_tool_schema()
    tool_rounds = 0
    active_model = gemini_model if use_gemini else groq_model

    for _ in range(_NL_MAX_TOOL_ROUNDS):
        data = _invoke_llm(messages, tools)
        active_model = gemini_model if use_gemini else groq_model
        msg = _nl_message_from_response(data)
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            content = msg.get("content")
            if isinstance(content, str) and content.strip():
                return {
                    "answer": content.strip(),
                    "model": active_model,
                    "dialect": dialect_label,
                    "tool_rounds": tool_rounds,
                }
            return {
                "answer": "(No text reply from the model. Try rephrasing your question.)",
                "model": active_model,
                "dialect": dialect_label,
                "tool_rounds": tool_rounds,
            }

        messages.append(
            {
                "role": "assistant",
                "content": msg.get("content"),
                "tool_calls": tool_calls,
            }
        )

        for tc in tool_calls:
            tool_rounds += 1
            tid = tc.get("id") or "call_unknown"
            fn = (tc.get("function") or {}).get("name")
            raw_args = (tc.get("function") or {}).get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else {}
            except json.JSONDecodeError:
                args = {}
            if fn != "query_cases_database":
                tool_payload: Dict[str, Any] = {"error": f"Unknown tool {fn!r}"}
            else:
                sql = args.get("sql") if isinstance(args, dict) else None
                if not isinstance(sql, str) or not sql.strip():
                    tool_payload = {"error": "Missing sql string in tool arguments"}
                else:
                    try:
                        rows = _sql_executor(sql.strip())
                        tool_payload = {
                            "row_count": len(rows),
                            "rows": _nl_sanitize_rows(rows),
                        }
                    except Exception as ex:  # noqa: BLE001
                        logger.info("LLM SQL tool error: %s", ex)
                        tool_payload = {"error": str(ex)}
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tid,
                    "name": "query_cases_database",
                    "content": _nl_json_tool_content(tool_payload),
                }
            )

    return {
        "answer": "Stopped after too many tool rounds - please ask a simpler question.",
        "model": active_model,
        "dialect": dialect_label,
        "tool_rounds": tool_rounds,
    }


# Facet tree API: rebuilt when case count changes (not persisted to disk)
_facet_tree_cache_payload: Optional[Dict[str, Any]] = None
_facet_tree_cache_key: Optional[tuple] = None


def _parse_facet_constraints_param(raw: Optional[str]) -> Dict[str, List[str]]:
    """Query JSON: { field_key: [allowed values, ...], ... }; any tag on the case may match."""
    if not raw or not str(raw).strip():
        return {}
    try:
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            return {}
        valid_keys = {k for k, _ in DEFAULT_FACET_ORDER}
        out: Dict[str, List[str]] = {}
        for k, v in obj.items():
            fk = str(k)
            if fk not in valid_keys:
                continue
            if isinstance(v, list):
                out[fk] = [str(x) for x in v if x is not None and str(x).strip() != ""]
            elif v is not None and str(v).strip():
                out[fk] = [str(v).strip()]
        return out
    except json.JSONDecodeError:
        return {}


def _parse_include_facets_param(raw: Optional[str]) -> Optional[List[str]]:
    """Comma-separated field keys for ``/api/facet-tree``.

    ``None`` (query param absent): full DEFAULT order.
    Present but empty (e.g. ``?include_facets=``): no partition fields — one cohort.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return []
    valid = {k for k, _ in DEFAULT_FACET_ORDER}
    parts = [p.strip() for p in s.split(",") if p.strip()]
    filtered = [p for p in parts if p in valid]
    return filtered or None


def _redis_cache_payload_hash(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:48]


def _triage_saved_bundle_corpus_live(constraints: Dict[str, List[str]]) -> Dict[str, Any]:
    """
    Run the saved triage bundle on live DB cases (facet-filtered when constraints are set).
    Response shape matches the former /api/triage-model-corpus JSON-file contract; no
    triage_corpus_predictions.json is read.
    """
    try:
        from triage import build_corpus_predictions_payload, default_bundle_path, load_triage_bundle
    except ImportError as e:
        logger.warning("triage live corpus: import failed: %s", e)
        return {
            "corpus_predictions_available": False,
            "corpus_error": f"Triage module unavailable: {e}",
            "model_case_ids_by_tier": {},
            "corpus_class_names": [],
            "n_cases": 0,
            "facet_filter_applied": bool(constraints),
            "corpus_predictions_stale": False,
        }

    try:
        bundle_path = default_bundle_path()
        bundle = load_triage_bundle(bundle_path)
    except FileNotFoundError as e:
        return {
            "corpus_predictions_available": False,
            "corpus_error": str(e),
            "model_case_ids_by_tier": {},
            "corpus_class_names": [],
            "n_cases": 0,
            "facet_filter_applied": bool(constraints),
            "corpus_predictions_stale": False,
        }
    except Exception as e:
        logger.exception("triage live corpus: bundle load failed")
        return {
            "corpus_predictions_available": False,
            "corpus_error": f"Could not load triage bundle: {e}",
            "model_case_ids_by_tier": {},
            "corpus_class_names": [],
            "n_cases": 0,
            "facet_filter_applied": bool(constraints),
            "corpus_predictions_stale": False,
        }

    bp_resolved = str(Path(bundle_path).resolve())
    cases = storage.get_all_cases(include_raw_data=False) or []
    enrich_cases_with_era_period(cases)
    filtered = filter_cases_by_constraints(cases, constraints) if constraints else cases

    if not filtered:
        cn = list(bundle.class_names)
        return {
            "corpus_predictions_available": True,
            "model_case_ids_by_tier": {n: [] for n in cn},
            "corpus_class_names": cn,
            "n_cases": 0,
            "corpus_predictions_stale": False,
            "facet_filter_applied": bool(constraints),
            "corpus_predictions_meta": {
                "generated_at": datetime.now().isoformat(),
                "bundle_path": bp_resolved,
                "n_cases_db": len(cases),
                "n_cases_in_view": 0,
                "source": "live_db",
            },
        }

    try:
        payload = build_corpus_predictions_payload(filtered, bundle, bp_resolved)
    except Exception as e:
        logger.exception("triage live corpus: inference failed")
        return {
            "corpus_predictions_available": False,
            "corpus_error": (
                f"Model inference failed ({e}). Retrain with the same Python as the API: "
                "./.venv/bin/python scripts/run/train_triage_model.py --out models/triage_bundle.joblib"
            ),
            "model_case_ids_by_tier": {},
            "corpus_class_names": [],
            "n_cases": 0,
            "facet_filter_applied": bool(constraints),
            "corpus_predictions_stale": False,
        }

    return {
        "corpus_predictions_available": True,
        "model_case_ids_by_tier": payload["model_case_ids_by_tier"],
        "corpus_class_names": payload["class_names"],
        "n_cases": payload["n_cases"],
        "corpus_predictions_stale": False,
        "facet_filter_applied": bool(constraints),
        "corpus_predictions_meta": {
            "generated_at": payload["generated_at"],
            "bundle_path": payload["bundle_path"],
            "n_cases_db": len(cases),
            "n_cases_in_view": payload["n_cases"],
            "source": "live_db",
        },
    }


def _facet_tree_cache_key_tuple(
    case_count: int,
    max_depth: Optional[int],
    constraints: Dict[str, List[str]],
    include_facets: Optional[List[str]],
) -> tuple:
    if include_facets is None:
        inc = "*"
    elif len(include_facets) == 0:
        inc = ""
    else:
        inc = ",".join(sorted(include_facets))
    cons = json.dumps(constraints, sort_keys=True, ensure_ascii=True)
    return (case_count, max_depth, cons, inc)

# Cached case count (avoids DB hit on every request - case count rarely changes)
_case_count_cache = None
_case_count_cache_time = 0.0
_CASE_COUNT_TTL = 30  # seconds


def _perpetrator_age_bin_label(age: int) -> str:
    """Label for stats chart: ages 18–19 use explicit bin (perp ages are filtered to 18+)."""
    if 18 <= age <= 19:
        return "18-19"
    lo = (age // 5) * 5
    return f"{lo}-{lo + 4}"


def _agencies_involved_for_case(case: Dict[str, Any], parse_field) -> set:
    """Unique stored agency labels for one case (agencies_involved only; no read-path rewrite)."""
    agencies = parse_field(case.get("agencies_involved", []))
    out: set = set()
    for org in agencies:
        if org and isinstance(org, str) and org.strip():
            out.add(org.strip())
    return out


def get_case_count() -> int:
    """
    Lightweight helper for counting cases.
    Cached for 30s to avoid DB hit on every cluster-groups/stats request.
    """
    global _case_count_cache, _case_count_cache_time
    try:
        now = time.time()
        if _case_count_cache is not None and (now - _case_count_cache_time) < _CASE_COUNT_TTL:
            return _case_count_cache
        count = storage.get_case_count()
        _case_count_cache = count
        _case_count_cache_time = now
        return count
    except Exception:
        return _case_count_cache if _case_count_cache is not None else 0


def _slim_for_cluster_groups(case_groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Strip case objects to ID strings only - frontend only needs IDs for the bubble chart.
    Full case data is fetched via /api/cases when user clicks. Reduces payload 10-50x.
    """
    if not case_groups:
        return []
    result = []
    for group in case_groups:
        slim_group = {k: v for k, v in group.items() if k != 'cases' and k != 'internal_groups'}
        cases = group.get('cases', [])
        slim_group['cases'] = [
            c.get('id') if isinstance(c, dict) else (c if isinstance(c, str) else None)
            for c in cases
        ]
        slim_group['cases'] = [x for x in slim_group['cases'] if x]
        internal = group.get('internal_groups', [])
        slim_group['internal_groups'] = [
            {
                'cases': [
                    c.get('id') if isinstance(c, dict) else (c if isinstance(c, str) else None)
                    for c in ig.get('cases', [])
                ],
                'size': ig.get('size', 0)
            }
            for ig in internal
        ]
        for ig in slim_group['internal_groups']:
            ig['cases'] = [x for x in ig['cases'] if x]
        result.append(slim_group)
    return result


# --- Automated analysis / cluster warmup (never compute on the request path) ---
_automated_analysis_lock = threading.Lock()
_automated_analysis_computing = False
_automated_analysis_compute_count = 0  # asserts single-flight under concurrent cold hits
_automated_analysis_mem_cache = None
_automated_analysis_mem_case_count = None
_CASES_SUMMARIES_CHUNK_SEM = threading.BoundedSemaphore(8)

# Declared before startup thread so background warmers never race NameError
_tags_cache = None
_tags_cache_case_count = 0
_cluster_groups_cache = None
_cluster_groups_cache_case_count = None


def _load_cases_slim_chunked(chunk_size: int = 500) -> List[Dict[str, Any]]:
    """Stream cases from DB in chunks (no raw_data) — avoids full-table materialization spike."""
    cases: List[Dict[str, Any]] = []
    offset = 0
    while True:
        chunk = storage.get_cases_slim_chunk(offset, chunk_size) or []
        if not chunk:
            break
        cases.extend(chunk)
        if len(chunk) < chunk_size:
            break
        offset += chunk_size
    return cases


def _hydrate_keyword_sample_texts(cases: List[Dict[str, Any]], sample_n: int = 10) -> None:
    """Attach case_text onto a small sample for semantic keywords (avoid loading all narratives)."""
    sample = [c for c in cases[:sample_n] if isinstance(c, dict) and c.get("id")]
    if not sample:
        return
    ids = [c["id"] for c in sample]
    full = storage.get_cases_by_ids(ids, include_raw_data=True) or []
    text_by_id: Dict[str, str] = {}
    for fc in full:
        if isinstance(fc, dict) and fc.get("id"):
            text = _extract_case_text_value(fc)
            if text:
                text_by_id[fc["id"]] = text
    for c in sample:
        t = text_by_id.get(c["id"])
        if t:
            c["case_text"] = t


def _schedule_automated_analysis_warmup(case_count: int, reason: str = "request") -> bool:
    """
    Single-flight: start at most one background compute. Returns True if this call started it.
    Compute NEVER runs on the request thread.
    """
    global _automated_analysis_computing, _automated_analysis_compute_count

    with _automated_analysis_lock:
        if _automated_analysis_computing:
            return False
        _automated_analysis_computing = True
        _automated_analysis_compute_count += 1
        compute_id = _automated_analysis_compute_count

    def _runner():
        global _automated_analysis_computing, _automated_analysis_mem_cache, _automated_analysis_mem_case_count
        global _cluster_groups_cache, _cluster_groups_cache_case_count
        global _tags_cache, _tags_cache_case_count
        try:
            # Grep-proof: this string lives only on the startup/background path.
            print(
                f"⚠️  No Redis automated-analysis cache, computing on-demand (this is slow) "
                f"[background compute=#{compute_id} reason={reason}]..."
            )
            cases = _load_cases_slim_chunked()
            if not cases:
                print("⚠️  Automated analysis warmup: no cases loaded")
                return
            _hydrate_keyword_sample_texts(cases, sample_n=10)
            analysis_results = run_automated_analysis(cases)
            # Warm tags from the same slim load before freeing it
            try:
                case_topics = set()
                severity_indicators = set()
                platforms_used = set()
                investigation_types = set()
                relationships = set()
                status = set()
                for c in cases:
                    for t in (c.get('case_topics') or []):
                        if t: case_topics.add(t)
                    for s in (c.get('severity_indicators') or []):
                        if s: severity_indicators.add(s)
                    for p in (c.get('platforms_used') or []):
                        if p: platforms_used.add(p)
                    for inv_t in investigation_types_for_case(c):
                        investigation_types.add(inv_t)
                    if c.get('relationship_to_victim'): relationships.add(c['relationship_to_victim'])
                    if c.get('perpetrator_registered_sex_offender'): status.add('registered_sex_offender')
                tags_result = {
                    "case_topics": sorted(case_topics), "severity_indicators": sorted(severity_indicators),
                    "platforms_used": sorted(platforms_used), "investigation_types": sorted(investigation_types),
                    "relationships": sorted(relationships), "status": sorted(status)
                }
                _tags_cache = tags_result
                _tags_cache_case_count = len(cases)
                set_cached(get_cache_key('tags', version=len(cases)), tags_result, ttl=86400)
            except Exception as tag_err:
                print(f"⚠️  Tags warm during AA compute failed: {tag_err}")
            del cases
            gc.collect()

            stored_aa = storage.store_automated_analysis_slim(analysis_results, case_count)
            stored_cg = storage.store_precomputed_clusters(analysis_results, case_count)
            if not stored_aa:
                print("❌ Failed to persist automated_analysis_slim after background compute")
            if not stored_cg:
                print("❌ Failed to persist slim cluster groups after background compute")

            result = {
                "success": True,
                "analysis": analysis_results,
                "cached": True,
                "source": "background",
            }
            cache_key = get_cache_key("automated-analysis", version=case_count)
            redis_ok = set_cached(cache_key, result, ttl=86400)
            _automated_analysis_mem_cache = result
            _automated_analysis_mem_case_count = case_count

            slim_groups = _slim_for_cluster_groups(analysis_results.get("case_groups", []))
            cg_result = {
                "success": True,
                "case_groups": slim_groups,
                "cached": True,
                "source": "background",
            }
            set_cached(get_cache_key("cluster-groups", version=case_count), cg_result, ttl=86400)
            _cluster_groups_cache = cg_result
            _cluster_groups_cache_case_count = case_count
            if stored_aa and redis_ok:
                print(f"✅ Automated analysis warmed and persisted ({case_count} cases, compute=#{compute_id})")
            elif redis_ok or _automated_analysis_mem_cache is not None:
                print(
                    f"✅ Automated analysis warmed in memory/Redis ({case_count} cases, compute=#{compute_id})"
                    + ("" if stored_aa else "; Postgres slim persist failed")
                )
            else:
                print(
                    f"⚠️  Automated analysis computed ({case_count} cases, compute=#{compute_id}) "
                    "but cache persist incomplete"
                )
        except Exception as e:
            print(f"⚠️  Error in automated analysis background compute: {e}")
        finally:
            with _automated_analysis_lock:
                _automated_analysis_computing = False

    threading.Thread(target=_runner, daemon=True, name=f"aa-warmup-{compute_id}").start()
    return True


def _build_automated_analysis_response(analysis: Dict[str, Any], source: str, cached: bool) -> Dict[str, Any]:
    analysis = _attach_case_text_to_automated_analysis(analysis) if isinstance(analysis, dict) else analysis
    return {
        "success": True,
        "analysis": analysis,
        "cached": cached,
        "source": source,
        "_cache_source": source,
    }


# In-process cache for /api/cases to keep local/dev fast even without Redis
_cases_cache = {
    "include_raw_false": None,
    "include_raw_true": None,
}
_cases_cache_case_count = 0

# Log database status on startup and pre-compute clusters
try:
    case_count = get_case_count()
    if db_path:
        print(f"Database active with path: {db_path}")
    else:
        print(f"Database active: PostgreSQL (via DATABASE_URL)")
    print(f"Cases in database: {case_count}")
    if case_count == 0:
        if db_path:
            print(f"⚠️  Warning: Database exists but contains 0 cases. Check if database file is in the correct location.")
        else:
            print(f"⚠️  Warning: PostgreSQL database contains 0 cases. Process PDFs to add cases.")
    else:
        # Pre-compute clusters + automated analysis on startup (background, non-blocking).
        # Load order: Redis → Postgres slim → background recompute only if both empty.
        import threading
        def precompute_clusters_background():
            global _cluster_groups_cache, _cluster_groups_cache_case_count, _tags_cache, _tags_cache_case_count
            global _automated_analysis_mem_cache, _automated_analysis_mem_case_count
            try:
                print("Pre-computing clusters in background...")
                case_count = get_case_count()
                cache_key = get_cache_key('cluster-groups', version=case_count)
                cached_result = get_cached(cache_key)
                if cached_result is not None:
                    _cluster_groups_cache = cached_result
                    _cluster_groups_cache_case_count = case_count
                    print(f"✅ Cluster cache warmed from Redis ({case_count} cases)")
                else:
                    slim_from_db = storage.get_cluster_groups_slim(case_count)
                    if slim_from_db and len(slim_from_db) > 0:
                        result = {"success": True, "case_groups": slim_from_db, "cached": True, "source": "startup"}
                        set_cached(cache_key, result, ttl=86400)
                        _cluster_groups_cache = result
                        _cluster_groups_cache_case_count = case_count
                        print(f"✅ Cluster cache warmed from DB slim ({case_count} cases)")

                # Warm automated-analysis: Redis → Postgres slim → schedule background compute
                aa_key = get_cache_key('automated-analysis', version=case_count)
                aa_cached = get_cached(aa_key)
                need_compute = False
                if aa_cached is not None:
                    _automated_analysis_mem_cache = aa_cached
                    _automated_analysis_mem_case_count = case_count
                    print(f"✅ Automated-analysis cache warmed from Redis ({case_count} cases)")
                else:
                    aa_from_db = storage.get_automated_analysis_slim(case_count)
                    if aa_from_db:
                        aa_result = {
                            "success": True,
                            "analysis": aa_from_db,
                            "cached": True,
                            "source": "startup",
                        }
                        set_cached(aa_key, aa_result, ttl=86400)
                        _automated_analysis_mem_cache = aa_result
                        _automated_analysis_mem_case_count = case_count
                        print(f"✅ Automated-analysis cache warmed from DB slim ({case_count} cases)")
                    else:
                        need_compute = True

                if _cluster_groups_cache is None:
                    need_compute = True

                if need_compute:
                    # Single compute path also refreshes cluster + AA caches; skip dual case loads
                    _schedule_automated_analysis_warmup(case_count, reason="startup")
                    return

                # Warm tags when missing (slim load only — never include_raw_data)
                if _tags_cache is None or _tags_cache_case_count != case_count:
                    cases = _load_cases_slim_chunked()
                    if cases:
                        case_topics = set()
                        severity_indicators = set()
                        platforms_used = set()
                        investigation_types = set()
                        relationships = set()
                        status = set()
                        for c in cases:
                            for t in (c.get('case_topics') or []):
                                if t: case_topics.add(t)
                            for s in (c.get('severity_indicators') or []):
                                if s: severity_indicators.add(s)
                            for p in (c.get('platforms_used') or []):
                                if p: platforms_used.add(p)
                            for inv_t in investigation_types_for_case(c):
                                investigation_types.add(inv_t)
                            if c.get('relationship_to_victim'): relationships.add(c['relationship_to_victim'])
                            if c.get('perpetrator_registered_sex_offender'): status.add('registered_sex_offender')
                        tags_result = {
                            "case_topics": sorted(case_topics), "severity_indicators": sorted(severity_indicators),
                            "platforms_used": sorted(platforms_used), "investigation_types": sorted(investigation_types),
                            "relationships": sorted(relationships), "status": sorted(status)
                        }
                        _tags_cache = tags_result
                        _tags_cache_case_count = len(cases)
                        set_cached(get_cache_key('tags', version=len(cases)), tags_result, ttl=86400)
                        del cases
                        gc.collect()
            except Exception as e:
                print(f"⚠️  Error pre-computing clusters: {e}")
        
        cluster_thread = threading.Thread(target=precompute_clusters_background, daemon=True)
        cluster_thread.start()
except Exception as e:
    print(f"⚠️  Database initialization warning: {e}")
    if db_path:
        print(f"   Looking for database at: {db_path}")
        print(f"   Database exists: {db_path.exists()}")
    else:
        print(f"   Using PostgreSQL (check DATABASE_URL environment variable)")


@app.get("/", response_class=HTMLResponse)
async def serve_home():
    """Serve the home page"""
    html_path = Path(__file__).parent.parent / "visualization" / "home.html"
    if html_path.exists():
        return HTMLResponse(content=read_utf8_text_file(html_path))
    else:
        return HTMLResponse(content="<h1>CaseLinker</h1><p>Home page not found. Go to <a href='/visualization'>/visualization</a></p>", status_code=404)


@app.get("/api/cases")
@limiter.limit("100/minute")
def get_all_cases(request: Request, include_raw_data: bool = False):
    """
    Get all cases from database.
    Uses Redis caching for fast responses (shared across all workers/instances).
    
    Args:
        include_raw_data: If True, include full raw_data (slower, larger payload).
                         Default False for faster initial loads.
    """
    global _cases_cache, _cases_cache_case_count

    if not _has_bulk_corpus_access(request):
        raise HTTPException(status_code=403, detail=_BULK_CASES_FORBIDDEN_DETAIL)

    try:
        # Get current case count for cache versioning
        current_case_count = get_case_count()

        # If Redis is available, prefer shared cache (works across workers)
        if REDIS_AVAILABLE:
            cache_key = get_cache_key(
                "cases",
                version=current_case_count,
                include_raw_data=include_raw_data,
            )

            cached_result = get_cached(cache_key)
            if cached_result is not None:
                return cached_result

        # Fallback / additional in-process cache for this worker
        cache_key_local = "include_raw_true" if include_raw_data else "include_raw_false"
        if (
            _cases_cache[cache_key_local] is not None
            and _cases_cache_case_count == current_case_count
        ):
            return _cases_cache[cache_key_local]

        # Cache miss - load from database
        cases = storage.get_all_cases(include_raw_data=include_raw_data)
        result = cases if cases else []

        # Update local in-process cache
        _cases_cache[cache_key_local] = result
        _cases_cache_case_count = current_case_count

        # Store in Redis cache (1 hour TTL) if available
        if REDIS_AVAILABLE:
            try:
                cache_key = get_cache_key(
                    "cases",
                    version=current_case_count,
                    include_raw_data=include_raw_data,
                )
                set_cached(cache_key, result, ttl=3600)
            except Exception:
                # If Redis write fails, it's non-fatal
                pass

        return result
    except Exception:
        # Last-resort fallback to direct database query
        try:
            return storage.get_all_cases(include_raw_data=include_raw_data) or []
        except Exception:
            return []


@app.get("/api/cases-summaries-chunk")
@limiter.limit("240/minute")
def cases_summaries_chunk(
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(300, ge=1, le=500),
):
    """
    Public paginated case summaries (slim fields, no raw narratives).
    Lets timelines load the full corpus via many small responses instead of one bulk JSON.
    Bounded concurrency (Phase 1d: 16 parallel chunks were a material RSS contributor).
    """
    acquired = _CASES_SUMMARIES_CHUNK_SEM.acquire(timeout=5.0)
    if not acquired:
        raise HTTPException(status_code=503, detail="Chunk endpoint busy; retry shortly")
    try:
        slice_cases = storage.get_cases_slim_chunk(offset, limit)
        return {
            "offset": offset,
            "limit": limit,
            "count": len(slice_cases),
            "summaries": [_case_summary_slim(c) for c in slice_cases],
        }
    except Exception:
        return {"offset": offset, "limit": limit, "count": 0, "summaries": []}
    finally:
        _CASES_SUMMARIES_CHUNK_SEM.release()


@app.post("/api/cases-summaries-by-ids")
@limiter.limit("120/minute")
def cases_summaries_by_ids(request: Request, body: CaseIdsBody):
    """
    Public batched summaries for known case ids (e.g. cluster membership).
    Caps at 500 ids per request; does not expose the whole database in one call.
    """
    raw = body.ids
    seen = set()
    ids: List[str] = []
    for x in raw:
        if isinstance(x, str) and x.strip() and x not in seen:
            seen.add(x)
            ids.append(x)
        if len(ids) >= 500:
            break
    if not ids:
        raise HTTPException(status_code=400, detail="Provide at least one case id")
    try:
        cases = storage.get_cases_by_ids(ids, include_raw_data=False)
        return {"summaries": [_case_summary_slim(c) for c in cases]}
    except Exception:
        return {"summaries": []}


@app.get("/api/case-count")
@limiter.limit("120/minute")
def get_case_count_endpoint(request: Request):
    """
    Total cases only (single COUNT query). For headers and spinners without downloading /api/cases.

    Redis-cached briefly so repeat reloads do not each hit the database; UIs also use sessionStorage.
    """
    try:
        if REDIS_AVAILABLE:
            cache_key = get_cache_key("case-count-slim")
            cached = get_cached(cache_key)
            if cached is not None:
                if isinstance(cached, dict) and "count" in cached:
                    return cached
                try:
                    return {"count": int(cached)}
                except (TypeError, ValueError):
                    pass
        n = storage.get_case_count()
        out = {"count": n}
        if REDIS_AVAILABLE:
            set_cached(get_cache_key("case-count-slim"), out, ttl=60)
        return out
    except Exception:
        return {"count": 0}


@app.get("/api/facet-distinct")
@limiter.limit("60/minute")
def get_facet_distinct(request: Request):
    """
    Distinct tag values per facet field (union of all tags on cases), for prune filters.
    The facet tree still partitions by primary bucket per level; filters match if any tag fits.
    """
    try:
        current_case_count = get_case_count()
        if REDIS_AVAILABLE:
            cache_key = get_cache_key("facet-distinct", field="all", version=current_case_count)
            cached = get_cached(cache_key)
            if cached is not None and "error" not in cached:
                return cached
        cases = storage.get_all_cases(include_raw_data=False) or []
        enrich_cases_with_era_period(cases)
        options: Dict[str, Any] = {}
        for field_key, label in DEFAULT_FACET_ORDER:
            options[field_key] = {
                "label": label,
                "values": distinct_field_values(cases, field_key),
            }
        out = {"total_cases": len(cases), "facets": options}
        if REDIS_AVAILABLE:
            set_cached(
                get_cache_key("facet-distinct", field="all", version=current_case_count),
                out,
                ttl=3600,
            )
        return out
    except Exception as e:
        logger.exception("facet-distinct failed: %s", e)
        return {"error": str(e), "total_cases": 0, "facets": {}}


@app.get("/api/facet-tree")
@limiter.limit("60/minute")
def get_facet_tree(
    request: Request,
    max_depth: Optional[int] = Query(
        None,
        description="Limit facet levels (see DEFAULT_FACET_ORDER in facet_tree). Omit for full tree.",
        ge=1,
        le=32,
    ),
    facet_constraints: Optional[str] = Query(
        None,
        description='JSON object mapping field keys to allowed value lists (any tag on case may match), e.g. {"case_topics":["family"]}',
    ),
    include_facets: Optional[str] = Query(
        None,
        description="Comma-separated facet field keys (subset, order follows DEFAULT). Omit for all dimensions. "
        "Send empty (include_facets=) for no splits — single cohort.",
    ),
):
    """
    Deterministic facet decision tree over the case store (group-centric cohorts).
    Built in memory from `get_all_cases(include_raw_data=False)` — not stored as a separate file.
    Cached per (case_count, max_depth, constraints, include_facets).
    """
    global _facet_tree_cache_payload, _facet_tree_cache_key

    try:
        current_count = get_case_count()
        constraints = _parse_facet_constraints_param(facet_constraints)
        include_list = _parse_include_facets_param(include_facets)
        cache_key = _facet_tree_cache_key_tuple(current_count, max_depth, constraints, include_list)
        tree_ph = _redis_cache_payload_hash(
            {
                "max_depth": max_depth,
                "facet_constraints": facet_constraints if facet_constraints is not None else "__ABSENT__",
                "include_facets": include_facets if include_facets is not None else "__ABSENT__",
            }
        )
        if REDIS_AVAILABLE:
            redis_tree_key = get_cache_key("facet-tree", h=tree_ph, version=current_count)
            redis_cached = get_cached(redis_tree_key)
            if redis_cached is not None and not redis_cached.get("error"):
                _facet_tree_cache_payload = redis_cached
                _facet_tree_cache_key = cache_key
                return redis_cached
        if _facet_tree_cache_payload is not None and _facet_tree_cache_key == cache_key:
            return _facet_tree_cache_payload

        all_cases = storage.get_all_cases(include_raw_data=False) or []
        enrich_cases_with_era_period(all_cases)
        source_count = len(all_cases)
        cases = filter_cases_by_constraints(all_cases, constraints)
        order = facet_order_subset(DEFAULT_FACET_ORDER, include_list)
        active_constraints = {k: v for k, v in constraints.items() if v}
        root_label = "Matching cases" if active_constraints else None
        root = build_facet_tree(
            cases,
            facet_order=order,
            max_depth=max_depth,
            root_label=root_label,
        )
        payload = {
            "total_cases": len(cases),
            "source_case_count": source_count,
            "node_count": count_nodes(root),
            "tree_max_depth": max_tree_depth(root),
            "max_depth_param": max_depth,
            "facet_levels": len(order),
            "facet_levels_full": len(DEFAULT_FACET_ORDER),
            "facet_order": [{"field": k, "label": lab} for k, lab in order],
            "prune_constraints": constraints,
            "include_facets": include_list,
            "root": root.to_dict(),
        }
        _facet_tree_cache_payload = payload
        _facet_tree_cache_key = cache_key
        if REDIS_AVAILABLE:
            set_cached(
                get_cache_key("facet-tree", h=tree_ph, version=current_count),
                payload,
                ttl=3600,
            )
        return payload
    except Exception as e:
        logger.exception("facet-tree failed: %s", e)
        return {
            "error": str(e),
            "total_cases": 0,
            "source_case_count": 0,
            "node_count": 0,
            "tree_max_depth": 0,
            "max_depth_param": max_depth,
            "facet_levels": len(DEFAULT_FACET_ORDER),
            "facet_levels_full": len(DEFAULT_FACET_ORDER),
            "facet_order": [
                {"field": k, "label": lab} for k, lab in DEFAULT_FACET_ORDER
            ],
            "prune_constraints": {},
            "include_facets": None,
            "root": None,
        }


COHORT_SMALL_THRESHOLD = 3
COHORT_DEMO_ACCESS_KEY = os.getenv("COHORT_DEMO_ACCESS_KEY", "demo")


class FacetCohortMembersBody(BaseModel):
    facet_path: List[Dict[str, Any]] = Field(default_factory=list)
    facet_constraints: Dict[str, List[str]] = Field(default_factory=dict)
    access_key: Optional[str] = None


def _facet_path_tuples(raw_path: List[Dict[str, Any]]) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for step in raw_path:
        if not isinstance(step, dict):
            continue
        fk = step.get("facet") or step.get("field")
        val = step.get("value")
        if fk is not None and val is not None:
            out.append((str(fk), str(val)))
    return out


@app.post("/api/facet-cohort-members")
@limiter.limit("60/minute")
def post_facet_cohort_members(request: Request, body: FacetCohortMembersBody):
    """
    Case IDs for the cohort at a facet-tree node: same prune constraints as the tree,
    then each path step matches if the case has that value among its tags for the field.
    IDs are omitted for
    small cohorts (n < 3) unless access_key matches the demo key.
    """
    try:
        current_count = get_case_count()
        rk = None
        if REDIS_AVAILABLE:
            body_payload = body.model_dump() if hasattr(body, "model_dump") else body.dict()
            ph = _redis_cache_payload_hash(body_payload)
            rk = get_cache_key("facet-cohort", h=ph, version=current_count)
            cached = get_cached(rk)
            if cached is not None and "error" not in cached:
                return cached
        all_cases = storage.get_all_cases(include_raw_data=False) or []
        enrich_cases_with_era_period(all_cases)
        constraints = body.facet_constraints or {}
        cases = filter_cases_by_constraints(all_cases, constraints)
        path_tuples = _facet_path_tuples(body.facet_path)
        members = cohort_members_for_path(cases, path_tuples)
        ids = sorted(
            str(c["id"])
            for c in members
            if c.get("id") is not None and str(c.get("id")).strip() != ""
        )
        count = len(ids)
        key_ok = (body.access_key or "").strip() == COHORT_DEMO_ACCESS_KEY
        if count < COHORT_SMALL_THRESHOLD:
            if not key_ok:
                out = {
                    "count": count,
                    "case_ids": None,
                    "requires_access_key": True,
                    "threshold": COHORT_SMALL_THRESHOLD,
                    "message": (
                        "This cohort has fewer than three cases. Listing IDs is gated "
                        "because small sets raise mosaic and adversarial-use risk. "
                        "Enter the demo access key to reveal case IDs for use elsewhere "
                        "in the system (for example case visualization)."
                    ),
                }
                if REDIS_AVAILABLE and rk:
                    set_cached(rk, out, ttl=3600)
                return out
        out = {
            "count": count,
            "case_ids": ids,
            "requires_access_key": False,
            "threshold": COHORT_SMALL_THRESHOLD,
        }
        if REDIS_AVAILABLE and rk:
            set_cached(rk, out, ttl=3600)
        return out
    except Exception as e:
        logger.exception("facet-cohort-members failed: %s", e)
        return {"error": str(e), "count": 0, "case_ids": None, "requires_access_key": False}


# Technology revolver: platforms_used + technology-signal buckets in extracted_features
_TECHNOLOGY_REVOLVER_SNIPPET_VER = 11
_technology_revolver_cache = None
_technology_revolver_cache_case_count = None
_technology_revolver_cache_snippet_ver = None

@app.get("/api/tags")
@limiter.limit("60/minute")
def get_unique_tags(request: Request):
    """
    Get unique tags/topics from all cases for populating selectors.
    Uses in-memory -> Redis -> DB. Tags rarely change when cases are static.
    """
    global _tags_cache, _tags_cache_case_count

    try:
        current_case_count = get_case_count()

        # 1. In-memory cache
        if _tags_cache is not None and _tags_cache_case_count == current_case_count:
            out = {k: _tags_cache[k] for k in ("case_topics", "severity_indicators", "platforms_used", "investigation_types", "relationships", "status")}
            out["cached"] = True
            return out

        # 2. Redis cache
        cache_key = get_cache_key('tags', version=current_case_count)
        cached = get_cached(cache_key)
        if cached is not None:
            _tags_cache = cached
            _tags_cache_case_count = current_case_count
            out = {k: cached[k] for k in ("case_topics", "severity_indicators", "platforms_used", "investigation_types", "relationships", "status")}
            out["cached"] = True
            return out

        # 3. Compute from cases
        cases = storage.get_all_cases(include_raw_data=False)
        
        # Extract unique values
        case_topics = set()
        severity_indicators = set()
        platforms_used = set()
        investigation_types = set()
        relationships = set()
        status = set()
        
        for case in cases:
            # Case Topics
            topics = case.get('case_topics', [])
            if isinstance(topics, list):
                case_topics.update(t for t in topics if t)
            
            # Severity Indicators
            severity = case.get('severity_indicators', [])
            if isinstance(severity, list):
                severity_indicators.update(s for s in severity if s)
            
            # Platforms
            platforms = case.get('platforms_used', [])
            if isinstance(platforms, list):
                platforms_used.update(p for p in platforms if p)
            
            # Investigation Type
            for inv_type in investigation_types_for_case(case):
                investigation_types.add(inv_type)
            
            # Relationship
            rel = case.get('relationship_to_victim')
            if rel:
                relationships.add(rel)
            
            # Registered Sex Offender
            if case.get('perpetrator_registered_sex_offender'):
                status.add('registered_sex_offender')
        
        result = {
            "case_topics": sorted(list(case_topics)),
            "severity_indicators": sorted(list(severity_indicators)),
            "platforms_used": sorted(list(platforms_used)),
            "investigation_types": sorted(list(investigation_types)),
            "relationships": sorted(list(relationships)),
            "status": sorted(list(status))
        }
        _tags_cache = result
        _tags_cache_case_count = current_case_count
        set_cached(cache_key, result, ttl=86400)

        out = {k: result[k] for k in ("case_topics", "severity_indicators", "platforms_used", "investigation_types", "relationships", "status")}
        out["cached"] = False
        return out
    except Exception as e:
        from error_handler import handle_error
        return handle_error(e)


@app.get("/api/cases/{case_id}")
def get_case(request: Request, case_id: str):
    """Get a specific case by ID (20 requests per IP per day UTC; see _enforce_case_id_daily_limit)."""
    _enforce_case_id_daily_limit(request)
    case = storage.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    # Public callers can still fetch a case, but never raw narrative payloads.
    if not _has_bulk_corpus_access(request):
        case = _sanitize_case_for_public(case)
    return case


@app.get("/api/stats")
@limiter.limit("60/minute")
def get_stats(request: Request):
    """
    Get statistics about cases.
    Uses Redis caching for fast responses.
    """
    try:
        # Get current case count for cache versioning
        current_case_count = get_case_count()
        
        # Build cache key
        cache_key = get_cache_key('stats', version=current_case_count)
        
        # Try Redis cache first
        cached_result = get_cached(cache_key)
        if cached_result is not None:
            return cached_result
        
        # Cache miss - compute stats (no raw_data needed - faster)
        try:
            cases = storage.get_all_cases(include_raw_data=False)
        except Exception:
            cases = []
        
        if not cases:
            result = {
                "total_cases": 0,
                "sources": [],
                "source_count": 0,
                "unique_features": 0,
                "unique_organizations": 0,
                "date_range": {"start": None, "end": None}
            }
            set_cached(cache_key, result, ttl=3600)
            return result
        
        # Get unique sources
        sources = set()
        for case in cases:
            source = case.get('source') or case.get('raw_data', {}).get('source')
            if source:
                sources.add(source)
        
        # Calculate total extracted features - DIRECT COUNT from actual database data
        total_features = 0
        for case in cases:
            # Count array/list features - each item counts as 1 feature
            platforms = case.get('platforms_used', [])
            if isinstance(platforms, list) and platforms:
                total_features += len([p for p in platforms if p])
            
            topics = case.get('case_topics', [])
            if isinstance(topics, list) and topics:
                total_features += len([t for t in topics if t])
            
            severity = case.get('severity_indicators', [])
            if isinstance(severity, list) and severity:
                total_features += len([s for s in severity if s])
            
            agencies = case.get('agencies_involved', [])
            if isinstance(agencies, list) and agencies:
                total_features += len([a for a in agencies if a])
        
        # Calculate unique organizations (already normalized at ingestion time)
        def parse_field(field):
            """Parse JSON string fields or return list/array as-is"""
            if isinstance(field, str):
                try:
                    return json.loads(field)
                except:
                    return []
            return field if field else []
        
        unique_orgs = set()
        for case in cases:
            agencies = parse_field(case.get('agencies_involved', []))
            organizations = parse_field(case.get('organizations', []))
            # Organizations are already normalized at ingestion time, just count unique ones
            for org in agencies + organizations:
                if org and isinstance(org, str) and org.strip():
                    unique_orgs.add(org.strip())
            
            # Count single-value features (1 if exists)
            if case.get('investigation_type'):
                total_features += 1
            if case.get('relationship_to_victim'):
                total_features += 1
            if case.get('perpetrator_registered_sex_offender') is True:
                total_features += 1
            if case.get('perpetrator_age') is not None:
                total_features += 1
            if case.get('victim_count') and isinstance(case.get('victim_count'), (int, float)) and case.get('victim_count') > 0:
                total_features += 1
            
            # Count complex objects (1 if has any data)
            evidence = case.get('evidence_volume')
            if evidence and isinstance(evidence, dict):
                if evidence.get('images') or evidence.get('videos') or evidence.get('storage_size'):
                    total_features += 1
            
            prosecution = case.get('prosecution_outcome')
            if prosecution and isinstance(prosecution, dict):
                if prosecution.get('booking_status') or prosecution.get('charges') or prosecution.get('jail'):
                    total_features += 1
            
            victim_demo = case.get('case_demographics') or case.get('victim_demographics')
            if victim_demo and isinstance(victim_demo, dict):
                if (
                    victim_demo.get('ages')
                    or victim_demo.get('age_range')
                    or victim_demo.get('victim_gender')
                ):
                    total_features += 1
            if case.get('perpetrator_gender'):
                total_features += 1
        
        result = {
            "total_cases": len(cases),
            "sources": list(sources),
            "source_count": len(sources),
            "unique_features": total_features,
            "unique_organizations": len(unique_orgs),
            "date_range": {
                "start": min((c.get('date_range', {}).get('start') for c in cases if c.get('date_range', {}).get('start')), default=None),
                "end": max((c.get('date_range', {}).get('end') for c in cases if c.get('date_range', {}).get('end')), default=None)
            }
        }
        
        # Store in Redis cache (1 hour TTL)
        set_cached(cache_key, result, ttl=3600)
        
        return result
    except Exception as e:
        # Fallback to direct computation
        try:
            cases = storage.get_all_cases()
            return {
                "total_cases": len(cases) if cases else 0,
                "sources": [],
                "source_count": 0,
                "unique_features": 0,
                "unique_organizations": 0,
                "date_range": {"start": None, "end": None}
            }
        except:
            return {
                "total_cases": 0,
                "sources": [],
                "source_count": 0,
                "unique_features": 0,
                "unique_organizations": 0,
                "date_range": {"start": None, "end": None}
            }


@app.post("/api/tag-threader")
@limiter.limit("60/minute")
def get_tag_threader(request: Request, selected_tags: List[Dict[str, str]]):
    """
    Query cases matching selected tags and create threaded tag links.
    
    Args:
        selected_tags: List of dictionaries with 'tag' and 'category' keys
            Example: [{"tag": "production", "category": "case_topics"}]
    
    Returns:
        Dictionary with intersection cases and tag results
    """
    current_count = get_case_count()
    if REDIS_AVAILABLE:
        tags_keyed = sorted(
            selected_tags or [],
            key=lambda d: (
                str((d or {}).get("tag", "")),
                str((d or {}).get("category", "")),
            ),
        )
        ph = _redis_cache_payload_hash(tags_keyed)
        rk = get_cache_key("tag-threader", h=ph, version=current_count)
        cached = get_cached(rk)
        if cached is not None:
            return cached
    cases = storage.get_all_cases()
    result = tag_threader(cases, selected_tags)
    if REDIS_AVAILABLE:
        set_cached(rk, result, ttl=3600)
    return result


@app.post("/api/return-tagged-cases")
@limiter.limit("60/minute")
def get_tagged_cases(request: Request, selected_tags: List[Dict[str, str]]):
    """
    Return all cases matching the selected tags.
    
    Args:
        selected_tags: List of dictionaries with 'tag' and 'category' keys
            Example: [{"tag": "production", "category": "case_topics"}]
    
    Returns:
        List of case dictionaries matching ALL selected tags
    """
    current_count = get_case_count()
    if REDIS_AVAILABLE:
        tags_keyed = sorted(
            selected_tags or [],
            key=lambda d: (
                str((d or {}).get("tag", "")),
                str((d or {}).get("category", "")),
            ),
        )
        ph = _redis_cache_payload_hash(tags_keyed)
        rk = get_cache_key("return-tagged", h=ph, version=current_count)
        cached = get_cached(rk)
        if cached is not None:
            return _sanitize_tagged_cases_response(request, cached)
    cases = storage.get_all_cases()
    matching_cases = return_tagged_cases(cases, selected_tags)
    out = {"cases": matching_cases}
    if REDIS_AVAILABLE:
        set_cached(rk, out, ttl=3600)
    return _sanitize_tagged_cases_response(request, out)


@app.get("/api/case-ids-by-filter")
@limiter.limit("100/minute")
def get_case_ids_by_filter(
    request: Request,
    organization: str = None,
    relationship: str = None,
    prosecution_status: str = None,
    age_range: str = None,
    severity_indicator: str = None,
    platform: str = None,
    year: str = None,
    investigation_type: str = None
):
    """
    Get case IDs filtered by various criteria.
    Returns just the case IDs that match the filter.
    """
    try:
        current_count = get_case_count()
        rk = None
        if REDIS_AVAILABLE:
            filter_params = {
                "organization": organization,
                "relationship": relationship,
                "prosecution_status": prosecution_status,
                "age_range": age_range,
                "severity_indicator": severity_indicator,
                "platform": platform,
                "year": year,
                "investigation_type": investigation_type,
            }
            ph = _redis_cache_payload_hash(filter_params)
            rk = get_cache_key("case-ids-filter", h=ph, version=current_count)
            cached = get_cached(rk)
            if cached is not None and "error" not in cached:
                return cached
        cases = storage.get_all_cases(include_raw_data=False)
        
        import json
        def parse_field(field):
            if isinstance(field, str):
                try:
                    return json.loads(field)
                except:
                    return []
            return field if field else []
        
        filtered_cases = cases
        
        # Filter by organization (exact match on stored agencies_involved)
        if organization:
            org_search = organization.strip()
            filtered_cases = [
                c for c in filtered_cases
                if org_search in _agencies_involved_for_case(c, parse_field)
            ]
        
        # Filter by relationship
        if relationship:
            filtered_cases = [
                c for c in filtered_cases
                if c.get('relationship_to_victim') == relationship
            ]
        
        # Filter by prosecution status
        if prosecution_status:
            def normalize_prosecution_status(prosecution):
                """
                Mirror the logic used in stats aggregation so bar counts and
                filtered case IDs stay in sync.
                """
                if not prosecution:
                    return None
                if isinstance(prosecution, dict):
                    # Same fallback chain as in stats: booking_status → status → 'prosecuted'
                    return (
                        prosecution.get('booking_status')
                        or prosecution.get('status')
                        or 'prosecuted'
                    )
                return str(prosecution)

            filtered_cases = [
                c for c in filtered_cases
                if normalize_prosecution_status(c.get('prosecution_outcome')) == prosecution_status
            ]
        
        # Filter by age range (e.g., "25-29")
        # Match bubble chart logic: only count ages between 18-99
        if age_range:
            try:
                age_min, age_max = map(int, age_range.split('-'))
                filtered_cases = [
                    c for c in filtered_cases
                    if c.get('perpetrator_age') and (
                        (isinstance(c.get('perpetrator_age'), list) and
                         any(age_min <= age <= age_max for age in c.get('perpetrator_age') 
                             if isinstance(age, (int, float)) and 18 <= age <= 99)) or
                        (isinstance(c.get('perpetrator_age'), (int, float)) and 
                         18 <= c.get('perpetrator_age') <= 99 and
                         age_min <= c.get('perpetrator_age') <= age_max)
                    )
                ]
            except:
                pass
        
        # Filter by severity indicator
        if severity_indicator:
            filtered_cases = [
                c for c in filtered_cases
                if severity_indicator in parse_field(c.get('severity_indicators', []))
            ]
        
        # Filter by platform
        if platform:
            filtered_cases = [
                c for c in filtered_cases
                if platform in parse_field(c.get('platforms_used', []))
            ]
        
        # Filter by year
        if year:
            filtered_cases = [
                c for c in filtered_cases
                if (c.get('date_start') and str(c.get('date_start'))[:4] == year) or
                   (isinstance(c.get('date_range'), dict) and 
                    c.get('date_range').get('start') and 
                    str(c.get('date_range').get('start'))[:4] == year)
            ]
        
        # Filter by investigation type
        if investigation_type:
            inv_filter = investigation_type.lower()
            filtered_cases = [
                c for c in filtered_cases
                if inv_filter in investigation_types_for_case(c)
            ]
        
        case_ids = [c.get('id') for c in filtered_cases if c.get('id')]
        
        out = {
            "case_ids": case_ids,
            "count": len(case_ids),
            "filter": {
                "organization": organization,
                "relationship": relationship,
                "prosecution_status": prosecution_status,
                "age_range": age_range,
                "severity_indicator": severity_indicator,
                "platform": platform,
                "year": year,
                "investigation_type": investigation_type
            }
        }
        if REDIS_AVAILABLE and rk:
            set_cached(rk, out, ttl=3600)
        return out
    except Exception as e:
        from error_handler import handle_error
        return handle_error(e)


@app.post("/api/cache/clear")
@limiter.limit("10/hour")  # Rate limit to prevent abuse
def clear_cache(request: Request):
    """
    Clear all cached data (useful when code changes but case count stays same).
    Requires authentication token or environment variable for security.
    """
    try:
        expected_token = os.getenv('CACHE_CLEAR_TOKEN')
        if not expected_token:
            raise HTTPException(
                status_code=403,
                detail="Cache clear is disabled (CACHE_CLEAR_TOKEN not configured).",
            )
        token = request.query_params.get('token')
        if not token or token != expected_token:
            raise HTTPException(
                status_code=403,
                detail="Unauthorized. Provide ?token=YOUR_TOKEN.",
            )
        
        if REDIS_AVAILABLE:
            cleared = clear_all_cache()
            return {
                "success": True,
                "message": f"Cleared {cleared} cache entries",
                "cache_type": "Redis"
            }
        else:
            return {
                "success": True,
                "message": "No Redis cache to clear (using direct database queries)",
                "cache_type": "None"
            }
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/stats-detailed")
@limiter.limit("60/minute")
def get_detailed_stats(request: Request):
    """
    Get detailed statistics for visualization charts.
    Returns feature coverage, platform trends, organization involvement, etc.
    Uses Redis caching for fast responses.
    """
    try:
        # Get current case count for cache versioning
        current_case_count = get_case_count()
        
        # Build cache key
        cache_key = get_cache_key('stats-detailed', version=current_case_count)
        
        # Try Redis cache first
        cached_result = get_cached(cache_key)
        if cached_result is not None:
            return cached_result
        
        # Cache miss - compute stats
        cases = storage.get_all_cases(include_raw_data=False)
        total_cases = len(cases)
        
        if total_cases == 0:
            empty_result = {
                "feature_coverage": {},
                "platform_trends": {},
                "top_organizations": [],
                "agency_frequency": {},
                "relationship_distribution": [],
                "prosecution_distribution": [],
                "perpetrator_age_data": [],
                "severity_indicators_top": [],
                "investigation_type_distribution": [],
                "total_cases": 0
            }
            set_cached(cache_key, empty_result, ttl=3600)
            return empty_result
        
        # 1. Feature Extraction Coverage
        feature_coverage = {}
        
        # Parse JSON fields safely
        import json
        def parse_field(field):
            if isinstance(field, str):
                try:
                    return json.loads(field)
                except:
                    return []
            return field if field else []
        
        # Calculate coverage for each feature type
        severity_count = sum(1 for c in cases if parse_field(c.get('severity_indicators', [])))
        prosecution_count = sum(1 for c in cases if c.get('prosecution_outcome'))
        relationship_count = sum(1 for c in cases if c.get('relationship_to_victim'))
        platforms_count = sum(1 for c in cases if parse_field(c.get('platforms_used', [])))
        investigation_count = sum(1 for c in cases if c.get('investigation_type'))
        victim_count = sum(1 for c in cases if c.get('victim_count') is not None)
        perp_age_count = sum(1 for c in cases if c.get('perpetrator_age') is not None)
        perp_registry_count = sum(1 for c in cases if c.get('perpetrator_registered_sex_offender') is True)
        evidence_count = sum(1 for c in cases if c.get('evidence_volume') and isinstance(c.get('evidence_volume'), dict) and any(c.get('evidence_volume', {}).values()))
        agencies_count = sum(1 for c in cases if parse_field(c.get('agencies_involved', [])))
        date_count = sum(1 for c in cases if c.get('date_start') or c.get('date_range'))
        # Severity phrases: dangerous, stated, told, continue, attacked, out_of_control
        severity_phrases_count = sum(1 for c in cases if parse_field(c.get('severity_phrases', [])))
        locations_count = sum(1 for c in cases if parse_field(c.get('locations', [])))
        
        feature_coverage = {
            "Severity Indicators": (severity_count / total_cases * 100) if total_cases > 0 else 0,
            "Severity Phrases": (severity_phrases_count / total_cases * 100) if total_cases > 0 else 0,
            "Prosecution": (prosecution_count / total_cases * 100) if total_cases > 0 else 0,
            "Relationship to Victim": (relationship_count / total_cases * 100) if total_cases > 0 else 0,
            "Platforms Used": (platforms_count / total_cases * 100) if total_cases > 0 else 0,
            "Investigation Type": (investigation_count / total_cases * 100) if total_cases > 0 else 0,
            "Victim Count": (victim_count / total_cases * 100) if total_cases > 0 else 0,
            "Perpetrator Age": (perp_age_count / total_cases * 100) if total_cases > 0 else 0,
            "Registry Status": (perp_registry_count / total_cases * 100) if total_cases > 0 else 0,
            "Evidence": (evidence_count / total_cases * 100) if total_cases > 0 else 0,
            "Agencies Involved": (agencies_count / total_cases * 100) if total_cases > 0 else 0,
            "Date Range": (date_count / total_cases * 100) if total_cases > 0 else 0,
            "Locations": (locations_count / total_cases * 100) if total_cases > 0 else 0
        }
        
        # 2. Platform Usage Over Time
        from collections import defaultdict, Counter
        import json
        platform_by_year = defaultdict(lambda: defaultdict(int))
        
        for case in cases:
            year = None
            date_start = case.get('date_start') or (case.get('date_range', {}) if isinstance(case.get('date_range'), dict) else {}).get('start')
            if date_start:
                try:
                    year = str(date_start)[:4]
                except:
                    pass
            
            if not year:
                # Try to extract from raw_data
                raw_data = case.get('raw_data', {})
                if isinstance(raw_data, dict):
                    month_year = raw_data.get('month_year', '')
                    if month_year:
                        # Handle formats like "September 2025" or just "2025"
                        if ' ' in month_year:
                            year_match = month_year.split()[-1]
                        elif month_year.isdigit() and len(month_year) == 4:
                            # month_year is just a year like "2022" or "2023"
                            year_match = month_year
                        else:
                            year_match = None
                        if year_match and year_match.isdigit():
                            year = year_match
            
            if year and year.isdigit() and 2010 <= int(year) <= 2025:
                platforms = parse_field(case.get('platforms_used', []))
                for platform in platforms:
                    platform_by_year[year][platform] += 1
        
        # Get top 7 platforms overall
        all_platforms = Counter()
        for year_data in platform_by_year.values():
            all_platforms.update(year_data)
        top_platforms = [p[0] for p in all_platforms.most_common(7)]
        
        platform_trends = {
            "years": sorted(platform_by_year.keys()),
            "platforms": top_platforms,
            "data": {}
        }
        
        for year in platform_trends["years"]:
            platform_trends["data"][year] = {platform: platform_by_year[year][platform] for platform in top_platforms}
        
        # 3. Top Organizations (stored agencies_involved; normalized at ingest only)
        org_counter = Counter()
        for case in cases:
            for org in _agencies_involved_for_case(case, parse_field):
                org_counter[org] += 1

        top_organizations = [{"name": name, "count": count} for name, count in org_counter.most_common(15)]
        
        # 4. Agency Frequency Distribution
        # Count how many organizations appear in exactly N cases
        org_frequency = Counter(org_counter.values())
        agency_frequency = {
            "cases_per_org": sorted(org_frequency.keys()),
            "num_organizations": [org_frequency[k] for k in sorted(org_frequency.keys())]
        }
        
        # 5. Relationship to Victim Distribution
        relationship_counter = Counter()
        for case in cases:
            rel = case.get('relationship_to_victim')
            if rel:
                relationship_counter[rel] += 1
        relationship_distribution = [{"name": name, "count": count} for name, count in relationship_counter.most_common()]
        
        # 6. Prosecution Distribution
        prosecution_counter = Counter()
        for case in cases:
            prosecution = case.get('prosecution_outcome')
            if prosecution:
                if isinstance(prosecution, dict):
                    status = prosecution.get('booking_status') or prosecution.get('status') or 'prosecuted'
                else:
                    status = str(prosecution)
                prosecution_counter[status] += 1
        prosecution_distribution = [{"name": name, "count": count} for name, count in prosecution_counter.most_common()]
        
        # 7. Perpetrator Age Data (for bubble chart)
        # Count unique cases per age bin (not individual age occurrences)
        # This matches the filter behavior so bubble counts match filter results
        age_bins = defaultdict(set)  # Use set to track unique case IDs
        for case in cases:
            case_id = case.get('id')
            ages = case.get('perpetrator_age')
            if ages and case_id:
                case_ages = []
                if isinstance(ages, list):
                    case_ages = [int(a) for a in ages if isinstance(a, (int, float)) and 18 <= a <= 99]
                elif isinstance(ages, (int, float)) and 18 <= ages <= 99:
                    case_ages = [int(ages)]
                
                # Add case to each age bin it belongs to
                for age in case_ages:
                    bin_key = _perpetrator_age_bin_label(age)
                    age_bins[bin_key].add(case_id)
        
        # Convert sets to counts
        perpetrator_age_data = [
            {"age": age, "count": len(case_ids)} 
            for age, case_ids in sorted(age_bins.items(), key=lambda x: int(x[0].split('-')[0]))
        ]
        
        # 8. Severity Indicators (most common)
        severity_counter = Counter()
        for case in cases:
            severities = parse_field(case.get('severity_indicators', []))
            for sev in severities:
                severity_counter[sev] += 1
        severity_indicators_top = [{"name": name.replace('_', ' ').title(), "count": count} for name, count in severity_counter.most_common(10)]
        
        # 9. Investigation Type Distribution
        investigation_counter = Counter()
        for case in cases:
            for inv_type in investigation_types_for_case(case):
                investigation_counter[inv_type] += 1
        investigation_type_distribution = [{"name": name.replace('_', ' ').title(), "count": count} for name, count in investigation_counter.most_common()]
        
        result = {
            "feature_coverage": feature_coverage,
            "platform_trends": platform_trends,
            "top_organizations": top_organizations,
            "agency_frequency": agency_frequency,
            "relationship_distribution": relationship_distribution,
            "prosecution_distribution": prosecution_distribution,
            "perpetrator_age_data": perpetrator_age_data,
            "severity_indicators_top": severity_indicators_top,
            "investigation_type_distribution": investigation_type_distribution,
            "total_cases": total_cases
        }
        
        # Store in Redis cache (1 hour TTL)
        set_cached(cache_key, result, ttl=3600)
        
        return result
    except Exception as e:
        from error_handler import handle_error
        return handle_error(e)


_REVOLVER_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|(?<=[.!?][\"''])\s+")

# Narrative rarely spells canonical list strings verbatim; add prose synonyms for snippet finding.
_REVOLVER_LABEL_SYNONYMS: Dict[str, Tuple[str, ...]] = {
    "CyberTipline": (
        r"Cyber\s*Tipline",
        r"CyberTip\b",
        r"Cybertipline",
        r"Cyber\s*Tip\s*Line",
        r"missingkids\.org/cybertipline",
    ),
    # PDF line wraps often split "mega." and "nz"; plain \bMega\.nz\b then misses.
    "Mega.nz": (
        r"mega\s*\.\s*nz",
        r"mega\s+dot\s+nz",
    ),
}


def _parse_jsonish_list(field: Any) -> List[str]:
    if field is None:
        return []
    if isinstance(field, list):
        return [str(x).strip() for x in field if x is not None and str(x).strip()]
    if isinstance(field, str):
        try:
            parsed = json.loads(field)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if x is not None and str(x).strip()]
        except (json.JSONDecodeError, TypeError):
            pass
        s = field.strip()
        return [s] if s else []
    return []


def _platform_token_regex(platform: str) -> re.Pattern:
    """
    Match how a tag may appear in narrative text, not only the canonical list string.
    Slash-separated names (e.g. 'Twitter / X') also match 'Twitter', flexible 'Twitter / X',
    but we avoid lone '\\bX\\b' (too noisy in prose).
    """
    name = (platform or "").strip()
    if not name:
        return re.compile("$^")

    # Uppercase AIM only; (?i:...) limits case-insensitivity to the AOL phrase (revolver outer IGNORECASE
    # would otherwise match prose "aim").
    if name == "AOL Instant Messenger":
        return re.compile(r"(?:\bAIM\b|(?i:AOL\s+Instant\s+Messenger))")

    alternatives: List[str] = []

    if "/" in name:
        segs = [s.strip() for s in name.split("/") if s.strip()]
        if len(segs) >= 2:
            alternatives.append(r"\s*/\s*".join(re.escape(s) for s in segs))
        for s in segs:
            if len(s) < 2:
                continue
            if re.search(r"\s", s):
                alternatives.append(re.escape(s))
            else:
                alternatives.append(rf"\b{re.escape(s)}\b")

    esc = re.escape(name)
    if re.search(r"\s", name):
        alternatives.append(esc)
    else:
        alternatives.append(rf"\b{esc}\b")

    for syn in _REVOLVER_LABEL_SYNONYMS.get(name, ()):
        alternatives.append(syn)

    uniq = sorted(set(alternatives), key=len, reverse=True)
    return re.compile("(?:" + "|".join(uniq) + ")", re.IGNORECASE)


def _crop_around_match(s: str, m: re.Match, max_len: int) -> str:
    """
    Return a substring of s that contains the full match span and is at most max_len
    characters, with ellipses when truncated. Avoids cutting off the platform token.
    """
    n = len(s)
    if n <= max_len:
        return s
    a, b = m.span()
    if b - a >= max_len:
        piece = s[a : a + max_len].rstrip()
        return ("…" if a > 0 else "") + piece + ("…" if a + max_len < n else "")

    center = (a + b) // 2
    half = max_len // 2
    start = max(0, min(center - half, n - max_len))
    end = min(n, start + max_len)
    if start > a:
        start = max(0, a)
        end = min(n, start + max_len)
    if end < b:
        start = max(0, b - max_len)
        end = min(n, start + max_len)
    piece = s[start:end].strip()
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < n else ""
    return (prefix + piece + suffix).strip()


def _snippet_for_platform(case_text: str, pat: re.Pattern, max_len: int = 320) -> Optional[str]:
    """
    Prefer a sentence that contains the platform; crop around the match so the token
    stays visible. If no sentence matches, use the first document-level match in text.
    """
    if not case_text:
        return None
    for chunk in _REVOLVER_SENTENCE_SPLIT.split(case_text):
        t = " ".join(chunk.split())
        if len(t) < 4:
            continue
        m = pat.search(t)
        if not m:
            continue
        return _crop_around_match(t, m, max_len)
    m = pat.search(case_text)
    if not m:
        return None
    return _crop_around_match(case_text, m, max_len)


def _labels_for_tech_bucket(case: Dict[str, Any], bucket: str) -> List[str]:
    """Values for one bucket: case column first, then extracted_features merge fallback."""
    labs = _parse_jsonish_list(case.get(bucket))
    if labs:
        return labs
    ef = case.get("extracted_features")
    if isinstance(ef, dict):
        return _parse_jsonish_list(ef.get(bucket))
    return []


_TECH_REVOLVER_BUCKETS = (
    "platforms_used",
    "investigation_technology",
    "anonymization_network",
    "p2p_clients",
    "offense_technology",
)

_TECH_REVOLVER_ERA_ROMANS: Tuple[str, ...] = ("I", "II", "III", "IV")

_TECH_REVOLVER_TEXT_IDS_PER_LABEL = 15
_TECH_REVOLVER_TEXT_IDS_CAP = 600


def _era_roman_for_slim_case(case: Dict[str, Any]) -> Optional[str]:
    """Map case year to Case Studies era I–IV (facet_tree buckets); None if outside ranges."""
    y = infer_case_year(case)
    if y is None:
        return None
    for i, (lo, hi, _) in enumerate(ERA_PERIOD_BUCKETS):
        if lo <= y <= hi:
            return _TECH_REVOLVER_ERA_ROMANS[i]
    return None


def _slim_cases_with_era_tag(slim_cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Shallow copy each row and set _era Roman or None (not persisted)."""
    out: List[Dict[str, Any]] = []
    for c in slim_cases:
        cc = dict(c)
        cc["_era"] = _era_roman_for_slim_case(cc)
        out.append(cc)
    return out


def _aggregate_technology_revolver(
    slim_cases: List[Dict[str, Any]],
    era_filter: Optional[str] = None,
) -> Tuple[int, Dict[str, set], Dict[str, Dict[str, Dict[str, Any]]], List[str]]:
    """
    Scan slim case rows (no full narrative) for labels and per-label case membership.
    If era_filter is set ("I".."IV"), only cases whose _era matches are counted and bucketed.
    total_cases in the return value is always the denominator for this slice:
    all rows when era_filter is None, else rows with that era (including those with no tech labels).
    """
    if era_filter is None:
        slice_rows = slim_cases
        total_cases = len(slim_cases)
    else:
        slice_rows = [c for c in slim_cases if c.get("_era") == era_filter]
        total_cases = len(slice_rows)

    label_buckets: Dict[str, set] = {}
    label_case_map: Dict[str, Dict[str, Dict[str, Any]]] = {}

    for c in slice_rows:
        cid = c.get("id")
        cid_key = str(cid) if cid is not None and str(cid) != "" else f"__row_{id(c)}"
        for bucket in _TECH_REVOLVER_BUCKETS:
            seen_in_bucket: set = set()
            for lab in _labels_for_tech_bucket(c, bucket):
                if not lab or lab in seen_in_bucket:
                    continue
                seen_in_bucket.add(lab)
                if lab not in label_buckets:
                    label_buckets[lab] = set()
                label_buckets[lab].add(bucket)
                if lab not in label_case_map:
                    label_case_map[lab] = {}
                label_case_map[lab][cid_key] = c

    names_sorted = sorted(
        label_case_map.keys(),
        key=lambda lab: (-len(label_case_map[lab]), lab.lower()),
    )
    return total_cases, label_buckets, label_case_map, names_sorted


def _revolver_text_case_ids(
    label_case_map: Dict[str, Dict[str, Dict[str, Any]]],
    names_sorted: List[str],
    per_label: int = _TECH_REVOLVER_TEXT_IDS_PER_LABEL,
    cap: int = _TECH_REVOLVER_TEXT_IDS_CAP,
) -> List[str]:
    """Case ids to load with narrative — capped batch so we never hydrate the full corpus.

    Pass 1 adds up to ``per_label`` distinct ids per label while traversing labels by popularity,
    stopping when ``cap`` ids are queued (existing behavior).

    Pass 2 adds one id for any label that had **no** representative in pass 1. Otherwise rare
    tags (e.g. single-case ``Mega.nz``) never get narrative loaded and excerpts always show empty
    even though counts are correct from slim rows.
    """
    ids: List[str] = []
    seen: set = set()
    for label in names_sorted:
        if len(ids) >= cap:
            break
        n_add = 0
        for cid_key in label_case_map[label].keys():
            if cid_key.startswith("__"):
                continue
            if cid_key in seen:
                continue
            seen.add(cid_key)
            ids.append(cid_key)
            n_add += 1
            if n_add >= per_label:
                break

    for label in names_sorted:
        cmap = label_case_map.get(label) or {}
        label_ids = [k for k in cmap.keys() if not str(k).startswith("__")]
        if not label_ids:
            continue
        if any(k in seen for k in label_ids):
            continue
        cid_key = label_ids[0]
        if cid_key not in seen:
            seen.add(cid_key)
            ids.append(cid_key)

    return ids


def _chambers_technology_revolver(
    label_buckets: Dict[str, set],
    label_case_map: Dict[str, Dict[str, Dict[str, Any]]],
    names_sorted: List[str],
    text_by_id: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    from collections import Counter

    chambers_out: List[Dict[str, Any]] = []
    for label in names_sorted:
        subset = list(label_case_map[label].values())
        n = len(subset)
        pat = _platform_token_regex(label)
        snippets: List[str] = []
        snippet_case_ids: List[str] = []
        seen_norm: set = set()
        text_cap = 20000
        for cid_key in label_case_map[label].keys():
            if cid_key.startswith("__"):
                continue
            full = text_by_id.get(cid_key)
            if not full:
                continue
            raw_txt = full.get("case_text") or ""
            if not raw_txt and isinstance(full.get("raw_data"), dict):
                raw_txt = str((full.get("raw_data") or {}).get("case_text") or "")
            snippet = _snippet_for_platform(raw_txt[:text_cap], pat)
            if not snippet:
                continue
            key = snippet.lower()
            if key in seen_norm:
                continue
            seen_norm.add(key)
            snippets.append(snippet)
            snippet_case_ids.append(cid_key)
            if len(snippets) >= 5:
                break

        topics = Counter()
        severities = Counter()
        for c in subset:
            for t in _parse_jsonish_list(c.get("case_topics")):
                topics[t] += 1
            for s in _parse_jsonish_list(c.get("severity_indicators")):
                severities[s] += 1
        cohort_tags = {
            "case_topics": [
                {"tag": t, "count": ct, "pct_of_platform_cases": round(100 * ct / n, 1)}
                for t, ct in topics.most_common(5)
                if t
            ],
            "severity_indicators": [
                {"tag": s, "count": ct, "pct_of_platform_cases": round(100 * ct / n, 1)}
                for s, ct in severities.most_common(5)
                if s
            ],
        }

        chambers_out.append(
            {
                "label": label,
                "buckets": sorted(label_buckets.get(label, set())),
                "case_count": n,
                "snippets": snippets,
                "snippet_case_ids": snippet_case_ids,
                "cohort_tags": cohort_tags,
            }
        )

    return chambers_out


def _technology_revolver_payload_dict(
    total_cases: int,
    chambers_out: List[Dict[str, Any]],
    eras_block: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "total_cases": total_cases,
        "chambers": chambers_out,
        "bucket_keys": list(_TECH_REVOLVER_BUCKETS),
        "extraction_code_hook": (
            "src/Processing Layer/Pattern Processing Layer/processing.py — "
            "extract_platforms() (column platforms_used) and extract_technology_signals() "
            "(investigation_technology, anonymization_network, p2p_clients in extracted_features)."
        ),
        "coverage_note": (
            "Counts are per extracted label after re-ingest; regex gaps in either extractor still undercount."
        ),
        "snippet_ver": _TECHNOLOGY_REVOLVER_SNIPPET_VER,
    }
    if eras_block is not None:
        out["eras"] = eras_block
    return out


def _compute_technology_revolver_payload() -> Dict[str, Any]:
    """Slim scan + batched narrative load; suitable for cold cache without reading every case_text."""
    slim_cases = storage.get_all_cases(include_raw_data=False) or []
    slim_annotated = _slim_cases_with_era_tag(slim_cases)
    total_cases, label_buckets, label_case_map, names_sorted = _aggregate_technology_revolver(
        slim_annotated, era_filter=None
    )
    ids = _revolver_text_case_ids(label_case_map, names_sorted)
    loaded = storage.get_cases_by_ids(ids, include_raw_data=True) if ids else []
    text_by_id = {str(c["id"]): c for c in loaded}
    chambers = _chambers_technology_revolver(label_buckets, label_case_map, names_sorted, text_by_id)

    eras_block: Dict[str, Any] = {}
    for i, roman in enumerate(_TECH_REVOLVER_ERA_ROMANS):
        lo, hi, _facet_label = ERA_PERIOD_BUCKETS[i]
        etot, ebuckets, elcm, enames = _aggregate_technology_revolver(slim_annotated, era_filter=roman)
        echambers = _chambers_technology_revolver(ebuckets, elcm, enames, text_by_id)
        eras_block[roman] = {
            "roman": roman,
            "years": f"{lo}–{hi}",
            "facet_label": _facet_label,
            "total_cases": etot,
            "distinct_tags": len(echambers),
            "chambers": echambers,
        }

    return _technology_revolver_payload_dict(total_cases, chambers, eras_block=eras_block)


@app.get("/api/technology-revolver")
@limiter.limit("30/minute")
def get_technology_revolver(request: Request):
    """
    Technology revolver: distinct labels across platforms_used and technology-signal buckets,
    per-label case counts, text excerpts, and co-occurring case_topics / severity_indicators.

    Payload includes top-level ``total_cases`` / ``chambers`` for the full corpus and an ``eras``
    object keyed by Roman numerals ``I``..``IV`` (years aligned with ``facet_tree.ERA_PERIOD_BUCKETS``
    / Case Studies). Each era entry has ``total_cases``, ``distinct_tags``, ``chambers``, ``years``,
    and ``facet_label`` for filtering the UI without a second request.
    """
    global _technology_revolver_cache, _technology_revolver_cache_case_count, _technology_revolver_cache_snippet_ver
    try:
        current_case_count = get_case_count()

        if (
            _technology_revolver_cache is not None
            and _technology_revolver_cache_case_count == current_case_count
            and _technology_revolver_cache_snippet_ver == _TECHNOLOGY_REVOLVER_SNIPPET_VER
        ):
            out = dict(_technology_revolver_cache)
            out["cached"] = True
            return out

        cache_key = get_cache_key(
            "technology-revolver", version=current_case_count, snippet_v=_TECHNOLOGY_REVOLVER_SNIPPET_VER
        )
        cached = get_cached(cache_key)
        if cached is not None:
            _technology_revolver_cache = cached
            _technology_revolver_cache_case_count = current_case_count
            _technology_revolver_cache_snippet_ver = _TECHNOLOGY_REVOLVER_SNIPPET_VER
            out = dict(cached)
            out["cached"] = True
            return out

        slim_row = storage.get_technology_revolver_slim(current_case_count)
        if (
            slim_row is not None
            and int(slim_row.get("total_cases", -1)) == int(current_case_count)
            and slim_row.get("snippet_ver") == _TECHNOLOGY_REVOLVER_SNIPPET_VER
        ):
            payload = dict(slim_row)
            payload["cached"] = True
            payload["source"] = "database"
            set_cached(cache_key, payload, ttl=3600)
            _technology_revolver_cache = payload
            _technology_revolver_cache_case_count = current_case_count
            _technology_revolver_cache_snippet_ver = _TECHNOLOGY_REVOLVER_SNIPPET_VER
            return payload

        payload = _compute_technology_revolver_payload()
        payload["cached"] = False
        storage.store_technology_revolver_slim(payload, current_case_count)
        set_cached(cache_key, payload, ttl=3600)
        _technology_revolver_cache = payload
        _technology_revolver_cache_case_count = current_case_count
        _technology_revolver_cache_snippet_ver = _TECHNOLOGY_REVOLVER_SNIPPET_VER
        return payload
    except Exception as e:
        logger.exception("technology-revolver failed: %s", e)
        return {
            "error": str(e),
            "total_cases": 0,
            "chambers": [],
            "bucket_keys": list(_TECH_REVOLVER_BUCKETS),
            "extraction_code_hook": (
                "src/Processing Layer/Pattern Processing Layer/processing.py — "
                "extract_platforms() / extract_technology_signals()"
            ),
            "coverage_note": None,
            "cached": False,
        }


@app.get("/api/cluster-groups")
@limiter.limit("60/minute")
async def cluster_groups_endpoint(request: Request):
    """
    Lightweight endpoint for cluster / case-group visualizations.
    Returns slimmed case_groups (IDs only) - full case data fetched on click.
    Load order: memory → Redis → DB slim. Cold miss schedules background compute
    and returns 202 — never computes inline.
    """
    global _cluster_groups_cache, _cluster_groups_cache_case_count
    try:
        current_case_count = get_case_count()

        # 1. In-memory cache (fastest - no network/DB)
        if (_cluster_groups_cache is not None and
                _cluster_groups_cache_case_count == current_case_count):
            _cluster_groups_cache['_cache_source'] = 'memory'
            return _cluster_groups_cache

        cache_key = get_cache_key('cluster-groups', version=current_case_count)

        # 2. Redis cache
        cached_result = get_cached(cache_key)
        if cached_result is not None:
            cached_result['_cache_source'] = 'redis'
            _cluster_groups_cache = cached_result
            _cluster_groups_cache_case_count = current_case_count
            return cached_result

        # 3. Slim table (small fetch, ~10KB vs ~1MB full blob)
        slim_groups = await asyncio.to_thread(storage.get_cluster_groups_slim, current_case_count)
        if slim_groups and len(slim_groups) > 0:
            result = {
                "success": True,
                "case_groups": slim_groups,
                "cached": True,
                "source": "database"
            }
            set_cached(cache_key, result, ttl=86400)
            _cluster_groups_cache = result
            _cluster_groups_cache_case_count = current_case_count
            return result

        # 4. Cold: schedule single-flight background compute; never block the request
        _schedule_automated_analysis_warmup(current_case_count, reason="cluster-groups")
        return JSONResponse(
            status_code=202,
            content={"status": "warming", "success": False, "case_groups": []},
        )
    except Exception as e:
        import traceback
        return {"success": False, "error": str(e), "traceback": traceback.format_exc()}


@app.get("/api/automated-analysis")
@limiter.limit("30/minute")
async def automated_analysis_endpoint(request: Request):
    """
    Full automated analysis (case groups, triaged cases, insights).
    Load order: memory → Redis → Postgres slim. Cold miss returns 202 and
    schedules a single background compute (never on the request path).
    """
    global _automated_analysis_mem_cache, _automated_analysis_mem_case_count
    try:
        current_case_count = get_case_count()

        if (
            _automated_analysis_mem_cache is not None
            and _automated_analysis_mem_case_count == current_case_count
        ):
            analysis = _automated_analysis_mem_cache.get("analysis")
            return _build_automated_analysis_response(
                analysis if isinstance(analysis, dict) else {},
                source="memory",
                cached=True,
            )

        cache_key = get_cache_key('automated-analysis', version=current_case_count)

        cached_result = get_cached(cache_key)
        if cached_result is not None:
            analysis = cached_result.get("analysis")
            if isinstance(analysis, dict):
                out = _build_automated_analysis_response(analysis, source="redis", cached=True)
                _automated_analysis_mem_cache = {
                    "success": True,
                    "analysis": analysis,
                    "cached": True,
                    "source": "redis",
                }
                _automated_analysis_mem_case_count = current_case_count
                return out

        # Postgres slim is source of truth when Redis is cold
        aa_from_db = await asyncio.to_thread(
            storage.get_automated_analysis_slim, current_case_count
        )
        if aa_from_db:
            result = {
                "success": True,
                "analysis": aa_from_db,
                "cached": True,
                "source": "database",
            }
            set_cached(cache_key, result, ttl=86400)
            _automated_analysis_mem_cache = result
            _automated_analysis_mem_case_count = current_case_count
            return _build_automated_analysis_response(aa_from_db, source="database", cached=True)

        # Cold: schedule single-flight background compute; never compute inline
        _schedule_automated_analysis_warmup(current_case_count, reason="automated-analysis")
        return JSONResponse(
            status_code=202,
            content={"status": "warming", "success": False},
        )
    except Exception as e:
        import traceback
        return {"success": False, "error": str(e), "traceback": traceback.format_exc()}


@app.get("/api")
def api_root():
    """API root endpoint"""
    return {"message": "CaseLinker API", "version": "1.0"}


@app.get("/healthz")
async def healthz():
    """Liveness probe: no DB, Redis, or compute dependencies."""
    return Response(content="ok", media_type="text/plain", status_code=200)


@app.get("/robots.txt")
async def robots_txt():
    """Keep crawlers off expensive API/ontology routes."""
    body = "User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /ontology/\nDisallow: /sparql\n"
    return PlainTextResponse(content=body)


@app.get("/favicon.ico")
async def favicon():
    """Minimal favicon so crawlers/browsers stop probing other routes."""
    # 16x16 indigo pixel PNG
    import base64
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    return Response(content=png, media_type="image/png")


@app.get("/visualization", response_class=HTMLResponse)
async def serve_visualization():
    """Serve the HTML visualization page"""
    html_path = Path(__file__).parent.parent / "visualization" / "visualization.html"
    if html_path.exists():
        return HTMLResponse(content=read_utf8_text_file(html_path))
    else:
        return HTMLResponse(content="<h1>Visualization not found</h1>", status_code=404)

@app.get("/analysis", response_class=HTMLResponse)
async def serve_analysis():
    """Serve the HTML analysis page"""
    html_path = Path(__file__).parent.parent / "visualization" / "analysis.html"
    if html_path.exists():
        return HTMLResponse(content=read_utf8_text_file(html_path))
    else:
        return HTMLResponse(content="<h1>Analysis page not found</h1>", status_code=404)

@app.get("/clusters", response_class=HTMLResponse)
async def serve_clusters():
    """Serve the HTML clusters page"""
    html_path = Path(__file__).parent.parent / "visualization" / "clusters.html"
    if html_path.exists():
        return HTMLResponse(content=read_utf8_text_file(html_path))
    else:
        return HTMLResponse(content="<h1>Clusters page not found</h1>", status_code=404)

@app.get("/api/location-stats")
@limiter.limit("60/minute")
def get_location_stats(request: Request):
    """
    Get aggregated location statistics (no raw cases).
    Returns location data with counts and case IDs for US map visualization.
    This endpoint is optimized for performance - returns only aggregated data.
    """
    try:
        # Get current case count for cache versioning
        current_case_count = get_case_count()
        
        # Build cache key
        cache_key = get_cache_key('location-stats', version=current_case_count)
        
        # Try Redis cache first
        cached_result = get_cached(cache_key)
        if cached_result is not None:
            return cached_result
        
        # Cache miss - aggregate location data
        cases = storage.get_all_cases(include_raw_data=False)
        
        # Aggregate locations
        location_map = {}
        for case in cases:
            locations = case.get('locations', [])
            if isinstance(locations, str):
                import json
                try:
                    locations = json.loads(locations)
                except:
                    locations = []
            
            if not isinstance(locations, list):
                locations = []
            
            case_id = case.get('id', 'unknown')
            
            for loc in locations:
                if loc and isinstance(loc, str) and loc.strip():
                    loc_clean = loc.strip()
                    if loc_clean not in location_map:
                        location_map[loc_clean] = {
                            'location': loc_clean,
                            'count': 0,
                            'caseIds': []
                        }
                    location_map[loc_clean]['count'] += 1
                    location_map[loc_clean]['caseIds'].append(case_id)
        
        # Convert to list
        location_data = list(location_map.values())
        
        # Store in cache (1 hour TTL)
        set_cached(cache_key, location_data, ttl=3600)
        
        return location_data
    except Exception as e:
        # Fallback to empty list on error
        return []


@app.get("/stats", response_class=HTMLResponse)
async def serve_stats():
    """Serve the HTML stats page"""
    html_path = Path(__file__).parent.parent / "visualization" / "stats.html"
    if html_path.exists():
        return HTMLResponse(content=read_utf8_text_file(html_path))
    else:
        return HTMLResponse(content="<h1>Stats page not found</h1>", status_code=404)

@app.get("/search", response_class=HTMLResponse)
async def serve_search():
    """Serve the HTML search page"""
    html_path = Path(__file__).parent.parent / "visualization" / "search.html"
    if html_path.exists():
        return HTMLResponse(content=read_utf8_text_file(html_path))
    else:
        return HTMLResponse(content="<h1>Search page not found</h1>", status_code=404)


@app.get("/query", response_class=HTMLResponse)
async def serve_query():
    """Custom analysis: browser-side JS snippets calling public APIs only."""
    html_path = Path(__file__).parent.parent / "visualization" / "query.html"
    if html_path.exists():
        return HTMLResponse(content=read_utf8_text_file(html_path))
    return HTMLResponse(content="<h1>Query page not found</h1>", status_code=404)


@app.get("/llm", response_class=HTMLResponse)
async def serve_llm():
    """LLM assistant UI (Groq or Gemini + read-only DB via ``nl_llm`` / ``POST /api/llm/chat``)."""
    html_path = Path(__file__).parent.parent / "visualization" / "LLM.html"
    if html_path.exists():
        return HTMLResponse(content=read_utf8_text_file(html_path))
    return HTMLResponse(content="<h1>LLM page not found</h1>", status_code=404)


@app.post("/api/llm/chat")
@limiter.limit("15/minute")
def api_llm_chat(request: Request, body: LlmChatBody):
    """
    Public natural-language assistant (Groq by default, or Gemini when the model field starts with ``gemini``); may run validated SELECT on ``cases`` only.
    Requires ``GROQ_API_KEY`` for the default (Groq) path. If the model field starts with ``gemini``, only a Gemini API key is required (Groq key optional).
    Disable with ``CASLINKER_DISABLE_LLM_CHAT=1``.
    """
    off = os.getenv("CASLINKER_DISABLE_LLM_CHAT", "").strip().lower()
    if off in ("1", "true", "yes", "on"):
        raise HTTPException(status_code=403, detail="LLM chat is disabled by the operator.")
    mo = (body.model or "").strip()
    use_gemini_route = mo.lower().startswith("gemini")
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not use_gemini_route and not key:
        raise HTTPException(
            status_code=503,
            detail="LLM chat is not configured (set GROQ_API_KEY on the server).",
        )
    _enforce_llm_daily_limit(request)
    try:
        return nl_llm(
            body.question.strip(),
            provider=body.provider,
            model_override=body.model,
            api_key=key or "unset",
        )
    except requests.HTTPError as e:
        detail = str(e)
        if e.response is not None and e.response.text:
            detail = e.response.text[:800]
        raise HTTPException(status_code=502, detail=f"LLM upstream error: {detail}") from e
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Upstream request failed: {e}") from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


def _lifecycle_payload_html_snippet() -> str:
    """Embed L* payload in /lifecycle HTML so the public page needs no API key."""
    try:
        from state_machines.lifecycle_api import build_lifecycle_payload

        raw = json.dumps(build_lifecycle_payload(), ensure_ascii=False)
        safe = raw.replace("</", "<\\/")
        return (
            f'  <script id="lifecycle-payload" type="application/json">{safe}</script>\n'
        )
    except Exception as exc:
        logging.getLogger(__name__).error("lifecycle payload embed failed: %s", exc, exc_info=True)
        return ""


@app.get("/lifecycle", response_class=HTMLResponse)
async def serve_lifecycle():
    """Lifecycle analysis page (public; data embedded server-side)."""
    viz_dir = Path(__file__).parent.parent / "visualization"
    html_path = viz_dir / "lifecycle.html"
    if not html_path.exists():
        return HTMLResponse(content="<h1>Lifecycle page not found</h1>", status_code=404)
    html = read_utf8_text_file(html_path)
    js_path = viz_dir / "assets" / "lifecycle.js"
    css_path = viz_dir / "assets" / "lifecycle.css"
    if js_path.is_file():
        v = int(js_path.stat().st_mtime)
        html = html.replace(
            "/viz-assets/lifecycle.js",
            f"/viz-assets/lifecycle.js?v={v}",
            1,
        )
    if css_path.is_file():
        v = int(css_path.stat().st_mtime)
        html = html.replace(
            "/viz-assets/lifecycle.css",
            f"/viz-assets/lifecycle.css?v={v}",
            1,
        )
    snippet = _lifecycle_payload_html_snippet()
    if snippet and "</body>" in html:
        html = html.replace("</body>", snippet + "</body>", 1)
    return HTMLResponse(content=html)


@app.get("/api/lifecycle/cases")
@limiter.limit("100/minute")
def get_lifecycle_cases(request: Request):
    """
    L* visualization payload for all 5 PACER state-machine cases.
    Trusted key or localhost only (same gate as GET /api/cases).
    Public /lifecycle page embeds this payload server-side.
    """
    if not _has_bulk_corpus_access(request):
        raise HTTPException(status_code=403, detail=_LIFECYCLE_API_FORBIDDEN_DETAIL)
    from state_machines.lifecycle_api import build_lifecycle_payload

    try:
        return build_lifecycle_payload()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lifecycle data unavailable: {e}") from e


@app.get("/api/lifecycle/lstar")
@limiter.limit("60/minute")
def get_lifecycle_lstar(request: Request):
    """
    Full L* computation output (state_machines/data/lstar_all_cases.json).
    Trusted key or localhost only.
    """
    if not _has_bulk_corpus_access(request):
        raise HTTPException(status_code=403, detail=_LIFECYCLE_API_FORBIDDEN_DETAIL)
    from state_machines.lifecycle_api import load_lstar_raw

    try:
        return load_lstar_raw()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lifecycle L* output unavailable: {e}") from e


@app.get("/api/lifecycle/canonical")
@limiter.limit("60/minute")
def get_lifecycle_canonical(request: Request):
    """
    Public: the 5 canonical PACER state-machine cases (enticement, production,
    sextortion, enterprise, trafficking) with phases, transitions, and
    affordance annotations. Same data the public /lifecycle page embeds
    server-side, minus the expansion-case records. No CaseLinker-Key required;
    intended for external embeds (e.g. partner research sites).
    """
    from state_machines.lifecycle_api import build_lifecycle_payload

    try:
        payload = build_lifecycle_payload()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lifecycle data unavailable: {e}") from e

    payload.pop("expansion_cases", None)
    payload["cases"] = payload.get("canonical_cases", [])
    return payload


@app.get("/triage", response_class=HTMLResponse)
async def serve_triage():
    """Serve the triage ML evaluation page"""
    html_path = Path(__file__).parent.parent / "visualization" / "triage.html"
    if html_path.exists():
        return HTMLResponse(content=read_utf8_text_file(html_path))
    return HTMLResponse(content="<h1>Triage page not found</h1>", status_code=404)


@app.get("/api/triage-eval")
def api_triage_eval(
    model: str = Query("rf", description="rf or tree"),
    criterion: str = Query("entropy", description="gini, entropy, or log_loss"),
    no_agencies: bool = Query(False),
    seed: int = Query(42),
    test_size: float = Query(0.2, ge=0.05, le=0.45),
):
    """
    Run the same 80/20-style eval as scripts/verify/test_triage.py on the live DB,
    using train_triage_model.train_pipeline and rule-based triage labels.
    """
    try:
        import math

        import numpy as np
        from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
        from sklearn.model_selection import train_test_split
        from train_triage_model import (
            cases_to_dataframe,
            make_labels,
            priority_scores_by_id,
            train_pipeline,
        )
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"Triage eval unavailable: {e}") from e

    if model not in ("rf", "tree"):
        raise HTTPException(status_code=400, detail="model must be rf or tree")
    if criterion not in ("gini", "entropy", "log_loss"):
        raise HTTPException(status_code=400, detail="criterion must be gini, entropy, or log_loss")

    current_count = get_case_count()
    eval_ph = None
    if REDIS_AVAILABLE:
        eval_ph = _redis_cache_payload_hash(
            {
                "model": model,
                "criterion": criterion,
                "no_agencies": bool(no_agencies),
                "seed": int(seed),
                "test_size": float(test_size),
            }
        )
        eval_rk = get_cache_key("triage-eval", h=eval_ph, version=current_count)
        cached_eval = get_cached(eval_rk)
        if cached_eval is not None:
            return cached_eval

    cases = storage.get_all_cases(include_raw_data=False)
    min_cases = max(20, int(math.ceil(1.0 / test_size)) + 5)
    if len(cases) < min_cases:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least {min_cases} cases for stratified split; found {len(cases)}",
        )

    use_agencies = not no_agencies
    id_to_score = priority_scores_by_id(cases)
    scores = np.array([id_to_score[c["id"]] for c in cases])
    y, class_names, bin_edges = make_labels(scores, n_bins=3)
    df = cases_to_dataframe(cases, include_agencies=use_agencies)
    X = df.drop(columns=["id"])

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=seed, stratify=y
    )

    pipe = train_pipeline(
        X_train,
        y_train,
        model,
        seed,
        use_agencies=use_agencies,
        criterion=criterion,
    )
    y_pred = pipe.predict(X_test)

    acc = float(accuracy_score(y_test, y_pred))
    cm = confusion_matrix(y_test, y_pred, labels=list(range(len(class_names))))
    report_dict = classification_report(
        y_test, y_pred, target_names=class_names, zero_division=0, output_dict=True
    )

    case_ids_by_tier: Dict[str, List[str]] = {name: [] for name in class_names}
    for i, c in enumerate(cases):
        tier = class_names[int(y[i])]
        cid = c.get("id")
        if cid is not None:
            case_ids_by_tier[tier].append(str(cid))
    for tier in case_ids_by_tier:
        case_ids_by_tier[tier] = sorted(case_ids_by_tier[tier])

    out: Dict[str, Any] = {
        "n_cases": len(cases),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "accuracy": acc,
        "classification_report": report_dict,
        "confusion_matrix": cm.tolist(),
        "class_names": class_names,
        "bin_edges": bin_edges,
        "case_ids_by_tier": case_ids_by_tier,
        "model": model,
        "criterion": criterion,
        "use_agencies": use_agencies,
        "seed": seed,
        "test_size": test_size,
    }

    if REDIS_AVAILABLE and eval_ph is not None:
        set_cached(
            get_cache_key("triage-eval", h=eval_ph, version=current_count),
            out,
            ttl=86400,
        )
    return out


@app.get("/api/triage-model-corpus")
@limiter.limit("60/minute")
def api_triage_model_corpus(
    request: Request,
    facet_constraints: Optional[str] = Query(
        None,
        description='JSON object: { field_key: [allowed values, ...], ... }; any tag may match.',
    ),
):
    """
    Model-predicted tiers from the saved bundle over the live database (and optional
    facet filter). Does not read triage_corpus_predictions.json.
    """
    constraints = _parse_facet_constraints_param(facet_constraints)
    current_count = get_case_count()
    rk = None
    if REDIS_AVAILABLE:
        ph = _redis_cache_payload_hash({"facet_constraints": facet_constraints or ""})
        rk = get_cache_key("triage-corpus", h=ph, version=current_count)
        cached = get_cached(rk)
        if cached is not None and cached.get("corpus_predictions_available"):
            return cached
    out = _triage_saved_bundle_corpus_live(constraints)
    if REDIS_AVAILABLE and rk and out.get("corpus_predictions_available"):
        set_cached(rk, out, ttl=3600)
    return out


class LiveTriageRequest(BaseModel):
    raw: str = Field("", description="Pasted batch text (Case 1 : … Case 2 : …)")


@app.post("/api/triage-live")
def api_triage_live(body: LiveTriageRequest):
    """
    Process pasted narratives through the normal extraction pipeline (in memory only),
    classify tiers with the saved triage bundle. Does not persist case text or features.
    """
    if not (body.raw or "").strip():
        raise HTTPException(status_code=400, detail="raw text is required")

    try:
        from triage import run_live_triage
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"Live triage unavailable: {e}") from e

    try:
        out = run_live_triage(body.raw)
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        logger.exception("live triage failed")
        raise HTTPException(status_code=500, detail=str(e)) from e

    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("message", "empty_input"))

    return {
        "class_names": out["class_names"],
        "case_ids_by_tier": out["case_ids_by_tier"],
        "predictions": out["predictions"],
        "n_cases": out["n_cases"],
        "bundle_path": out.get("bundle_path"),
        "use_agencies": out.get("use_agencies"),
    }


@app.get("/case-studies", response_class=HTMLResponse)
async def serve_case_studies():
    """Serve the HTML case studies page (gate + reading experience)."""
    html_path = Path(__file__).parent.parent / "visualization" / "case-studies.html"
    if html_path.exists():
        return HTMLResponse(content=read_utf8_text_file(html_path))
    else:
        return HTMLResponse(content="<h1>Case Studies page not found</h1>", status_code=404)


# ---- Case Studies content + community notes ----------------------------------
# Content lives in data/case_studies.json (eras + studies). Community notes live
# in data/case_study_notes.json. Notes are best-effort persistence: on Railway's
# default ephemeral filesystem they reset on redeploy. Mount a volume at /data
# (or swap to the DB) for durable storage.

_Q1_EVIDENCE_PATH = Path(__file__).parent.parent / "ontology" / "q1" / "q1_evidence.json"
_Q1_VALID_TIERS = frozenset({"stated", "inferred", "named_only"})

_CASE_STUDIES_CONTENT_PATH = Path(__file__).parent.parent / "data" / "case_studies.json"
_CASE_STUDIES_NOTES_PATH = Path(__file__).parent.parent / "data" / "case_study_notes.json"
_CASE_STUDIES_NOTES_MAX_NAME = 80
_CASE_STUDIES_NOTES_MAX_TEXT = 1500


def _load_q1_evidence() -> Dict[str, Any]:
    if not _Q1_EVIDENCE_PATH.exists():
        raise HTTPException(status_code=404, detail="Q1 evidence data not available")
    try:
        data = json.loads(read_utf8_text_file(_Q1_EVIDENCE_PATH))
    except (json.JSONDecodeError, OSError) as e:
        logger.exception("q1 evidence load failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to load Q1 evidence")
    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        raise HTTPException(status_code=500, detail="Invalid Q1 evidence format")
    return data


def _q1_resolve_platform_name(records: List[Dict[str, Any]], platform: str) -> Optional[str]:
    """Case-insensitive match to canonical platform label in evidence records."""
    needle = platform.strip().casefold()
    if not needle:
        return None
    for rec in records:
        label = rec.get("platform")
        if isinstance(label, str) and label.casefold() == needle:
            return label
    return None


def _q1_platform_evidence_index(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_platform: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        plat = rec.get("platform")
        tier = rec.get("stated_vs_inferred")
        if not isinstance(plat, str) or not plat:
            continue
        if tier not in _Q1_VALID_TIERS:
            continue
        row = by_platform.get(plat)
        if row is None:
            row = {
                "platform": plat,
                "platform_type": rec.get("platform_type") or "",
                "case_count": 0,
                "tier_counts": {"stated": 0, "inferred": 0, "named_only": 0},
            }
            by_platform[plat] = row
        row["case_count"] += 1
        row["tier_counts"][tier] += 1

    platforms = sorted(by_platform.values(), key=lambda r: (-r["case_count"], r["platform"].casefold()))
    return {"platforms": platforms, "count": len(platforms)}


def _q1_platform_evidence_cases(
    records: List[Dict[str, Any]],
    platform: str,
    tier: Optional[str] = None,
) -> Dict[str, Any]:
    canonical = _q1_resolve_platform_name(records, platform)
    if not canonical:
        raise HTTPException(status_code=404, detail=f"Unknown platform: {platform}")

    cases: List[Dict[str, Any]] = []
    for rec in records:
        if rec.get("platform") != canonical:
            continue
        rec_tier = rec.get("stated_vs_inferred")
        if rec_tier not in _Q1_VALID_TIERS:
            continue
        if tier and rec_tier != tier:
            continue
        cases.append(
            {
                "case_id": rec.get("case_id"),
                "tier": rec_tier,
                "evidence_quote": (rec.get("evidence_quote") or "").strip(),
            }
        )

    cases.sort(key=lambda c: (c.get("case_id") or ""))
    return {
        "platform": canonical,
        "platform_type": next(
            (r.get("platform_type") or "" for r in records if r.get("platform") == canonical),
            "",
        ),
        "case_count": len(cases),
        "cases": cases,
    }


def _load_case_studies_content() -> Dict[str, Any]:
    if not _CASE_STUDIES_CONTENT_PATH.exists():
        return {"version": 0, "eras": [], "case_studies": [], "default_google_form_url": ""}
    return json.loads(read_utf8_text_file(_CASE_STUDIES_CONTENT_PATH))


def _load_case_study_notes() -> List[Dict[str, Any]]:
    if not _CASE_STUDIES_NOTES_PATH.exists():
        return []
    try:
        data = json.loads(read_utf8_text_file(_CASE_STUDIES_NOTES_PATH))
        notes = data.get("notes", []) if isinstance(data, dict) else []
        return notes if isinstance(notes, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_case_study_notes(notes: List[Dict[str, Any]]) -> None:
    _CASE_STUDIES_NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_note": "Community notes for case studies. Reset on Railway redeploy unless a persistent volume is mounted at /data.",
        "notes": notes,
    }
    with open(_CASE_STUDIES_NOTES_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


@app.get("/api/q1/platform-evidence")
@limiter.limit("60/minute")
def api_q1_platform_evidence(
    request: Request,
    platform: Optional[str] = Query(default=None),
    tier: Optional[str] = Query(default=None),
):
    """Q1 platform harm evidence: platform index or per-platform case cohort with tiers and quotes."""
    if tier is not None:
        tier_norm = tier.strip().lower()
        if tier_norm not in _Q1_VALID_TIERS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid tier; expected one of: {', '.join(sorted(_Q1_VALID_TIERS))}",
            )
        tier = tier_norm

    data = _load_q1_evidence()
    records = data.get("records") or []
    meta = data.get("_meta") or {}

    if platform is None or not platform.strip():
        payload = _q1_platform_evidence_index(records)
        payload["_meta"] = meta
        return payload

    payload = _q1_platform_evidence_cases(records, platform, tier)
    payload["_meta"] = meta
    if tier:
        payload["tier"] = tier
    return payload


@app.get("/api/case-studies")
@limiter.limit("60/minute")
def api_case_studies_content(request: Request):
    """Return the case-studies content document (eras + studies)."""
    try:
        return _load_case_studies_content()
    except Exception as e:
        logger.exception("case-studies content load failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to load case studies content")


@app.get("/api/case-studies/notes/{case_id}")
@limiter.limit("120/minute")
def api_case_studies_notes_get(request: Request, case_id: str):
    """Return community notes for a single case study, oldest first."""
    notes = _load_case_study_notes()
    filtered = [n for n in notes if isinstance(n, dict) and n.get("case_id") == case_id]
    filtered.sort(key=lambda n: n.get("ts", ""))
    return {"case_id": case_id, "notes": filtered, "count": len(filtered)}


class CaseStudyNoteRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    text: str = Field(..., min_length=1, max_length=4000)


@app.post("/api/case-studies/notes/{case_id}")
@limiter.limit("6/minute")
def api_case_studies_notes_post(request: Request, case_id: str, body: CaseStudyNoteRequest):
    """Append a community note for a case study. Light validation; no auth."""
    content = _load_case_studies_content()
    valid_ids = {c.get("id") for c in content.get("case_studies", []) if isinstance(c, dict)}
    if case_id not in valid_ids:
        raise HTTPException(status_code=404, detail="Unknown case_id")

    name = (body.name or "").strip()[:_CASE_STUDIES_NOTES_MAX_NAME] or "Anonymous"
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Note text required")
    text = text[:_CASE_STUDIES_NOTES_MAX_TEXT]

    import uuid
    note = {
        "id": uuid.uuid4().hex,
        "case_id": case_id,
        "name": name,
        "text": text,
        "ts": datetime.utcnow().isoformat() + "Z",
    }
    notes = _load_case_study_notes()
    notes.append(note)
    try:
        _save_case_study_notes(notes)
    except OSError as e:
        logger.warning("case-studies notes persist failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to save note")
    return note


@app.get("/tech-landscape", response_class=HTMLResponse)
async def serve_tech_landscape():
    """Serve the Technology page (/tech-landscape); data from GET /api/technology-revolver."""
    html_path = Path(__file__).parent.parent / "visualization" / "tech-landscape.html"
    if html_path.exists():
        return HTMLResponse(content=read_utf8_text_file(html_path))
    return HTMLResponse(content="<h1>Tech Landscape</h1><p>Page not found</p>", status_code=404)


@app.get("/sources", response_class=HTMLResponse)
async def serve_sources():
    """Serve the HTML sources page"""
    html_path = Path(__file__).parent.parent / "visualization" / "sources.html"
    if html_path.exists():
        return HTMLResponse(content=read_utf8_text_file(html_path))
    else:
        return HTMLResponse(content="<h1>Sources page not found</h1>", status_code=404)

@app.get("/audit", response_class=HTMLResponse)
async def serve_audit():
    """Serve the HTML audit page"""
    html_path = Path(__file__).parent.parent / "visualization" / "audit.html"
    if html_path.exists():
        return HTMLResponse(content=read_utf8_text_file(html_path))
    else:
        return HTMLResponse(content="<h1>Audit page not found</h1>", status_code=404)


@app.get("/under-the-hood", response_class=HTMLResponse)
async def serve_under_the_hood():
    """Serve the HTML under-the-hood architecture page"""
    html_path = Path(__file__).parent.parent / "visualization" / "under-the-hood.html"
    if html_path.exists():
        return HTMLResponse(content=read_utf8_text_file(html_path))
    else:
        return HTMLResponse(content="<h1>Under the Hood</h1><p>Page not found</p>", status_code=404)

@app.get("/patterns", response_class=HTMLResponse)
async def serve_patterns():
    """Serve the Patterns research documentation page"""
    html_path = Path(__file__).parent.parent / "visualization" / "patterns.html"
    if html_path.exists():
        return HTMLResponse(content=read_utf8_text_file(html_path))
    else:
        return HTMLResponse(content="<h1>Patterns page not found</h1>", status_code=404)


@app.get("/patterns/graph", response_class=HTMLResponse)
async def serve_patterns_graph():
    """Serve the CAC Ontology knowledge graph explorer (Phase 2)"""
    html_path = Path(__file__).parent.parent / "visualization" / "patterns-graph.html"
    if html_path.exists():
        return HTMLResponse(content=read_utf8_text_file(html_path))
    else:
        return HTMLResponse(content="<h1>Knowledge graph page not found</h1>", status_code=404)


@app.get("/patterns/questions/{question_id}", response_class=HTMLResponse)
async def serve_patterns_question(question_id: str):
    """
    Serve an interactive question findings page (Q1–Q3).

    Expected IDs:
      - q01 .. q03
      - q1  .. q3 (normalized to zero-padded)
    """
    q = (question_id or "").strip().lower()
    # Normalize q1 → q01 (and q001 → q01 if someone pastes it)
    if re.fullmatch(r"q\d{1,3}", q or ""):
        n = int(q[1:])
        q = f"q{n:02d}"

    if not re.fullmatch(r"q0[1-3]", q):
        return HTMLResponse(content="<h1>Question page not found</h1>", status_code=404)

    html_path = Path(__file__).parent.parent / "visualization" / "questions" / f"{q}.html"
    if html_path.exists():
        return HTMLResponse(content=read_utf8_text_file(html_path))
    return HTMLResponse(content="<h1>Question page not found</h1>", status_code=404)


_viz_assets = Path(__file__).resolve().parent.parent / "visualization" / "assets"
if _viz_assets.is_dir():
    app.mount("/viz-assets", StaticFiles(directory=str(_viz_assets)), name="viz_assets")

# Serve ontology/graph_output/ (staging + universe/ + big_bang/ subdirs).
# Patterns viz loads only graph_output/universe/ and graph_output/big_bang/.
_graph_output = Path(__file__).resolve().parent.parent / "ontology" / "graph_output"
_graph_output.mkdir(parents=True, exist_ok=True)
app.mount(
    "/ontology/graph_output",
    StaticFiles(directory=str(_graph_output)),
    name="graph_output",
)

# Serve ontology/question_data/ JSON files for interactive question pages.
_question_data = Path(__file__).resolve().parent.parent / "ontology" / "question_data"
if _question_data.is_dir():
    app.mount(
        "/ontology/question_data",
        StaticFiles(directory=str(_question_data)),
        name="question_data",
    )

# Q01 affordance table: q1_evidence.json, q1_harm_analysis.json (manual harm vectors).
_q1_data = Path(__file__).resolve().parent.parent / "ontology" / "q1"
if _q1_data.is_dir():
    app.mount(
        "/ontology/q1",
        StaticFiles(directory=str(_q1_data)),
        name="q1_data",
    )

# Q02 lifecycle table: q2_evidence.json, q2_lifecycle.json (manual pathway synthesis).
_q2_data = Path(__file__).resolve().parent.parent / "ontology" / "q2"
if _q2_data.is_dir():
    app.mount(
        "/ontology/q2",
        StaticFiles(directory=str(_q2_data)),
        name="q2_data",
    )

# Q03 intervention table: q3_evidence.json, q3_interventions.json (manual leverage synthesis).
_q3_data = Path(__file__).resolve().parent.parent / "ontology" / "q3"
if _q3_data.is_dir():
    app.mount(
        "/ontology/q3",
        StaticFiles(directory=str(_q3_data)),
        name="q3_data",
    )

_ontology_dir = Path(__file__).resolve().parent.parent / "ontology"
_q_results_path = _ontology_dir / "q_results.json"
if _q_results_path.is_file():

    @app.get("/ontology/q_results.json")
    def serve_q_results():
        return FileResponse(str(_q_results_path), media_type="application/json")

def _compare_pool_id_order() -> List[str]:
    """Stratified 200 ids for Patterns demo chips (from select_cases.py output)."""
    p = _ontology_dir / "selected_200_ids.txt"
    if not p.is_file():
        return []
    return [ln.strip() for ln in p.read_text().splitlines() if ln.strip()]


def _graph_pool_subdir(pool: str) -> str:
    """Filesystem subdir under graph_output/ for a Patterns pool."""
    p = (pool or "compare").strip().lower()
    if p == "compare":
        return "universe"
    if p in ("all", "big_bang"):
        return "big_bang"
    if p == "universe":
        return "universe"
    if p == "analysis":
        return "analysis"
    raise ValueError(f"unknown graph pool: {pool}")


def _ontology_graph_case_entries(
    pool: str = "all",
) -> Dict[str, Dict[str, Any]]:
    """case_id -> {case_id, path, ttl_path} for graphs in graph_output/{subdir}/."""
    by_id: Dict[str, Dict[str, Any]] = {}
    subdir = _graph_pool_subdir(pool)
    scan_dir = _graph_output / subdir
    url_prefix = f"/ontology/graph_output/{subdir}"
    if not scan_dir.is_dir():
        return by_id
    for entry in scan_dir.glob("*.jsonld"):
        case_id = entry.stem
        ttl = entry.with_suffix(".ttl")
        by_id[case_id] = {
            "case_id": case_id,
            "path": f"{url_prefix}/{entry.name}",
            "ttl_path": f"{url_prefix}/{ttl.name}" if ttl.exists() else None,
        }
    return by_id


def _universe_graph_count() -> int:
    d = _graph_output / "universe"
    return len(list(d.glob("*.jsonld"))) if d.is_dir() else 0


@app.get("/api/ontology/cases")
def api_ontology_cases(
    pool: str = Query(
        "compare",
        description="compare | all (Big Bang half-sample) | universe | analysis (big_bang.py 1000)",
    ),
):
    """
    Patterns graph case catalog (metadata only — no JSON-LD bodies).

    - pool=compare (default): up to 200 curated cases with graphs in graph_output/universe/
    - pool=all: Big Bang half-sample at graph_output/big_bang/
    - pool=universe: every graph in graph_output/universe/
    - pool=analysis: analysis_ids.txt cases in graph_output/analysis/ (MCP/research cohorts)
    """
    from fastapi.responses import JSONResponse

    pool_norm = (pool or "compare").strip().lower()
    if pool_norm not in ("compare", "all", "universe", "analysis"):
        raise HTTPException(
            status_code=400,
            detail="pool must be 'compare', 'all', 'universe', or 'analysis'",
        )

    if pool_norm == "compare" and pool_norm in _ontology_catalog_mem:
        payload = _ontology_catalog_mem[pool_norm]
        return JSONResponse(
            content=payload,
            headers={"Cache-Control": "public, max-age=3600"},
        )

    if str(_ontology_dir) not in sys.path:
        sys.path.insert(0, str(_ontology_dir))
    from merge_graph_cache import graph_dir_for_pool, graph_manifest  # noqa: E402

    universe_total = _universe_graph_count()

    if pool_norm == "compare":
        manifest = graph_manifest(graph_dir_for_pool("compare"))
        redis_key = get_cache_key("ontology_catalog", pool="compare", manifest=manifest)
        redis_hit = get_cached(redis_key)
        if isinstance(redis_hit, dict) and redis_hit.get("graph_manifest") == manifest:
            _ontology_catalog_mem["compare"] = redis_hit
            return JSONResponse(
                content=redis_hit,
                headers={"Cache-Control": "public, max-age=3600"},
            )
        graphs = _ontology_graph_case_entries("compare")
        compare_ids = _compare_pool_id_order()
        cases = [graphs[cid] for cid in compare_ids if cid in graphs]
        payload = {
            "pool": "compare",
            "cases": cases,
            "corpus_total": universe_total,
            "compare_pool_size": len(cases),
            "graph_manifest": manifest,
        }
        _ontology_catalog_mem["compare"] = payload
        set_cached(
            get_cache_key("ontology_catalog", pool="compare", manifest=manifest),
            payload,
            ttl=86400 * 7,
        )
        return JSONResponse(
            content=payload,
            headers={"Cache-Control": "public, max-age=3600"},
        )

    if pool_norm in ("all", "universe", "analysis"):
        scan_pool = (
            "all" if pool_norm == "all"
            else "analysis" if pool_norm == "analysis"
            else "universe"
        )
        manifest = graph_manifest(graph_dir_for_pool(scan_pool))
        graphs = _ontology_graph_case_entries(scan_pool)
        cases = sorted(graphs.values(), key=lambda r: r["case_id"])
        payload = {
            "pool": pool_norm,
            "cases": cases,
            "corpus_total": universe_total if pool_norm in ("all", "analysis") else len(cases),
            "graph_manifest": manifest,
        }
        if pool_norm == "analysis":
            payload["analysis_pool_size"] = len(cases)
        return JSONResponse(
            content=payload,
            headers={"Cache-Control": "public, max-age=300"},
        )

    raise HTTPException(status_code=400, detail=f"unknown pool: {pool_norm}")


_ontology_catalog_mem: Dict[str, Any] = {}
_ontology_merged_mem: Dict[str, Dict[str, Any]] = {}


@app.get("/api/ontology/merged")
def api_ontology_merged(
    pool: str = Query("compare", description="compare | all | universe | analysis"),
):
    """
    Pre-merged flat RDF nodes for Patterns (Redis + disk + in-process cache).

    After graph_output changes, manifest rotates and cache rebuilds on first request.
    """
    pool_norm = (pool or "compare").strip().lower()
    if pool_norm not in ("compare", "all", "universe", "analysis"):
        raise HTTPException(
            status_code=400,
            detail="pool must be 'compare', 'all', 'universe', or 'analysis'",
        )

    mem_key = pool_norm
    if mem_key in _ontology_merged_mem:
        out = dict(_ontology_merged_mem[mem_key])
        out["cache"] = "memory"
        return out

    ontology_dir = Path(__file__).resolve().parent.parent / "ontology"
    if str(ontology_dir) not in sys.path:
        sys.path.insert(0, str(ontology_dir))
    from merge_graph_cache import get_or_build_merged  # noqa: E402

    try:
        payload = get_or_build_merged(
            pool_norm,
            redis_get=get_cached,
            redis_set=lambda k, v, ttl=604800: set_cached(k, v, ttl=ttl),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Slim response for Redis round-trips; full flat_nodes always returned to client
    _ontology_merged_mem[mem_key] = payload
    return {
        "pool": payload.get("pool"),
        "manifest": payload.get("manifest"),
        "n_cases": payload.get("n_cases"),
        "n_nodes": payload.get("n_nodes"),
        "flat_nodes": payload.get("flat_nodes"),
        "cache": payload.get("cache"),
    }


@app.post("/api/ontology/cache/warm")
def api_ontology_cache_warm(
    pool: str = Query("all", description="compare, all, universe, analysis, or both (all four)"),
):
    """Rebuild merged graph disk/redis caches (run after batch graph generation)."""
    ontology_dir = Path(__file__).resolve().parent.parent / "ontology"
    if str(ontology_dir) not in sys.path:
        sys.path.insert(0, str(ontology_dir))
    from merge_graph_cache import get_or_build_merged, warm_all_caches  # noqa: E402

    _ontology_catalog_mem.clear()
    _ontology_merged_mem.clear()
    pool_arg = pool.strip().lower()
    pools = (
        ["compare", "all", "universe", "analysis"]
        if pool_arg == "both"
        else [pool_arg]
    )
    results = []
    for p in pools:
        if p not in ("compare", "all", "universe", "analysis"):
            continue
        payload = get_or_build_merged(
            p,
            redis_get=get_cached,
            redis_set=lambda k, v, ttl=604800: set_cached(k, v, ttl=ttl),
        )
        results.append(
            {
                "pool": p,
                "n_cases": payload.get("n_cases"),
                "n_nodes": payload.get("n_nodes"),
                "cache": payload.get("cache"),
            }
        )
    return {"warmed": results}


_OXIGRAPH_URL = os.environ.get("OXIGRAPH_URL", "").strip().rstrip("/")
_SPARQL_HTTP_TIMEOUT_S = float(os.environ.get("SPARQL_HTTP_TIMEOUT_S", "32"))


async def _sparql_query_from_request(request: Request) -> str:
    """Read a SPARQL 1.1 Protocol query from GET or POST; reject Update payloads."""
    if request.query_params.get("update"):
        raise HTTPException(
            status_code=405,
            detail="SPARQL Update is not allowed on this endpoint.",
        )
    if request.method == "GET":
        query = request.query_params.get("query")
        if not query or not str(query).strip():
            raise HTTPException(status_code=400, detail="Missing query parameter.")
        return str(query)

    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type == "application/sparql-update":
        raise HTTPException(
            status_code=405,
            detail="SPARQL Update is not allowed on this endpoint.",
        )
    if content_type == "application/sparql-query":
        raw = (await request.body()).decode("utf-8", errors="replace")
        if not raw.strip():
            raise HTTPException(status_code=400, detail="Missing SPARQL query.")
        return raw

    form = await request.form()
    if form.get("update"):
        raise HTTPException(
            status_code=405,
            detail="SPARQL Update is not allowed on this endpoint.",
        )
    query = form.get("query")
    if not query or not str(query).strip():
        raise HTTPException(
            status_code=400,
            detail="Missing SPARQL query (POST application/sparql-query or form field query=).",
        )
    return str(query)


@app.api_route(
    "/sparql",
    methods=["GET", "POST"],
    tags=["SPARQL"],
    summary="SPARQL 1.1 Query (public)",
)
@limiter.limit("30/minute")
async def sparql_query(request: Request):
    """Public SPARQL 1.1 Query proxy over the CASE/UCO/CAC case graphs.

    Query-only (`SELECT`, `CONSTRUCT`, `ASK`, `DESCRIBE`). GET `?query=` or POST
    `application/sparql-query` / form `query=`. Default `Accept` is SPARQL Results
    JSON. Named graph per case; default graph is the union. 30/minute per IP.
    Update and `SERVICE` are rejected. User-facing guide: ontology/docs/SPARQL.md.
    """
    if not _OXIGRAPH_URL:
        raise HTTPException(
            status_code=503,
            detail="SPARQL store is not configured (set OXIGRAPH_URL).",
        )
    if rebuild_in_progress():
        raise HTTPException(
            status_code=503,
            detail="SPARQL store is being rebuilt. Retry shortly.",
        )

    query_text = await _sparql_query_from_request(request)
    try:
        prepared = prepare_sparql_query(query_text)
    except SparqlRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    accept = request.headers.get("accept") or "application/sparql-results+json"
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(_SPARQL_HTTP_TIMEOUT_S, connect=5.0)
        ) as client:
            upstream = await client.post(
                f"{_OXIGRAPH_URL}/query",
                content=prepared.query.encode("utf-8"),
                headers={
                    "Content-Type": "application/sparql-query",
                    "Accept": accept,
                },
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail=f"SPARQL query timed out after {_SPARQL_HTTP_TIMEOUT_S:.0f}s.",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail="SPARQL store is unreachable.",
        ) from exc

    media_type = upstream.headers.get("content-type") or "application/sparql-results+json"
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=media_type,
    )


# MCP mounts: legacy SSE at /mcp/sse + Streamable HTTP at /mcp-http
try:
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from caselinker_mcp.server import build_mcp_sse_app, build_mcp_streamable_app

    app.mount("/mcp", build_mcp_sse_app())
    # Legacy SSE: GET /mcp/sse, POST /mcp/messages?session_id=...
    app.mount("/mcp-http", build_mcp_streamable_app())
    # Streamable HTTP: GET+POST /mcp-http/ (single endpoint; trailing slash avoids 307)
    globals()["_mcp_streamable_enabled"] = True
except Exception as _mcp_mount_err:
    print(f"Warning: MCP mount failed: {_mcp_mount_err}", file=sys.stderr)


if __name__ == "__main__":
    import uvicorn
    import sys
    import os
    from pathlib import Path
    
    # Add project root to path for config import
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))
    
    try:
        from config import API_HOST, API_PORT, API_RELOAD
    except ImportError:
        # Fallback to defaults if config not found
        API_HOST = "0.0.0.0"
        API_PORT = 8000
        API_RELOAD = False
    
    # Use environment variables for production hosting (Railway, Render, etc.)
    port = int(os.environ.get("PORT", API_PORT))
    host = os.environ.get("HOST", API_HOST)
    
    # Disable reload when running directly (causes warning)
    # Use: uvicorn run.main:app --reload (from project root) for reload
    uvicorn.run(app, host=host, port=port, reload=False)
