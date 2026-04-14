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
def test_api_apps_returns_all_catalog_apps(tmp_path: pytest.FixtureLookupError) -> None:  # type: ignore[override]
    """GET /api/apps returns all catalog apps even when config only lists a few."""
    from pathlib import Path

    import yaml
    from fastapi.testclient import TestClient

    from stackr.catalog import Catalog
    from stackr.web.app import create_app

    config_path = tmp_path / "stackr.yml"  # type: ignore[operator]
    # Config lists only one app — dashboard must still show the full catalog
    config_path.write_text(
        yaml.dump(
            {
                "global": {"data_dir": "/tmp/data"},
                "network": {"domain": "test.com"},
                "security": {"socket_proxy": False},
                "apps": [{"name": "jellyfin", "enabled": True}],
            }
        )
    )

    application = create_app(Path(str(config_path)))
    client = TestClient(application)
    resp = client.get("/api/apps")
    assert resp.status_code == 200
    data = resp.json()
    names = {a["name"] for a in data}

    catalog_names = {a.name for a in Catalog().all()}
    assert catalog_names <= names, (
        f"Missing from /api/apps: {catalog_names - names}"
    )
    # jellyfin should be marked enabled, grafana should be disabled
    by_name = {a["name"]: a for a in data}
    assert by_name["jellyfin"]["enabled"] is True
    assert by_name["grafana"]["enabled"] is False


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


@_SKIP_HTTPX
def test_api_settings_get(tmp_path: pytest.FixtureLookupError) -> None:  # type: ignore[override]
    """GET /api/settings returns 200 with expected keys."""
    from pathlib import Path

    import yaml
    from fastapi.testclient import TestClient

    from stackr.web.app import create_app

    config_path = tmp_path / "stackr.yml"  # type: ignore[operator]
    config_path.write_text(
        yaml.dump(
            {
                "global": {
                    "data_dir": "/srv/appdata",
                    "timezone": "Europe/Berlin",
                    "puid": 1001,
                    "pgid": 1001,
                },
                "network": {
                    "domain": "lab.example.com",
                    "local_domain": "home.lab.example.com",
                },
                "security": {"socket_proxy": False},
                "apps": [],
            }
        )
    )

    application = create_app(Path(str(config_path)))
    client = TestClient(application)
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    expected_keys = {
        "data_dir", "timezone", "puid", "pgid",
        "domain", "local_domain",
    }
    assert expected_keys <= set(data.keys())
    assert data["data_dir"] == "/srv/appdata"
    assert data["timezone"] == "Europe/Berlin"
    assert data["puid"] == 1001
    assert "traefik_enabled" not in data
    assert "dns_provider" not in data
    assert "network_mode" not in data


@_SKIP_HTTPX
def test_api_settings_post(tmp_path: pytest.FixtureLookupError) -> None:  # type: ignore[override]
    """POST /api/settings with form data updates the config file."""
    from pathlib import Path

    import yaml
    from fastapi.testclient import TestClient

    from stackr.web.app import create_app

    config_path = tmp_path / "stackr.yml"  # type: ignore[operator]
    config_path.write_text(
        yaml.dump(
            {
                "global": {"data_dir": "/old", "timezone": "UTC", "puid": 1000, "pgid": 1000},
                "network": {
                    "domain": "old.com",
                    "local_domain": "home.old.com",
                },
                "security": {"socket_proxy": False},
                "apps": [],
            }
        )
    )

    application = create_app(Path(str(config_path)))
    client = TestClient(application)
    resp = client.post(
        "/api/settings",
        data={
            "data_dir": "/new/appdata",
            "timezone": "America/New_York",
            "puid": "2000",
            "pgid": "2000",
            "domain": "new.example.com",
            "local_domain": "home.new.example.com",
        },
    )
    assert resp.status_code == 200
    assert "saved" in resp.text.lower() or "✓" in resp.text

    written = yaml.safe_load(Path(str(config_path)).read_text())
    assert written["global"]["data_dir"] == "/new/appdata"
    assert written["global"]["timezone"] == "America/New_York"
    assert written["global"]["puid"] == 2000
    assert written["network"]["domain"] == "new.example.com"
    assert "traefik" not in written
