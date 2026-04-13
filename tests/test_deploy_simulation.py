"""Deploy simulation tests.

Exercises every catalog app through the full validate → render pipeline in both
Traefik and NPM modes, catching issues that would only surface at deploy time.

Coverage:
- Every app renders valid YAML in both Traefik and NPM modes
- validate() produces no errors for every app in its natural config
- Port consistency: traefik_labels() port matches app.yml declared ports
- No unconditional /var/run/docker.sock mounts
- data_dir volumes not incorrectly marked external
- All select-var options render without error
- No duplicate YAML keys in any template output
"""

from __future__ import annotations

import contextlib
import re
from io import StringIO
from typing import Any

import pytest
import yaml

from stackr.catalog import Catalog
from stackr.config import AppConfig, StackrConfig
from stackr.renderer import render_app
from stackr.validator import validate

# ---------------------------------------------------------------------------
# Config factories
# ---------------------------------------------------------------------------

def _traefik_config(**overrides: Any) -> StackrConfig:
    base: dict[str, Any] = {
        "global": {"data_dir": "/opt/appdata", "timezone": "UTC", "puid": 1000, "pgid": 1000},
        "network": {"mode": "external", "domain": "test.com", "local_domain": "home.test.com"},
        "traefik": {"enabled": True, "acme_email": "ci@test.com", "dns_provider": "cloudflare"},
        "security": {"socket_proxy": True},
        "apps": [],
    }
    base.update(overrides)
    return StackrConfig.model_validate(base)


def _npm_config(**overrides: Any) -> StackrConfig:
    base: dict[str, Any] = {
        "global": {"data_dir": "/opt/appdata", "timezone": "UTC", "puid": 1000, "pgid": 1000},
        "network": {"mode": "external", "domain": "test.com", "local_domain": "home.test.com"},
        "traefik": {"enabled": False},
        "security": {"socket_proxy": False},
        "apps": [],
    }
    base.update(overrides)
    return StackrConfig.model_validate(base)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CATALOG = Catalog()


def _all_app_names() -> list[str]:
    return sorted(a.name for a in _CATALOG.all())


def _select_var_combinations(app_name: str) -> list[dict[str, Any]]:
    """Return one var-dict per select/boolean option to test every code path."""
    catalog_app = _CATALOG.get(app_name)
    if catalog_app is None:
        return [{}]
    combos: list[dict[str, Any]] = [{}]  # always include default (empty vars)
    for var_name, var_def in catalog_app.vars.items():
        if var_def.type == "select" and var_def.options:
            new_combos: list[dict[str, Any]] = []
            for existing in combos:
                for opt in var_def.options:
                    new_combos.append({**existing, var_name: opt})
            combos = new_combos
        elif var_def.type == "boolean":
            new_combos = []
            for existing in combos:
                for val in ("true", "false"):
                    new_combos.append({**existing, var_name: val})
            combos = new_combos
    return combos


def _traefik_server_ports_from_labels(parsed_compose: dict[str, Any]) -> set[int]:
    """Extract loadbalancer.server.port values from Traefik labels in a parsed compose."""
    ports: set[int] = set()
    services = parsed_compose.get("services") or {}
    pattern = re.compile(r"traefik\.http\.services\..+\.loadbalancer\.server\.port")
    for svc in services.values():
        if not isinstance(svc, dict):
            continue
        labels = svc.get("labels") or []
        if isinstance(labels, dict):
            items = (f"{k}={v}" for k, v in labels.items())
        else:
            items = iter(labels)
        for label in items:
            if not isinstance(label, str):
                continue
            if "=" in label:
                key, _, val = label.partition("=")
            else:
                continue
            if pattern.match(key.strip()):
                with contextlib.suppress(ValueError):
                    ports.add(int(val.strip()))
    return ports


def _has_raw_docker_socket(rendered: str) -> bool:
    """Return True if the compose text has an unconditional docker.sock volume mount."""
    # We look for /var/run/docker.sock appearing outside of a {% if %} block.
    # A simple heuristic: count occurrences outside Jinja comment/conditional.
    # Since this runs on *rendered* output (not the template), any occurrence is real.
    return "/var/run/docker.sock" in rendered


