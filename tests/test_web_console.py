from __future__ import annotations

from starlette.routing import Mount
from fastapi.testclient import TestClient

from app.main import app


def test_public_app_is_api_only():
    """8020 只暴露 API；前端由 vite dev server 单独提供。"""
    client = TestClient(app)
    assert client.get("/").status_code == 404
    assert client.get("/ui/").status_code == 404
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/health").status_code == 200
    assert [route.path for route in app.routes if isinstance(route, Mount)] == []