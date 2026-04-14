"""Tests for config loading and Pydantic validation."""

import textwrap
from pathlib import Path

from stackr.config import StackrConfig, load_config


def _config_from_dict(d: dict) -> StackrConfig:
    return StackrConfig.model_validate(d)


def test_minimal_config():
    cfg = _config_from_dict({"global": {"data_dir": "/data"}})
    assert str(cfg.global_.data_dir) == "/data"
    assert cfg.network.domain == "example.com"


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


def test_apps_none_coerced_to_empty_list():
    """apps: with no YAML value parses as None — must not raise a validation error."""
    cfg = _config_from_dict({"apps": None})
    # Auto-injection prepends nginx-proxy-manager as the default reverse proxy
    assert all(a.name == "nginx-proxy-manager" for a in cfg.apps)


def test_apps_missing_key_defaults_to_empty():
    """apps key entirely absent from config must not raise a validation error."""
    cfg = _config_from_dict({})
    assert isinstance(cfg.apps, list)


def test_no_traefik_config():
    """TraefikConfig and traefik field must not exist after removal."""
    import stackr.config as cfg
    assert not hasattr(cfg, "TraefikConfig")
    config = StackrConfig.model_validate({
        "global": {"data_dir": "/data", "timezone": "UTC", "puid": 1000, "pgid": 1000},
        "network": {"domain": "test.com", "local_domain": "home.test.com"},
        "security": {"socket_proxy": False},
    })
    assert not hasattr(config, "traefik")
    assert not hasattr(config.network, "mode")


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
