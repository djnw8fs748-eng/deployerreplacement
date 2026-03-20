"""Pre-deploy validation.

Checks run before any containers are touched:
- Unresolved ${VAR} secrets
- DNS provider env vars present for the configured provider
- Port conflicts between enabled apps
- Container name conflicts
- Missing hard dependencies (requires:)
- Missing external volumes
- Auth provider dependency (authentik/authelia must be enabled if configured)
- CrowdSec dependency (crowdsec must be enabled if security.crowdsec: true)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from stackr.catalog import Catalog, CatalogApp
from stackr.config import AppConfig, StackrConfig
from stackr.dns_providers import get_provider
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
    _check_dns_provider(config, env, result)
    _check_security_stack(config, enabled_names, result)

    for app_config in config.enabled_apps:
        catalog_app = _resolve_catalog(app_config, catalog, result)
        if catalog_app is None:
            continue

        _check_secrets(app_config, config, env, result)
        _check_dependencies(app_config, catalog_app, enabled_names, result)
        _check_ports(app_config, catalog_app, seen_ports, result)
        _check_container_name(app_config, seen_names, result)
        _check_external_volumes(app_config, catalog_app, data_dir, result)

    return result


def _check_dns_provider(
    config: StackrConfig,
    env: dict[str, str],
    result: ValidationResult,
) -> None:
    """Validate that all required env vars for the configured DNS provider are present."""
    if not config.traefik.enabled:
        return
    provider = get_provider(config.traefik.dns_provider)
    if provider is None:
        result.warn(
            "traefik",
            f"DNS provider '{config.traefik.dns_provider}' is not in the provider registry. "
            "Ensure required env vars are set manually.",
        )
        return
    for var in provider.required_env:
        if var not in env:
            result.error(
                "traefik",
                f"DNS provider '{provider.display_name}' requires env var '{var}' "
                f"(set it in .stackr.env or export it in your shell).",
            )


def _check_security_stack(
    config: StackrConfig,
    enabled_names: set[str],
    result: ValidationResult,
) -> None:
    """Validate that security stack components are consistent."""
    # Auth provider must be enabled as an app when configured
    provider = config.security.auth_provider
    if provider not in ("none", "google_oauth") and provider not in enabled_names:
        result.error(
            "security",
            f"auth_provider is set to '{provider}' but '{provider}' is not in apps. "
            f"Add it or set auth_provider: none.",
        )

    # CrowdSec must be enabled as an app when crowdsec: true
    if config.security.crowdsec and "crowdsec" not in enabled_names:
        result.error(
            "security",
            "security.crowdsec is true but 'crowdsec' is not in apps. "
            "Add it or set crowdsec: false.",
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
    config: StackrConfig,
    env: dict[str, str],
    result: ValidationResult,
) -> None:
    # Check traefik dns_provider_env values
    for key, val in config.traefik.dns_provider_env.items():
        unresolved = find_unresolved(val, env)
        for u in unresolved:
            result.error(
                "traefik",
                f"Unresolved secret: ${{{u}}} (in traefik.dns_provider_env.{key})",
            )

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
