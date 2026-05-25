# Stackr

A declarative homelab Docker Compose deployment tool. Define your self-hosted apps in a single YAML file and let Stackr handle rendering, secret management, validation, and deployment.

Stackr replaces Deployrr (a closed-source PHP/Bash binary) with a fully open, auditable Python implementation.

## Features

- **Declarative config**: one `stackr.yml` drives your entire homelab
- **App catalog**: 42 apps across 10 categories — databases, AI, media, monitoring, storage, and more
- **Default reverse proxy**: nginx-proxy-manager is pre-wired as the default proxy — no extra configuration required
- **Secret management**: auto-generated secrets stored in `.stackr.env`, shell env takes priority
- **Pre-deploy validation**: port conflicts, missing secrets, unknown apps, dependency checks, security stack consistency
- **State tracking**: SQLite database at `~/.stackr/stackr.db` stores compose content and image digests per app
- **Drift detection**: `stackr status` reports `drift` when a live container's image digest differs from the digest recorded at last deploy
- **Image digest tracking**: `stackr update` redeploys only when upstream images actually change
- **Always-on API service**: `stackr api` runs a REST API on port 7274; `deploy`/`validate`/`status` CLI commands proxy through it automatically when it is reachable
- **Socket proxy**: no app mounts the raw Docker socket when `security.socket_proxy: true`
- **CrowdSec**: crowd-sourced IP reputation integration
- **Backup/restore**: `stackr backup` / `restore` / `snapshots` — restic-based encrypted backups with auto-generated password
- **Deployrr migration**: `stackr migrate --from deployrr` maps an existing Deployrr app list to a `stackr.yml`
- **Alerts**: ntfy, Gotify, or webhook notifications on deploy failures and `stackr doctor` errors
- **Remote shares**: `stackr mount` / `umount` for SMB, NFS, and Rclone mounts declared under `mounts:` in `stackr.yml`
- **Catalog updates**: `stackr catalog update` downloads the latest catalog from GitHub
- **Interactive TUI**: `stackr ui` opens a terminal app browser — toggle apps on/off, edit settings and mounts, save config
- **Web UI**: `stackr web` opens the browser dashboard; all settings editable via tabbed panel (Global, Network, Security, Backup, Alerts, Mounts), per-app var overrides, live log streaming
- **Persistent API service**: `stackr service install` registers the API as a systemd user service (Linux) or launchd LaunchAgent (macOS)
- **Self-upgrade**: `stackr upgrade` pulls and installs the latest version from GitHub in one command
- **Full catalog init**: `stackr init` generates a `stackr.yml` with all catalog apps pre-listed (disabled by default)

## Requirements

- Python 3.11+
- Docker Engine 24+ with the Compose plugin (`docker compose`)

## Installation

### One-command (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/djnw8fs748-eng/deployerreplacement/main/install.sh | bash
```

This installs Stackr via `pipx` into an isolated environment and adds the `stackr` command to your PATH.

### Via pipx

```bash
pipx install git+https://github.com/djnw8fs748-eng/deployerreplacement.git
```

The TUI (`stackr ui`) and web UI (`stackr web`) are included in the base install — no extras required.

### From source

```bash
git clone https://github.com/djnw8fs748-eng/deployerreplacement.git
cd deployerreplacement
pip install uv
uv pip install -e ".[dev]"
```

## Upgrading

```bash
stackr upgrade
```

Pulls and installs the latest commit from GitHub via `pipx install --force`. This is the correct way to upgrade — `pipx upgrade` reports "already at latest version" for git-installed packages and does nothing.

If the version number looks unchanged after upgrading, reload your shell:

```bash
exec $SHELL
```

## Uninstalling

```bash
# Via the installer script
curl -fsSL https://raw.githubusercontent.com/djnw8fs748-eng/deployerreplacement/main/install.sh | bash -s -- --uninstall

# Or via the CLI (if stackr is still on your PATH)
stackr uninstall
stackr uninstall --yes   # skip all confirmation prompts
```

Both methods remove the pipx package and prompt before deleting `~/.stackr` (state, catalog, generated secrets). `.stackr.env` files in project directories are left in place — delete them manually if you no longer need the secrets they contain.

## Quickstart

```bash
# 1. Initialise a config directory
stackr init

# 2. Check your environment before deploying
stackr doctor

# 3. Validate config
stackr validate

# 4. Preview what will change
stackr plan

