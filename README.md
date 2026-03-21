# Stackr

A declarative homelab Docker Compose deployment tool. Define your self-hosted apps in a single YAML file and let Stackr handle rendering, secret management, validation, and deployment.

Stackr replaces Deployrr (a closed-source PHP/Bash binary) with a fully open, auditable Python implementation.

## Features

- **Declarative config**: one `stackr.yml` drives your entire homelab
- **App catalog**: 38 apps across 11 categories — databases, AI, media, monitoring, storage, and more
- **Secret management**: auto-generated secrets stored in `.stackr.env`, shell env takes priority
- **Pre-deploy validation**: port conflicts, missing secrets, unknown apps, dependency checks, DNS provider env vars, security stack consistency
- **State tracking**: stores full compose content + image digests for genuine rollback and smart update detection
- **Image digest tracking**: `stackr update` redeployes only when upstream images actually change
- **Network modes**: `external`, `internal`, or `hybrid` with automatic Traefik label generation
- **Socket proxy**: no app mounts the raw Docker socket when `security.socket_proxy: true`
- **CrowdSec**: crowd-sourced IP reputation and Traefik bouncer integration
- **Authentik / Authelia**: forward-auth SSO with automatic Traefik middleware labels
- **Multi-DNS providers**: Cloudflare, Route 53, Porkbun, Namecheap, DigitalOcean, DuckDNS, GoDaddy, deSEC, Hetzner, OVH
- **Deep-merge overrides**: apply custom compose keys on top of any catalog template
- **Health checks**: `stackr doctor` verifies Docker, networks, secrets, and catalog before deploying
- **Backup/restore**: `stackr backup` / `restore` / `snapshots` — restic-based encrypted backups with auto-generated password
- **Deployrr migration**: `stackr migrate --from deployrr` maps an existing Deployrr app list to a `stackr.yml`
- **Alerts**: ntfy, Gotify, or webhook notifications on deploy failures and `stackr doctor` errors
- **Remote shares**: `stackr mount` / `umount` for SMB, NFS, and Rclone mounts; declared under `mounts:` in `stackr.yml`
- **Catalog updates**: `stackr catalog update` downloads the latest catalog from GitHub
- **Interactive TUI**: `stackr ui` opens a terminal app browser — toggle apps on/off, see details, save config
- **Web UI** (optional): `stackr web` launches a FastAPI + HTMX browser dashboard for point-and-click management

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
  mode: external               # external | internal | hybrid
  domain: example.com          # public domain (external/hybrid)
  local_domain: home.example.com  # LAN domain (internal/hybrid)

traefik:
  enabled: true
  acme_email: you@example.com  # Let's Encrypt registration email
  dns_provider: cloudflare     # DNS challenge provider name
  dns_provider_env:
    CF_DNS_API_TOKEN: ${CF_DNS_API_TOKEN}   # resolved from env / .stackr.env

security:
  socket_proxy: true           # route Docker API through socket-proxy
  crowdsec: true               # enable CrowdSec bouncer
  auth_provider: authelia      # authelia | authentik | none | <custom-app-name>

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

### Network modes

| Mode | Behaviour |
|------|-----------|
| `external` | Apps exposed only via public domain over HTTPS |
| `internal` | Apps exposed only via local domain (LAN), TLS via DNS challenge |
| `hybrid` | Apps exposed on both public and local domains simultaneously |

## Secret management

Secrets are resolved in this priority order (highest first):

1. **Shell environment** — `export CF_DNS_API_TOKEN=abc123`
2. **`.stackr.env` file** — auto-created by `stackr init`, never committed
3. **Auto-generated** — Stackr generates random secrets for required vars on first deploy

`.stackr.env` format:

```
# DO NOT COMMIT THIS FILE
CF_DNS_API_TOKEN=abc123
MY_APP_SECRET=<auto-generated>
```

## CLI reference

