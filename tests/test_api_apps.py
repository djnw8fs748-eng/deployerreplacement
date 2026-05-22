"""Tests for /api/v1/apps routes."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

pytest.importorskip("httpx")
from httpx import ASGITransport, AsyncClient

from stackr.api.app import create_api
from stackr.engine.state import AppState, DeployEvent


@pytest.fixture
def cfg_path(tmp_path: Path) -> Path:
    p = tmp_path / "stackr.yml"
    p.write_text(
        "global:\n  data_dir: /opt/appdata\n"
        "network:\n  domain: test.local\n  local_domain: home.test.local\n"
        "apps:\n  - name: jellyfin\n    enabled: true\n"
    )
    return p


@pytest.fixture
def api(cfg_path: Path):
    return create_api(cfg_path)


@pytest.mark.asyncio
async def test_list_apps_returns_list(api) -> None:
    with patch("stackr.api.deps.StateDB") as MockDB:
        MockDB.return_value.list_apps.return_value = [
            AppState(name="jellyfin", enabled=True, status="running")
        ]
        MockDB.return_value.migrate_from_json.return_value = None
        async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
            resp = await client.get("/api/v1/apps/")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_get_app_not_in_db_returns_unknown(api) -> None:
    with patch("stackr.api.deps.StateDB") as MockDB:
        MockDB.return_value.get_app.return_value = None
        MockDB.return_value.migrate_from_json.return_value = None
        async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
            resp = await client.get("/api/v1/apps/jellyfin")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "jellyfin"
    assert data["status"] == "unknown"


@pytest.mark.asyncio
async def test_get_app_history(api) -> None:
    event = DeployEvent(
        app_name="jellyfin",
        event_type="deploy",
        success=True,
        stdout="done",
        stderr="",
        exit_code=0,
        duration_ms=1000,
        command="docker compose up -d",
        started_at="2026-01-01T00:00:00+00:00",
        id=1,
    )
    with patch("stackr.api.deps.StateDB") as MockDB:
        MockDB.return_value.get_app_history.return_value = [event]
        MockDB.return_value.migrate_from_json.return_value = None
        async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
            resp = await client.get("/api/v1/apps/jellyfin/history")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["success"] is True


@pytest.mark.asyncio
async def test_toggle_app(api, cfg_path: Path) -> None:
    with patch("stackr.api.deps.StateDB") as MockDB:
        MockDB.return_value.get_app.return_value = None
        MockDB.return_value.migrate_from_json.return_value = None
        async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
            resp = await client.post("/api/v1/apps/jellyfin/toggle")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_vars_returns_dict(api) -> None:
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        resp = await client.get("/api/v1/apps/jellyfin/vars")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


@pytest.mark.asyncio
async def test_put_vars_updates_config(api, cfg_path: Path) -> None:
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        resp = await client.put("/api/v1/apps/jellyfin/vars", json={"port": "8096"})
    assert resp.status_code == 200
    saved = yaml.safe_load(cfg_path.read_text())
    jellyfin = next(a for a in saved.get("apps", []) if a["name"] == "jellyfin")
    assert jellyfin.get("vars", {}).get("port") == "8096"
