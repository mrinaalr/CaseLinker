"""HEAD on a GET page returns that page's status and an empty body."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "run"

# Load this file by path. Another test puts src/ on sys.path, and src/main.py
# is also named main, so a bare import can bind the extractor instead.
_spec = importlib.util.spec_from_file_location("caselinker_run_main", RUN / "main.py")
main = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["caselinker_run_main"] = main
_spec.loader.exec_module(main)


def test_head_on_get_pages_returns_200_and_no_body():
    with TestClient(main.app) as client:
        for path in ("/", "/patterns", "/crash-course"):
            headers = {"accept-encoding": "identity"}
            got = client.get(path, headers=headers)
            head = client.head(path, headers=headers)
            assert got.status_code == 200, path
            assert head.status_code == 200, path
            assert head.content == b""
            assert head.headers["content-length"] == got.headers["content-length"]
