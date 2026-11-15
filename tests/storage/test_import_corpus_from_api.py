"""Corpus export streams table rows; the import script rebuilds sqlite without Railway."""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
STORAGE = ROOT / "src" / "Storage Layer"
for entry in (str(STORAGE), str(ROOT / "run"), str(ROOT / "scripts" / "run")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import import_corpus_from_api as importer  # noqa: E402
from corpus_export import iter_corpus_json  # noqa: E402
from storage import CaseStorage  # noqa: E402

ASSERTION_ID = 424242
RUN_ID = "run_fixture0001"
CASE_ID = "fixture_2026_001"
DOC_VERSION = "docv_fixture0001"
KEY = "test-trusted-key"


def _seed(path: Path) -> CaseStorage:
    storage = CaseStorage(str(path))
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO extraction_runs (run_id, started_at) VALUES (?, ?)",
        (RUN_ID, "2026-01-01T00:00:00Z"),
    )
    conn.execute(
        """INSERT INTO cases (
            id, source, perpetrator_count, extraction_run_id, document_version_id, raw_data
        ) VALUES (?, ?, ?, ?, ?, ?)""",
        (CASE_ID, "FIXTURE", 2, RUN_ID, DOC_VERSION, "{}"),
    )
    conn.execute(
        """INSERT INTO field_assertions (
            id, run_id, case_id, field, method, family, value_json, span_ok
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (ASSERTION_ID, RUN_ID, CASE_ID, "victim_count", "fixture", "fixture", "1", 1),
    )
    conn.execute(
        """INSERT INTO field_resolutions (
            id, run_id, case_id, field, rule_set_version, status
        ) VALUES (?, ?, ?, ?, ?, ?)""",
        (77, RUN_ID, CASE_ID, "victim_count", "resolve_v3.0", "final"),
    )
    conn.execute(
        """INSERT INTO review_queue (
            id, run_id, case_id, field, rule_set_version, reason
        ) VALUES (?, ?, ?, ?, ?, ?)""",
        (15, RUN_ID, CASE_ID, "victim_count", "resolve_v3.0", "needs_review"),
    )
    conn.commit()
    conn.close()
    return storage


def _counts(path: Path) -> dict[str, int]:
    conn = sqlite3.connect(path)
    out = {}
    for table in ("cases", "field_assertions", "field_resolutions", "review_queue"):
        out[table] = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    conn.close()
    return out


def test_import_script_does_not_read_database_url():
    text = (ROOT / "scripts" / "run" / "import_corpus_from_api.py").read_text()
    assert "DATABASE_URL" not in text
    assert "/api/corpus" in text
    assert "/api/cases" not in text


def test_export_skips_missing_table_and_keeps_case_columns(tmp_path: Path):
    storage = _seed(tmp_path / "source.db")
    conn = sqlite3.connect(storage.db_path)
    conn.execute("DROP TABLE automated_analysis_slim")
    conn.commit()
    conn.close()
    body = json.loads(b"".join(iter_corpus_json(storage)))
    assert "automated_analysis_slim" not in body
    assert "cases" in body
    case = body["cases"][0]
    assert case["extraction_run_id"] == RUN_ID
    assert case["document_version_id"] == DOC_VERSION
    assert case["perpetrator_count"] == 2
    assert body["field_assertions"][0]["id"] == ASSERTION_ID
    assert body["extraction_runs"][0]["run_id"] == RUN_ID


def test_round_trip_preserves_ids_and_ignores_unknown_columns(tmp_path: Path):
    storage = _seed(tmp_path / "source.db")
    text = b"".join(iter_corpus_json(storage)).decode()
    # A postgres-only column must not fail the sqlite insert.
    case_key = '"perpetrator_count":2'
    assert case_key in text
    text = text.replace(case_key, case_key + ',"investigation_methods":["drop-me"]', 1)
    pieces = [text[i : i + 5] for i in range(0, len(text), 5)]
    dest = tmp_path / "dest.db"
    importer.load_corpus(pieces, dest)

    assert _counts(dest) == _counts(Path(storage.db_path))
    conn = sqlite3.connect(dest)
    case = conn.execute(
        "SELECT perpetrator_count, extraction_run_id, document_version_id FROM cases"
    ).fetchone()
    assert case == (2, RUN_ID, DOC_VERSION)
    assert conn.execute("SELECT id FROM field_assertions").fetchone()[0] == ASSERTION_ID
    assert conn.execute("SELECT id FROM field_resolutions").fetchone()[0] == 77
    assert conn.execute("SELECT id FROM review_queue").fetchone()[0] == 15
    assert conn.execute("SELECT run_id FROM extraction_runs").fetchone()[0] == RUN_ID
    seq = conn.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = 'field_assertions'"
    ).fetchone()[0]
    assert seq == ASSERTION_ID
    conn.execute(
        """INSERT INTO field_assertions (
            run_id, case_id, field, method, family, value_json, span_ok
        ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (RUN_ID, CASE_ID, "other", "fixture", "fixture", "1", 1),
    )
    new_id = conn.execute(
        "SELECT id FROM field_assertions WHERE field = 'other'"
    ).fetchone()[0]
    assert new_id == ASSERTION_ID + 1
    columns = {row[1] for row in conn.execute("PRAGMA table_info(cases)")}
    assert "investigation_methods" not in columns
    conn.close()


def test_import_requires_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CASELINKER_KEY", raising=False)
    assert importer.main() == 1


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _serve() -> None:
    """Boot run/main.py against SOURCE_DB. Never loads the repo .env database."""
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    os.environ["DATABASE_URL"] = ""
    os.environ.pop("ALLOW_RUNTIME_CLUSTER_COMPUTE", None)

    import dotenv

    dotenv.load_dotenv = lambda *args, **kwargs: False

    import config

    config.DATABASE_PATH = str(Path(os.environ["SOURCE_DB"]).resolve())
    os.environ["CASELINKER_TRUSTED_KEYS"] = os.environ["TRUSTED_KEY"]

    sys.path.insert(0, str(ROOT / "run"))
    import main

    if os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL leaked into the corpus test server")
    if Path(main.db_path).resolve() != Path(os.environ["SOURCE_DB"]).resolve():
        raise SystemExit(f"server db is {main.db_path}, not the temp sqlite")

    from fastapi.testclient import TestClient

    with TestClient(main.app) as client:
        denied = client.get("/api/corpus")
        assert denied.status_code == 403, denied.text
        wrong = client.get("/api/corpus", headers={"CaseLinker-Key": "not-the-key"})
        assert wrong.status_code == 403, wrong.text
        ok = client.get("/api/corpus", headers={"CaseLinker-Key": os.environ["TRUSTED_KEY"]})
        assert ok.status_code == 200, ok.text[:300]
        body = ok.json()
        assert body["field_assertions"][0]["id"] == ASSERTION_ID
        assert body["cases"][0]["extraction_run_id"] == RUN_ID
        assert body["cases"][0]["document_version_id"] == DOC_VERSION
    print("GATE_OK", flush=True)


def _serve_only() -> None:
    """Listen on PORT. Separate process from the TestClient gate check."""
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    os.environ["DATABASE_URL"] = ""
    os.environ.pop("ALLOW_RUNTIME_CLUSTER_COMPUTE", None)

    import dotenv

    dotenv.load_dotenv = lambda *args, **kwargs: False

    import config

    config.DATABASE_PATH = str(Path(os.environ["SOURCE_DB"]).resolve())
    os.environ["CASELINKER_TRUSTED_KEYS"] = os.environ["TRUSTED_KEY"]

    sys.path.insert(0, str(ROOT / "run"))
    import main

    if Path(main.db_path).resolve() != Path(os.environ["SOURCE_DB"]).resolve():
        raise SystemExit(f"server db is {main.db_path}, not the temp sqlite")

    import uvicorn

    uvicorn.run(
        main.app,
        host="127.0.0.1",
        port=int(os.environ["PORT"]),
        log_level="warning",
    )


def _child_env(source: Path, port: int) -> dict[str, str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = ""
    env.pop("ALLOW_RUNTIME_CLUSTER_COMPUTE", None)
    env["SOURCE_DB"] = str(source)
    env["PORT"] = str(port)
    env["TRUSTED_KEY"] = KEY
    env["CASELINKER_TRUSTED_KEYS"] = KEY
    env["PYTHONUNBUFFERED"] = "1"
    return env


def test_local_server_and_trusted_key_rebuilds_sqlite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source = tmp_path / "source.db"
    dest = tmp_path / "rebuilt.db"
    _seed(source)
    port = _free_port()
    env = _child_env(source, port)
    gate = subprocess.run(
        [sys.executable, str(Path(__file__)), "--gate-corpus-test"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert gate.returncode == 0, gate.stdout + gate.stderr
    assert "GATE_OK" in gate.stdout

    log_path = tmp_path / "server.log"
    log_file = log_path.open("w")
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__)), "--serve-corpus-test"],
        cwd=str(ROOT),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.time() + 60
        while time.time() < deadline:
            if proc.poll() is not None:
                log_file.flush()
                raise AssertionError(
                    f"server exited {proc.returncode}\n{log_path.read_text()}"
                )
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            proc.kill()
            log_file.flush()
            raise AssertionError(f"server never listened on {port}\n{log_path.read_text()}")

        monkeypatch.setenv("CASELINKER_KEY", KEY)
        monkeypatch.setenv("CASELINKER_API_URL", f"http://127.0.0.1:{port}")
        monkeypatch.setenv("CASELINKER_DB", str(dest))
        assert "railway" not in os.environ["CASELINKER_API_URL"]
        assert importer.main() == 0
        assert _counts(dest) == _counts(source)
        conn = sqlite3.connect(dest)
        assert conn.execute("SELECT id FROM field_assertions").fetchone()[0] == ASSERTION_ID
        assert conn.execute(
            "SELECT extraction_run_id, document_version_id FROM cases"
        ).fetchone() == (RUN_ID, DOC_VERSION)
        conn.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_file.close()


if __name__ == "__main__":
    if "--gate-corpus-test" in sys.argv:
        _serve()
    elif "--serve-corpus-test" in sys.argv:
        _serve_only()
