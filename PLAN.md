# Deployrr Alternative: "Stackr" — Implementation Plan

## What Deployrr Is (and Its Shortcomings)

Deployrr is a homelab Docker Compose automation platform with:
- 150+ pre-configured self-hosted applications
- Traefik reverse proxy with automatic SSL
- Security stack (socket proxy, CrowdSec, SSO)
- Backup/restore, monitoring, remote share mounting
- Web UI for point-and-click management

**Key limitations that this project improves on:**
- PHP + Bash codebase — hard to extend, maintain, and contribute to
- Distributed as opaque `.app` binaries — difficult to audit or modify
- Only Cloudflare for DNS challenges
- Only Ubuntu/Debian Linux
- Tightly coupled architecture (everything assumes Traefik + specific folder structure)
- No declarative configuration — state is implicit

---

## Proposed Architecture: "Stackr"

A modern, open, composable homelab deployment tool built in Python.

### Core Design Principles

1. **Declarative** — describe what you want in a YAML config file; Stackr figures out the rest
2. **Composable** — apps are independent; pick exactly what you want
3. **Auditable** — everything is plain text (YAML + Jinja2 templates), no binary blobs
4. **Multi-distro** — works on any distro with Docker installed
5. **Multi-provider** — DNS challenges via ACME for Cloudflare, Route53, Namecheap, Porkbun, etc.
6. **Community-first** — app catalog is a plain folder of YAML files anyone can contribute to

---

## Technology Stack

| Component       | Choice              | Reason                                              |
|----------------|---------------------|-----------------------------------------------------|
| Language        | Python 3.11+        | Rich ecosystem, readable, Jinja2 templating built-in|
| CLI framework   | Typer               | Auto-generated help, type safety, intuitive API     |
| TUI             | Textual             | Full terminal UI for interactive app selection      |
| Templates       | Jinja2              | Industry-standard, flexible Docker Compose rendering|
| Config format   | YAML                | Human-readable, easy to diff/version-control        |
| Web UI (opt.)   | FastAPI + HTMX      | Lightweight, no heavy JS framework needed           |
| Package mgmt    | uv / pipx           | Fast, modern Python packaging                       |
| Distribution    | Single zipapp or pipx install | Easy one-command install               |

---

## Repository Structure

```
stackr/
├── stackr/                    # Main Python package
│   ├── __init__.py
│   ├── cli.py                 # Typer CLI entrypoint
│   ├── tui.py                 # Textual TUI app selector
│   ├── config.py              # User config loading/validation (Pydantic)
│   ├── catalog.py             # App catalog loader
│   ├── renderer.py            # Jinja2 compose file renderer
│   ├── deployer.py            # docker compose up/down/pull orchestration
│   ├── traefik.py             # Traefik config generator
│   ├── secrets.py             # .env file and secret management
│   ├── state.py               # Deployed state tracking (lock file)
│   ├── validator.py           # Pre-deploy conflict and config validation
│   ├── backup.py              # Backup/restore logic
│   ├── network.py             # Docker network setup
│   └── web/                   # Optional FastAPI web UI
│       ├── app.py
│       ├── routes.py
│       └── templates/         # HTMX Jinja2 HTML templates
│
├── catalog/                   # App catalog (community-contributed)
│   ├── _base/                 # Shared base templates
│   │   ├── socket-proxy.yml.j2
│   │   └── traefik-labels.yml.j2
│   ├── media/
│   │   ├── jellyfin/
│   │   │   ├── app.yml        # App metadata
│   │   │   └── compose.yml.j2 # Jinja2 compose template
│   │   ├── plex/
│   │   └── ...
│   ├── monitoring/
│   ├── security/
│   ├── network/
│   ├── databases/
│   ├── ai/
│   └── ...                    # All 24 categories from Deployrr
│
├── tests/
│   ├── test_config.py         # Pydantic schema validation tests
│   ├── test_renderer.py       # Jinja2 template rendering tests
│   ├── test_catalog.py        # Catalog loader and validation tests
│   ├── test_validator.py      # Conflict detection tests
│   └── catalog/               # Render smoke tests for every catalog entry
│
├── .github/
│   └── workflows/
│       ├── ci.yml             # Lint, test, catalog render dry-run on every PR
│       └── catalog-validate.yml # Validate new/changed catalog entries
│
├── stackr.yml.example         # Example user config file
├── pyproject.toml
├── README.md
└── install.sh                 # One-command installer
```

