from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from run.main import app

pytestmark = pytest.mark.smoke


def test_application_exposes_minimum_service_contract() -> None:
    paths = {route.path for route in app.routes}

    assert app.title == "CaseLinker API"
    assert {"/", "/api", "/api/case-count", "/healthz"}.issubset(paths)


def test_health_endpoint_is_live() -> None:
    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text == "ok"
