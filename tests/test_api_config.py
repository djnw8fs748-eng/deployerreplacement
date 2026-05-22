"""Tests for /api/v1/config routes."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytest.importorskip("httpx")
from httpx import ASGITransport, AsyncClient

from stackr.api.app import create_api


@pytest.fixture
def cfg_path(tmp_path: Path) -> Path:
    p = tmp_path / "stackr.yml"
    p.write_text(
        "global:\n  data_dir: /opt/appdata\n  timezone: UTC\n  puid: 1000\n  pgid: 1000\n"
        "network:\n  domain: test.local\n  local_domain: home.test.local\n"
        "security:\n  socket_proxy: false\n"
        "backup:\n  enabled: false\n"
        "alerts:\n  enabled: false\n"
    )
    return p


@pytest.fixture
def api(cfg_path: Path):
    return create_api(cfg_path)


@pytest.mark.asyncio
async def test_get_config_returns_full_config(api) -> None:
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        resp = await client.get("/api/v1/config/")
    assert resp.status_code == 200
    data = resp.json()
    assert "global" in data
    assert "network" in data
    assert "security" in data


@pytest.mark.asyncio
async def test_put_global_updates_timezone(api, cfg_path: Path) -> None:
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        resp = await client.put("/api/v1/config/global", json={"timezone": "Europe/London"})
    assert resp.status_code == 200
    saved = yaml.safe_load(cfg_path.read_text())
    assert saved["global"]["timezone"] == "Europe/London"


@pytest.mark.asyncio
async def test_put_network_updates_domain(api, cfg_path: Path) -> None:
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        resp = await client.put("/api/v1/config/network", json={"domain": "newdomain.com"})
    assert resp.status_code == 200
    saved = yaml.safe_load(cfg_path.read_text())
    assert saved["network"]["domain"] == "newdomain.com"


@pytest.mark.asyncio
async def test_put_security_updates_socket_proxy(api, cfg_path: Path) -> None:
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        resp = await client.put("/api/v1/config/security", json={"socket_proxy": True})
    assert resp.status_code == 200
    saved = yaml.safe_load(cfg_path.read_text())
    assert saved["security"]["socket_proxy"] is True


@pytest.mark.asyncio
async def test_put_ignores_none_fields(api, cfg_path: Path) -> None:
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        await client.put("/api/v1/config/global", json={"timezone": "America/New_York"})
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        resp = await client.put("/api/v1/config/global", json={"puid": 1001})
    assert resp.status_code == 200
    saved = yaml.safe_load(cfg_path.read_text())
    assert saved["global"]["timezone"] == "America/New_York"
    assert saved["global"]["puid"] == 1001
