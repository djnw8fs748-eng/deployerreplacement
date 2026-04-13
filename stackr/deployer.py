"""Docker Compose orchestration.

Deploy flow:
  validate → render → pull images → docker compose up -d → update state
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml
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
    check_image_updates: bool = False,
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
        _ensure_data_dirs(compose_content, str(config.global_.data_dir))
        compose_path = _write_compose(app_config.name, compose_content)

        # Determine whether anything has changed before pulling images so we
        # don't waste bandwidth on apps that will be skipped.
        compose_changed = state.is_changed(app_config.name, compose_content)
        if not compose_changed:
            if check_image_updates:
                from stackr import images as img
                if not img.images_changed(app_config.name, compose_content, state):
                    console.print(f"  [dim]SKIP[/dim]   {app_config.name} (unchanged)")
                    continue
                console.print(f"  [cyan]UPDATE[/cyan] {app_config.name} (new image)")
            else:
                console.print(f"  [dim]SKIP[/dim]   {app_config.name} (unchanged)")
                continue
        else:
            console.print(f"  [green]DEPLOY[/green] {app_config.name}")

        # Pull images only for apps that will actually be (re)deployed.
        if pull:
            _run_compose(compose_path, ["pull", "--quiet"])

        try:
            _run_compose(compose_path, ["up", "-d", "--remove-orphans"])
        except Exception as exc:
            if config.alerts.enabled:
                from stackr.alerts import send_alert

                send_alert(
                    f"Deploy failed: {app_config.name}",
                    str(exc),
                    config.alerts,
                )
            raise
        if pull:
            from stackr import images as img
            digests: dict[str, str] = img.collect_digests(compose_content)
            state.set_app(app_config.name, compose_content, image_digests=digests)
        else:
            existing_app = state.get_app(app_config.name)
            preserved = existing_app.image_digests if existing_app else {}
            state.set_app(app_config.name, compose_content, image_digests=preserved)
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
    _run_compose(compose_path, ["down"])
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
        console.print(f"[red]No state found for '{app_name}'. Nothing to roll back.[/red]")
        raise SystemExit(1)
    if not app_state.compose_content:
        console.print(f"[red]No stored compose content for '{app_name}'. Cannot roll back.[/red]")
        raise SystemExit(1)
    console.print(f"  [magenta]ROLLBACK[/magenta] {app_name}")
    compose_path = _write_compose(app_name, app_state.compose_content)
    _run_compose(compose_path, ["up", "-d", "--remove-orphans"])
    state.set_app(app_name, app_state.compose_content, image_digests=app_state.image_digests)
    state.save()


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


def _ensure_data_dirs(compose_content: str, data_dir: str) -> None:
    """Create host-side bind-mount directories that live under data_dir.

    Parses the rendered compose YAML and mkdir -p's any host volume paths
    that begin with data_dir so Docker doesn't error on missing directories.
    Skips paths that cannot be created (permission denied, missing ancestor)
    and prints a warning so the user can resolve it manually.
    """
    from rich.console import Console as _Console
    _console = _Console()

    data_root = Path(data_dir)

    # Attempt to create the root data directory itself first. If it doesn't
    # exist and can't be created (e.g. /opt requires root), warn and stop —
    # there's no point attempting subdirectories.
    if not data_root.exists():
        try:
            data_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _console.print(
                f"  [yellow]WARN[/yellow]  Cannot create data directory "
                f"[bold]{data_root}[/bold]: {exc.strerror}. "
                f"Run: [bold]sudo mkdir -p {data_root} && "
                f"sudo chown $USER:$USER {data_root}[/bold]"
            )
            return

    try:
        parsed = yaml.safe_load(compose_content)
    except yaml.YAMLError:
        return
    if not isinstance(parsed, dict):
        return
    services = parsed.get("services") or {}
    for service in services.values():
        if not isinstance(service, dict):
            continue
        for vol in service.get("volumes") or []:
            if not isinstance(vol, str):
                continue
            host_part = vol.split(":")[0]
            host_path = Path(host_part)
            try:
                host_path.relative_to(data_root)
            except ValueError:
                continue
            try:
                host_path.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                _console.print(
                    f"  [yellow]WARN[/yellow]  Could not create data directory "
                    f"[bold]{host_path}[/bold]: {exc.strerror}. "
                    "Create it manually or re-run with sudo."
                )


def _run_compose(
    compose_path: Path,
    args: list[str],
    capture: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    cmd = ["docker", "compose", "-f", str(compose_path), *args]
    if capture:
        return subprocess.run(cmd, check=True, capture_output=True)
    return subprocess.run(cmd, check=True)
