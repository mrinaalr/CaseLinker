"""Put Storage Layer on sys.path the same way src/main.py does, and keep every test off production."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]

# --- production guard -------------------------------------------------------------------------
# run/main.py loads .env with override=False, and .env holds the production DATABASE_URL and
# REDIS_URL. A test that imported main without DATABASE_URL='' would open production Postgres
# (and run its startup DDL). Set the variables empty here, before any test module is collected, so
# load_dotenv never fills them; then refuse any connection or environment that names a production host.
GUARDED_VARS = ("DATABASE_URL", "REDIS_URL", "REDIS_PASSWORD")
PRODUCTION_MARKERS = ("rlwy.net", "railway.internal", "railway.app")


def _dotenv_hosts(path: Path) -> set:
    hosts = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return hosts
    for line in lines:
        key, _, value = line.partition("=")
        if key.strip() in ("DATABASE_URL", "REDIS_URL") and "://" in value:
            host = urlparse(value.strip().strip("'\"")).hostname
            if host:
                hosts.add(host)
    return hosts


PRODUCTION_HOSTS = _dotenv_hosts(ROOT / ".env") | _dotenv_hosts(ROOT / "run" / ".env")


def names_production(value) -> bool:
    text = str(value or "")
    return any(m in text for m in PRODUCTION_MARKERS) or any(h in text for h in PRODUCTION_HOSTS)


for _var in GUARDED_VARS:
    os.environ[_var] = ""

# No import-time cache warming in run/main.py: its thread prints into other tests' captured output.
os.environ["CASELINKER_NO_WARMUP"] = "1"

# run/main.py opens <repo>/config.DATABASE_PATH at import and creates it if missing. In a clone without the
# local corpus DB that left an empty caselinker.db in the repo root, so tests that skip when the corpus DB is
# absent ran against an empty file and failed. Point main at a scratch file instead, only when no corpus DB exists.
if not (ROOT / "caselinker.db").exists():
    import tempfile

    sys.path.insert(0, str(ROOT))
    import config as _config

    _config.DATABASE_PATH = str(Path(tempfile.mkdtemp(prefix="caselinker-tests-")) / "caselinker.db")

# A test that deletes DATABASE_URL (to force SQLite) and then imports run/main.py used to get the
# production URL back from .env through load_dotenv(override=False). Under pytest, dotenv never
# applies or returns the guarded variables, so no test can resolve production from a file.
try:
    import dotenv as _dotenv

    _real_dotenv_values = _dotenv.dotenv_values

    def _guarded_dotenv_values(*args, **kwargs):
        return {k: v for k, v in _real_dotenv_values(*args, **kwargs).items() if k not in GUARDED_VARS}

    def _guarded_load_dotenv(dotenv_path=None, stream=None, verbose=False, override=False, interpolate=True,
                             encoding="utf-8"):
        values = _guarded_dotenv_values(dotenv_path=dotenv_path, stream=stream, verbose=verbose,
                                        interpolate=interpolate, encoding=encoding)
        for key, value in values.items():
            if value is not None and (override or key not in os.environ):
                os.environ[key] = value
        return bool(values)

    _dotenv.dotenv_values = _guarded_dotenv_values
    _dotenv.load_dotenv = _guarded_load_dotenv
    _dotenv.main.dotenv_values = _guarded_dotenv_values
    _dotenv.main.load_dotenv = _guarded_load_dotenv
except ImportError:
    pass


def _refuse(kind: str):
    raise RuntimeError(f"test tried to open a production {kind} connection; tests must never reach production")


try:
    import psycopg2 as _psycopg2

    _real_pg_connect = _psycopg2.connect

    def _guarded_pg_connect(*args, **kwargs):
        if names_production(args) or names_production(kwargs) or names_production(os.environ.get("DATABASE_URL")):
            _refuse("Postgres")
        return _real_pg_connect(*args, **kwargs)

    _psycopg2.connect = _guarded_pg_connect
except ImportError:
    pass

try:
    import redis as _redis

    _real_redis_init = _redis.Redis.__init__

    def _guarded_redis_init(self, *args, **kwargs):
        if names_production(args) or names_production(kwargs):
            _refuse("Redis")
        _real_redis_init(self, *args, **kwargs)

    _redis.Redis.__init__ = _guarded_redis_init
except ImportError:
    pass
STORAGE = ROOT / "src" / "Storage Layer"
if str(STORAGE) not in sys.path:
    sys.path.insert(0, str(STORAGE))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# Importing run/main.py builds CaseStorage() on the default path, which creates an empty,
# schema-only caselinker.db in a checkout that has none. Tests that read the real corpus
# skip on `not DB.exists()`, so a later pytest run then fails them instead of skipping.
# Remove the file at session end only if this session created it and it holds no cases.
import sqlite3 as _sqlite3

import pytest as _pytest

_REPO_DB = ROOT / "caselinker.db"
# Recorded at conftest import, before test modules (and run/main.py) are collected.
_DB_EXISTED_AT_START = _REPO_DB.exists()


@_pytest.fixture(scope="session", autouse=True)
def _remove_empty_db_created_by_this_session():
    yield
    if _DB_EXISTED_AT_START or not _REPO_DB.exists():
        return
    try:
        with _sqlite3.connect(f"file:{_REPO_DB}?mode=ro", uri=True) as conn:
            n = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
    except _sqlite3.Error:
        return
    if n == 0:
        _REPO_DB.unlink()


@_pytest.fixture(autouse=True)
def _never_production():
    """Fail loudly if a test leaves a production database or Redis URL in the environment."""
    yield
    leaked = [v for v in GUARDED_VARS if names_production(os.environ.get(v))]
    if leaked:
        raise AssertionError(f"production host in {', '.join(leaked)} after this test; tests must never reach production")