# 5. Deploy
stackr deploy
```

## Configuration

Copy `stackr.yml.example` as a starting point:

```bash
cp stackr.yml.example stackr.yml
```

### Full reference

```yaml
global:
  data_dir: /opt/appdata       # host path for persistent app data
  timezone: Europe/London      # TZ identifier (default: UTC)
  puid: 1000
  pgid: 1000

catalog:
  source: github               # github | local
  version: latest              # pin to a release tag (e.g. v1.2.0) or "latest"

network:
  domain: example.com          # public domain (used in compose templates)
  local_domain: home.example.com  # LAN domain

security:
  socket_proxy: false          # route Docker API through socket-proxy sidecar
  crowdsec: false              # enable CrowdSec integration (requires crowdsec in apps)

backup:
  enabled: false
  destination: /mnt/backup     # restic repository path (local, s3:bucket/path, etc.)
  schedule: "0 2 * * *"        # informational — no built-in scheduler

alerts:
  enabled: false
  provider: ntfy               # ntfy | gotify | webhook
  url: https://ntfy.sh/my-homelab-alerts
  token: ${NTFY_TOKEN}         # optional Bearer token, resolved from env / .stackr.env

apps:
  - name: jellyfin
    enabled: true
    vars:
      hardware_accel: vaapi    # catalog-defined variable
    overrides:                 # deep-merged on top of rendered compose
      services:
        jellyfin:
          mem_limit: "4g"

  - name: radarr
    enabled: true
```

## Secret management

Secrets are resolved in this priority order (highest first):

1. **Shell environment** — `export MY_SECRET=abc123`
2. **`.stackr.env` file** — auto-created by `stackr init`, never committed
3. **Auto-generated** — Stackr generates random secrets for required vars on first deploy

`.stackr.env` format:

```
# DO NOT COMMIT THIS FILE
MY_APP_SECRET=<auto-generated>
```

## CLI reference

```
stackr init                   Interactive setup wizard — generates stackr.yml and .stackr.env
stackr doctor                 Check Docker, networks, secrets, and catalog health
stackr validate               Validate config without deploying
stackr render <app>           Print generated compose YAML (for debugging)
stackr plan                   Show what would change (diff against current state)
stackr deploy [app]           Validate, render, pull images, and deploy
stackr update                 Pull latest images, redeploy when images or config changed
stackr stop <app>             Stop a running app
stackr restart <app>          Restart without full redeploy
stackr remove <app>           Stop and remove an app's containers
stackr rollback <app>         Redeploy using the last stored compose content
stackr status [app]           Show running/stopped/drift status of all apps
stackr logs <app>             Stream logs for an app
stackr shell <app>            Open a shell inside the app's primary container
stackr list [--category C]    List all catalog apps
stackr search <query>         Search catalog by name or description
stackr ui                     Launch the interactive TUI app browser
stackr api [--port 7274]      Start the REST API server (OpenAPI docs at /api/docs)
stackr web [--port 7274]      Open the web UI in a browser (requires stackr api)
stackr service install        Install the API as a persistent background service
stackr service uninstall      Remove the persistent service
stackr service start          Start the service
stackr service stop           Stop the service
stackr service restart        Restart the service
stackr service status         Show service status
stackr upgrade                Upgrade stackr to the latest version from GitHub
stackr backup                 Run a restic backup to the configured destination
stackr restore <snapshot>     Restore from a backup snapshot
stackr snapshots              List available backup snapshots
stackr migrate [--from deployrr] --input apps.txt --output stackr.yml
stackr mount                  Mount all remote shares from stackr.yml
stackr umount                 Unmount all remote shares from stackr.yml
stackr catalog update         Download the latest catalog from GitHub
stackr catalog version        Show current catalog version and app count
stackr uninstall              Remove the stackr pipx package and optionally ~/.stackr
stackr uninstall --yes        Skip all confirmation prompts
```

## App catalog

42 apps across 10 categories. All are pre-listed in the config generated by `stackr init` — disabled by default, ready to toggle on.

### Categories and apps

| Category | Apps |
|----------|------|
| **network** | nginx-proxy-manager, adguardhome, pihole, wireguard, headscale, gluetun |
| **security** | socket-proxy, crowdsec, pocket-id, tinyauth, vaultwarden |
| **media** | jellyfin, plex, radarr, sonarr, prowlarr, bazarr, lidarr, readarr, seerr, tdarr, qbittorrent |
| **monitoring** | uptime-kuma, grafana, prometheus, loki, netdata |
| **management** | portainer, dozzle, watchtower, heimdall, flame |
| **dashboard** | homepage |
| **storage** | filebrowser, duplicati |
| **database** | postgres, mariadb, redis, mongo |
| **ai** | ollama, open-webui |
| **gaming** | minecraft |

### Port semantics

`ports` in `app.yml` is the container port (informational; used by the validator).
`host_ports` in `app.yml` are actual host-bound ports checked for conflicts at validation time.
Apps proxied through nginx-proxy-manager share container ports without conflict — only `host_ports` need to be unique across your stack.

### Adding a custom app

Create the following structure anywhere on disk (or inside `stackr/catalog/` for built-in apps):

```
my-catalog/my-app/
  app.yml           # metadata, ports, host_ports, volumes, vars
  compose.yml.j2    # Jinja2 compose template
