"""Traefik middleware label generators.

Produces the Traefik label dicts needed to attach forward-auth middleware
to a service, based on the configured auth provider.
"""

from __future__ import annotations

from stackr.config import SecurityConfig, StackrConfig

# Middleware names by provider — must match what the provider's compose template declares
_MIDDLEWARE_NAME: dict[str, str] = {
    "authentik": "authentik@docker",
    "authelia": "authelia@docker",
}


def auth_middleware_name(security: SecurityConfig) -> str | None:
    """Return the Traefik middleware name for the configured auth provider, or None."""
    return _MIDDLEWARE_NAME.get(security.auth_provider)


def auth_middleware_labels(service: str, config: StackrConfig) -> dict[str, str]:
    """Return Traefik labels that attach the forward-auth middleware to *service*.

    Returns an empty dict if no auth provider is configured.
    """
    middleware = auth_middleware_name(config.security)
    if middleware is None:
        return {}
    return {
        f"traefik.http.routers.{service}.middlewares": middleware,
    }


def crowdsec_middleware_labels(service: str, config: StackrConfig) -> dict[str, str]:
    """Return Traefik labels that attach the CrowdSec bouncer middleware.

    Returns an empty dict if CrowdSec is not enabled.
    """
    if not config.security.crowdsec:
        return {}
    return {
        f"traefik.http.routers.{service}.middlewares": "crowdsec-bouncer@file",
    }


def combined_middleware_labels(service: str, config: StackrConfig) -> dict[str, str]:
    """Return middleware labels combining auth and CrowdSec where both are enabled."""
    middlewares: list[str] = []

    if config.security.crowdsec:
        middlewares.append("crowdsec-bouncer@file")

    auth = auth_middleware_name(config.security)
    if auth:
        middlewares.append(auth)

    if not middlewares:
        return {}

    return {
        f"traefik.http.routers.{service}.middlewares": ",".join(middlewares),
    }
