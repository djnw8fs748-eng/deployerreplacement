"""Jinja2 compose file renderer."""

from __future__ import annotations

import re
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from stackr.catalog import CatalogApp
from stackr.config import AppConfig, StackrConfig


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
        # Traefik has been removed from the Stackr engine.
        # traefik_labels() always returns {} so catalog templates render without labels.
        return {}

    ctx = {
        "global": stackr_config.global_,
        "network": stackr_config.network,
        "security": stackr_config.security,
        "vars": resolved_vars,
        "traefik_labels": traefik_labels_helper,
        "app": catalog_app,
    }

    template = env.get_template("compose.yml.j2")
    rendered = template.render(**ctx)

    # traefik_labels() returns {} so the for-loop in catalog templates emits nothing,
    # leaving a bare ``labels:`` key with no value.  Docker Compose rejects null
    # labels — strip them here so deploys always produce valid compose files.
    rendered = _strip_empty_labels(rendered)

    # Apply user overrides (deep-merged on top of rendered compose)
    if app_config.overrides:
        rendered = _apply_overrides(rendered, app_config.overrides)

    return rendered


def _strip_empty_labels(rendered: str) -> str:
    """Remove ``labels:`` keys with no following content.

    A bare ``labels:`` with no indented children is null in YAML, which Docker
    Compose V2 rejects.  This arises whenever traefik_labels() returns {} and
    the template for-loop emits nothing.
    """
    # Match a labels: line at any indentation whose next non-blank line is at
    # the same or lesser indentation (i.e. no deeper-indented children follow).
    return re.sub(
        r"^( *)labels:\s*\n(?!(?:\1 |\1\t))",
        "",
        rendered,
        flags=re.MULTILINE,
    )


def _apply_overrides(rendered_yaml: str, overrides: dict[str, Any]) -> str:
    base: dict[str, Any] = yaml.safe_load(rendered_yaml) or {}
    merged = _deep_merge(base, overrides)
    return str(yaml.dump(merged, default_flow_style=False, allow_unicode=True))


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result
