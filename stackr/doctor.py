"""Pre-flight environment health checks.

Checks run by `stackr doctor`:
- Docker daemon reachable
- Docker Compose plugin installed
- proxy Docker network exists
- socket_proxy network exists (when security.socket_proxy: true)
- State file exists and is valid JSON
- DNS provider env vars present
- .stackr.env file exists
- All enabled apps present in catalog
- Backup destination is writable (when backup.enabled: true)
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from rich.console import Console
from rich.table import Table

from stackr.config import StackrConfig
from stackr.dns_providers import get_provider
from stackr.state import DEFAULT_STATE_DIR, STATE_FILE

console = Console()

Status = Literal["ok", "warn", "fail"]


@dataclass
class DoctorCheck:
    name: str
    status: Status
    message: str


def run_doctor(
    config: StackrConfig,
    env: dict[str, str],
    config_dir: Path | None = None,
) -> bool:
    """Run all health checks and print a Rich table. Returns True if no failures."""
    checks: list[DoctorCheck] = [
        _check_docker_daemon(),
        _check_compose_plugin(),
        _check_proxy_network(),
    ]
    if config.security.socket_proxy:
        checks.append(_check_socket_proxy_network())
    checks.append(_check_state_file())
    checks.extend(_check_dns_env(config, env))
    checks.append(_check_stackr_env(config_dir or Path(".")))
    checks.append(_check_catalog_apps(config))
    if config.backup.enabled:
        checks.append(_check_backup_destination(config))

    table = Table(title="Stackr Doctor", show_header=True, header_style="bold")
    table.add_column("Check", style="bold")
    table.add_column("Status", min_width=6)
    table.add_column("Details")

    any_fail = False
    for check in checks:
        if check.status == "ok":
            status_str = "[green]OK[/green]"
        elif check.status == "warn":
            status_str = "[yellow]WARN[/yellow]"
        else:
            status_str = "[red]FAIL[/red]"
            any_fail = True
        table.add_row(check.name, status_str, check.message)

    console.print(table)

    if any_fail and config.alerts.enabled:
        from stackr.alerts import send_alert

        send_alert("Stackr doctor failed", "One or more pre-flight checks failed.", config.alerts)

    return not any_fail


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_docker_daemon() -> DoctorCheck:
    result = subprocess.run(["docker", "info"], capture_output=True)
    if result.returncode == 0:
        return DoctorCheck("Docker daemon", "ok", "Running")
    return DoctorCheck("Docker daemon", "fail", "Docker is not running or not installed")


def _check_compose_plugin() -> DoctorCheck:
    result = subprocess.run(
        ["docker", "compose", "version"], capture_output=True, text=True
    )
    if result.returncode == 0:
        version = result.stdout.strip().splitlines()[0]
        return DoctorCheck("Compose plugin", "ok", version)
    return DoctorCheck("Compose plugin", "fail", "'docker compose' plugin not found")


def _check_proxy_network() -> DoctorCheck:
    result = subprocess.run(["docker", "network", "inspect", "proxy"], capture_output=True)
    if result.returncode == 0:
        return DoctorCheck("proxy network", "ok", "Exists")
    return DoctorCheck(
        "proxy network", "warn", "Not yet created — run 'stackr deploy' to create it"
    )


def _check_socket_proxy_network() -> DoctorCheck:
    result = subprocess.run(
        ["docker", "network", "inspect", "socket_proxy"], capture_output=True
    )
    if result.returncode == 0:
        return DoctorCheck("socket_proxy network", "ok", "Exists")
    return DoctorCheck(
        "socket_proxy network", "warn", "Not yet created — run 'stackr deploy'"
    )


def _check_state_file() -> DoctorCheck:
    state_path = DEFAULT_STATE_DIR / STATE_FILE
    if not state_path.exists():
        return DoctorCheck(
            "State file", "warn", f"Not found at {state_path} (created on first deploy)"
        )
    try:
        with open(state_path) as f:
            json.load(f)
        return DoctorCheck("State file", "ok", str(state_path))
    except (json.JSONDecodeError, OSError) as exc:
        return DoctorCheck("State file", "fail", f"Corrupt or unreadable: {exc}")


def _check_dns_env(config: StackrConfig, env: dict[str, str]) -> list[DoctorCheck]:
    if not config.traefik.enabled:
        return []
    provider = get_provider(config.traefik.dns_provider)
    if provider is None:
        return [
            DoctorCheck(
                "DNS env vars",
                "warn",
                f"Provider '{config.traefik.dns_provider}' not in registry"
                " — verify env vars manually",
            )
        ]
    checks = []
    for var in provider.required_env:
        if var in env:
            checks.append(DoctorCheck(f"DNS env: {var}", "ok", "Set"))
        else:
            checks.append(
                DoctorCheck(f"DNS env: {var}", "fail", "Missing — add to .stackr.env or export")
            )
    return checks


def _check_stackr_env(config_dir: Path) -> DoctorCheck:
    env_file = config_dir / ".stackr.env"
    if env_file.exists():
        return DoctorCheck(".stackr.env", "ok", str(env_file))
    return DoctorCheck(".stackr.env", "warn", f"Not found at {env_file} — run 'stackr init'")


def _check_catalog_apps(config: StackrConfig) -> DoctorCheck:
    from stackr.catalog import Catalog

    catalog = Catalog()
    missing = [
        a.name
        for a in config.enabled_apps
        if not a.catalog_path and catalog.get(a.name) is None
    ]
    if missing:
        return DoctorCheck(
            "Catalog apps", "fail", f"Unknown app(s): {', '.join(missing)}"
        )
    return DoctorCheck(
        "Catalog apps", "ok", f"{len(config.enabled_apps)} enabled app(s) found in catalog"
    )


def _check_backup_destination(config: StackrConfig) -> DoctorCheck:
    dest = config.backup.destination
    if not dest.exists():
        return DoctorCheck(
            "Backup destination", "warn", f"{dest} does not exist — create it before backing up"
        )
    if not os.access(dest, os.W_OK):
        return DoctorCheck("Backup destination", "warn", f"{dest} is not writable")
    return DoctorCheck("Backup destination", "ok", str(dest))
