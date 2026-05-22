"""Integration smoke tests for the full Stackr API."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("httpx")
from httpx import ASGITransport, AsyncClient

from stackr.api.app import create_api


@pytest.fixture
def api(tmp_path: Path):
    cfg = tmp_path / "stackr.yml"
    cfg.write_text(
        "global:\n  data_dir: /opt/appdata\n"
        "network:\n  domain: test.local\n  local_domain: home.test.local\n"
    )
    return create_api(cfg)


@pytest.mark.asyncio
async def test_openapi_schema_available(api) -> None:
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        resp = await client.get("/api/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert schema["info"]["title"] == "Stackr API"


@pytest.mark.asyncio
async def test_all_route_prefixes_registered(api) -> None:
    """Smoke-test that all routers are mounted by hitting their list endpoints."""
    with patch("stackr.engine.docker.docker_available", return_value=True), \
         patch("stackr.engine.docker.network_exists", return_value=True):
        async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
            routes_to_check = [
                "/api/v1/system/health",
                "/api/v1/catalog/",
                "/api/v1/config/",
                "/api/v1/mounts/",
                "/api/v1/deploy/status",
            ]
            for route in routes_to_check:
                resp = await client.get(route)
                assert resp.status_code in (200, 201), f"Route {route} returned {resp.status_code}"


def test_create_api_raises_without_fastapi(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import builtins
    real_import = builtins.__import__

    def blocked(name: str, *args: object, **kwargs: object) -> object:
        if name == "fastapi":
            raise ImportError("blocked")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    with pytest.raises(RuntimeError, match="FastAPI"):
        create_api(tmp_path / "stackr.yml")


@pytest.mark.asyncio
async def test_spa_root_returns_html(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """GET / should serve the SPA index.html."""
    import stackr.api.app as api_module
    monkeypatch.setattr(api_module, "_STATIC_DIR", tmp_path)
    (tmp_path / "index.html").write_text("<!DOCTYPE html><html><body>Stackr</body></html>")
    (tmp_path / "style.css").write_text("body{}")
    (tmp_path / "app.js").write_text("/* js */")

    cfg = tmp_path / "stackr.yml"
    cfg.write_text(
        "global:\n  data_dir: /opt/appdata\n"
        "network:\n  domain: test.local\n  local_domain: home.test.local\n"
    )
    api = create_api(cfg)
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_static_files_served(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /static/style.css and /static/app.js should return 200 when files exist."""
    import stackr.api.app as api_module
    monkeypatch.setattr(api_module, "_STATIC_DIR", tmp_path)
    (tmp_path / "index.html").write_text("<!DOCTYPE html><html><body>Stackr</body></html>")
    (tmp_path / "style.css").write_text("body { color: red; }")
    (tmp_path / "app.js").write_text("console.log('test');")

    cfg = tmp_path / "stackr.yml"
    cfg.write_text(
        "global:\n  data_dir: /opt/appdata\n"
        "network:\n  domain: test.local\n  local_domain: home.test.local\n"
    )
    api = create_api(cfg)
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        css = await client.get("/static/style.css")
        js = await client.get("/static/app.js")
    assert css.status_code == 200
    assert js.status_code == 200


def test_service_systemd_unit_uses_api_command() -> None:
    from pathlib import Path

    from stackr.service import _systemd_unit
    unit = _systemd_unit(Path("/home/user/stackr.yml"), "127.0.0.1", 7274)
    assert "stackr api" in unit
    assert "7274" in unit
    assert "stackr web" not in unit


def test_service_launchd_plist_uses_api_command() -> None:
    from pathlib import Path

    from stackr.service import _launchd_plist
    plist = _launchd_plist(Path("/home/user/stackr.yml"), "127.0.0.1", 7274)
    assert "stackr" in plist
    assert "api" in plist
    assert "web" not in plist
