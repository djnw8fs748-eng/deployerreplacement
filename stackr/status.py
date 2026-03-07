"""Live status with drift detection."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rich.console import Console
from rich.table import Table

from stackr.deployer import COMPOSE_DIR
from stackr.state import State

console = Console()


def show_status(state: State, app_name: str | None = None) -> None:
    all_state = state.all_apps()
    compose_apps = _discover_compose_apps()

    all_names = sorted(set(all_state.keys()) | compose_apps)
    if app_name:
        all_names = [n for n in all_names if n == app_name]

    table = Table(title="Stackr App Status", show_header=True, header_style="bold")
    table.add_column("App", style="bold")
    table.add_column("State")
    table.add_column("Docker")
    table.add_column("Drift")
    table.add_column("Deployed At")

    for name in all_names:
        in_state = name in all_state
        in_compose = name in compose_apps
        docker_status = _docker_status(name) if in_compose else "—"
        app_state = all_state.get(name)

        if in_state and in_compose:
            drift = "ok"
            state_label = "[green]deployed[/green]"
        elif in_state and not in_compose:
            drift = "[yellow]missing compose[/yellow]"
            state_label = "[yellow]state only[/yellow]"
        elif not in_state and in_compose:
            drift = "[yellow]not in state[/yellow]"
            state_label = "[yellow]untracked[/yellow]"
        else:
            drift = "—"
            state_label = "[dim]unknown[/dim]"

        deployed_at = app_state.deployed_at[:19].replace("T", " ") if app_state else "—"

        table.add_row(name, state_label, docker_status, drift, deployed_at)

    console.print(table)


def _discover_compose_apps() -> set[str]:
    if not COMPOSE_DIR.exists():
        return set()
    return {d.name for d in COMPOSE_DIR.iterdir() if d.is_dir()}


def _docker_status(app_name: str) -> str:
    compose_path = COMPOSE_DIR / app_name / "docker-compose.yml"
    if not compose_path.exists():
        return "—"
    result = subprocess.run(
        ["docker", "compose", "-f", str(compose_path), "ps", "--format", "json"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return "[dim]stopped[/dim]"

    import json
    try:
        services = json.loads(result.stdout)
        if isinstance(services, list):
            states = {s.get("State", "unknown") for s in services}
        else:
            states = {services.get("State", "unknown")}
        if states == {"running"}:
            return "[green]running[/green]"
        elif "running" in states:
            return "[yellow]partial[/yellow]"
        else:
            return "[red]stopped[/red]"
    except (json.JSONDecodeError, AttributeError):
        return "[dim]unknown[/dim]"
