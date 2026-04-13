"""Stackr CLI — powered by Typer."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
import yaml
from rich.console import Console
from rich.table import Table

from stackr.catalog import Catalog
from stackr.config import StackrConfig, load_config
from stackr.secrets import build_env
from stackr.state import State


def _version_callback(value: bool) -> None:
    if value:
        from stackr import __version__

        typer.echo(f"stackr {__version__}")
        raise typer.Exit()


app = typer.Typer(
    name="stackr",
    help="A declarative, composable homelab deployment tool.",
    no_args_is_help=True,
)


@app.callback()
def _main(
    version: Annotated[
        bool,
        typer.Option("--version", "-V", callback=_version_callback, is_eager=True,
                     help="Show version and exit."),
    ] = False,
) -> None:
    pass
catalog_app = typer.Typer(help="Manage the app catalog.")
app.add_typer(catalog_app, name="catalog")

console = Console()

_DEFAULT_CONFIG = Path("stackr.yml")


def _load(config_path: Path) -> tuple[StackrConfig, Catalog, dict[str, str], State]:
    if not config_path.exists():
        console.print(f"[red]Config not found: {config_path}[/red]")
        console.print("Run [bold]stackr init[/bold] to create one.")
        raise typer.Exit(1)

    config = load_config(config_path)
    catalog = Catalog()
    env = build_env(config_path.parent)
    state = State()
    return config, catalog, env, state


# ---------------------------------------------------------------------------
# stackr init
# ---------------------------------------------------------------------------

@app.command()
def init(
    output: Annotated[
        Path, typer.Option("--output", "-o", help="Output config file path")
    ] = _DEFAULT_CONFIG,
) -> None:
    """Interactive setup wizard — generates stackr.yml and .stackr.env."""
    from stackr.secrets import init_env_file

    console.print("[bold green]Stackr Setup Wizard[/bold green]\n")

    data_dir = typer.prompt("Data directory", default="/opt/appdata")
    timezone = typer.prompt("Timezone", default="UTC")
    puid = typer.prompt("PUID", default="1000")
    pgid = typer.prompt("PGID", default="1000")
    domain = typer.prompt("Public domain (e.g. example.com)", default="example.com")
    local_domain = typer.prompt("Local domain (e.g. home.example.com)", default=f"home.{domain}")
    mode = typer.prompt("Network mode", default="external", show_choices=True,
                        prompt_suffix=" [external/internal/hybrid]: ")

    # Proxy choice: nginx-proxy-manager (default) or traefik
    proxy = typer.prompt(
        "Reverse proxy",
        default="nginx-proxy-manager",
        prompt_suffix=" [nginx-proxy-manager/traefik]: ",
    ).strip().lower()
    use_traefik = proxy == "traefik"

    # Traefik-specific settings — only prompted when traefik is chosen
    acme_email = ""
    dns_provider = ""
    dns_provider_env: dict[str, str] = {}
    if use_traefik:
        acme_email = typer.prompt("ACME email for Let's Encrypt certs", default="")
        from stackr.dns_providers import list_providers, required_env_vars
        provider_names = ", ".join(list_providers())
        dns_provider = typer.prompt(f"DNS provider ({provider_names}, or custom)", default="")

        # Build dns_provider_env from the registry; for unknown/custom providers
        # generate a generic placeholder so the user knows to fill it in.
        env_vars = required_env_vars(dns_provider)
        if env_vars:
            dns_provider_env = {v: f"${{{v}}}" for v in env_vars}
        elif dns_provider:
            key = f"{dns_provider.upper()}_API_TOKEN"
            dns_provider_env = {key: f"${{{key}}}"}

    # Build the header config (everything except apps)
    header = {
        "global": {
            "data_dir": data_dir,
            "timezone": timezone,
            "puid": int(puid),
            "pgid": int(pgid),
        },
        "network": {
            "mode": mode,
            "domain": domain,
            "local_domain": local_domain,
        },
        "traefik": {
            "enabled": use_traefik,
            "acme_email": acme_email,
            "dns_provider": dns_provider,
            "dns_provider_env": dns_provider_env,
        },
        "security": {
            "socket_proxy": use_traefik,  # socket-proxy is only needed with traefik
            "crowdsec": False,
            "auth_provider": "none",
        },
        "backup": {
            "enabled": False,
            "destination": "/mnt/backup",
            "schedule": "0 2 * * *",
        },
    }

    # Collect all catalog apps grouped by category.
    # nginx-proxy-manager and portainer are enabled by default; everything else is off.
    # When the user chose traefik, traefik replaces nginx-proxy-manager.
    _DEFAULT_ENABLED = ({"traefik", "portainer"} if use_traefik
                        else {"nginx-proxy-manager", "portainer"})
    catalog = Catalog()
    apps_by_category: dict[str, list[str]] = {}
    for cat_app in sorted(catalog.all(), key=lambda a: (a.category, a.name)):
        apps_by_category.setdefault(cat_app.category, []).append(cat_app.name)

    # Write config file manually so we can insert category comments in the apps block.
    with open(output, "w") as f:
        f.write(yaml.dump(header, default_flow_style=False, allow_unicode=True, sort_keys=False))
        f.write("\napps:\n")
        for category, names in sorted(apps_by_category.items()):
            f.write(f"\n  # --- {category} ---\n")
            for name in names:
                enabled = name in _DEFAULT_ENABLED
                f.write(f"  - name: {name}\n")
                f.write(f"    enabled: {'true' if enabled else 'false'}\n")

    config_dir = output.parent
    env_file = init_env_file(config_dir)

    # Add .stackr.env to .gitignore
    gitignore = config_dir / ".gitignore"
    ignore_entry = ".stackr.env\n"
    if gitignore.exists():
        if ignore_entry.strip() not in gitignore.read_text():
            with open(gitignore, "a") as f:
                f.write(ignore_entry)
    else:
        gitignore.write_text(ignore_entry)

    proxy_name = "traefik" if use_traefik else "nginx-proxy-manager"
    total = sum(len(v) for v in apps_by_category.values())
    console.print(f"\n[green]Config written to[/green] {output}")
    console.print(f"  {total} apps listed — {proxy_name} and portainer enabled by default.")
    console.print(f"[green]Secrets file:[/green]    {env_file}  (gitignored)")
    console.print("\nNext steps:")
    console.print("  1. Run [bold]stackr ui[/bold] to toggle apps on/off interactively")
    console.print("     or edit [bold]stackr.yml[/bold] directly")
    if use_traefik:
        console.print("  2. Add your DNS API token to [bold].stackr.env[/bold]")
    else:
        console.print("  2. After deploying, open [bold]http://<host>:81[/bold] to configure")
        console.print("     Nginx Proxy Manager (default login: admin@example.com / changeme)")
    console.print("  3. Run [bold]stackr validate[/bold] to check your config")
    console.print("  4. Run [bold]stackr deploy[/bold] to start everything")


# ---------------------------------------------------------------------------
# stackr validate
# ---------------------------------------------------------------------------

@app.command()
def validate(
    config_path: Annotated[Path, typer.Option("--config", "-c")] = _DEFAULT_CONFIG,
) -> None:
    """Validate stackr.yml without deploying."""
    from stackr.validator import validate as run_validate

    config, catalog, env, _ = _load(config_path)
    result = run_validate(config, catalog, env, data_dir=Path(str(config.global_.data_dir)))

    if result.warnings:
        for w in result.warnings:
            console.print(f"  [yellow]WARN[/yellow]  {w}")

    if result.ok:
        console.print("[green]Validation passed.[/green]")
    else:
        for e in result.errors:
            console.print(f"  [red]ERROR[/red] {e}")
        console.print(f"\n[red]Validation failed with {len(result.errors)} error(s).[/red]")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# stackr render
# ---------------------------------------------------------------------------

@app.command()
def render(
    app_name: Annotated[str, typer.Argument(help="App name to render")],
    config_path: Annotated[Path, typer.Option("--config", "-c")] = _DEFAULT_CONFIG,
) -> None:
    """Print the generated compose YAML for an app (for debugging)."""
    from stackr.renderer import render_app

    config, catalog, _, _ = _load(config_path)

    app_config = next((a for a in config.enabled_apps if a.name == app_name), None)
    if app_config is None:
        console.print(f"[red]App '{app_name}' not found or not enabled.[/red]")
        raise typer.Exit(1)

    catalog_entry = catalog.get(app_name)
    if catalog_entry is None:
        console.print(f"[red]App '{app_name}' not found in catalog.[/red]")
        raise typer.Exit(1)

    rendered = render_app(app_config, catalog_entry, config)
    console.print(rendered)


# ---------------------------------------------------------------------------
# stackr plan
# ---------------------------------------------------------------------------

@app.command()
def plan(
    config_path: Annotated[Path, typer.Option("--config", "-c")] = _DEFAULT_CONFIG,
) -> None:
    """Show what would change vs. current deployed state (dry run)."""
    from stackr.renderer import render_app

    config, catalog, env, state = _load(config_path)

    table = Table(title="Deploy Plan", show_header=True, header_style="bold")
    table.add_column("App", style="bold")
    table.add_column("Action")
    table.add_column("Reason")

    for app_config in config.enabled_apps:
        catalog_entry = catalog.get(app_config.name)
        if catalog_entry is None:
            table.add_row(app_config.name, "[red]ERROR[/red]", "Not in catalog")
            continue

        try:
            rendered = render_app(app_config, catalog_entry, config)
        except Exception as exc:
            table.add_row(app_config.name, "[red]ERROR[/red]", str(exc))
            continue

        if state.is_changed(app_config.name, rendered):
            app_state = state.get_app(app_config.name)
            reason = "new app" if app_state is None else "compose changed"
            table.add_row(app_config.name, "[green]deploy[/green]", reason)
        else:
            table.add_row(app_config.name, "[dim]no-op[/dim]", "unchanged")

    console.print(table)


# ---------------------------------------------------------------------------
# stackr deploy
# ---------------------------------------------------------------------------

@app.command()
def deploy(
    app_name: Annotated[str | None, typer.Argument(help="Deploy a single app")] = None,
    config_path: Annotated[Path, typer.Option("--config", "-c")] = _DEFAULT_CONFIG,
    skip_pull: Annotated[bool, typer.Option("--skip-pull", help="Do not pull images")] = False,
) -> None:
    """Deploy all enabled apps (or a single app)."""
    from stackr.deployer import deploy as run_deploy
    from stackr.validator import validate as run_validate

    config, catalog, env, state = _load(config_path)
    result = run_validate(config, catalog, env, data_dir=Path(str(config.global_.data_dir)))

    run_deploy(config, catalog, result, state, app_name=app_name, pull=not skip_pull)
    console.print("[green]Done.[/green]")


# ---------------------------------------------------------------------------
# stackr stop / restart / remove
# ---------------------------------------------------------------------------

@app.command()
def stop(
    app_name: Annotated[str, typer.Argument()],
    config_path: Annotated[Path, typer.Option("--config", "-c")] = _DEFAULT_CONFIG,
) -> None:
    """Stop an app."""
    from stackr.deployer import stop_app
    _, _, _, state = _load(config_path)
    stop_app(app_name, state)


@app.command()
def restart(
    app_name: Annotated[str, typer.Argument()],
    config_path: Annotated[Path, typer.Option("--config", "-c")] = _DEFAULT_CONFIG,
) -> None:
    """Restart an app without full redeploy."""
    from stackr.deployer import restart_app
    _load(config_path)
    restart_app(app_name)


@app.command()
def remove(
    app_name: Annotated[str, typer.Argument()],
    config_path: Annotated[Path, typer.Option("--config", "-c")] = _DEFAULT_CONFIG,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
) -> None:
    """Remove an app and its containers."""
    from stackr.deployer import remove_app
    _, _, _, state = _load(config_path)
    if not yes:
        typer.confirm(f"Remove '{app_name}' and its containers?", abort=True)
    remove_app(app_name, state)


# ---------------------------------------------------------------------------
# stackr rollback
# ---------------------------------------------------------------------------

@app.command()
def rollback(
    app_name: Annotated[str, typer.Argument()],
    config_path: Annotated[Path, typer.Option("--config", "-c")] = _DEFAULT_CONFIG,
) -> None:
    """Redeploy the last known-good compose for an app."""
    from stackr.deployer import rollback as run_rollback
    config, catalog, _, state = _load(config_path)
    run_rollback(app_name, config, catalog, state)


# ---------------------------------------------------------------------------
# stackr status
# ---------------------------------------------------------------------------

@app.command()
def status(
    app_name: Annotated[str | None, typer.Argument()] = None,
    config_path: Annotated[Path, typer.Option("--config", "-c")] = _DEFAULT_CONFIG,
) -> None:
    """Show running/stopped/drifted status of all apps."""
    from stackr.status import show_status
    _, _, _, state = _load(config_path)
    show_status(state, app_name=app_name)


# ---------------------------------------------------------------------------
# stackr logs / shell
# ---------------------------------------------------------------------------

@app.command()
def logs(
    app_name: Annotated[str, typer.Argument()],
    follow: Annotated[bool, typer.Option("--follow", "-f")] = True,
    config_path: Annotated[Path, typer.Option("--config", "-c")] = _DEFAULT_CONFIG,
) -> None:
    """Tail logs for an app."""
    from stackr.deployer import tail_logs
    _load(config_path)
    tail_logs(app_name, follow=follow)


@app.command()
def shell(
    app_name: Annotated[str, typer.Argument()],
    service: Annotated[str | None, typer.Option("--service", "-s")] = None,
    sh: Annotated[str, typer.Option("--shell")] = "sh",
    config_path: Annotated[Path, typer.Option("--config", "-c")] = _DEFAULT_CONFIG,
) -> None:
    """Open an interactive shell in a running app container."""
    from stackr.deployer import shell_app
    _load(config_path)
    shell_app(app_name, service=service, shell=sh)


# ---------------------------------------------------------------------------
# stackr list / search
# ---------------------------------------------------------------------------

@app.command(name="list")
def list_apps(
    category: Annotated[str | None, typer.Option("--category", "-c")] = None,
) -> None:
    """List available apps in the catalog."""
    from stackr.catalog import Catalog
    catalog = Catalog()

    apps = catalog.by_category(category) if category else catalog.all()

    table = Table(title="App Catalog", show_header=True, header_style="bold")
    table.add_column("Name", style="bold")
    table.add_column("Category")
    table.add_column("Description")
    table.add_column("Ports")

    for a in sorted(apps, key=lambda x: (x.category, x.name)):
        table.add_row(
            a.name,
            a.category,
            a.description[:60] + ("…" if len(a.description) > 60 else ""),
            ", ".join(str(p) for p in a.ports) or "—",
        )

    console.print(table)


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Search term")],
) -> None:
    """Search the app catalog."""
    from stackr.catalog import Catalog
    catalog = Catalog()
    results = catalog.search(query)

    if not results:
        console.print(f"No apps matching '{query}'.")
        return

    for a in results:
        console.print(f"[bold]{a.name}[/bold]  ({a.category})  — {a.description}")


# ---------------------------------------------------------------------------
# stackr update
# ---------------------------------------------------------------------------

@app.command()
def update(
    config_path: Annotated[Path, typer.Option("--config", "-c")] = _DEFAULT_CONFIG,
) -> None:
    """Pull latest images and redeploy apps with changes (including upstream image updates)."""
    from stackr.deployer import deploy as run_deploy
    from stackr.validator import validate as run_validate

    config, catalog, env, state = _load(config_path)
    result = run_validate(config, catalog, env, data_dir=Path(str(config.global_.data_dir)))
    run_deploy(config, catalog, result, state, pull=True, check_image_updates=True)
    console.print("[green]Update complete.[/green]")


# ---------------------------------------------------------------------------
# stackr backup / restore
# ---------------------------------------------------------------------------

@app.command()
def backup(
    config_path: Annotated[Path, typer.Option("--config", "-c")] = _DEFAULT_CONFIG,
) -> None:
    """Run a backup now."""
    from stackr.backup import backup as run_backup
    from stackr.state import DEFAULT_STATE_DIR

    config, _, env, _ = _load(config_path)
    try:
        run_backup(
            destination=str(config.backup.destination),
            data_dir=config.global_.data_dir,
            state_dir=DEFAULT_STATE_DIR,
            config_dir=config_path.parent,
            env=env,
        )
    except RuntimeError as exc:
        console.print(f"[red]Backup failed: {exc}[/red]")
        raise typer.Exit(1) from exc


@app.command()
def restore(
    snapshot: Annotated[str, typer.Argument(help="Snapshot ID to restore (e.g. 'latest')")],
    config_path: Annotated[Path, typer.Option("--config", "-c")] = _DEFAULT_CONFIG,
    target: Annotated[Path | None, typer.Option("--target", "-t")] = None,
) -> None:
    """Restore from a backup snapshot."""
    from stackr.backup import restore as run_restore

    config, _, env, _ = _load(config_path)
    try:
        run_restore(
            snapshot=snapshot,
            destination=str(config.backup.destination),
            target=target or config.global_.data_dir,
            config_dir=config_path.parent,
            env=env,
        )
    except RuntimeError as exc:
        console.print(f"[red]Restore failed: {exc}[/red]")
        raise typer.Exit(1) from exc


@app.command()
def snapshots(
    config_path: Annotated[Path, typer.Option("--config", "-c")] = _DEFAULT_CONFIG,
) -> None:
    """List available backup snapshots."""
    from stackr.backup import list_snapshots

    config, _, env, _ = _load(config_path)
    try:
        snaps = list_snapshots(str(config.backup.destination), config_path.parent, env)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    if not snaps:
        console.print("No snapshots found.")
        return

    table = Table(title="Backup Snapshots", show_header=True, header_style="bold")
    table.add_column("ID", style="bold")
    table.add_column("Time")
    table.add_column("Hostname")
    table.add_column("Paths")

    for snap in snaps:
        snap_id = str(snap.get("short_id", snap.get("id", "")))[:8]
        time_str = str(snap.get("time", ""))[:19].replace("T", " ")
        hostname = str(snap.get("hostname", ""))
        paths = ", ".join(str(p) for p in snap.get("paths", []))
        table.add_row(snap_id, time_str, hostname, paths)

    console.print(table)


# ---------------------------------------------------------------------------
# stackr migrate
# ---------------------------------------------------------------------------

@app.command()
def migrate(
    from_tool: Annotated[str, typer.Option("--from")] = "deployrr",
    input_file: Annotated[Path | None, typer.Option("--input", "-i")] = None,
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("stackr.yml"),
) -> None:
    """Generate stackr.yml from a Deployrr app list."""
    from stackr.catalog import Catalog
    from stackr.migrate import migrate_from_deployrr, write_stackr_yml

    if from_tool != "deployrr":
        console.print(f"[red]Unknown source '{from_tool}'. Only 'deployrr' is supported.[/red]")
        raise typer.Exit(1)

    if input_file:
        app_names = [n for n in input_file.read_text().splitlines() if n.strip()]
    else:
        console.print("Enter Deployrr app names (one per line, empty line to finish):")
        app_names = []
        while True:
            name = typer.prompt("", prompt_suffix="")
            if not name.strip():
                break
            app_names.append(name.strip())

    catalog = Catalog()
    catalog_names = {a.name for a in catalog.all()}
    mapped, unmapped = migrate_from_deployrr(app_names, catalog_names)

    write_stackr_yml(output, mapped)
    console.print(f"[green]Written to {output}[/green]  ({len(mapped)} apps)")

    if unmapped:
        console.print(f"\n[yellow]Could not map {len(unmapped)} app(s) — check manually:[/yellow]")
        for name in unmapped:
            console.print(f"  • {name}")


# ---------------------------------------------------------------------------
# stackr doctor
# ---------------------------------------------------------------------------

@app.command()
def doctor(
    config_path: Annotated[Path, typer.Option("--config", "-c")] = _DEFAULT_CONFIG,
) -> None:
    """Check environment health: Docker, networks, secrets, and catalog consistency."""
    from stackr.doctor import run_doctor

    if not config_path.exists():
        console.print(f"[red]Config not found: {config_path}[/red]")
        console.print("Run [bold]stackr init[/bold] to create one.")
        raise typer.Exit(1)

    config = load_config(config_path)
    env = build_env(config_path.parent)
    ok = run_doctor(config, env, config_dir=config_path.parent)
    if not ok:
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# stackr mount / umount
# ---------------------------------------------------------------------------


@app.command()
def mount(
    config_path: Annotated[Path, typer.Option("--config", "-c")] = _DEFAULT_CONFIG,
) -> None:
    """Mount all remote shares configured under `mounts:` in stackr.yml."""
    from stackr.mounts import mount_all

    config, _, _, _ = _load(config_path)
    if not config.mounts:
        console.print("[yellow]No mounts configured.[/yellow]")
        return
    results = mount_all(config.mounts)  # type: ignore[arg-type]
    failures = [r for r in results if not r.ok]
    if failures:
        raise typer.Exit(1)


@app.command()
def umount(
    config_path: Annotated[Path, typer.Option("--config", "-c")] = _DEFAULT_CONFIG,
) -> None:
    """Unmount all remote shares configured under `mounts:` in stackr.yml."""
    from stackr.mounts import umount_all

    config, _, _, _ = _load(config_path)
    if not config.mounts:
        console.print("[yellow]No mounts configured.[/yellow]")
        return
    results = umount_all(config.mounts)  # type: ignore[arg-type]
    failures = [r for r in results if not r.ok]
    if failures:
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# stackr web
# ---------------------------------------------------------------------------


@app.command()
def web(
    config_path: Annotated[Path, typer.Option("--config", "-c")] = _DEFAULT_CONFIG,
    host: Annotated[str, typer.Option("--host", "-H")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", "-p")] = 8000,
) -> None:
    """Launch the web UI (requires the 'web' extra: pip install 'stackr[web]')."""
    from stackr.web import HAS_FASTAPI

    if not HAS_FASTAPI:
        console.print(
            "[red]Web UI requires FastAPI and Uvicorn.[/red]\n"
            "Install them with: [bold]pip install 'stackr[web]'[/bold]"
        )
        raise typer.Exit(1)

    try:
        import uvicorn
    except ImportError:
        console.print(
            "[red]uvicorn is required for the web UI.[/red]\n"
            "Install it with: [bold]pip install 'stackr[web]'[/bold]"
        )
        raise typer.Exit(1) from None

    from stackr.web.app import create_app

    console.print(f"Starting Stackr web UI on [bold]http://{host}:{port}[/bold]")
    application = create_app(config_path)
    uvicorn.run(application, host=host, port=port)


# ---------------------------------------------------------------------------
# stackr catalog subcommands
# ---------------------------------------------------------------------------

@catalog_app.command(name="update")
def catalog_update(
    tag: Annotated[
        str, typer.Option("--tag", "-t", help="Release tag to install (default: latest)")
    ] = "latest",
) -> None:
    """Download and install the latest app catalog from GitHub."""
    from stackr.catalog_sync import (
        download_and_install,
        fetch_latest_tag,
        read_installed_version,
    )

    installed = read_installed_version()
    if installed:
        console.print(f"Installed catalog version: [bold]{installed}[/bold]")
    else:
        console.print("No user-installed catalog — using built-in.")

    try:
        if tag == "latest":
            console.print("Fetching latest release tag from GitHub…")
            tag = fetch_latest_tag()

        console.print(f"Downloading catalog [bold]{tag}[/bold]…")
        download_and_install(tag)
        console.print(f"[green]Catalog updated to {tag}.[/green]")
        console.print("Restart Stackr commands to use the new catalog.")
    except Exception as exc:
        console.print(f"[red]Catalog update failed: {exc}[/red]")
        raise typer.Exit(1) from exc


@catalog_app.command(name="version")
def catalog_version() -> None:
    """Show current catalog path, version, and available app count."""
    from stackr.catalog import BUILTIN_CATALOG, USER_CATALOG, Catalog
    from stackr.catalog_sync import read_installed_version

    catalog = Catalog()
    installed = read_installed_version()

    if installed:
        console.print(f"Catalog:       [bold]user-installed[/bold] ({installed})")
        console.print(f"Path:          {USER_CATALOG}")
    else:
        console.print("Catalog:       [bold]built-in[/bold]")
        console.print(f"Path:          {BUILTIN_CATALOG}")

    console.print(f"Apps loaded:   {len(catalog.all())}")
    console.print(f"Categories:    {', '.join(catalog.categories())}")


# ---------------------------------------------------------------------------
# stackr upgrade
# ---------------------------------------------------------------------------


@app.command()
def upgrade() -> None:
    """Upgrade stackr to the latest version from GitHub."""
    import shutil
    import subprocess

    from stackr.catalog_sync import GITHUB_REPO

    pipx = shutil.which("pipx")
    if not pipx:
        console.print("[red]pipx not found — cannot upgrade.[/red]")
        console.print("Install pipx then re-run: [bold]stackr upgrade[/bold]")
        raise typer.Exit(1)

    repo_url = f"git+https://github.com/{GITHUB_REPO}.git"
    console.print(f"Upgrading stackr from [bold]{repo_url}[/bold] ...")

    result = subprocess.run(
        [pipx, "install", "--force", repo_url],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        console.print(f"[red]Upgrade failed:[/red]\n{result.stderr.strip()}")
        raise typer.Exit(1)

    # Read new version from the freshly installed binary
    which_stackr = shutil.which("stackr")
    if which_stackr:
        ver = subprocess.run(
            [which_stackr, "--version"], capture_output=True, text=True
        )
        new_version = ver.stdout.strip()
    else:
        new_version = "unknown"

    console.print(f"[green]Upgrade complete.[/green] {new_version}")
    console.print(
        "\n[yellow]Note:[/yellow] Restart your shell or run [bold]exec $SHELL[/bold] "
        "if the version number above looks unchanged."
    )


# ---------------------------------------------------------------------------
# stackr uninstall
# ---------------------------------------------------------------------------


@app.command()
def uninstall(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip all confirmation prompts")] = False,
) -> None:
    """Remove stackr, its state directory, and optionally its pipx package."""
    import shutil
    import subprocess

    from stackr.state import DEFAULT_STATE_DIR

    console.print("[bold red]Stackr Uninstaller[/bold red]\n")

    # --- Remove pipx package ---
    pipx = shutil.which("pipx")
    if pipx:
        result = subprocess.run([pipx, "list"], capture_output=True, text=True)
        if "package stackr" in result.stdout:
            if yes or typer.confirm("Remove stackr pipx package?", default=True):
                subprocess.run([pipx, "uninstall", "stackr"], check=True)
                console.print("[green]pipx package removed.[/green]")
        else:
            console.print("[yellow]stackr not found in pipx — skipping package removal.[/yellow]")
    else:
        console.print("[yellow]pipx not found — skipping package removal.[/yellow]")

    # --- Remove ~/.stackr state/catalog directory ---
    state_dir = DEFAULT_STATE_DIR
    if state_dir.exists():
        console.print(f"\nFound data directory: [bold]{state_dir}[/bold]")
        console.print("  Contains: app state, catalog overrides, and generated secrets.")
        if yes or typer.confirm("Remove it?", default=False):
            shutil.rmtree(state_dir)
            console.print(f"[green]Removed {state_dir}[/green]")
        else:
            console.print(f"[yellow]Kept {state_dir}[/yellow]")
    else:
        console.print(f"[dim]State directory not found ({state_dir}) — nothing to remove.[/dim]")

    # --- Remind about .stackr.env files ---
    console.print(
        "\n[yellow]Note:[/yellow] Any [bold].stackr.env[/bold] files in your project "
        "directories were not removed.\n"
        "      Delete them manually if you no longer need the secrets they contain."
    )
    console.print("\n[green]Uninstall complete.[/green]")


# ---------------------------------------------------------------------------
# stackr ui
# ---------------------------------------------------------------------------


@app.command()
def ui(
    config_path: Annotated[Path, typer.Option("--config", "-c")] = _DEFAULT_CONFIG,
) -> None:
    """Launch the interactive TUI app browser."""
    has_textual: bool
    try:
        from stackr.tui import HAS_TEXTUAL, StackrTUI

        has_textual = HAS_TEXTUAL
    except ImportError:
        has_textual = False

    if not has_textual:
        console.print(
            "[red]TUI requires the 'textual' package.[/red]\n"
            "Install it with: [bold]pip install 'stackr[tui]'[/bold]"
        )
        raise typer.Exit(1)

    from stackr.catalog import Catalog

    catalog = Catalog()
    tui = StackrTUI(config_path=config_path, catalog=catalog)
    tui.run()


# ---------------------------------------------------------------------------
# stackr service subcommands
# ---------------------------------------------------------------------------

service_app = typer.Typer(help="Manage the Stackr web UI as a persistent background service.")
app.add_typer(service_app, name="service")


@service_app.command(name="install")
def service_install(
    config_path: Annotated[Path, typer.Option("--config", "-c")] = _DEFAULT_CONFIG,
    host: Annotated[str, typer.Option("--host", "-H")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", "-p")] = 8000,
) -> None:
    """Install and start the web UI as a persistent service (systemd on Linux, launchd on macOS)."""
    from stackr.service import install, is_installed

    if is_installed():
        console.print(
            "[yellow]Service is already installed. "
            "Run [bold]stackr service restart[/bold] to apply changes, or uninstall first.[/yellow]"
        )
        raise typer.Exit(1)
    try:
        install(config_path, host=host, port=port)
        console.print(f"[green]Service installed and started. Web UI at http://{host}:{port}[/green]")
    except Exception as exc:
        console.print(f"[red]Failed to install service: {exc}[/red]")
        raise typer.Exit(1) from exc


@service_app.command(name="uninstall")
def service_uninstall() -> None:
    """Stop, disable and remove the persistent service unit."""
    from stackr.service import uninstall

    try:
        uninstall()
        console.print("[green]Service uninstalled.[/green]")
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    except Exception as exc:
        console.print(f"[red]Failed to uninstall service: {exc}[/red]")
        raise typer.Exit(1) from exc


@service_app.command(name="start")
def service_start() -> None:
    """Start the web UI service."""
    from stackr.service import start

    try:
        start()
        console.print("[green]Service started.[/green]")
    except Exception as exc:
        console.print(f"[red]Failed to start service: {exc}[/red]")
        raise typer.Exit(1) from exc


@service_app.command(name="stop")
def service_stop() -> None:
    """Stop the web UI service."""
    from stackr.service import stop

    try:
        stop()
        console.print("[yellow]Service stopped.[/yellow]")
    except Exception as exc:
        console.print(f"[red]Failed to stop service: {exc}[/red]")
        raise typer.Exit(1) from exc


@service_app.command(name="restart")
def service_restart() -> None:
    """Restart the web UI service."""
    from stackr.service import restart

    try:
        restart()
        console.print("[green]Service restarted.[/green]")
    except Exception as exc:
        console.print(f"[red]Failed to restart service: {exc}[/red]")
        raise typer.Exit(1) from exc


@service_app.command(name="status")
def service_status() -> None:
    """Show the current status of the web UI service."""
    from stackr.service import is_installed, status

    if not is_installed():
        console.print(
            "[yellow]Service is not installed. "
            "Run [bold]stackr service install[/bold] first.[/yellow]"
        )
        raise typer.Exit(1)
    console.print(status())


if __name__ == "__main__":
    app()
