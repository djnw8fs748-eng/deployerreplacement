"""Render smoke tests for Phase 2 security catalog apps."""

from __future__ import annotations

import yaml

from stackr.catalog import Catalog
from stackr.config import AppConfig, StackrConfig
from stackr.renderer import render_app


def _make_config(**overrides: object) -> StackrConfig:
    base: dict[str, object] = {
        "global": {"data_dir": "/opt/appdata", "timezone": "UTC", "puid": 1000, "pgid": 1000},
        "network": {"mode": "external", "domain": "test.com", "local_domain": "home.test.com"},
        "traefik": {"enabled": True, "acme_email": "test@test.com", "dns_provider": "cloudflare"},
        "security": {"socket_proxy": True, "crowdsec": False, "auth_provider": "none"},
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
        assert "crowdsec-bouncer" in parsed["services"]

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


class TestAuthentikRender:
    def test_renders_valid_yaml(self):
        catalog = Catalog()
        app = catalog.get("authentik")
        assert app is not None
        rendered = render_app(AppConfig(name="authentik"), app, _make_config())
        parsed = yaml.safe_load(rendered)
        assert "services" in parsed

    def test_all_four_services_present(self):
        catalog = Catalog()
        app = catalog.get("authentik")
        assert app is not None
        rendered = render_app(AppConfig(name="authentik"), app, _make_config())
        parsed = yaml.safe_load(rendered)
        services = parsed["services"]
        assert "authentik-server" in services
        assert "authentik-worker" in services
        assert "authentik-postgres" in services
        assert "authentik-redis" in services

    def test_forward_auth_middleware_declared(self):
        catalog = Catalog()
        app = catalog.get("authentik")
        assert app is not None
        rendered = render_app(AppConfig(name="authentik"), app, _make_config())
        assert "forwardauth" in rendered
        assert "authentik" in rendered

    def test_socket_proxy_used_when_enabled(self):
        catalog = Catalog()
        app = catalog.get("authentik")
        assert app is not None
        rendered = render_app(AppConfig(name="authentik"), app, _make_config())
        assert "socket_proxy" in rendered

    def test_docker_socket_mounted_when_no_proxy(self):
        catalog = Catalog()
        app = catalog.get("authentik")
        assert app is not None
        config = _make_config(security={"socket_proxy": False, "auth_provider": "none"})
        rendered = render_app(AppConfig(name="authentik"), app, config)
        assert "/var/run/docker.sock" in rendered

    def test_custom_version_var(self):
        catalog = Catalog()
        app = catalog.get("authentik")
        assert app is not None
        app_config = AppConfig(name="authentik", vars={"version": "2024.8"})
        rendered = render_app(app_config, app, _make_config())
        assert "2024.8" in rendered


class TestAutheliaRender:
    def test_renders_valid_yaml(self):
        catalog = Catalog()
        app = catalog.get("authelia")
        assert app is not None
        rendered = render_app(AppConfig(name="authelia"), app, _make_config())
        parsed = yaml.safe_load(rendered)
        assert "services" in parsed

    def test_authelia_and_redis_services_present(self):
        catalog = Catalog()
        app = catalog.get("authelia")
        assert app is not None
        rendered = render_app(AppConfig(name="authelia"), app, _make_config())
        parsed = yaml.safe_load(rendered)
        assert "authelia" in parsed["services"]
        assert "authelia-redis" in parsed["services"]

    def test_forward_auth_middleware_declared(self):
        catalog = Catalog()
        app = catalog.get("authelia")
        assert app is not None
        rendered = render_app(AppConfig(name="authelia"), app, _make_config())
        assert "forwardauth" in rendered
        assert "authelia" in rendered

    def test_domain_in_auth_redirect(self):
        catalog = Catalog()
        app = catalog.get("authelia")
        assert app is not None
        rendered = render_app(AppConfig(name="authelia"), app, _make_config())
        assert "test.com" in rendered

    def test_internal_network_isolated(self):
        catalog = Catalog()
        app = catalog.get("authelia")
        assert app is not None
        rendered = render_app(AppConfig(name="authelia"), app, _make_config())
        parsed = yaml.safe_load(rendered)
        assert "authelia-internal" in parsed.get("networks", {})


class TestValidatorSecurityChecks:
    """Integration tests for the new Phase 2 validator checks."""

    def test_dns_provider_missing_env_fails(self):
        from stackr.catalog import Catalog
        from stackr.validator import validate

        config = _make_config(
            traefik={"enabled": True, "acme_email": "a@b.com", "dns_provider": "cloudflare"},
        )
        result = validate(config, Catalog(), env={})
        assert not result.ok
        assert any("CF_DNS_API_TOKEN" in e.message for e in result.errors)

    def test_dns_provider_env_present_passes(self):
        from stackr.catalog import Catalog
        from stackr.validator import validate

        config = _make_config(
            traefik={"enabled": True, "acme_email": "a@b.com", "dns_provider": "cloudflare"},
        )
        result = validate(config, Catalog(), env={"CF_DNS_API_TOKEN": "abc"})
        dns_errors = [e for e in result.errors if "CF_DNS_API_TOKEN" in e.message]
        assert dns_errors == []

    def test_unknown_dns_provider_warns(self):
        from stackr.catalog import Catalog
        from stackr.validator import validate

        config = _make_config(
            traefik={"enabled": True, "acme_email": "a@b.com", "dns_provider": "myprovider"},
        )
        result = validate(config, Catalog(), env={})
        assert any("myprovider" in w.message for w in result.warnings)

    def test_auth_provider_not_in_apps_fails(self):
        from stackr.catalog import Catalog
        from stackr.validator import validate

        config = _make_config(
            security={"socket_proxy": False, "auth_provider": "authentik"},
            traefik={"enabled": True, "acme_email": "a@b.com", "dns_provider": "cloudflare"},
        )
        result = validate(config, Catalog(), env={"CF_DNS_API_TOKEN": "x"})
        assert any("auth_provider" in e.message for e in result.errors)

    def test_crowdsec_true_without_app_fails(self):
        from stackr.catalog import Catalog
        from stackr.validator import validate

        config = _make_config(
            security={"socket_proxy": False, "crowdsec": True, "auth_provider": "none"},
            traefik={"enabled": True, "acme_email": "a@b.com", "dns_provider": "cloudflare"},
        )
        result = validate(config, Catalog(), env={"CF_DNS_API_TOKEN": "x"})
        assert any("crowdsec" in e.message for e in result.errors)

    def test_route53_all_vars_required(self):
        from stackr.catalog import Catalog
        from stackr.validator import validate

        config = _make_config(
            traefik={"enabled": True, "acme_email": "a@b.com", "dns_provider": "route53"},
        )
        # Only provide one of the three required vars
        result = validate(config, Catalog(), env={"AWS_ACCESS_KEY_ID": "key"})
        error_messages = " ".join(e.message for e in result.errors)
        assert "AWS_SECRET_ACCESS_KEY" in error_messages
        assert "AWS_REGION" in error_messages
