"""Render smoke tests for Phase 2 security catalog apps."""

from __future__ import annotations

import yaml

from stackr.catalog import Catalog
from stackr.config import AppConfig, StackrConfig
from stackr.renderer import render_app


def _make_config(**overrides: object) -> StackrConfig:
    base: dict[str, object] = {
        "global": {"data_dir": "/opt/appdata", "timezone": "UTC", "puid": 1000, "pgid": 1000},
        "network": {"domain": "test.com", "local_domain": "home.test.com"},
        "security": {"socket_proxy": True, "crowdsec": False},
    }
    base.update(overrides)
    return StackrConfig.model_validate(base)


class TestCrowdSecRender:
    def test_renders_valid_yaml(self):
        catalog = Catalog()
        app = catalog.get("crowdsec")
        assert app is not None
        config = _make_config(security={"socket_proxy": True, "crowdsec": True})
        rendered = render_app(AppConfig(name="crowdsec"), app, config)
        parsed = yaml.safe_load(rendered)
        assert "services" in parsed
        assert "crowdsec" in parsed["services"]
        # crowdsec-bouncer sidecar removed — native Traefik plugin handles bouncing
        assert "crowdsec-bouncer" not in parsed["services"]

    def test_mounts_traefik_log_volume(self):
        catalog = Catalog()
        app = catalog.get("crowdsec")
        assert app is not None
        rendered = render_app(AppConfig(name="crowdsec"), app, _make_config())
        assert "traefik/logs" in rendered

    def test_uses_socket_proxy_network_when_enabled(self):
        catalog = Catalog()
        app = catalog.get("crowdsec")
        assert app is not None
        rendered = render_app(AppConfig(name="crowdsec"), app, _make_config())
        assert "socket_proxy" in rendered

    def test_no_socket_proxy_network_when_disabled(self):
        catalog = Catalog()
        app = catalog.get("crowdsec")
        assert app is not None
        config = _make_config(security={"socket_proxy": False, "crowdsec": False})
        rendered = render_app(AppConfig(name="crowdsec"), app, config)
        assert "socket_proxy" not in rendered


class TestValidatorSecurityChecks:
    """Integration tests for the Phase 2 validator checks."""

    def test_crowdsec_true_without_app_fails(self):
        from stackr.catalog import Catalog
        from stackr.validator import validate

        config = _make_config(
            security={"socket_proxy": False, "crowdsec": True},
        )
        result = validate(config, Catalog(), env={})
        assert any("crowdsec" in e.message for e in result.errors)

    def test_crowdsec_true_with_app_passes(self):
        from stackr.catalog import Catalog
        from stackr.validator import validate

        config = _make_config(
            security={"socket_proxy": False, "crowdsec": True},
            apps=[{"name": "crowdsec", "enabled": True}],
        )
        result = validate(config, Catalog(), env={})
        crowdsec_errors = [e for e in result.errors if "crowdsec" in e.message]
        assert crowdsec_errors == []
