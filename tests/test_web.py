"""Tests for stackr.web — FastAPI web UI.

Route tests are skipped when FastAPI / httpx are not installed.
Helper tests (HAS_FASTAPI flag, create_app error path) always run.
"""

from __future__ import annotations

import pytest

from stackr.web import HAS_FASTAPI

# ---------------------------------------------------------------------------
# Import guard
# ---------------------------------------------------------------------------


def test_has_fastapi_is_bool() -> None:
    assert isinstance(HAS_FASTAPI, bool)


def test_create_app_raises_without_fastapi(monkeypatch: pytest.MonkeyPatch) -> None:
    """create_app must raise RuntimeError when fastapi is not importable."""
    import builtins

    real_import = builtins.__import__

    def blocked_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "fastapi":
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    from stackr.web.app import create_app

    with pytest.raises(RuntimeError, match="FastAPI"):
        create_app()


# ---------------------------------------------------------------------------
# Route tests (skipped when FastAPI or httpx not installed)
# ---------------------------------------------------------------------------

_SKIP = pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")

try:
    import httpx  # noqa: F401

    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

_SKIP_HTTPX = pytest.mark.skipif(
    not (HAS_FASTAPI and _HAS_HTTPX), reason="fastapi or httpx not installed"
)


@_SKIP_HTTPX
def test_dashboard_returns_html(tmp_path: pytest.FixtureLookupError) -> None:  # type: ignore[override]
    """GET / returns HTML with app cards."""
    from pathlib import Path

    import yaml
    from fastapi.testclient import TestClient

    from stackr.web.app import create_app

    config_path = tmp_path / "stackr.yml"  # type: ignore[operator]
    config_path.write_text(
        yaml.dump(
            {
                "global": {"data_dir": "/tmp/data"},
                "network": {"domain": "test.com"},
                "traefik": {"enabled": False},
                "security": {"socket_proxy": False},
                "apps": [{"name": "jellyfin", "enabled": True}],
            }
        )
    )

    application = create_app(Path(str(config_path)))
    client = TestClient(application)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Stackr" in resp.text
    assert "jellyfin" in resp.text.lower()


@_SKIP_HTTPX
def test_api_apps_json(tmp_path: pytest.FixtureLookupError) -> None:  # type: ignore[override]
    """GET /api/apps returns a JSON list."""
    from pathlib import Path

    import yaml
    from fastapi.testclient import TestClient

    from stackr.web.app import create_app

    config_path = tmp_path / "stackr.yml"  # type: ignore[operator]
    config_path.write_text(
        yaml.dump(
            {
                "global": {"data_dir": "/tmp/data"},
                "network": {"domain": "test.com"},
                "traefik": {"enabled": False},
                "security": {"socket_proxy": False},
                "apps": [{"name": "grafana", "enabled": True}],
            }
        )
    )

    application = create_app(Path(str(config_path)))
    client = TestClient(application)
    resp = client.get("/api/apps")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    names = [a["name"] for a in data]
    assert "grafana" in names


@_SKIP_HTTPX
def test_api_catalog_json(tmp_path: pytest.FixtureLookupError) -> None:  # type: ignore[override]
    """GET /api/catalog returns all catalog apps."""
    from pathlib import Path

    import yaml
    from fastapi.testclient import TestClient

    from stackr.web.app import create_app

    config_path = tmp_path / "stackr.yml"  # type: ignore[operator]
    config_path.write_text(
        yaml.dump(
            {
                "global": {"data_dir": "/tmp/data"},
                "network": {"domain": "test.com"},
                "traefik": {"enabled": False},
                "security": {"socket_proxy": False},
                "apps": [],
            }
        )
    )

    application = create_app(Path(str(config_path)))
    client = TestClient(application)
    resp = client.get("/api/catalog")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert all("name" in a for a in data)
