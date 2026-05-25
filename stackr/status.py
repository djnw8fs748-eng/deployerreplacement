"""CLI status display using Docker SDK."""
from __future__ import annotations

from rich.console import Console
from rich.table import Table

from stackr.engine.deployer import COMPOSE_DIR
from stackr.engine.docker import get_container_status
from stackr.engine.state import StateDB

console = Console()

_STATUS_COLORS = {
    "running": "green",
    "stopped": "red",
    "degraded": "yellow",
    "unknown": "dim",
    "drift": "yellow",
}


def show_status(db: StateDB, app_name: str | None = None) -> None:
    all_state = {app.name: app for app in db.list_apps()}
    compose_apps = _discover_compose_apps()

    all_names = sorted(set(all_state.keys()) | compose_apps)
    if app_name:
        all_names = [n for n in all_names if n == app_name]

    table = Table(title="Stackr App Status", show_header=True, header_style="bold")
    table.add_column("App", style="bold")
    table.add_column("DB Status")
    table.add_column("Docker")
    table.add_column("Deployed At")

    for name in all_names:
        state = all_state.get(name)
        db_status = state.status if state else "—"
        try:
            cs = get_container_status(name)
            docker_status = cs.status
        except Exception:
            docker_status = "unknown"
        color = _STATUS_COLORS.get(docker_status, "dim")
        table.add_row(
            name,
            db_status,
            f"[{color}]{docker_status}[/{color}]",
            state.deployed_at or "—" if state else "—",
        )

    console.print(table)


def _discover_compose_apps() -> set[str]:
    """Return names of apps with a compose file in COMPOSE_DIR."""
    if not COMPOSE_DIR.exists():
        return set()
    return {p.parent.name for p in COMPOSE_DIR.glob("*/docker-compose.yml")}
