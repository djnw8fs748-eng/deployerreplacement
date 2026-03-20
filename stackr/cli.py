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

app = typer.Typer(
    name="stackr",
    help="A declarative, composable homelab deployment tool.",
    no_args_is_help=True,
)
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
    acme_email = typer.prompt("ACME email for Let's Encrypt certs", default="")
    dns_provider = typer.prompt("DNS provider", default="cloudflare")

    config = {
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
            "enabled": True,
            "acme_email": acme_email,
            "dns_provider": dns_provider,
            "dns_provider_env": {
                "CF_DNS_API_TOKEN": "${CF_DNS_API_TOKEN}",
            },
        },
        "security": {
            "socket_proxy": True,
            "crowdsec": False,
            "auth_provider": "none",
        },
        "backup": {
            "enabled": False,
            "destination": "/mnt/backup",
            "schedule": "0 2 * * *",
        },
        "apps": [
            {"name": "traefik", "enabled": True},
            {"name": "portainer", "enabled": True},
        ],
    }

    with open(output, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

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

    console.print(f"\n[green]Config written to[/green] {output}")
    console.print(f"[green]Secrets file:[/green]    {env_file}  (gitignored)")
    console.print("\nNext steps:")
    console.print("  1. Edit [bold]stackr.yml[/bold] to enable the apps you want")
    console.print("  2. Add your DNS API token to [bold].stackr.env[/bold]")
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


if __name__ == "__main__":
    app()
