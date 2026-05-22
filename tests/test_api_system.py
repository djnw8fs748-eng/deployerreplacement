"""Tests for /api/v1/system routes."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

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
async def test_health_docker_down(api) -> None:
    with patch("stackr.engine.docker.docker_available", return_value=False), \
         patch("stackr.engine.docker.network_exists", return_value=False):
        async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
            resp = await client.get("/api/v1/system/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["healthy"] is False
    assert any(c["name"] == "docker" for c in data["checks"])


@pytest.mark.asyncio
async def test_health_docker_up(api) -> None:
    with patch("stackr.engine.docker.docker_available", return_value=True), \
         patch("stackr.engine.docker.network_exists", return_value=True):
        async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
            resp = await client.get("/api/v1/system/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["healthy"] is True


@pytest.mark.asyncio
async def test_validate_returns_result(api) -> None:
    with patch("stackr.engine.validator.validate") as mock_val:
        mock_result = MagicMock()
        mock_result.ok = True
        mock_result.errors = []
        mock_result.warnings = []
        mock_val.return_value = mock_result
        async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
            resp = await client.post("/api/v1/system/validate")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_secret_names_returns_list(api) -> None:
    mock_env = {"MY_SECRET": "val", "OTHER": "x"}
    with patch("stackr.api.deps.build_env", return_value=mock_env):
        async with AsyncClient(
            transport=ASGITransport(app=api), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/system/secrets")
    assert resp.status_code == 200
    data = resp.json()
    assert "names" in data
    assert isinstance(data["names"], list)
