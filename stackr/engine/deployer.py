"""Deploy orchestration using StateDB and OperationResult."""
from __future__ import annotations

import hashlib
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import yaml
from rich.console import Console

from stackr.engine.catalog import Catalog, CatalogApp
from stackr.engine.config import AppConfig, StackrConfig
from stackr.engine.docker import (
    OperationResult,
    compose_down,
    compose_pull,
    compose_stop,
    compose_up,
    ensure_networks,
    get_image_digests,
)
from stackr.engine.renderer import render_app
from stackr.engine.state import AppState, DeployEvent, StateDB
from stackr.engine.validator import ValidationResult

console = Console()
COMPOSE_DIR = Path.home() / ".stackr" / "compose"


def deploy_app(
    app_name: str,
    compose_content: str,
    db: StateDB,
    compose_base_dir: Path = COMPOSE_DIR,
    *,
    pull: bool = True,
) -> OperationResult:
    """Deploy a single app. Always records result in DB."""
    compose_path = _write_compose(app_name, compose_content, compose_base_dir)

    if pull:
        pull_result = compose_pull(app_name, compose_path)
        db.record_event(_to_event(pull_result))
        if not pull_result.success:
            return pull_result

    result = compose_up(app_name, compose_path)
    db.record_event(_to_event(result))

    compose_hash = hashlib.sha256(compose_content.encode()).hexdigest()
    image_digests = (
        get_image_digests(app_name, _services(compose_content)) if result.success else {}
    )

    existing = db.get_app(app_name)
    deployed_at = datetime.now(UTC).isoformat() if result.success else (
        existing.deployed_at if existing else None
    )
    db.set_app(AppState(
        name=app_name,
        enabled=existing.enabled if existing else True,
        compose_hash=compose_hash,
        compose_yaml=compose_content,
        status="running" if result.success else "failed",
        deployed_at=deployed_at,
        last_error=None if result.success else result.error,
        image_digests=image_digests,
    ))
    return result


def stop_app(app_name: str, db: StateDB, compose_base_dir: Path = COMPOSE_DIR) -> OperationResult:
    """Stop an app's containers without removing them."""
    compose_path = _compose_path(app_name, compose_base_dir)
    result = compose_stop(app_name, compose_path)
    db.record_event(_to_event(result))
    existing = db.get_app(app_name)
    if existing and result.success:
        db.set_app(AppState(
            **{**existing.__dict__, "status": "stopped"}
        ))
    return result


def remove_app(app_name: str, db: StateDB, compose_base_dir: Path = COMPOSE_DIR) -> OperationResult:
    """Run docker compose down (no -v; volumes are preserved)."""
    compose_path = _compose_path(app_name, compose_base_dir)
    result = compose_down(app_name, compose_path)
    db.record_event(_to_event(result))
    if result.success:
        existing = db.get_app(app_name)
        if existing:
            db.set_app(AppState(**{**existing.__dict__, "status": "removed"}))
    return result


def rollback_app(
    app_name: str, db: StateDB, compose_base_dir: Path = COMPOSE_DIR
) -> OperationResult:
    """Redeploy the last stored compose content from DB."""
    existing = db.get_app(app_name)
    if existing is None or not existing.compose_yaml:
        return OperationResult(
            success=False,
            app_name=app_name,
            event_type="rollback",
            stdout="",
            stderr="No stored compose content for rollback",
            exit_code=None,
            duration_ms=0,
            command=None,
            error="No stored compose content for rollback",
        )
    return deploy_app(app_name, existing.compose_yaml, db, compose_base_dir, pull=False)


