"""Put Storage Layer on sys.path the same way src/main.py does."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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


@_pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """A missing spaCy model fails closed. Those v2 tests skip instead of failing."""
    outcome = yield
    report = outcome.get_result()
    if call.when == "call" and call.excinfo is not None and call.excinfo.typename == "SystemExit":
        if "spaCy model" in str(call.excinfo.value):
            report.outcome = "skipped"
            report.longrepr = (str(call.excinfo.value), "", "")


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
