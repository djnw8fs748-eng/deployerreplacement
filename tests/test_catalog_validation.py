"""Catalog validation CI suite.

Five checks run for every app.yml + compose.yml.j2 pair in stackr/catalog/:

  1. Template renders to valid YAML with default vars.
  2. Rendered compose has no Traefik labels (Traefik removed from Stackr).
  3. Every host_port declared in app.yml appears in the rendered compose.
  4. Every volume path declared in app.yml appears in the rendered compose.
  5. All vars referenced in the template are declared in app.yml
     (StrictUndefined catches this at render time in check 1, but this
     asserts it explicitly so failures are readable).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from stackr.engine.catalog import BUILTIN_CATALOG, CatalogApp, _load_app
from stackr.engine.config import AppConfig, StackrConfig
from stackr.engine.renderer import render_app

_CATALOG_DIR = BUILTIN_CATALOG

_STUB_CONFIG = StackrConfig.model_validate({
    "global": {"data_dir": "/opt/appdata", "timezone": "UTC", "puid": 1000, "pgid": 1000},
    "network": {"domain": "test.com", "local_domain": "home.test.com"},
    "security": {"socket_proxy": True},
})

_ALL_APP_YMLS = sorted(_CATALOG_DIR.glob("*/*/app.yml"))


def _app_id(app_yml: Path) -> str:
    return app_yml.parent.name


def _render_app(catalog_app: CatalogApp) -> tuple[str, dict]:
    """Render an app with all defaults and return (rendered_str, parsed_dict)."""
    app_config = AppConfig(name=catalog_app.name)
    rendered = render_app(app_config, catalog_app, _STUB_CONFIG)
    parsed = yaml.safe_load(rendered)
    return rendered, parsed


@pytest.mark.parametrize("app_yml", _ALL_APP_YMLS, ids=_app_id)
def test_renders_to_valid_yaml(app_yml: Path) -> None:
    """Check 1: template renders without error and produces parseable YAML."""
    catalog_app = _load_app(app_yml)
    rendered, parsed = _render_app(catalog_app)
    assert isinstance(parsed, dict), f"{catalog_app.name}: rendered output is not a YAML mapping"
    assert "services" in parsed, f"{catalog_app.name}: rendered compose missing 'services' key"


@pytest.mark.parametrize("app_yml", _ALL_APP_YMLS, ids=_app_id)
def test_no_traefik_labels(app_yml: Path) -> None:
    """Check 2: Traefik has been removed — no Traefik labels in any compose template."""
    catalog_app = _load_app(app_yml)
    rendered, _ = _render_app(catalog_app)
    assert "traefik.enable" not in rendered, (
        f"{catalog_app.name}: rendered compose contains 'traefik.enable' — "
        "Traefik has been removed from Stackr"
    )


@pytest.mark.parametrize("app_yml", _ALL_APP_YMLS, ids=_app_id)
def test_host_ports_appear_in_rendered_compose(app_yml: Path) -> None:
    """Check 3: every host_port declared in app.yml appears in the rendered compose."""
    catalog_app = _load_app(app_yml)
    if not catalog_app.host_ports:
        return
    rendered, _ = _render_app(catalog_app)
    for port in catalog_app.host_ports:
        assert str(port) in rendered, (
            f"{catalog_app.name}: host_port {port} declared in app.yml "
            "but not found in rendered compose — add it to the 'ports:' mapping"
        )


@pytest.mark.parametrize("app_yml", _ALL_APP_YMLS, ids=_app_id)
def test_volume_paths_appear_in_rendered_compose(app_yml: Path) -> None:
    """Check 4: every volume path declared in app.yml appears in the rendered compose."""
    catalog_app = _load_app(app_yml)
    if not catalog_app.volumes:
        return
    rendered, _ = _render_app(catalog_app)
    for vol in catalog_app.volumes:
        assert vol.path in rendered, (
            f"{catalog_app.name}: volume path '{vol.path}' declared in app.yml "
            "but not found in rendered compose — verify the volume binding in the template"
        )


@pytest.mark.parametrize("app_yml", _ALL_APP_YMLS, ids=_app_id)
def test_template_vars_match_declared_vars(app_yml: Path) -> None:
    """Check 5: every vars.X reference in the template is declared in app.yml."""
    catalog_app = _load_app(app_yml)
    template_source = catalog_app.compose_template_path.read_text()
    declared_vars = set(catalog_app.vars.keys())
    referenced_vars = set(re.findall(r'\bvars\.(\w+)', template_source))
    undeclared = referenced_vars - declared_vars
    assert not undeclared, (
        f"{catalog_app.name}: template references vars not declared in app.yml: "
        f"{sorted(undeclared)} — add them to the 'vars:' section of app.yml"
    )
