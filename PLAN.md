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

network:
  mode: external                  # internal | external | hybrid
  domain: example.com
  local_domain: home.example.com

traefik:
  enabled: true
  acme_email: user@example.com
  dns_provider: cloudflare        # cloudflare | route53 | namecheap | porkbun | etc.
  dns_provider_env:
    CF_DNS_API_TOKEN: "${CF_DNS_API_TOKEN}"

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
  - name: radarr
    enabled: true
  - name: prowlarr
    enabled: true
  - name: traefik
    enabled: true
  - name: authentik
    enabled: true
```

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
requires:
  - traefik          # optional dependency declaration
vars:
  hardware_accel:
    type: select
    options: [none, vaapi, nvidia, intel_qsv]
    default: none
    description: Hardware transcoding acceleration
ports:
  - 8096             # Jellyfin web UI (internal use only, Traefik handles external)
volumes:
  - name: config
    path: /config
  - name: media
    path: /media
    external: true   # User must mount this
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
stackr plan                   # Show what would be deployed (dry run)
stackr deploy                 # Deploy/update all enabled apps
stackr deploy <app>           # Deploy a specific app
stackr stop <app>             # Stop a specific app
stackr remove <app>           # Remove a specific app and its containers
stackr update                 # Pull latest images and redeploy
stackr backup                 # Run backup now
stackr restore <snapshot>     # Restore from a backup snapshot
stackr status                 # Show running/stopped status of all apps
stackr logs <app>             # Tail logs for an app
stackr ui                     # Launch the TUI interactive selector
stackr web                    # Start the optional web UI (FastAPI)
stackr catalog update         # Pull latest catalog from GitHub
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

## Implementation Phases

### Phase 1 — Foundation (MVP)
**Goal**: Deploy a basic set of apps from a config file.

- [ ] Project setup (pyproject.toml, uv, Typer CLI skeleton)
- [ ] Config loading with Pydantic validation (`stackr.yml`)
- [ ] App catalog loader (reads `catalog/*/app.yml`)
- [ ] Jinja2 compose renderer
- [ ] `stackr init` wizard (prompts for basic settings, writes `stackr.yml`)
- [ ] `stackr deploy` (renders templates → runs `docker compose up -d`)
- [ ] `stackr status` (wraps `docker compose ps`)
- [ ] Traefik app entry with socket-proxy support
- [ ] 10 seed apps: traefik, portainer, jellyfin, radarr, sonarr, prowlarr, homepage, uptime-kuma, adguardhome, vaultwarden

### Phase 2 — Security & Networking
**Goal**: Full security stack out of the box.

- [ ] Socket proxy integration (all apps route through it)
- [ ] CrowdSec integration
- [ ] Authentik app template + auto-configuration
- [ ] Authelia app template
- [ ] Multi-DNS provider support (Cloudflare, Route53, Porkbun, Namecheap)
- [ ] Internal / External / Hybrid networking modes
- [ ] `stackr plan` dry-run command

### Phase 3 — App Catalog Expansion
**Goal**: Reach parity with Deployrr's 150+ apps.

- [ ] All 24 categories from Deployrr's app list
- [ ] App dependency resolution (e.g., Radarr requires a download client)
- [ ] App variable prompts and validation
- [ ] `stackr search` and `stackr list` commands

### Phase 4 — TUI
**Goal**: Point-and-click terminal experience.

- [ ] Textual TUI for app browsing and toggling
- [ ] Live compose preview pane
- [ ] Config editor within TUI
- [ ] `stackr ui` command

### Phase 5 — Operations
**Goal**: Day-2 operations: backup, update, monitoring.

- [ ] Backup/restore (`borgbackup` or `restic` integration)
- [ ] `stackr update` (pull images, rolling redeploy)
- [ ] `stackr logs` with follow mode
- [ ] Remote share mounting (SMB, NFS, Rclone) via pre-deploy hooks
- [ ] Health checks and alerts (optional ntfy/Gotify integration)

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
| TUI                        | No                    | Yes (Textual)                       |
| Web UI                     | Yes (PHP)             | Optional (FastAPI + HTMX)           |

---

## Install Experience (Goal)

```bash
# One-command install (like Deployrr)
curl -fsSL https://raw.githubusercontent.com/your-org/stackr/main/install.sh | bash

# Or via pipx
pipx install stackr

# Then
stackr init       # guided setup
stackr deploy     # everything up and running
```

---

## Immediate Next Steps

1. Initialize Python project with `uv init` and Typer
2. Define Pydantic config schema for `stackr.yml`
3. Build catalog loader and Jinja2 renderer
4. Create first 3 app templates (traefik, socket-proxy, jellyfin) to prove the pattern
5. Wire up `stackr deploy` end-to-end
6. Write `install.sh`
