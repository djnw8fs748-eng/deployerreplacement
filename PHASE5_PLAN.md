# Phase 5 — Operations: Implementation Plan

## Overview

Phase 5 completes the day-2 operations story: automated backup/restore, a migration tool
to import existing Deployrr setups, and health-alert notifications.

**Status:** Planned — not yet implemented.
**Prerequisite:** Phases 1–4 complete.

---

## Wave 1 — Backup / Restore

### Goal

Replace the `backup.py` stub with a real restic-based implementation.

### Design

```
stackr backup                     # back up data_dir + state + config_dir
stackr restore <snapshot>         # restore from a specific restic snapshot ID
stackr snapshots                  # list available snapshots with timestamps
```

`restic` must be installed on the host; Stackr manages the repository password
via the existing `ensure_secret("STACKR_RESTIC_PASSWORD", config_dir, env)` mechanism
(auto-generated on first use, stored in `.stackr.env`).

### Files to Create / Modify

#### `stackr/backup.py` — replace stub

```python
"""Restic-based backup and restore."""

def _check_restic() -> None:
    """Raise RuntimeError if restic is not on PATH."""

def _ensure_repo_initialized(destination: str, restic_env: dict[str, str]) -> None:
    """Run `restic init` only when the repository does not yet exist."""

def backup(
    destination: str,
    data_dir: Path,
    state_dir: Path,
    config_dir: Path,
    env: dict[str, str],
) -> None:
    """Back up data_dir, state_dir, and config_dir to destination."""

def restore(
    snapshot: str,
    destination: str,
    target: Path,
    config_dir: Path,
    env: dict[str, str],
) -> None:
    """Restore snapshot to target directory."""

def list_snapshots(
    destination: str,
    config_dir: Path,
    env: dict[str, str],
) -> list[dict[str, object]]:
    """Return parsed restic snapshot list (JSON)."""
```

Key points:
- All functions accept explicit `config_dir` and `env` for testability.
- `backup()` passes `capture_output=True` to suppress Docker-style progress noise;
  exceptions raise `RuntimeError` for clean CLI error handling.
- Repository init is idempotent: `restic snapshots --json` exit-code 0 → already inited.
- Password is auto-generated and stored in `.stackr.env` as `STACKR_RESTIC_PASSWORD`.

#### `stackr/cli.py` — update `backup`, `restore`; add `snapshots`

```python
@app.command()
def backup(config_path: Path = _DEFAULT_CONFIG) -> None:
    config, _, env, _ = _load(config_path)
    from stackr.backup import backup as run_backup
    from stackr.state import DEFAULT_STATE_DIR
    run_backup(
        destination=str(config.backup.destination),
        data_dir=config.global_.data_dir,
        state_dir=DEFAULT_STATE_DIR,
        config_dir=config_path.parent,
        env=env,
    )

@app.command()
def restore(
    snapshot: Annotated[str, typer.Argument()],
    config_path: Path = _DEFAULT_CONFIG,
    target: Annotated[Path | None, typer.Option()] = None,
) -> None:
    config, _, env, _ = _load(config_path)
    from stackr.backup import restore as run_restore
    run_restore(
        snapshot=snapshot,
        destination=str(config.backup.destination),
        target=target or config.global_.data_dir,
        config_dir=config_path.parent,
        env=env,
    )

@app.command()
def snapshots(config_path: Path = _DEFAULT_CONFIG) -> None:
    """List available backup snapshots."""
    config, _, env, _ = _load(config_path)
    from stackr.backup import list_snapshots
    snaps = list_snapshots(str(config.backup.destination), config_path.parent, env)
    # render Rich table: ID, time, hostname, paths
```

#### `tests/test_backup.py` — new

- Mock `shutil.which` returning `None` → test `_check_restic` raises `RuntimeError`.
- Mock `subprocess.run` for `snapshots` call (exit 1) → triggers `init` path.
- Mock `subprocess.run` for full `backup()` happy path.
- Mock `subprocess.run` for `list_snapshots` with sample JSON.
- Test `restore()` delegates correct args to subprocess.

### Acceptance Criteria

- `stackr backup` backs up three paths (data, state, config) via restic.
- `stackr restore latest` restores to `data_dir`.
- `stackr snapshots` prints a Rich table with ID, timestamp, hostname.
- `stackr doctor` gains a new check: `backup.destination` directory is writable (warn if not).
- All tests pass; ruff + mypy clean.

---

## Wave 2 — Deployrr Migration Tool

### Goal

Allow users migrating from Deployrr to generate a working `stackr.yml` from their
existing Deployrr app list.

### Design

```
stackr migrate --from deployrr [--input apps.txt] [--output stackr.yml]
```

- `--input`: path to a plain-text file listing Deployrr app names, one per line.
  If omitted, prompts the user to enter names interactively.
- `--output`: path for the generated `stackr.yml` (default: `stackr.yml`).
- Warns about app names with no catalog match; lists them at the end.

### Files to Create / Modify

#### `stackr/migrate.py` — new module