def deploy_all(
    config: StackrConfig,
    catalog: Catalog,
    validation: ValidationResult,
    db: StateDB,
    *,
    app_name: str | None = None,
    pull: bool = True,
    force: bool = False,
) -> list[OperationResult]:
    """Deploy all enabled apps (or a single app if app_name is given)."""
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

    results: list[OperationResult] = []
    for app_config in apps:
        catalog_app = _get_catalog_app(app_config, catalog)
        if catalog_app is None:
            continue

        compose_content = render_app(app_config, catalog_app, config)
        failed_dirs = _ensure_data_dirs(compose_content, str(config.global_.data_dir))
        if failed_dirs:
            paths_str = " ".join(str(p) for p in failed_dirs)
            console.print(
                f"  [red]ERROR[/red]  {app_config.name} — could not create data dirs.\n"
                f"         [bold]sudo mkdir -p {paths_str}[/bold]"
            )
            continue

        compose_hash = hashlib.sha256(compose_content.encode()).hexdigest()
        if not force and not db.is_changed(app_config.name, compose_hash):
            console.print(f"  [dim]SKIP[/dim]   {app_config.name} (unchanged)")
            continue

        console.print(f"  [cyan]DEPLOY[/cyan] {app_config.name}")
        result = deploy_app(app_config.name, compose_content, db, pull=pull)
        results.append(result)

        if result.success:
            console.print(f"  [green]OK[/green]     {app_config.name}")
        else:
            console.print(f"  [red]FAIL[/red]   {app_config.name}: {result.error}")

    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _write_compose(app_name: str, content: str, base_dir: Path = COMPOSE_DIR) -> Path:
    path = _compose_path(app_name, base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _compose_path(app_name: str, base_dir: Path = COMPOSE_DIR) -> Path:
    return base_dir / app_name / "docker-compose.yml"


def _services(compose_content: str) -> list[str]:
    try:
        data = yaml.safe_load(compose_content)
        return list((data or {}).get("services", {}).keys())
    except Exception:
        return []


def _to_event(result: OperationResult) -> DeployEvent:
    return DeployEvent(
        app_name=result.app_name,
        event_type=result.event_type,
        success=result.success,
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.exit_code,
        duration_ms=result.duration_ms,
        command=result.command,
    )


def _get_catalog_app(app_config: AppConfig, catalog: Catalog) -> CatalogApp | None:
    try:
        return catalog.get(app_config.name)
    except KeyError:
        console.print(f"  [yellow]WARN[/yellow]  {app_config.name} not in catalog — skipping")
        return None


def restart_app(app_name: str, compose_base_dir: Path = COMPOSE_DIR) -> None:
    """Restart an app's containers without full redeploy."""
    compose_path = _compose_path(app_name, compose_base_dir)
    if not compose_path.exists():
        console.print(f"[red]No compose file found for '{app_name}'.[/red]")
        raise SystemExit(1)
    console.print(f"  [cyan]RESTART[/cyan] {app_name}")
    _run_compose(compose_path, ["restart"])


def tail_logs(app_name: str, follow: bool = True, compose_base_dir: Path = COMPOSE_DIR) -> None:
    """Tail logs for an app (interactive, not captured)."""
    compose_path = _compose_path(app_name, compose_base_dir)
    if not compose_path.exists():
        console.print(f"[red]No compose file found for '{app_name}'.[/red]")
        raise SystemExit(1)
    args = ["logs"]
    if follow:
        args.append("-f")
    _run_compose(compose_path, args, capture=False)


def shell_app(
    app_name: str,
    service: str | None = None,
    shell: str = "sh",
    compose_base_dir: Path = COMPOSE_DIR,
) -> None:
    """Open an interactive shell in a running container."""
    compose_path = _compose_path(app_name, compose_base_dir)
    if not compose_path.exists():
        console.print(f"[red]No compose file found for '{app_name}'.[/red]")
        raise SystemExit(1)
    svc = service or app_name
    _run_compose(compose_path, ["exec", svc, shell], capture=False)


def _run_compose(
    compose_path: Path,
    args: list[str],
    capture: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    """Run a docker compose subcommand. Use capture=False for interactive commands."""
    cmd = ["docker", "compose", "-f", str(compose_path), *args]
    if capture:
        return subprocess.run(cmd, check=True, capture_output=True)
    return subprocess.run(cmd, check=True)


def _ensure_data_dirs(compose_content: str, data_dir: str) -> list[Path]:
    """Create host-side bind-mount directories that live under data_dir.

    Parses the rendered compose YAML and mkdir -p's any host volume paths
    that begin with data_dir. Falls back to sudo when the current user lacks
    write permission (common when data_dir is under /opt).

    Returns a list of paths that still could not be created after the sudo
    attempt (e.g. sudo not available or passwordless sudo not configured).
    The caller should skip the deploy when this is non-empty.
    """
    data_root = Path(data_dir)
    failed: list[Path] = []
    try:
        parsed = yaml.safe_load(compose_content)
    except yaml.YAMLError:
        return failed
    if not isinstance(parsed, dict):
        return failed
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
            if host_path.exists():
                continue
            try:
                host_path.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                result = subprocess.run(
                    ["sudo", "mkdir", "-p", str(host_path)],
                    capture_output=True,
                )
                if result.returncode != 0:
                    failed.append(host_path)
    return failed