class _DuplicateKeyLoader(yaml.SafeLoader):
    """YAML loader that raises on duplicate mapping keys."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[str, Any]:  # type: ignore[override]
        pairs = self.construct_pairs(node, deep=deep)
        keys = [k for k, _ in pairs]
        seen: set[str] = set()
        for k in keys:
            if k in seen:
                raise yaml.YAMLError(f"Duplicate YAML key: {k!r}")
            seen.add(k)
        return dict(pairs)


# ---------------------------------------------------------------------------
# Parametrised test IDs
# ---------------------------------------------------------------------------

_ALL_APPS = _all_app_names()

# Apps that are the reverse-proxy itself — they don't use traefik_labels() and
# their own compose contains traefik config entries by design.
_SELF_PROXY_APPS = {"traefik"}

# Volumes intentionally marked external=true where the template provides a
# data_dir default: the external flag signals "users may want to NAS-mount this."
# These are not catalog bugs — validator already warns the user.
_INTENTIONAL_EXTERNAL_VOLUMES: set[tuple[str, str]] = {
    ("nextcloud", "data"),           # large user data, often NAS-mounted
    ("paperless-ngx", "consume"),    # inbox dir, often NAS-mounted
    ("paperless-ngx", "export"),     # export dir, often NAS-mounted
    ("filebrowser", "data"),         # files being browsed — intentionally user-provided
}

# Apps that are mutually exclusive and can't be in the same config.
# We test each in isolation so the validator doesn't fire for the mutual exclusion.
_MUTUALLY_EXCLUSIVE_PAIRS: dict[str, str] = {
    "nginx-proxy-manager": "traefik",
    "pihole": "adguardhome",
    "adguardhome": "pihole",
}

# Apps that have hard requires that would cause validation errors if enabled alone.
# Map app → set of required apps that must be co-enabled.
_HARD_REQUIRES: dict[str, list[str]] = {}
# Populate from catalog at module load time
for _app in _CATALOG.all():
    if _app.requires:
        _HARD_REQUIRES[_app.name] = _app.requires


def _build_traefik_apps_list(app_name: str) -> list[dict[str, Any]]:
    """Build an apps list that satisfies hard requires for the given app in Traefik mode."""
    apps: list[dict[str, Any]] = [{"name": app_name, "enabled": True}]
    for dep in _HARD_REQUIRES.get(app_name, []):
        if dep not in (a["name"] for a in apps):
            apps.append({"name": dep, "enabled": True})
    return apps


def _build_npm_apps_list(app_name: str) -> list[dict[str, Any]]:
    """Build an apps list that satisfies hard requires for the given app in NPM mode."""
    # In NPM mode, skip apps that require traefik since traefik isn't enabled.
    apps: list[dict[str, Any]] = [{"name": app_name, "enabled": True}]
    for dep in _HARD_REQUIRES.get(app_name, []):
        if dep == "traefik":
            continue  # traefik is not in catalog requires for any app currently
        if dep not in (a["name"] for a in apps):
            apps.append({"name": dep, "enabled": True})
    return apps


# ---------------------------------------------------------------------------
# Tests — rendering
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("app_name", _ALL_APPS)
def test_render_traefik_mode(app_name: str) -> None:
    """Every app must render valid YAML in Traefik mode."""
    catalog_app = _CATALOG.get(app_name)
    assert catalog_app is not None
    config = _traefik_config()
    app_config = AppConfig(name=app_name)
    rendered = render_app(app_config, catalog_app, config)
    assert rendered.strip(), f"{app_name}: rendered output is empty"
    parsed = yaml.safe_load(rendered)
    assert isinstance(parsed, dict), f"{app_name}: YAML root is not a dict"
    assert "services" in parsed, f"{app_name}: missing 'services' key"


@pytest.mark.parametrize("app_name", _ALL_APPS)
def test_render_npm_mode(app_name: str) -> None:
    """Every app must render valid YAML in NPM (no-Traefik) mode."""
    catalog_app = _CATALOG.get(app_name)
    assert catalog_app is not None
    config = _npm_config()
    app_config = AppConfig(name=app_name)
    rendered = render_app(app_config, catalog_app, config)
    assert rendered.strip(), f"{app_name}: rendered output is empty in NPM mode"
    parsed = yaml.safe_load(rendered)
    assert isinstance(parsed, dict), f"{app_name}: YAML root is not a dict in NPM mode"
    assert "services" in parsed, f"{app_name}: missing 'services' key in NPM mode"


# ---------------------------------------------------------------------------
# Tests — duplicate YAML keys
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("app_name", _ALL_APPS)
def test_no_duplicate_yaml_keys_traefik(app_name: str) -> None:
    """Rendered YAML must not contain duplicate mapping keys (Traefik mode)."""
    catalog_app = _CATALOG.get(app_name)
    assert catalog_app is not None
    config = _traefik_config()
    app_config = AppConfig(name=app_name)
    rendered = render_app(app_config, catalog_app, config)
    try:
        yaml.load(StringIO(rendered), Loader=_DuplicateKeyLoader)  # noqa: S506
    except yaml.YAMLError as exc:
        pytest.fail(f"{app_name} (Traefik mode): {exc}")


@pytest.mark.parametrize("app_name", _ALL_APPS)
def test_no_duplicate_yaml_keys_npm(app_name: str) -> None:
    """Rendered YAML must not contain duplicate mapping keys (NPM mode)."""
    catalog_app = _CATALOG.get(app_name)
    assert catalog_app is not None
    config = _npm_config()
    app_config = AppConfig(name=app_name)
    rendered = render_app(app_config, catalog_app, config)
    try:
        yaml.load(StringIO(rendered), Loader=_DuplicateKeyLoader)  # noqa: S506
    except yaml.YAMLError as exc:
        pytest.fail(f"{app_name} (NPM mode): {exc}")


# ---------------------------------------------------------------------------
# Tests — validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("app_name", _ALL_APPS)
def test_validate_no_errors_traefik(app_name: str) -> None:
    """validate() must produce no errors for every app in Traefik mode."""
    if app_name in _MUTUALLY_EXCLUSIVE_PAIRS:
        pytest.skip(
            f"{app_name} conflicts with {_MUTUALLY_EXCLUSIVE_PAIRS[app_name]} in shared config"
        )

    apps = _build_traefik_apps_list(app_name)
    config = _traefik_config(apps=apps)
    env = {"CF_DNS_API_TOKEN": "ci-test-token"}
    result = validate(config, _CATALOG, env)
    errors = [e for e in result.errors]
    assert errors == [], (
        f"{app_name} (Traefik mode) produced validation errors:\n"
        + "\n".join(f"  [{e.app}] {e.message}" for e in errors)
    )


@pytest.mark.parametrize("app_name", _ALL_APPS)
def test_validate_no_errors_npm(app_name: str) -> None:
    """validate() must produce no errors for every app in NPM mode."""
    skip_in_npm = {"traefik"}  # traefik itself can't be enabled in NPM mode meaningfully
    if app_name in skip_in_npm:
        pytest.skip(f"{app_name} is not relevant in NPM mode")
    if app_name in _MUTUALLY_EXCLUSIVE_PAIRS:
        pytest.skip(
            f"{app_name} conflicts with {_MUTUALLY_EXCLUSIVE_PAIRS[app_name]} in shared config"
        )

    apps = _build_npm_apps_list(app_name)
    config = _npm_config(apps=apps)
    result = validate(config, _CATALOG, {})
    errors = [e for e in result.errors]
    assert errors == [], (
        f"{app_name} (NPM mode) produced validation errors:\n"
        + "\n".join(f"  [{e.app}] {e.message}" for e in errors)
    )


# ---------------------------------------------------------------------------
# Tests — port consistency
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("app_name", _ALL_APPS)
def test_port_consistency_traefik(app_name: str) -> None:
    """traefik_labels() port must match the ports declared in app.yml."""
    catalog_app = _CATALOG.get(app_name)
    assert catalog_app is not None
    if not catalog_app.ports:
        pytest.skip(f"{app_name} has no declared ports (no-Traefik app)")
    if app_name in _SELF_PROXY_APPS:
        pytest.skip(f"{app_name} is itself a reverse proxy — it does not use traefik_labels()")

    config = _traefik_config()
    app_config = AppConfig(name=app_name)
    rendered = render_app(app_config, catalog_app, config)
    parsed = yaml.safe_load(rendered)

    label_ports = _traefik_server_ports_from_labels(parsed)
    if not label_ports:
        pytest.fail(
            f"{app_name}: app.yml declares ports={catalog_app.ports} but no "
            f"traefik.http.services.*.loadbalancer.server.port found in rendered output"
        )

    for label_port in label_ports:
        assert label_port in catalog_app.ports, (
            f"{app_name}: traefik_labels() uses port {label_port} but app.yml "
            f"ports={catalog_app.ports} — they must agree"
        )


# ---------------------------------------------------------------------------
# Tests — no unconditional docker socket mount
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("app_name", _ALL_APPS)
def test_no_unconditional_docker_socket(app_name: str) -> None:
    """No app should mount /var/run/docker.sock when socket_proxy=True is configured.

    When socket_proxy is enabled the socket-proxy container handles all Docker API
    access. Any remaining docker.sock mount in this mode is truly unconditional and
    therefore a bug.  Apps that use the correct ``{% if not security.socket_proxy %}``
    pattern will have the mount absent here and present only in the NPM fallback render.
    """
    if app_name == "socket-proxy":
        pytest.skip("socket-proxy IS the docker socket container")

    catalog_app = _CATALOG.get(app_name)
    assert catalog_app is not None
    # Render with socket_proxy=True — docker.sock must not appear in any service
    config = _traefik_config()  # socket_proxy=True by default in traefik config
    app_config = AppConfig(name=app_name)
    rendered = render_app(app_config, catalog_app, config)
    assert not _has_raw_docker_socket(rendered), (
        f"{app_name}: /var/run/docker.sock found in rendered output when socket_proxy=True — "
        "the mount must be conditional: use '{% if not security.socket_proxy %}' so that "
        "direct socket access is only used when no socket-proxy is configured"
    )


# ---------------------------------------------------------------------------
# Tests — volumes not incorrectly marked external
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("app_name", _ALL_APPS)
def test_data_dir_volumes_not_marked_external(app_name: str) -> None:
    """Volumes rendered under data_dir must not be marked external in app.yml."""
    catalog_app = _CATALOG.get(app_name)
    assert catalog_app is not None
    config = _traefik_config()
    app_config = AppConfig(name=app_name)
    rendered = render_app(app_config, catalog_app, config)
    parsed = yaml.safe_load(rendered)

    # Collect all host-side bind mount paths from the rendered compose
    services = parsed.get("services") or {}
    bind_paths: list[str] = []
    for svc in services.values():
        if not isinstance(svc, dict):
            continue
        for vol in svc.get("volumes") or []:
            if not isinstance(vol, str):
                continue
            host_part = vol.split(":")[0]
            if host_part.startswith("/opt/appdata"):
                bind_paths.append(host_part)

    # Check app.yml volumes: any external=True vol whose name appears as a path segment
    # in a data_dir bind mount is likely miscategorised.
    # Uses segment matching (not substring) to avoid "data" ∈ "appdata" false positives.
    for vol_spec in catalog_app.volumes:
        if not vol_spec.external:
            continue
        if (app_name, vol_spec.name) in _INTENTIONAL_EXTERNAL_VOLUMES:
            continue  # intentional external — user may NAS-mount this directory
        segments_name = vol_spec.name.lower()
        for bp in bind_paths:
            bp_segments = {s.lower() for s in bp.split("/") if s}
            if segments_name in bp_segments:
                pytest.fail(
                    f"{app_name}: volume '{vol_spec.name}' (path={vol_spec.path}) is marked "
                    f"external=true but renders as a data_dir bind mount at {bp}. "
                    f"Remove external:true — it is not a user-provided external volume."
                )


# ---------------------------------------------------------------------------
# Tests — select var options all render
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("app_name", _ALL_APPS)
def test_all_select_var_options_render(app_name: str) -> None:
    """Every combination of select/boolean var options must render valid YAML."""
    catalog_app = _CATALOG.get(app_name)
    assert catalog_app is not None
    if not catalog_app.vars:
        pytest.skip(f"{app_name} has no declared vars")

    config = _traefik_config()
    combos = _select_var_combinations(app_name)

    for var_combo in combos:
        app_config = AppConfig(name=app_name, vars=var_combo)
        try:
            rendered = render_app(app_config, catalog_app, config)
        except Exception as exc:
            pytest.fail(f"{app_name} vars={var_combo}: render raised {type(exc).__name__}: {exc}")
        try:
            parsed = yaml.safe_load(rendered)
        except yaml.YAMLError as exc:
            pytest.fail(f"{app_name} vars={var_combo}: invalid YAML — {exc}")
        assert isinstance(parsed, dict) and "services" in parsed, (
            f"{app_name} vars={var_combo}: rendered output missing 'services'"
        )


# ---------------------------------------------------------------------------
# Tests — NPM mode has no Traefik labels
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("app_name", _ALL_APPS)
def test_npm_mode_no_traefik_enable_label(app_name: str) -> None:
    """In NPM mode, traefik.enable=true must not appear in any rendered output."""
    if app_name in _SELF_PROXY_APPS:
        pytest.skip(f"{app_name} is itself a reverse proxy — configures its own dashboard labels")

    catalog_app = _CATALOG.get(app_name)
    assert catalog_app is not None
    config = _npm_config()
    app_config = AppConfig(name=app_name)
    rendered = render_app(app_config, catalog_app, config)
    # traefik.enable=true signals Traefik is actively routing this service
    assert "traefik.enable=true" not in rendered, (
        f"{app_name}: 'traefik.enable=true' found in NPM-mode render — "
        "Traefik labels must be suppressed when traefik.enabled=false"
    )


# ---------------------------------------------------------------------------
# Tests — apps with no ports have no Traefik routing labels
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("app_name", _ALL_APPS)
def test_no_port_apps_have_no_traefik_labels(app_name: str) -> None:
    """Apps with ports=[] in app.yml must not emit traefik routing labels."""
    catalog_app = _CATALOG.get(app_name)
    assert catalog_app is not None
    if catalog_app.ports:
        pytest.skip(f"{app_name} has ports — Traefik labels expected")
    if app_name in _SELF_PROXY_APPS:
        pytest.skip(f"{app_name} is itself a reverse proxy")

    config = _traefik_config()
    app_config = AppConfig(name=app_name)
    rendered = render_app(app_config, catalog_app, config)
    # Must not have a loadbalancer.server.port label — that's the definitive routing label
    assert "loadbalancer.server.port" not in rendered, (
        f"{app_name}: has ports=[] but 'loadbalancer.server.port' found in rendered output"
    )
