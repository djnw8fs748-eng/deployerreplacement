"""Tests for Traefik middleware label generation."""

from __future__ import annotations

from stackr.config import StackrConfig
from stackr.middleware import (
    auth_middleware_labels,
    auth_middleware_name,
    combined_middleware_labels,
    crowdsec_middleware_labels,
)


def _make_config(**kwargs: object) -> StackrConfig:
    base: dict[str, object] = {
        "global": {"data_dir": "/data"},
        "network": {"mode": "external", "domain": "test.com", "local_domain": "home.test.com"},
        "traefik": {"enabled": True, "acme_email": "a@b.com", "dns_provider": "cloudflare"},
        "security": {"socket_proxy": False, "crowdsec": False, "auth_provider": "none"},
    }
    base.update(kwargs)
    return StackrConfig.model_validate(base)


class TestAuthMiddlewareName:
    def test_authentik(self):
        config = _make_config(security={"socket_proxy": False, "auth_provider": "authentik"})
        assert auth_middleware_name(config.security) == "authentik@docker"

    def test_authelia(self):
        config = _make_config(security={"socket_proxy": False, "auth_provider": "authelia"})
        assert auth_middleware_name(config.security) == "authelia@docker"

    def test_none(self):
        config = _make_config()
        assert auth_middleware_name(config.security) is None

    def test_google_oauth(self):
        config = _make_config(
            security={"socket_proxy": False, "auth_provider": "google_oauth"}
        )
        assert auth_middleware_name(config.security) is None


class TestAuthMiddlewareLabels:
    def test_authentik_labels_contain_middleware(self):
        config = _make_config(security={"socket_proxy": False, "auth_provider": "authentik"})
        labels = auth_middleware_labels("myapp", config)
        assert "traefik.http.routers.myapp.middlewares" in labels
        assert labels["traefik.http.routers.myapp.middlewares"] == "authentik@docker"

    def test_authelia_labels_contain_middleware(self):
        config = _make_config(security={"socket_proxy": False, "auth_provider": "authelia"})
        labels = auth_middleware_labels("myapp", config)
        assert labels["traefik.http.routers.myapp.middlewares"] == "authelia@docker"

    def test_no_provider_returns_empty(self):
        config = _make_config()
        assert auth_middleware_labels("myapp", config) == {}


class TestCrowdSecMiddlewareLabels:
    def test_crowdsec_enabled(self):
        config = _make_config(
            security={"socket_proxy": False, "crowdsec": True, "auth_provider": "none"}
        )
        labels = crowdsec_middleware_labels("myapp", config)
        assert "traefik.http.routers.myapp.middlewares" in labels
        assert "crowdsec-bouncer@file" in labels["traefik.http.routers.myapp.middlewares"]

    def test_crowdsec_disabled_returns_empty(self):
        config = _make_config()
        assert crowdsec_middleware_labels("myapp", config) == {}


class TestCombinedMiddlewareLabels:
    def test_crowdsec_only(self):
        config = _make_config(
            security={"socket_proxy": False, "crowdsec": True, "auth_provider": "none"}
        )
        labels = combined_middleware_labels("svc", config)
        assert labels["traefik.http.routers.svc.middlewares"] == "crowdsec-bouncer@file"

    def test_auth_only(self):
        config = _make_config(
            security={"socket_proxy": False, "crowdsec": False, "auth_provider": "authentik"}
        )
        labels = combined_middleware_labels("svc", config)
        assert labels["traefik.http.routers.svc.middlewares"] == "authentik@docker"

    def test_both_combined(self):
        config = _make_config(
            security={"socket_proxy": False, "crowdsec": True, "auth_provider": "authentik"}
        )
        labels = combined_middleware_labels("svc", config)
        middleware_str = labels["traefik.http.routers.svc.middlewares"]
        assert "crowdsec-bouncer@file" in middleware_str
        assert "authentik@docker" in middleware_str
        # crowdsec must come first (evaluated left-to-right by Traefik)
        assert middleware_str.index("crowdsec") < middleware_str.index("authentik")

    def test_neither_returns_empty(self):
        config = _make_config()
        assert combined_middleware_labels("svc", config) == {}
