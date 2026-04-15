"""Pre-deploy validation.

Checks run before any containers are touched:
- Unresolved ${VAR} secrets
- Port conflicts between enabled apps
- Container name conflicts
- Missing hard dependencies (requires:)
- Missing external volumes
- CrowdSec dependency check (_check_crowdsec)
- Mutually exclusive apps (pihole+adguardhome)
- VPN port conflicts (gluetun+qbittorrent when use_vpn: false)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from stackr.catalog import Catalog, CatalogApp
from stackr.config import AppConfig, StackrConfig
from stackr.secrets import find_unresolved

_VAR_RE = re.compile(r"\$\{([^}]+)\}")


@dataclass
class ValidationError:
    app: str
    message: str

    def __str__(self) -> str:
        return f"[{self.app}] {self.message}"


@dataclass
class ValidationResult:
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def error(self, app: str, msg: str) -> None:
        self.errors.append(ValidationError(app, msg))

    def warn(self, app: str, msg: str) -> None:
        self.warnings.append(ValidationError(app, msg))


def validate(
    config: StackrConfig,
    catalog: Catalog,
    env: dict[str, str],
    data_dir: Path | None = None,
) -> ValidationResult:
    result = ValidationResult()
    enabled_names = {a.name for a in config.enabled_apps}

    seen_ports: dict[int, str] = {}
    seen_names: dict[str, str] = {}

    # Global checks (independent of individual apps)
    _check_crowdsec(config, enabled_names, result)
    _check_mutually_exclusive(enabled_names, result)
    _check_vpn_port_conflicts(config, enabled_names, result)

    for app_config in config.enabled_apps:
        catalog_app = _resolve_catalog(app_config, catalog, result)
        if catalog_app is None:
            continue

        _check_secrets(app_config, env, result)
        _check_dependencies(app_config, catalog_app, enabled_names, config, result)
        _check_ports(app_config, catalog_app, seen_ports, result)
        _check_container_name(app_config, seen_names, result)
        _check_external_volumes(app_config, catalog_app, data_dir, result)

    return result


def _check_crowdsec(
    config: StackrConfig,
    enabled_names: set[str],
    result: ValidationResult,
) -> None:
    """crowdsec: true requires the crowdsec app to be enabled."""
    if config.security.crowdsec and "crowdsec" not in enabled_names:
        result.errors.append(
            ValidationError(
                app="crowdsec",
                message="security.crowdsec is true but 'crowdsec' is not in apps",
            )
        )


# Pairs of apps that bind the same host ports and cannot both be enabled.
_MUTUALLY_EXCLUSIVE: list[tuple[str, str, str]] = [
    ("pihole", "adguardhome", "both bind host port 53 (DNS)"),
]


def _check_mutually_exclusive(
    enabled_names: set[str],
    result: ValidationResult,
) -> None:
    """Error when two apps that share host ports are both enabled."""
    for app_a, app_b, reason in _MUTUALLY_EXCLUSIVE:
        if app_a in enabled_names and app_b in enabled_names:
            result.error(
                app_a,
                f"'{app_a}' and '{app_b}' cannot both be enabled — {reason}. "
                f"Disable one of them.",
            )


def _check_vpn_port_conflicts(
    config: StackrConfig,
    enabled_names: set[str],
    result: ValidationResult,
) -> None:
    """Check for port conflicts between gluetun and apps that can route through it.

    Gluetun always binds port 6881 (qBittorrent's torrent port). When qBittorrent
    is also enabled but use_vpn is false, both containers try to bind 6881 on the
    host, causing a runtime conflict.
    """
    if "gluetun" not in enabled_names or "qbittorrent" not in enabled_names:
        return
    qbt_cfg = next((a for a in config.apps if a.name == "qbittorrent"), None)
    use_vpn = bool(qbt_cfg.vars.get("use_vpn", False)) if qbt_cfg else False
    if not use_vpn:
        result.error(
            "qbittorrent",
            "Port conflict: gluetun and qbittorrent both bind port 6881. "
            "Set use_vpn: true on qbittorrent to route its traffic through "
            "gluetun (recommended), or disable gluetun.",
        )


def _resolve_catalog(
    app_config: AppConfig,
    catalog: Catalog,
    result: ValidationResult,
) -> CatalogApp | None:
    if app_config.catalog_path:
        from stackr.catalog import _load_app

        app_yml = app_config.catalog_path / "app.yml"
        if not app_yml.exists():
            result.error(app_config.name, f"Local catalog app.yml not found: {app_yml}")
            return None
        return _load_app(app_yml)
    catalog_app = catalog.get(app_config.name)
    if catalog_app is None:
        result.error(app_config.name, f"App '{app_config.name}' not found in catalog.")
    return catalog_app


def _check_secrets(
    app_config: AppConfig,
    env: dict[str, str],
    result: ValidationResult,
) -> None:
    # Check app-level vars for ${VAR} references
    for k, v in app_config.vars.items():
        if isinstance(v, str):
            for u in find_unresolved(v, env):
                result.error(
                    app_config.name,
                    f"Unresolved secret: ${{{u}}} (in apps[{app_config.name}].vars.{k})",
                )


def _check_dependencies(
    app_config: AppConfig,
    catalog_app: CatalogApp,
    enabled_names: set[str],
    config: StackrConfig,
    result: ValidationResult,
) -> None:
    for dep in catalog_app.requires:
        if dep not in enabled_names:
            result.error(
                app_config.name,
                f"Missing hard dependency: '{dep}' must be enabled"
                " (add it to apps: in stackr.yml).",
            )
    for dep in catalog_app.suggests:
        if dep not in enabled_names:
            result.warn(
                app_config.name,
                f"Suggested app '{dep}' is not enabled.",
            )


def _check_container_name(
    app_config: AppConfig,
    seen_names: dict[str, str],
    result: ValidationResult,
) -> None:
    # By catalog convention, container_name equals the app name.
    # Detect duplicate names across enabled apps.
    name = app_config.name
    if name in seen_names:
        result.error(
            app_config.name,
            f"Container name '{name}' conflicts with app '{seen_names[name]}'. "
            "Each app must have a unique name.",
        )
    else:
        seen_names[name] = app_config.name


def _check_ports(
    app_config: AppConfig,
    catalog_app: CatalogApp,
    seen_ports: dict[int, str],
    result: ValidationResult,
) -> None:
    # Only check host_ports — ports are Traefik-proxied container ports and can be shared.
    for port in catalog_app.host_ports:
        if port in seen_ports:
            result.error(
                app_config.name,
                f"Port {port} conflicts with app '{seen_ports[port]}'.",
            )
        else:
            seen_ports[port] = app_config.name


def _check_external_volumes(
    app_config: AppConfig,
    catalog_app: CatalogApp,
    data_dir: Path | None,
    result: ValidationResult,
) -> None:
    if data_dir is None:
        return
    for vol in catalog_app.volumes:
        if vol.external:
            # External volumes should be declared; we warn but don't error
            # since paths are user-defined and may be mounted at runtime
            result.warn(
                app_config.name,
                f"Volume '{vol.name}' is marked external — ensure it is mounted before deploying.",
            )
