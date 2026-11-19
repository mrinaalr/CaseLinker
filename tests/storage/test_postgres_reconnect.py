"""A bulk ingest survives a dropped Postgres connection. No database: the pool is faked."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for sub in ("src", "src/Processing Layer", "src/Storage Layer"):
    if str(REPO / sub) not in sys.path:
        sys.path.insert(0, str(REPO / sub))

psycopg2 = pytest.importorskip("psycopg2")
import storage_postgres as sp  # noqa: E402


class FakeCursor:
    def __init__(self, conn, landed=()):
        self.conn = conn
        self.landed = list(landed)
        self.queries = []

    def execute(self, sql, params=None):
        if self.conn.closed:
            raise psycopg2.OperationalError("server closed the connection")
        self.queries.append(sql)

    def fetchall(self):
        return [(cid,) for cid in self.landed]

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConn:
    def __init__(self, name, closed=False, landed=()):
        self.name = name
        self.closed = closed
        self.landed = landed

    def cursor(self):
        return FakeCursor(self, self.landed)

    def rollback(self):
        pass

    def commit(self):
        pass


class FakePool:
    def __init__(self, conns):
        self.conns = list(conns)
        self.closed_out = []
        self.returned = []

    def getconn(self):
        return self.conns.pop(0)

    def putconn(self, conn, close=False):
        (self.closed_out if close else self.returned).append(conn.name)


def test_get_connection_replaces_a_connection_the_server_closed(monkeypatch):
    pool = FakePool([FakeConn("dead", closed=True), FakeConn("live")])
    monkeypatch.setattr(sp, "get_pool", lambda: pool)

    conn = sp.get_connection()

    assert conn.name == "live"
    assert pool.closed_out == ["dead"]


def test_store_cases_retries_a_dropped_batch_without_restoring_landed_cases(monkeypatch):
    first = FakeConn("first")
    second = FakeConn("second", landed=["c1"])
    pool = FakePool([first, second])
    monkeypatch.setattr(sp, "get_pool", lambda: pool)
    monkeypatch.setenv("STORE_COMMIT_BATCH", "3")

    calls = []

    def fake_commit(self, conn, cursor, batch):
        calls.append((conn.name, [c["id"] for c in batch]))
        if conn is first:
            conn.closed = True  # c1 committed per case, then the server dropped us
            return 1
        return len(batch)

    monkeypatch.setattr(sp.CaseStorage, "_commit_case_batch", fake_commit)
    storage = sp.CaseStorage.__new__(sp.CaseStorage)
    cases = [{"id": f"c{i}", "extraction_run_id": "run-1"} for i in (1, 2, 3)]

    stored = storage.store_cases(cases)

    assert stored == 3
    assert calls == [("first", ["c1", "c2", "c3"]), ("second", ["c2", "c3"])]
    assert pool.closed_out == ["first"]
    assert pool.returned == ["second"]