```
stackr init                   Initialise config and .stackr.env
stackr doctor                 Check Docker, networks, secrets, and catalog health
stackr validate               Validate config without deploying
stackr render <app>           Print generated compose YAML (debugging)
stackr plan                   Show what would change (diff against current state)
stackr deploy [app]           Validate, render, pull images, and deploy
stackr update                 Pull latest images, redeploy when images or config changed
stackr stop <app>             Stop a running app
stackr restart <app>          Restart without full redeploy
stackr remove <app>           Stop and remove an app's containers
stackr rollback <app>         Redeploy using the last stored compose content
stackr status [app]           Show status of all tracked apps
stackr logs <app>             Stream logs for an app
stackr shell <app>            Open a shell inside the app's primary container
stackr list [--category C]    List all catalog apps
stackr search <query>         Search catalog by name or description
stackr ui                     Launch the interactive TUI app browser
stackr web [--port 8000]      Launch the web UI (requires stackr[web])
stackr backup                 Run a restic backup to the configured destination
stackr restore <snapshot>     Restore from a backup snapshot
stackr snapshots              List available backup snapshots
stackr migrate [--from deployrr] --input apps.txt --output stackr.yml
stackr mount                  Mount all remote shares from stackr.yml
stackr umount                 Unmount all remote shares from stackr.yml
stackr catalog update         Download the latest catalog from GitHub
stackr catalog version        Show current catalog version and app count
stackr uninstall              Remove the stackr pipx package and optionally ~/.stackr
```

## App catalog

### Categories and apps

| Category | Apps |
|----------|------|
| **network** | traefik, adguardhome, pihole, wireguard, headscale, nginx-proxy-manager |
| **security** | socket-proxy, crowdsec, authentik, authelia, vaultwarden |
| **media** | jellyfin, plex, radarr, sonarr, prowlarr, bazarr, lidarr, readarr, overseerr, jellyseerr, tdarr, sabnzbd, qbittorrent, transmission |
| **monitoring** | uptime-kuma, grafana, prometheus, loki, netdata |
| **management** | portainer, dozzle, watchtower, heimdall, dasherr, flame |
| **dashboard** | homepage |
| **storage** | nextcloud, filebrowser, duplicati |
| **database** | postgres, mariadb, redis, mongo |
| **ai** | ollama, open-webui |
| **productivity** | gitea, paperless-ngx, freshrss, miniflux |
| **gaming** | minecraft |

### Port semantics

`ports` in `app.yml` is the container port for Traefik routing (passed to `traefik_labels()`).
`host_ports` in `app.yml` are actual host-bound ports checked for conflicts at validation time.
Apps proxied by Traefik share container ports without conflict — only `host_ports` are unique.

### Security stack

Enable CrowdSec and an auth provider in your config:

```yaml
security:
  socket_proxy: true
  crowdsec: true           # requires crowdsec in apps:
  auth_provider: authentik  # authentik | authelia | none

apps:
  - name: crowdsec
    enabled: true
  - name: authentik
    enabled: true
```

Stackr automatically:
- Validates that the auth provider app is in your `apps:` list
- Validates that `crowdsec` is in `apps:` when `security.crowdsec: true`
- Injects forward-auth middleware labels on Authentik/Authelia
- Configures the CrowdSec bouncer plugin in Traefik
- Shares Traefik access logs with the CrowdSec agent

### Supported DNS providers

| Provider | Required env vars |
|----------|------------------|
| Cloudflare | `CF_DNS_API_TOKEN` |
| AWS Route 53 | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` |
| Porkbun | `PORKBUN_API_KEY`, `PORKBUN_SECRET_API_KEY` |
| Namecheap | `NAMECHEAP_API_USER`, `NAMECHEAP_API_KEY` |
| DigitalOcean | `DO_AUTH_TOKEN` |
| DuckDNS | `DUCKDNS_TOKEN` |
| GoDaddy | `GODADDY_API_KEY`, `GODADDY_API_SECRET` |
| deSEC | `DESEC_TOKEN` |
| Hetzner | `HETZNER_API_KEY` |
| OVH | `OVH_ENDPOINT`, `OVH_APPLICATION_KEY`, `OVH_APPLICATION_SECRET`, `OVH_CONSUMER_KEY` |

Stackr validates that all required env vars are present before deploying.

### Catalog updates

```bash
# Download the latest catalog from GitHub
stackr catalog update

