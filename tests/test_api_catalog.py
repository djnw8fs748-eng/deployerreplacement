"""Tests for /api/v1/catalog routes."""
from __future__ import annotations

from pathlib import Path

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
async def test_catalog_list_returns_apps(api) -> None:
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        resp = await client.get("/api/v1/catalog/")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert all("name" in a for a in data)
    assert all("category" in a for a in data)


@pytest.mark.asyncio
async def test_catalog_get_known_app(api) -> None:
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        all_resp = await client.get("/api/v1/catalog/")
        name = all_resp.json()[0]["name"]
        resp = await client.get(f"/api/v1/catalog/{name}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == name
    assert "vars" in data
    assert "ports" in data


@pytest.mark.asyncio
async def test_catalog_get_unknown_app_returns_404(api) -> None:
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        resp = await client.get("/api/v1/catalog/this-app-does-not-exist")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_catalog_search(api) -> None:
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        resp = await client.get("/api/v1/catalog/?search=jelly")
    assert resp.status_code == 200
    data = resp.json()
    assert all(
        "jelly" in a["name"].lower() or "jelly" in a["description"].lower()
        for a in data
    )
