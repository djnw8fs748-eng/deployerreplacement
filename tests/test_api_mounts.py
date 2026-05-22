"""Tests for /api/v1/mounts routes."""
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
        "global:\n  data_dir: /opt/appdata\n"
        "network:\n  domain: test.local\n  local_domain: home.test.local\n"
        "mounts:\n"
        "  - name: nas\n    type: smb\n    remote: //nas/share\n"
        "    mountpoint: /mnt/nas\n    options: ''\n"
    )
    return p


@pytest.fixture
def api(cfg_path: Path):
    return create_api(cfg_path)


@pytest.mark.asyncio
async def test_list_mounts(api) -> None:
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        resp = await client.get("/api/v1/mounts/")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["name"] == "nas"


@pytest.mark.asyncio
async def test_add_mount(api, cfg_path: Path) -> None:
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        resp = await client.post("/api/v1/mounts/", json={
            "name": "backup",
            "type": "nfs",
            "remote": "nas:/backup",
            "mountpoint": "/mnt/backup",
        })
    assert resp.status_code == 201
    saved = yaml.safe_load(cfg_path.read_text())
    names = [m["name"] for m in saved.get("mounts", [])]
    assert "backup" in names


@pytest.mark.asyncio
async def test_add_mount_replaces_existing(api, cfg_path: Path) -> None:
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        resp = await client.post("/api/v1/mounts/", json={
            "name": "nas",
            "type": "smb",
            "remote": "//nas/newshare",
            "mountpoint": "/mnt/nas",
        })
    assert resp.status_code == 201
    saved = yaml.safe_load(cfg_path.read_text())
    mounts = {m["name"]: m for m in saved.get("mounts", [])}
    assert mounts["nas"]["remote"] == "//nas/newshare"
    assert len(mounts) == 1


@pytest.mark.asyncio
async def test_delete_mount(api, cfg_path: Path) -> None:
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        resp = await client.delete("/api/v1/mounts/nas")
    assert resp.status_code == 200
    saved = yaml.safe_load(cfg_path.read_text())
    names = [m["name"] for m in saved.get("mounts", [])]
    assert "nas" not in names


@pytest.mark.asyncio
async def test_delete_nonexistent_mount_returns_404(api) -> None:
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        resp = await client.delete("/api/v1/mounts/doesnotexist")
    assert resp.status_code == 404
