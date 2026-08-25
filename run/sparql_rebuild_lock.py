"""Rebuild fence for the public SPARQL proxy.

Wholesale Graph Store PUT /store can take tens of seconds on the full corpus.
Oxigraph does not expose a documented atomic swap that lets queries keep
seeing a consistent previous dataset for the whole upload, so /sparql returns
503 while a rebuild holds this lock.

The lock is a file (same container as the web process — the production rebuild
path is railway ssh on the web service) plus an optional Redis key so extra
web replicas 503 too when REDIS_URL is set.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
REDIS_KEY = "caselinker:sparql_rebuild"
# Long enough for a full-corpus PUT; crashed rebuilds expire instead of 503ing forever.
REDIS_TTL_S = 30 * 60


def lock_path() -> Path:
    return Path(os.environ.get("SPARQL_REBUILD_LOCK", "/tmp/caselinker-sparql-rebuild.lock"))


def acquire_rebuild_lock() -> Path:
    path = lock_path()
    path.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
    _redis_set_flag()
    return path


def release_rebuild_lock() -> None:
    lock_path().unlink(missing_ok=True)
    _redis_clear_flag()


def rebuild_in_progress() -> bool:
    if lock_path().is_file():
        return True
    return _redis_flag_set()


def _redis_set_flag() -> None:
    try:
        from redis_cache import set_cached

        set_cached(REDIS_KEY, {"active": True}, ttl=REDIS_TTL_S)
    except Exception:
        return


def _redis_clear_flag() -> None:
    try:
        from redis_cache import invalidate_cache_pattern

        invalidate_cache_pattern(REDIS_KEY)
    except Exception:
        return


def _redis_flag_set() -> bool:
    try:
        from redis_cache import get_cached

        return get_cached(REDIS_KEY) is not None
    except Exception:
        return False