```python
"""Deployrr → Stackr migration helpers."""

# Canonical name mapping (Deployrr name → Stackr catalog name)
_DEPLOYRR_MAP: dict[str, str] = {
    "portainer-ce": "portainer",
    "portainer-ee": "portainer",
    "adguard-home": "adguardhome",
    "bitwarden": "vaultwarden",
    "bitwarden-rs": "vaultwarden",
    "plex-media-server": "plex",
    "transmission-vpn": "transmission",
    "qbittorrent-vpn": "qbittorrent",
    "wireguard-easy": "wireguard",
    "grafana-oss": "grafana",
    "uptimekuma": "uptime-kuma",
    "uptime-kuma": "uptime-kuma",
    "paperless": "paperless-ngx",
    "miniflux-v2": "miniflux",
    "nextcloud-aio": "nextcloud",
    "traefik-v2": "traefik",
    # … complete list in implementation
}

_STRIP_SUFFIXES = ("-ce", "-ee", "-vpn", "-media", "-v2", "-oss", "-aio")

def map_app_name(deployrr_name: str) -> str:
    """Map one Deployrr app name to a Stackr catalog name."""

def migrate_from_deployrr(
    app_names: list[str],
    catalog_apps: set[str],
) -> tuple[list[dict[str, object]], list[str]]:
    """Return (mapped_app_dicts, unmapped_names)."""

def write_stackr_yml(
    output_path: Path,
    apps: list[dict[str, object]],
    *,
    data_dir: str = "/opt/appdata",
    timezone: str = "UTC",
    domain: str = "example.com",
    dns_provider: str = "cloudflare",
) -> None:
    """Emit a minimal stackr.yml skeleton with the given apps."""
```

#### `stackr/cli.py` — add `migrate` command

```python
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
        app_names = input_file.read_text().splitlines()
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
```

#### `tests/test_migrate.py` — new

- `test_map_app_name_direct_hit` — "portainer-ce" → "portainer"
- `test_map_app_name_suffix_strip` — "myapp-vpn" → "myapp"
- `test_map_app_name_passthrough` — unknown name returned unchanged
- `test_migrate_from_deployrr_splits_mapped_unmapped`
- `test_migrate_from_deployrr_deduplicates`
- `test_write_stackr_yml_is_valid_yaml` — written file parses cleanly
- `test_write_stackr_yml_contains_all_apps`

### Acceptance Criteria

- `stackr migrate --from deployrr --input apps.txt` writes a valid `stackr.yml`.
- Unknown app names are listed as warnings, not errors.
- `stackr validate` on the generated file passes for well-known app names.
- All tests pass; ruff + mypy clean.

---

## Wave 3 — Health Alerts (Optional / Stretch)

### Goal

Notify the user (via ntfy, Gotify, or webhook) when a deploy fails or a `stackr doctor`
check fails at `fail` level.

### Design

- Add `alerts` section to `stackr.yml`:

```yaml
alerts:
  enabled: true
  provider: ntfy          # ntfy | gotify | webhook
  url: https://ntfy.sh/my-homelab
  token: ${NTFY_TOKEN}    # optional auth token
```

- `stackr/alerts.py` — thin HTTP sender using `urllib.request` (no extra deps):

```python
def send_alert(title: str, message: str, config: AlertConfig) -> None:
    """POST a notification to the configured provider."""
```

- `deployer.py` calls `send_alert` when a deploy fails (catches exception so alerts
  never abort the deploy loop).
- `doctor.py` calls `send_alert` when `run_doctor` returns `False`.

### Files to Create / Modify

- `stackr/alerts.py` — new module
- `stackr/config.py` — add `AlertConfig` model, add `alerts` field to `StackrConfig`
- `stackr/deployer.py` — call `send_alert` on failure
- `stackr/doctor.py` — call `send_alert` on failure
- `tests/test_alerts.py` — new, mock `urllib.request.urlopen`

### Acceptance Criteria

- Alert fires on deploy failure and doctor failure.
- Alert is suppressed (warn only) when the HTTP call fails.
- `AlertConfig` validates `provider` to `ntfy | gotify | webhook`.
- All tests pass; ruff + mypy clean.

---

## Implementation Order

```
Wave 1 (backup/restore)  →  Wave 2 (migrate)  →  Wave 3 (alerts, optional)
```

Each wave is independently committable and mergeable. Waves 1 and 2 are required;
Wave 3 is a stretch goal.

## Testing Checklist (per wave)

1. New module has `tests/test_<module>.py`
2. Every test has at least one `assert`
3. Mocks use `mocker` from `pytest-mock`; no real filesystem writes to home dir
4. `pytest tests/ -v` — all pass
5. `ruff check stackr/ tests/` — clean
6. `mypy stackr/` — clean

## Definition of Done

- [ ] Wave 1: `stackr backup`, `stackr restore`, `stackr snapshots` implemented and tested
- [ ] Wave 2: `stackr migrate --from deployrr` implemented and tested
- [ ] Wave 3 (optional): `stackr/alerts.py` implemented and integrated
- [ ] README.md updated with new commands and `backup` config section
- [ ] CLAUDE.md updated with `backup.py`, `migrate.py`, `alerts.py` module entries