---

## Core Configuration File (`stackr.yml`)

Users maintain a single config file that Stackr reads:

```yaml
# stackr.yml
global:
  data_dir: /opt/appdata          # Where container data is stored
  timezone: America/New_York
  puid: 1000
  pgid: 1000

catalog:
  source: github                  # github | local
  version: v1.2.0                 # Pin to a specific catalog release; "latest" for HEAD
  local_path: null                # Path to local catalog dir when source: local

network:
  mode: external                  # internal | external | hybrid  (see Networking Modes below)
  domain: example.com
  local_domain: home.example.com

traefik:
  enabled: true
  acme_email: user@example.com
  dns_provider: cloudflare        # cloudflare | route53 | namecheap | porkbun | etc.
  dns_provider_env:
    CF_DNS_API_TOKEN: "${CF_DNS_API_TOKEN}"  # Resolved from shell env at deploy time

security:
  socket_proxy: true
  crowdsec: true
  auth_provider: authentik         # authentik | authelia | google_oauth | none

backup:
  enabled: true
  destination: /mnt/backup
  schedule: "0 2 * * *"           # cron expression

apps:
  - name: jellyfin
    enabled: true
    vars:
      hardware_accel: vaapi
    overrides:                     # Optional: patch the rendered compose YAML
      services:
        jellyfin:
          mem_limit: 4g
  - name: radarr
    enabled: true
  - name: prowlarr
    enabled: true
  - name: traefik
    enabled: true
  - name: authentik
    enabled: true
  - name: my-custom-app           # App not in the catalog
    enabled: true
    catalog_path: ./local-catalog/my-custom-app  # Points to a local app directory
```

---

## Networking Modes

The `network.mode` field controls how Traefik and apps are exposed:

