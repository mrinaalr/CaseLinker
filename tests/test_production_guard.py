"""tests/conftest.py keeps every test off the production database and Redis."""
import os

import pytest

from tests import conftest as guard


def test_database_and_redis_urls_are_blank_for_every_test():
    for var in guard.GUARDED_VARS:
        assert os.environ.get(var) == "", var


def test_main_does_not_refill_database_url_from_dotenv():
    """run/main.py calls load_dotenv(override=False); a blank value must survive it."""
    from dotenv import load_dotenv
    load_dotenv(guard.ROOT / ".env", override=False)
    assert os.environ.get("DATABASE_URL") == ""


@pytest.mark.parametrize("url", ["postgresql://u:p@nozomi.proxy.rlwy.net:5432/db",
                                 "redis://default:p@redis.railway.internal:6379"])
def test_production_hosts_are_recognised(url):
    assert guard.names_production(url)


def test_production_postgres_connect_is_refused():
    import psycopg2
    with pytest.raises(RuntimeError, match="production Postgres"):
        psycopg2.connect("postgresql://u:p@nozomi.proxy.rlwy.net:5432/db")


def test_production_redis_client_is_refused():
    import redis
    with pytest.raises(RuntimeError, match="production Redis"):
        redis.Redis(host="redis.railway.internal", port=6379)


def test_local_hosts_are_not_production():
    assert not guard.names_production("postgresql://user:pw@db.example.test:5432/corpus")
    assert not guard.names_production("redis://localhost:6379")


def test_deleted_database_url_is_not_refilled_from_dotenv(monkeypatch):
    """The path the four tests took: delenv, then run/main.py's load_dotenv(override=False)."""
    from dotenv import dotenv_values, load_dotenv
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    load_dotenv(guard.ROOT / ".env", override=False)
    assert "DATABASE_URL" not in os.environ and "REDIS_URL" not in os.environ
    assert "DATABASE_URL" not in dotenv_values(guard.ROOT / ".env")


def test_importing_main_after_delenv_uses_sqlite(monkeypatch, tmp_path):
    import importlib.util
    import sys
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("CASELINKER_DB", str(tmp_path / "t.db"))
    spec = importlib.util.spec_from_file_location("main_guard_probe", guard.ROOT / "run" / "main.py")
    main = importlib.util.module_from_spec(spec)
    sys.modules["main_guard_probe"] = main
    spec.loader.exec_module(main)
    assert "DATABASE_URL" not in os.environ
    assert getattr(main, "db_path", None) is not None, "main fell back to Postgres"


def test_main_starts_no_warmup_thread_under_pytest(monkeypatch, tmp_path):
    import importlib.util
    import sys
    import threading
    monkeypatch.setenv("CASELINKER_DB", str(tmp_path / "t.db"))
    before = {t.ident for t in threading.enumerate()}
    spec = importlib.util.spec_from_file_location("main_warmup_probe", guard.ROOT / "run" / "main.py")
    main = importlib.util.module_from_spec(spec)
    sys.modules["main_warmup_probe"] = main
    spec.loader.exec_module(main)
    started = [t for t in threading.enumerate() if t.ident not in before and t.daemon]
    assert os.environ.get("CASELINKER_NO_WARMUP") == "1" and started == []