# Pin to a specific release
stackr catalog update --tag v1.2.0

# Show current catalog version and app count
stackr catalog version
```

The downloaded catalog is stored at `~/.stackr/catalog/` and takes priority over the built-in one.
To revert to the built-in catalog, remove `~/.stackr/catalog/`.

### Adding a custom app

Create the following structure:

```
catalog/<category>/<app-name>/
  app.yml           # metadata, ports, host_ports, volumes, deps
  compose.yml.j2    # Jinja2 compose template
```

Minimal `app.yml` for a Traefik-proxied app:

```yaml
name: my-app
display_name: My App
description: What it does
category: management
homepage: https://...
exposure: external
requires:
  - traefik
ports:
  - 8080          # container port passed to traefik_labels()
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
    labels:
{% for k, v in traefik_labels(8080).items() %}
      - "{{ k }}={{ v }}"
{% endfor %}

networks:
  proxy:
    external: true
```

For apps without a web UI (databases, VPN tunnels, daemon services), omit the `proxy` network
and `traefik_labels()` entirely. See `catalog/database/postgres/` for an example.

## State and rollback

Stackr tracks every deployed app in `~/.stackr/state.json`. Each entry stores:
- Full rendered compose YAML (for genuine rollback)
- Compose content hash (for skip-unchanged detection)
- Image digests per service (for upstream update detection)
- Deployed timestamp

```bash
stackr rollback jellyfin   # redeploys from stored compose content
```

## Checking environment health

```bash
stackr doctor
```

Runs 8+ checks including:
- Docker daemon reachable
- `docker compose` plugin installed
- `proxy` and `socket_proxy` networks exist
- State file is valid JSON
- DNS provider env vars are set
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

The restic repository password is auto-generated on first use and stored in `.stackr.env`
as `STACKR_RESTIC_PASSWORD`.

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
# Mount all configured shares
stackr mount

# Unmount all configured shares
stackr umount
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

Apps are matched against the Stackr catalog. Unmapped names are listed so you can
add them manually.

## Web UI

A browser-based dashboard is included in the base install:

```bash
# Launch on localhost:8000
stackr web

# Custom host / port
stackr web --host 0.0.0.0 --port 9000
```

The web UI provides:
- App grid showing enabled/deployed status for every configured app
- One-click enable/disable toggle (updates `stackr.yml`)
- Per-app and full-stack deploy buttons
- Live log streaming via Server-Sent Events

## Interactive TUI

The `stackr ui` command opens a full-terminal app browser built with [Textual](https://textual.textualize.io/). It is included in the base install — no extra required.

```bash
# Launch
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
│ ▼ network          │  Requires:  traefik                 │
│   ✓ traefik        │                                     │
│   ○ pihole         │  Variables:                         │
│                    │   • hardware_accel = 'none'          │
│                    │     (vaapi, nvidia, intel_qsv)       │
├────────────────────┴─────────────────────────────────────┤
│ Space toggle  •  S save  •  Q quit                       │
└──────────────────────────────────────────────────────────┘
```

### Key bindings

| Key | Action |
|-----|--------|
| `Space` | Toggle the highlighted app on/off |
| `S` | Save current state to `stackr.yml` |
| `Q` | Quit |

If `stackr.yml` already exists, the TUI pre-populates enabled/disabled state from it.
Saving writes the complete toggle state back to the file, preserving existing `vars` and
`overrides` for entries that were already present.

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
pytest tests/ -v
pytest --cov=stackr --cov-report=term-missing
```