| Mode       | Description |
|------------|-------------|
| `external` | Traefik handles a public domain with ACME certs (Let's Encrypt via DNS challenge). All app subdomains resolve publicly. Use for servers reachable from the internet. |
| `internal` | Traefik handles a local-only domain (e.g., `home.example.com`). Certs issued via a private ACME CA (e.g., Step CA) or self-signed. Use for LAN-only homelabs. |
| `hybrid`   | Both modes active. Apps declare `exposure: external` or `exposure: internal` in their `app.yml`. Traefik runs two entrypoints with separate cert resolvers. |

All three modes still use the socket proxy — no app container ever touches the Docker socket directly.

---

## Secret Management

Stackr never stores secrets in `stackr.yml`. Instead:

### Resolution Order
1. **Shell environment** — `${VAR_NAME}` in `stackr.yml` is substituted from the calling shell's environment at deploy time.
2. **`.stackr.env` file** — a gitignored file in the same directory as `stackr.yml` that holds sensitive values (API tokens, passwords). Stackr loads this automatically before rendering templates.
3. **Auto-generated secrets** — for app-internal secrets (e.g., Vaultwarden admin token, Authentik secret key), Stackr generates a random value on first deploy and stores it in `.stackr.env` for idempotency.

### `.stackr.env` format
```bash
# .stackr.env  — DO NOT COMMIT THIS FILE
CF_DNS_API_TOKEN=your-token-here
VAULTWARDEN_ADMIN_TOKEN=generated-on-first-deploy
AUTHENTIK_SECRET_KEY=generated-on-first-deploy
```

### Rules
- `.stackr.env` is created by `stackr init` and added to `.gitignore` automatically.
- `stackr validate` warns if any `${VAR}` references in `stackr.yml` are unresolved.
- Stackr never writes secrets into rendered compose files — they are passed as env file references (`env_file: .stackr.env`) or via Docker secrets where supported.

---

## State Management

Stackr maintains a lock file at `~/.stackr/state.json` (path configurable) to track deployed state:

```json
{
  "deployed_at": "2024-01-15T02:00:00Z",
  "catalog_version": "v1.2.0",
  "apps": {
    "jellyfin": {
      "enabled": true,
      "compose_hash": "abc123",
      "image_digest": "sha256:...",
      "deployed_at": "2024-01-15T02:00:00Z"
    },
    "traefik": {
      "enabled": true,
      "compose_hash": "def456",
      "image_digest": "sha256:...",
      "deployed_at": "2024-01-14T10:00:00Z"
    }
  }
}
```

This enables:
- `stackr status` to show **drift** — containers that are running but not in state, or in state but not running
- `stackr update` to only redeploy apps whose compose hash or image digest has changed
- `stackr rollback` to redeploy the last known-good compose for an app
- Meaningful diffs in `stackr plan` (current state vs. desired state)

---

## Pre-Deploy Validation

Before any deploy, Stackr runs a validation pass that fails fast with clear errors:

- **Unresolved secrets**: any `${VAR}` not found in env or `.stackr.env`
- **Port conflicts**: two enabled apps declaring the same host port
- **Container name conflicts**: duplicate `container_name` across rendered templates
- **Missing dependencies**: app declares `requires: [traefik]` but traefik is not enabled
- **Invalid vars**: app var value not in the declared `options` list
- **External volumes missing**: volumes marked `external: true` that don't exist on the host

Run explicitly with `stackr validate` or automatically before every `stackr deploy`.

---

## App Catalog Format

Each app is a self-contained directory:

```yaml
# catalog/media/jellyfin/app.yml
name: jellyfin
display_name: Jellyfin
description: Free and open source media server
category: media
icon: jellyfin.png
homepage: https://jellyfin.org
version: latest
exposure: external              # external | internal | hybrid (used in hybrid network mode)
requires:
  - traefik                     # hard dependency — must be enabled
suggests:
  - authentik                   # soft dependency — warned if not enabled, not blocking
vars:
  hardware_accel:
    type: select
    options: [none, vaapi, nvidia, intel_qsv]
    default: none
    description: Hardware transcoding acceleration
ports:
  - 8096                        # Registered in global port registry to detect conflicts
volumes:
  - name: config
    path: /config
  - name: media
    path: /media
    external: true              # User must mount this — validated before deploy
```

```yaml
# catalog/media/jellyfin/compose.yml.j2  (Jinja2 template)
services:
  jellyfin:
    image: jellyfin/jellyfin:{{ vars.version | default('latest') }}
    container_name: jellyfin
    environment:
      - PUID={{ global.puid }}
      - PGID={{ global.pgid }}
      - TZ={{ global.timezone }}
    volumes:
      - {{ global.data_dir }}/jellyfin/config:/config
      - {{ media_path }}:/media:ro
    {% if vars.hardware_accel == 'vaapi' %}
    devices:
      - /dev/dri:/dev/dri
    {% endif %}
    networks:
      - proxy
    labels:
      {{ traefik_labels('jellyfin', 8096) }}
    restart: unless-stopped
```

---

## CLI Commands

```
stackr init                   # Interactive setup wizard, generates stackr.yml
stackr list                   # List all available apps in the catalog
stackr list --category media  # Filter by category
stackr search <query>         # Search the catalog
stackr validate               # Validate stackr.yml, resolve secrets, check conflicts (no deploy)
stackr render <app>           # Print the generated compose YAML for an app (debug)
stackr plan                   # Show what would change vs. current deployed state (dry run)
stackr deploy                 # Deploy/update all enabled apps
stackr deploy <app>           # Deploy a specific app
stackr stop <app>             # Stop a specific app
stackr restart <app>          # Restart a specific app without full redeploy
stackr remove <app>           # Remove a specific app and its containers
stackr shell <app>            # Open an interactive shell in a running app container
stackr update                 # Pull latest images and redeploy changed apps only
stackr rollback <app>         # Redeploy the last known-good compose for an app
stackr backup                 # Run backup now
stackr restore <snapshot>     # Restore from a backup snapshot
stackr status                 # Show running/stopped/drifted status of all apps
stackr logs <app>             # Tail logs for an app
stackr ui                     # Launch the TUI interactive selector
stackr web                    # Start the optional web UI (FastAPI)
stackr catalog update         # Pull latest catalog from GitHub (respects version pin)
stackr catalog version        # Show current catalog version and available releases
stackr migrate --from deployrr  # Import Deployrr app list and generate stackr.yml
```

---

## TUI (Interactive App Selector)

Built with Textual, the TUI allows:
- Browse apps by category
- Read app descriptions and requirements
- Toggle apps on/off with spacebar
- Edit per-app variables inline
- Preview the generated compose YAML before deploying

---

## Testing Strategy

### Unit Tests (`tests/`)
- `test_config.py` — valid and invalid `stackr.yml` schemas, secret resolution, override merging
- `test_renderer.py` — Jinja2 template rendering for each hardware/network/var combination
- `test_catalog.py` — catalog loader: missing fields, invalid var types, circular dependencies
- `test_validator.py` — port conflicts, name conflicts, missing dependencies, unresolved secrets

### Catalog Smoke Tests
Every catalog entry must pass a render dry-run with a minimal config. These run in CI on every PR that touches `catalog/`.

### CI (GitHub Actions)
- **On every PR**: lint (`ruff`), type check (`mypy`), unit tests, catalog render dry-run for changed entries
- **On catalog PRs**: validate `app.yml` schema, render all var combinations, check for port conflicts with existing catalog
- **Nightly**: full render of all 150+ apps against a reference config to catch catalog regressions

---

## Implementation Phases

### Phase 1 — Foundation (MVP)
**Goal**: Deploy a basic set of apps from a config file.

- [ ] Project setup (pyproject.toml, uv, Typer CLI skeleton)
- [ ] Config loading with Pydantic validation (`stackr.yml`)
- [ ] Secret resolution from shell env and `.stackr.env`; auto-generated secrets on first init
- [ ] App catalog loader (reads `catalog/*/app.yml`)
- [ ] Jinja2 compose renderer
- [ ] Pre-deploy validation: unresolved secrets, port conflicts, name conflicts, missing hard dependencies
- [ ] State lock file (`~/.stackr/state.json`) — write on deploy, read on status/plan
- [ ] `stackr init` wizard (prompts for basic settings, writes `stackr.yml` and `.stackr.env`, updates `.gitignore`)
- [ ] `stackr validate` — standalone validation command
- [ ] `stackr render <app>` — print rendered compose for debugging
- [ ] `stackr deploy` (validate → render → pull images → `docker compose up -d`; abort with error on validation failure)
- [ ] `stackr status` (live Docker state + drift detection against state file)
- [ ] Traefik app entry with socket-proxy support
- [ ] 10 seed apps: traefik, portainer, jellyfin, radarr, sonarr, prowlarr, homepage, uptime-kuma, adguardhome, vaultwarden
- [ ] Unit tests for config, renderer, catalog loader, and validator
- [ ] GitHub Actions CI (lint + tests)

### Phase 2 — Security & Networking
**Goal**: Full security stack out of the box.

- [ ] Socket proxy integration (all apps route through it)
- [ ] CrowdSec integration
- [ ] Authentik app template + auto-configuration
- [ ] Authelia app template
- [ ] Multi-DNS provider support (Cloudflare, Route53, Porkbun, Namecheap)
- [ ] All three networking modes (external, internal, hybrid) with cert resolver variants
- [ ] `stackr plan` — diff current state vs. desired state
- [ ] `stackr rollback <app>` — redeploy last known-good compose from state file

### Phase 3 — App Catalog Expansion
**Goal**: Reach parity with Deployrr's 150+ apps.

- [ ] All 24 categories from Deployrr's app list
- [ ] App dependency resolution (hard `requires` + soft `suggests`)
- [ ] App variable prompts and validation
- [ ] `stackr search` and `stackr list` commands
- [ ] Catalog render smoke tests for all entries in CI
- [ ] Port registry across the full catalog (detect conflicts at catalog level, not just at deploy time)

### Phase 4 — TUI
**Goal**: Point-and-click terminal experience.

- [ ] Textual TUI for app browsing and toggling
- [ ] Live compose preview pane
- [ ] Config editor within TUI
- [ ] `stackr ui` command

### Phase 5 — Operations
**Goal**: Day-2 operations: backup, update, monitoring.

- [ ] Backup/restore (`borgbackup` or `restic` integration)
- [ ] `stackr update` (pull images, redeploy only apps with changed image digest or compose hash)
- [ ] `stackr logs <app>` with follow mode
- [ ] `stackr restart <app>` and `stackr shell <app>`
- [ ] Remote share mounting (SMB, NFS, Rclone) via pre-deploy hooks
- [ ] Health checks and alerts (optional ntfy/Gotify integration)
- [ ] `stackr migrate --from deployrr` — parse Deployrr state and emit a `stackr.yml`

### Phase 6 — Web UI (Optional)
**Goal**: Browser-based management.

- [ ] FastAPI backend (reuses all CLI logic)
- [ ] HTMX frontend (app grid, toggle, logs viewer)
- [ ] `stackr web` to launch it as a container or local process

---

## Key Improvements Over Deployrr

| Feature                    | Deployrr              | Stackr                              |
|----------------------------|-----------------------|-------------------------------------|
| Language                   | PHP + Bash            | Python (readable, testable)         |
| Distribution               | Opaque binary `.app`  | Open source, pip/pipx installable   |
| Config                     | Implicit / wizard     | Declarative `stackr.yml`            |
| DNS providers              | Cloudflare only       | Cloudflare, Route53, Porkbun, etc.  |
| OS support                 | Ubuntu/Debian only    | Any Linux with Docker               |
| App catalog                | Bundled in binary     | Plain YAML files on GitHub          |
| Community contributions    | Closed                | Fork → add `catalog/app/` → PR      |
| Version control friendly   | No                    | Yes — `stackr.yml` is diffable      |
| CI/CD integration          | No                    | Yes — `stackr deploy` in pipelines  |
| Secret management          | Manual                | Auto-generated, env-resolved        |
| State tracking             | None                  | Lock file with drift detection      |
| Pre-deploy validation      | None                  | Conflicts, secrets, deps checked    |
| TUI                        | No                    | Yes (Textual)                       |
| Web UI                     | Yes (PHP)             | Optional (FastAPI + HTMX)           |
| Catalog versioning         | N/A                   | Pinnable to a release tag           |
| Migration from Deployrr    | N/A                   | `stackr migrate --from deployrr`    |

---

## Install Experience (Goal)

```bash
# One-command install (like Deployrr)
curl -fsSL https://raw.githubusercontent.com/your-org/stackr/main/install.sh | bash

# Or via pipx
pipx install stackr

# Then
stackr init       # guided setup — writes stackr.yml, .stackr.env, updates .gitignore
stackr deploy     # validates, renders, pulls images, starts everything
```

---

## Immediate Next Steps

1. Initialize Python project with `uv init` and Typer
2. Define Pydantic config schema for `stackr.yml` (including `catalog`, `overrides`, and `catalog_path` fields)
3. Design and implement `secrets.py` — env resolution, `.stackr.env` loading, auto-generation
4. Design state lock file schema and `state.py`
5. Build catalog loader and Jinja2 renderer
6. Implement pre-deploy validator (secrets, ports, names, deps)
7. Create first 3 app templates (traefik, socket-proxy, jellyfin) to prove the pattern
8. Wire up `stackr deploy` end-to-end with validate → render → pull → up
9. Write unit tests for all core modules
10. Write `install.sh` and set up GitHub Actions CI
