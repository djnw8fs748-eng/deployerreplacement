"""Docker Compose orchestration.

Deploy flow:
  validate → render → pull images → docker compose up -d → update state
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from rich.console import Console

from stackr.catalog import Catalog, CatalogApp
from stackr.config import AppConfig, StackrConfig
from stackr.network import ensure_networks
from stackr.renderer import render_app
from stackr.state import State
from stackr.validator import ValidationResult

console = Console()

COMPOSE_DIR = Path.home() / ".stackr" / "compose"


def deploy(
    config: StackrConfig,
    catalog: Catalog,
    validation: ValidationResult,
    state: State,
    app_name: str | None = None,
    pull: bool = True,
) -> None:
    if not validation.ok:
        console.print("[bold red]Validation failed — aborting deploy.[/bold red]")
        for err in validation.errors:
            console.print(f"  [red]ERROR[/red] {err}")
        raise SystemExit(1)

    for warn in validation.warnings:
        console.print(f"  [yellow]WARN[/yellow]  {warn}")

    ensure_networks(socket_proxy=config.security.socket_proxy)

    apps = config.enabled_apps
    if app_name:
        apps = [a for a in apps if a.name == app_name]
        if not apps:
            console.print(f"[red]App '{app_name}' not found or not enabled.[/red]")
            raise SystemExit(1)

    for app_config in apps:
        catalog_app = _get_catalog_app(app_config, catalog)
        if catalog_app is None:
            continue

        compose_content = render_app(app_config, catalog_app, config)
        compose_path = _write_compose(app_config.name, compose_content)

        if not state.is_changed(app_config.name, compose_content) and not pull:
            console.print(f"  [dim]SKIP[/dim]   {app_config.name} (unchanged)")
            continue

        console.print(f"  [green]DEPLOY[/green] {app_config.name}")

        if pull:
            _run_compose(compose_path, ["pull", "--quiet"])

        _run_compose(compose_path, ["up", "-d", "--remove-orphans"])
        state.set_app(app_config.name, compose_content)
        state.save()


def stop_app(app_name: str, state: State) -> None:
    compose_path = COMPOSE_DIR / app_name / "docker-compose.yml"
    if not compose_path.exists():
        console.print(f"[red]No compose file found for '{app_name}'.[/red]")
        raise SystemExit(1)
    console.print(f"  [yellow]STOP[/yellow]   {app_name}")
    _run_compose(compose_path, ["stop"])


def remove_app(app_name: str, state: State) -> None:
    compose_path = COMPOSE_DIR / app_name / "docker-compose.yml"
    if not compose_path.exists():
        console.print(f"[red]No compose file found for '{app_name}'.[/red]")
        raise SystemExit(1)
    console.print(f"  [red]REMOVE[/red] {app_name}")
    _run_compose(compose_path, ["down", "-v"])
    state.remove_app(app_name)
    state.save()


def restart_app(app_name: str) -> None:
    compose_path = COMPOSE_DIR / app_name / "docker-compose.yml"
    if not compose_path.exists():
        console.print(f"[red]No compose file found for '{app_name}'.[/red]")
        raise SystemExit(1)
    console.print(f"  [cyan]RESTART[/cyan] {app_name}")
    _run_compose(compose_path, ["restart"])


def tail_logs(app_name: str, follow: bool = True) -> None:
    compose_path = COMPOSE_DIR / app_name / "docker-compose.yml"
    if not compose_path.exists():
        console.print(f"[red]No compose file found for '{app_name}'.[/red]")
        raise SystemExit(1)
    args = ["logs"]
    if follow:
        args.append("-f")
    _run_compose(compose_path, args, capture=False)


def shell_app(app_name: str, service: str | None = None, shell: str = "sh") -> None:
    compose_path = COMPOSE_DIR / app_name / "docker-compose.yml"
    if not compose_path.exists():
        console.print(f"[red]No compose file found for '{app_name}'.[/red]")
        raise SystemExit(1)
    svc = service or app_name
    _run_compose(compose_path, ["exec", svc, shell], capture=False)


def rollback(
    app_name: str,
    config: StackrConfig,
    catalog: Catalog,
    state: State,
) -> None:
    app_state = state.get_app(app_name)
    if app_state is None:
        console.print(f"[red]No state found for '{app_name}'.[/red]")
        raise SystemExit(1)
    compose_path = COMPOSE_DIR / app_name / "docker-compose.yml"
    if not compose_path.exists():
        console.print(f"[red]No compose file found for '{app_name}'.[/red]")
        raise SystemExit(1)
    console.print(f"  [magenta]ROLLBACK[/magenta] {app_name}")
    _run_compose(compose_path, ["up", "-d", "--remove-orphans"])


def _get_catalog_app(
    app_config: AppConfig,
    catalog: Catalog,
) -> CatalogApp | None:
    if app_config.catalog_path:
        from stackr.catalog import _load_app
        app_yml = app_config.catalog_path / "app.yml"
        if not app_yml.exists():
            console.print(f"[red]Local catalog not found: {app_yml}[/red]")
            return None
        return _load_app(app_yml)
    return catalog.get(app_config.name)


def _write_compose(app_name: str, content: str) -> Path:
    app_dir = COMPOSE_DIR / app_name
    app_dir.mkdir(parents=True, exist_ok=True)
    path = app_dir / "docker-compose.yml"
    path.write_text(content)
    return path


def _run_compose(
    compose_path: Path,
    args: list[str],
    capture: bool = True,
) -> subprocess.CompletedProcess:  # type: ignore[type-arg]
    cmd = ["docker", "compose", "-f", str(compose_path), *args]
    if capture:
        return subprocess.run(cmd, check=True)
    else:
        return subprocess.run(cmd)
