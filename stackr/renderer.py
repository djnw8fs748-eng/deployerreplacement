"""Jinja2 compose file renderer."""

from __future__ import annotations

from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from stackr.catalog import CatalogApp
from stackr.config import AppConfig, StackrConfig


def _traefik_labels(
    service: str,
    port: int,
    config: StackrConfig,
    exposure: str = "external",
) -> dict[str, str]:
    """Generate Traefik labels for a service."""
    mode = config.network.mode
    domain = config.network.domain
    local_domain = config.network.local_domain

    labels: dict[str, str] = {"traefik.enable": "true"}

    def _router(name: str, host: str, entrypoint: str, certresolver: str | None) -> None:
        labels[f"traefik.http.routers.{name}.rule"] = f"Host(`{service}.{host}`)"
        labels[f"traefik.http.routers.{name}.entrypoints"] = entrypoint
        if certresolver:
            labels[f"traefik.http.routers.{name}.tls.certresolver"] = certresolver
        labels[f"traefik.http.routers.{name}.tls"] = "true"

    labels[f"traefik.http.services.{service}.loadbalancer.server.port"] = str(port)

    if mode == "external" or (mode == "hybrid" and exposure in ("external", "hybrid")):
        _router(service, domain, "websecure", config.traefik.dns_provider)

    if mode == "internal" or (mode == "hybrid" and exposure in ("internal", "hybrid")):
        router_name = f"{service}-local" if mode == "hybrid" else service
        # Use the same DNS-challenge resolver for internal domains — DNS challenge
        # works for any domain regardless of public accessibility.
        _router(router_name, local_domain, "websecure-local", config.traefik.dns_provider)

    return labels


def render_app(
    app_config: AppConfig,
    catalog_app: CatalogApp,
    stackr_config: StackrConfig,
) -> str:
    """Render the compose template for a single app, returning YAML string."""
    template_path = catalog_app.compose_template_path
    if not template_path.exists():
        raise FileNotFoundError(f"No compose template for {catalog_app.name}: {template_path}")

    env = Environment(
        loader=FileSystemLoader([
            str(template_path.parent),
            str(template_path.parent.parent.parent / "_base"),
        ]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    # Merge catalog defaults with user-supplied vars
    resolved_vars: dict[str, Any] = {
        k: v.default for k, v in catalog_app.vars.items()
    }
    resolved_vars.update(app_config.vars)

    def traefik_labels_helper(port: int, exposure: str | None = None) -> dict[str, str]:
        return _traefik_labels(
            catalog_app.name,
            port,
            stackr_config,
            exposure or catalog_app.exposure,
        )

    ctx = {
        "global": stackr_config.global_,
        "network": stackr_config.network,
        "traefik": stackr_config.traefik,
        "security": stackr_config.security,
        "vars": resolved_vars,
        "traefik_labels": traefik_labels_helper,
        "app": catalog_app,
    }

    template = env.get_template("compose.yml.j2")
    rendered = template.render(**ctx)

    # Apply user overrides (deep-merged on top of rendered compose)
    if app_config.overrides:
        rendered = _apply_overrides(rendered, app_config.overrides)

    return rendered


def _apply_overrides(rendered_yaml: str, overrides: dict[str, Any]) -> str:
    base = yaml.safe_load(rendered_yaml) or {}
    merged = _deep_merge(base, overrides)
    return yaml.dump(merged, default_flow_style=False, allow_unicode=True)


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result
