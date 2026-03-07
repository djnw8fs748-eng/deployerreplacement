"""Tests for config loading and Pydantic validation."""

import textwrap
from pathlib import Path

import pytest
import yaml

from stackr.config import StackrConfig, load_config


def _config_from_dict(d: dict) -> StackrConfig:
    return StackrConfig.model_validate(d)


def test_minimal_config():
    cfg = _config_from_dict({"global": {"data_dir": "/data"}})
    assert str(cfg.global_.data_dir) == "/data"
    assert cfg.network.mode == "external"


def test_invalid_network_mode():
    with pytest.raises(Exception, match="network.mode"):
        _config_from_dict({"network": {"mode": "invalid"}})


def test_invalid_auth_provider():
    with pytest.raises(Exception):
        _config_from_dict({"security": {"auth_provider": "unknown"}})


def test_socket_proxy_auto_injected():
    cfg = _config_from_dict({
        "traefik": {"enabled": True},
        "security": {"socket_proxy": True},
        "apps": [{"name": "traefik", "enabled": True}],
    })
    names = [a.name for a in cfg.apps]
    assert "socket-proxy" in names


def test_socket_proxy_deployed_before_traefik():
    """socket-proxy must appear before traefik in the deploy list."""
    cfg = _config_from_dict({
        "traefik": {"enabled": True},
        "security": {"socket_proxy": True},
        "apps": [],
    })
    names = [a.name for a in cfg.enabled_apps]
    assert names.index("socket-proxy") < names.index("traefik")


def test_socket_proxy_not_duplicated():
    cfg = _config_from_dict({
        "traefik": {"enabled": True},
        "security": {"socket_proxy": True},
        "apps": [
            {"name": "socket-proxy", "enabled": True},
            {"name": "traefik", "enabled": True},
        ],
    })
    assert [a.name for a in cfg.apps].count("socket-proxy") == 1


def test_enabled_apps_filter():
    cfg = _config_from_dict({
        "apps": [
            {"name": "jellyfin", "enabled": True},
            {"name": "radarr", "enabled": False},
        ],
    })
    enabled = [a.name for a in cfg.enabled_apps]
    assert "jellyfin" in enabled
    assert "radarr" not in enabled


def test_app_overrides():
    cfg = _config_from_dict({
        "apps": [{
            "name": "jellyfin",
            "enabled": True,
            "vars": {"hardware_accel": "vaapi"},
            "overrides": {"services": {"jellyfin": {"mem_limit": "4g"}}},
        }],
    })
    app = cfg.apps[-1]
    assert app.vars["hardware_accel"] == "vaapi"
    assert app.overrides["services"]["jellyfin"]["mem_limit"] == "4g"


def test_load_config_from_file(tmp_path: Path):
    config_file = tmp_path / "stackr.yml"
    config_file.write_text(textwrap.dedent("""
        global:
          data_dir: /opt/appdata
          timezone: America/New_York
        apps:
          - name: jellyfin
            enabled: true
    """))
    cfg = load_config(config_file)
    assert str(cfg.global_.data_dir) == "/opt/appdata"
    assert cfg.global_.timezone == "America/New_York"