### Linting and type checking

```bash
ruff check stackr tests
mypy stackr
```

### Project structure

```
stackr/
  cli.py            Typer CLI — all user-facing commands
  config.py         Pydantic config models (StackrConfig, AppConfig, …)
  catalog.py        App catalog loader; prefers ~/.stackr/catalog/ over built-in
  renderer.py       Jinja2 compose renderer + Traefik label generation
  secrets.py        Secret resolution and .stackr.env management
  state.py          State lock file (~/.stackr/state.json) with image digest tracking
  deployer.py       Deploy orchestration, rollback, and image update detection
  validator.py      Pre-deploy validation checks
  doctor.py         Environment health checks (stackr doctor)
  images.py         Image digest inspection and change detection
  catalog_sync.py   GitHub catalog download and install
  dns_providers.py  Registry of DNS providers and their required env vars
  middleware.py     Traefik forward-auth and CrowdSec middleware label generators
  network.py        Docker network helpers
  status.py         Rich terminal status table
  tui.py            Textual TUI app browser (stackr ui; requires textual extra)
  backup.py         Restic-based backup/restore (backup, restore, snapshots commands)
  migrate.py        Deployrr → stackr.yml migration (stackr migrate)
  alerts.py         Push notifications via ntfy, Gotify, or webhook
  doctor.py         Environment health checks (stackr doctor)
  mounts.py         Remote share mounting: SMB, NFS, Rclone (stackr mount/umount)
  web/              Optional FastAPI + HTMX web UI (stackr web; requires web extra)
    app.py          FastAPI application factory
    routes.py       API route handlers
    templates/      Jinja2 + HTMX HTML templates

catalog/
  ai/               ollama, open-webui
  database/         postgres, mariadb, redis, mongo
  gaming/           minecraft
  management/       portainer, dozzle, watchtower, heimdall, dasherr, flame
  media/            jellyfin, plex, radarr, sonarr, prowlarr, bazarr, lidarr,
                    readarr, overseerr, jellyseerr, tdarr, sabnzbd, qbittorrent,
                    transmission
  monitoring/       uptime-kuma, grafana, prometheus, loki, netdata
  network/          traefik, adguardhome, pihole, wireguard, headscale,
                    nginx-proxy-manager
  productivity/     gitea, paperless-ngx, freshrss, miniflux
  security/         socket-proxy, crowdsec, authentik, authelia, vaultwarden
  storage/          nextcloud, filebrowser, duplicati
  dashboard/        homepage

tests/
  test_catalog.py         Catalog loading and seed app presence
  test_catalog_sync.py    GitHub catalog download logic
  test_config.py          Config schema and validation
  test_deployer.py        Deploy orchestration and rollback
  test_dns_providers.py   DNS provider registry
  test_doctor.py          Environment health checks
  test_images.py          Image digest tracking
  test_middleware.py      Traefik middleware label generators
  test_renderer.py        Jinja2 rendering and smoke tests for all apps
  test_secrets.py         Secret resolution and .stackr.env management
  test_security_apps.py   Security stack app rendering and validation
  test_state.py           State lock file and image digest persistence
  test_tui.py             TUI helper functions; class/mount tests skip if textual absent
  test_validator.py       Pre-deploy validation checks
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
| `textual` | Terminal UI framework for `stackr ui` |
| `fastapi` | ASGI web framework for `stackr web` |
| `uvicorn` | ASGI server for `stackr web` |

**Development:**

| Package | Purpose |
|---------|---------|
| `pytest` | Test runner |
| `pytest-mock` | Mocking utilities |
| `ruff` | Linting and formatting |
| `mypy` | Static type checking |

## CI

GitHub Actions runs on every push and pull request:

- `ruff check` — linting
- `mypy` — type checking
- `pytest` — full test suite with catalog render smoke test for all 38 seed apps

## License

MIT
