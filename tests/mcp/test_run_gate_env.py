"""run_gate's pytest children must not reach production (Phase 4 plan §A gap 2).

Before the fix, _run_tests ran pytest with the parent's full environment, and
run/main.py's load_dotenv(override=False) could supply DATABASE_URL from .env.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

from caselinker_mcp import repair_expand as R

FAKE_URL = "postgresql://user:secret@prod.invalid:5432/db"

# The same two calls run/main.py makes at import time.
_LOAD_LIKE_MAIN = textwrap.dedent(
    """
    import os, sys
    from pathlib import Path
    from dotenv import load_dotenv
    root = Path(sys.argv[1])
    load_dotenv(root / ".env", override=False)
    load_dotenv(root / "run" / ".env", override=False)
    print(repr(os.getenv("DATABASE_URL")), repr(os.getenv("PROJECT_SECRET")))
    """
)


def _fake_root(tmp_path: Path) -> Path:
    (tmp_path / "run").mkdir()
    (tmp_path / ".env").write_text(f"DATABASE_URL={FAKE_URL}\nexport PROJECT_SECRET=abc\n# comment\n")
    (tmp_path / "run" / ".env").write_text("DATABASE_URL=postgresql://second.invalid/db\n")
    return tmp_path


def _child(env: dict, root: Path) -> str:
    out = subprocess.run([sys.executable, "-c", _LOAD_LIKE_MAIN, str(root)], env=env,
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def test_env_blanks_inherited_secrets_and_every_dotenv_key(tmp_path):
    root = _fake_root(tmp_path)
    parent = {"PATH": "/usr/bin", "HOME": "/home/x", "DATABASE_URL": FAKE_URL,
              "RAILWAY_ENVIRONMENT": "production", "SOME_OTHER_TOKEN": "t"}
    env = R._test_env(root, environ=parent)
    assert env["DATABASE_URL"] == ""
    assert env["PROJECT_SECRET"] == ""          # named only in .env
    assert env["RAILWAY_ENVIRONMENT"] == ""
    assert "SOME_OTHER_TOKEN" not in env        # not allow-listed, so not inherited
    assert env["PATH"] == "/usr/bin"
    assert R._dotenv_keys(root) == ["DATABASE_URL", "PROJECT_SECRET", "DATABASE_URL"]


def test_child_process_cannot_load_production_credentials(tmp_path):
    root = _fake_root(tmp_path)
    parent = {"PATH": "/usr/bin:/bin", "DATABASE_URL": FAKE_URL}
    assert _child(R._test_env(root, environ=parent), root) == "'' ''"


def test_control_without_isolation_does_load_credentials(tmp_path):
    """Shows the check above can fail: an un-scrubbed child reads .env."""
    root = _fake_root(tmp_path)
    assert _child({"PATH": "/usr/bin:/bin"}, root) == f"{FAKE_URL!r} 'abc'"


def test_run_tests_passes_isolated_env_to_every_pytest_child(monkeypatch):
    seen = []

    def fake_run(cmd, **kwargs):
        seen.append(kwargs)
        return SimpleNamespace(stdout="1 passed in 0.01s\n", returncode=0)

    monkeypatch.setenv("DATABASE_URL", FAKE_URL)
    monkeypatch.setattr(R.subprocess, "run", fake_run)
    result = R._run_tests()
    assert seen, "no test file was run"
    assert result["ok"]
    for kwargs in seen:
        assert "env" in kwargs, "pytest child inherited the parent environment"
        assert kwargs["env"]["DATABASE_URL"] == ""
        assert kwargs["env"]["CASELINKER_GATE_CHILD"] == "1"