```

Minimal `app.yml` for an NPM-proxied app:

```yaml
name: my-app
display_name: My App
description: What it does
category: management
homepage: https://...
requires: []
ports:
  - 8080          # container port (informational)
host_ports: []    # actual host-bound ports (for conflict detection)
volumes:
  - name: config
    path: /config
```

Minimal `compose.yml.j2`:

```jinja2
services:
  my-app:
    image: myorg/my-app:{{ vars.version | default('latest') }}
    container_name: my-app
    restart: unless-stopped
    environment:
      - PUID={{ global.puid }}
      - PGID={{ global.pgid }}
      - TZ={{ global.timezone }}
    volumes:
      - {{ global.data_dir }}/my-app/config:/config
    networks:
      - proxy

networks:
  proxy:
    external: true
```

For apps without a web UI (databases, VPN tunnels, game servers), omit the `proxy` network entirely and declare any host-bound ports under `host_ports:` in `app.yml`. See `stackr/catalog/database/postgres/` for an example.

Point Stackr at your custom catalog:

```yaml
# stackr.yml
catalog:
  source: local
  local_path: ./my-catalog
```

## State and rollback

Stackr tracks every deployed app in a SQLite database at `~/.stackr/stackr.db`. Each app record stores:

- Full rendered compose YAML (for genuine rollback)
- Compose content hash (for skip-unchanged detection)
- Image digests per service (for upstream update and drift detection)
- Deployed timestamp and last error

```bash
stackr rollback jellyfin   # redeploys from stored compose content
```

## Drift detection

`stackr status` compares the live Docker image digest against the digest recorded at last deploy. When they differ the app is shown as `drift`:

```
┌ Stackr App Status ────────────────────────────────────┐
│ App       Status    Deployed At          Last Error    │
│ jellyfin  running   2026-05-25 20:14:22               │
│ sonarr    drift     2026-05-23 11:30:01               │
│ radarr    stopped   2026-05-20 09:05:44               │
└───────────────────────────────────────────────────────┘
```

Run `stackr deploy sonarr` (or `stackr update`) to pull the new image and clear the drift.

## REST API and web UI

Stackr ships a FastAPI REST API that drives the browser dashboard. Start it with:

```bash
stackr api                    # listens on 0.0.0.0:7274
stackr api --port 8080        # custom port
```

Interactive API docs are available at `http://localhost:7274/api/docs`.

Once the API is running, open the dashboard:

```bash
stackr web                    # opens http://127.0.0.1:7274 in a browser
stackr web --port 8080        # custom port
```

The dashboard provides:

- App grid showing enabled/deployed/drift/stopped status for every configured app
- One-click enable/disable toggle (updates `stackr.yml`)
- Per-app and full-stack deploy buttons
- Live log streaming via Server-Sent Events
- **Full settings editor** — tabbed panel covering every config section: Global, Network, Security, Backup, Alerts, and Mounts CRUD
- **Per-app var overrides** — type-aware form (string/select/boolean/integer) loaded inline from the catalog

### CLI as API client

When `stackr api` is reachable, the `deploy`, `validate`, and `status` CLI commands automatically proxy through it rather than running inline — so you see real-time progress from whichever terminal you're in:

```bash
# With API running: proxies through http://127.0.0.1:7274
stackr deploy
stackr validate
stackr status

# These always run inline regardless of API availability:
stackr deploy --skip-pull
stackr deploy --force
```

### Persistent service

To keep the API running without a terminal session:

```bash
# Install and start as a background service
stackr service install

# Linux: systemd user service at ~/.config/systemd/user/stackr-api.service
# macOS: launchd LaunchAgent at ~/Library/LaunchAgents/dev.stackr.api.plist

# Manage the service
stackr service status
stackr service restart
stackr service stop
stackr service uninstall
```

The service starts automatically on login/reboot. Custom host, port, and config path can be set at install time:

```bash
stackr service install --host 0.0.0.0 --port 9000 --config /opt/stackr/stackr.yml
```

## Checking environment health

```bash
stackr doctor
```

Runs checks including:

- Docker daemon reachable
- `docker compose` plugin installed
- `proxy` and `socket_proxy` networks exist
- State database is accessible
- `.stackr.env` file exists
- All enabled apps are in the catalog

## Backup and restore

Stackr uses [restic](https://restic.net/) for encrypted, incremental backups.
`restic` must be installed on the host.

```bash
# Enable backups in stackr.yml:
#   backup:
#     enabled: true
#     destination: /mnt/backup    # or s3:bucket/path, sftp:host:/path, etc.

# Run a backup now
stackr backup

# List snapshots
stackr snapshots

# Restore a snapshot (default target: global.data_dir)
stackr restore latest
stackr restore abc1def2 --target /tmp/restore
```

The restic repository password is auto-generated on first use and stored in `.stackr.env` as `STACKR_RESTIC_PASSWORD`.

## Alerts

Stackr can send a push notification when a deploy fails or `stackr doctor` finds a failure.

```yaml
alerts:
  enabled: true
  provider: ntfy           # ntfy | gotify | webhook
  url: https://ntfy.sh/my-homelab-alerts
  token: ${NTFY_TOKEN}     # optional Bearer token
```

Supported providers: **ntfy**, **Gotify**, and any generic **webhook** (POST with JSON body).
HTTP errors from the alert provider are always swallowed so they never block a deploy.

## Remote share mounting

Declare SMB, NFS, or Rclone mounts under `mounts:` in `stackr.yml`:

```yaml
mounts:
  - name: media
    type: smb               # smb | nfs | rclone
    remote: //192.168.1.10/media
    mountpoint: /mnt/media
    username: myuser
    password: ${SMB_PASSWORD}

  - name: photos
    type: nfs
    remote: 192.168.1.10:/export/photos
    mountpoint: /mnt/photos
    options: ro,noatime

  - name: gdrive
    type: rclone
    remote: gdrive:          # rclone remote name (must be configured in rclone.conf)
    mountpoint: /mnt/gdrive
```

```bash
stackr mount     # mount all configured shares
stackr umount    # unmount all configured shares
```

**Requirements by mount type:**

| Type | Requirement |
|------|-------------|
| `smb` | `cifs-utils` (`mount.cifs` on PATH) |
| `nfs` | `nfs-common` / `nfs-utils` |
| `rclone` | `rclone` on PATH + configured remote; `fuse3` for FUSE mounts |

## Migrating from Deployrr

Use `stackr migrate` to convert a Deployrr app list into a `stackr.yml`:

```bash
# From a file (one app name per line)
stackr migrate --from deployrr --input my-deployrr-apps.txt --output stackr.yml

# Interactive (enter app names one by one)
stackr migrate --from deployrr
```

Apps are matched against the Stackr catalog. Unmapped names are listed so you can add them manually.

## Interactive TUI

The `stackr ui` command opens a full-terminal app browser built with [Textual](https://textual.textualize.io/). Included in the base install — no extras required.

```bash
stackr ui
stackr ui --config /path/to/stackr.yml
```

### Layout

```
┌─ Stackr — App Catalog ──────────────────────────────────┐
│ ▼ database         │  Jellyfin  ✓ ENABLED               │
│   ✓ postgres       │                                     │
│   ○ mariadb        │  Free and open source media server  │
│ ▼ media            │                                     │
│   ✓ jellyfin       │  Category:  media                   │
│   ○ plex           │  Homepage:  https://jellyfin.org    │
│ ▼ network          │                                     │
│   ✓ npm            │  Variables:                         │
│   ○ pihole         │   • hardware_accel = 'none'          │
│                    │     (vaapi, nvidia, intel_qsv)       │
├────────────────────┴─────────────────────────────────────┤
│ Space toggle  •  S save  •  Q quit                       │
└──────────────────────────────────────────────────────────┘
```

### Key bindings

| Key | Action |
|-----|--------|
| `Space` | Toggle the highlighted app on/off |
| `E` | Edit settings or mount entry |
| `A` | Add a new mount entry |
| `D` | Delete the selected mount |
| `S` | Save current state to `stackr.yml` |
| `Q` | Quit |

## Development

### Setup

```bash
git clone https://github.com/djnw8fs748-eng/deployerreplacement.git
cd deployerreplacement
pip install uv
uv pip install -e ".[dev]"
```

### Running tests

```bash
source .venv/bin/activate && pytest tests/ -v
```

### Linting and type checking

```bash
source .venv/bin/activate && ruff check stackr/ tests/ && mypy stackr/
```

### Project structure

```
stackr/
  cli.py              Typer CLI — all user-facing commands
  status.py           Rich terminal status table (standalone / API-client)
  service.py          Persistent service management: systemd (Linux) / launchd (macOS)
  migrate.py          Deployrr → stackr.yml migration

  engine/
    config.py         Pydantic config models (StackrConfig, AppConfig, …)
    catalog.py        App catalog loader; prefers ~/.stackr/catalog/ over built-in
    renderer.py       Jinja2 compose renderer
    secrets.py        Secret resolution and .stackr.env management
    state.py          SQLite state DB (~/.stackr/stackr.db) with image digest tracking
    deployer.py       Deploy orchestration and rollback
    validator.py      Pre-deploy validation checks
    docker.py         Docker SDK helpers: container status, image digests
    alerts.py         Push notifications via ntfy, Gotify, or webhook
    backup.py         Restic-based backup/restore
    mounts.py         Remote share mounting: SMB, NFS, Rclone

  api/
    app.py            FastAPI application factory + startup DB reconciliation
    deps.py           FastAPI dependency injection (DB, config, locks)
    jobs.py           Thread-safe deploy job store
    models.py         Pydantic API request/response models
    routes/
      apps.py         App CRUD, live status + drift detection, deploy/rollback
      deploy.py       Full-stack deploy endpoint with background job
      system.py       Health check, validation endpoint
      catalog.py      Catalog browse endpoints
      config.py       Config read/write endpoint
      mounts.py       Mounts CRUD endpoint

  catalog/
    ai/               ollama, open-webui
    dashboard/        homepage
    database/         postgres, mariadb, redis, mongo
    gaming/           minecraft
    management/       portainer, dozzle, watchtower, heimdall, flame
    media/            jellyfin, plex, radarr, sonarr, prowlarr, bazarr, lidarr,
                      readarr, seerr, tdarr, qbittorrent
    monitoring/       uptime-kuma, grafana, prometheus, loki, netdata
    network/          nginx-proxy-manager, adguardhome, pihole, wireguard,
                      headscale, gluetun
    security/         socket-proxy, crowdsec, pocket-id, tinyauth, vaultwarden
    storage/          filebrowser, duplicati

  web/
    app.py            Legacy HTMX app factory (superseded by stackr/api/)
    routes.py         Legacy HTMX route handlers

tests/
  test_api_*.py           REST API route and model tests
  test_api_drift.py       Drift detection and 5s status cache tests
  test_cli_api_client.py  CLI API-proxy behaviour (probe, deploy, fallback)
  test_cli_web.py         stackr web command tests
  test_catalog.py         Catalog loading and seed app presence
  test_catalog_validation.py  CI suite: 5 checks × 42 apps
  test_config.py          Config schema and validation
  test_deployer.py        Deploy orchestration and rollback
  test_renderer.py        Jinja2 rendering and smoke tests for all apps
  test_secrets.py         Secret resolution and .stackr.env management
  test_state.py           SQLite state DB and image digest persistence
  test_validator.py       Pre-deploy validation checks
  test_*.py               One file per module
```

### Dependencies

**Runtime:**

| Package | Purpose |
|---------|---------|
| `typer` | CLI framework |
| `pydantic` | Config schema and validation |
| `jinja2` | Compose template rendering |
| `pyyaml` | YAML parsing |
| `rich` | Terminal output |
| `python-dotenv` | `.stackr.env` loading |
| `docker` | Docker SDK (container status, image digests) |
| `textual` | Terminal UI framework for `stackr ui` |
| `fastapi` | ASGI web framework for `stackr api` |
| `uvicorn` | ASGI server for `stackr api` |

**Development:**

| Package | Purpose |
|---------|---------|
| `pytest` | Test runner |
| `pytest-asyncio` | Async test support |
| `pytest-mock` | Mocking utilities |
| `httpx` | Test client for FastAPI routes |
| `ruff` | Linting and formatting |
| `mypy` | Static type checking |

## CI

GitHub Actions runs on every push and pull request:

- `ruff check` — linting
- `mypy` — type checking
- `pytest` — full test suite including catalog validation for all 42 apps

## License

MIT
