# Stackr Rebuild Design

**Date:** 2026-05-21
**Status:** Approved
**Scope:** Full greenfield rebuild — no backwards compatibility requirement

---

## Goals

- API-first architecture: every capability reachable via REST API
- Always-on web UI served by a system service (systemd/launchd)
- Full management from the browser: apps, settings, mounts, logs, history, rollback
- Docker SDK for live status/inspection; subprocess for compose orchestration
- SQLite-backed state replacing the JSON lock file
- Structured error capture: every deploy operation result stored and surfaced in UI
- Drop TUI (Textual) entirely
- Single app catalog path with CI-enforced template validation
- CLI as API client when service is running; standalone fallback for scripting

---

## Section 1: Package Structure

```
stackr/
├── engine/              # Pure business logic — no HTTP, no CLI
│   ├── config.py            # Pydantic v2 config schema
│   ├── catalog.py           # App catalog loading and validation
│   ├── renderer.py          # Jinja2 template rendering
│   ├── validator.py         # Pre-deploy validation
│   ├── deployer.py          # Deploy orchestration
│   ├── state.py             # SQLite state management
│   ├── docker.py            # Docker SDK + subprocess hybrid
│   ├── secrets.py           # Secret resolution
│   ├── backup.py            # Restic backup/restore
│   ├── mounts.py            # SMB/NFS/Rclone mount management
│   └── alerts.py            # ntfy/Gotify/webhook notifications
├── api/                 # FastAPI REST API — thin shell over engine
│   ├── app.py               # FastAPI factory, service startup
│   ├── models.py            # Pydantic request/response models
│   └── routes/
│       ├── apps.py
│       ├── deploy.py
│       ├── config.py
│       ├── catalog.py
│       ├── mounts.py
│       └── system.py
├── cli/                 # Typer CLI — API client or standalone fallback
│   └── commands.py
├── web/                 # Static frontend — served by FastAPI
│   └── static/
│       ├── index.html
│       ├── app.js
│       └── style.css
├── catalog/             # Single app catalog path
│   └── <category>/<app>/
│       ├── app.yml
│       └── compose.yml.j2
└── service.py           # systemd/launchd service management (kept)
```

**Removed from current codebase:**
- `tui.py` — deleted, Textual removed from dependencies
- `web/templates/` — replaced by static files in `web/static/`
- `app_catalog/` — unified into `catalog/` (no more dual path)

---

## Section 2: State Management (SQLite)

**Location:** `~/.stackr/stackr.db`

Replaces `~/.stackr/state.json`. SQLite WAL mode for concurrent-safe reads/writes.

### Schema

```sql
CREATE TABLE app_state (
    name          TEXT PRIMARY KEY,
    enabled       INTEGER NOT NULL DEFAULT 0,
    compose_hash  TEXT,
    compose_yaml  TEXT,           -- stored for rollback
    status        TEXT,           -- 'running' | 'stopped' | 'degraded' | 'unknown' | 'drift'
    deployed_at   TEXT,           -- ISO timestamp
    last_error    TEXT            -- last deploy error message, if any
);

CREATE TABLE image_digests (
    app_name      TEXT NOT NULL,
    service_name  TEXT NOT NULL,
    digest        TEXT NOT NULL,
    checked_at    TEXT NOT NULL,
    PRIMARY KEY (app_name, service_name)
);

CREATE TABLE deploy_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    app_name      TEXT NOT NULL,
    event_type    TEXT NOT NULL,  -- 'deploy' | 'stop' | 'rollback' | 'remove'
    success       INTEGER NOT NULL,
    stdout        TEXT,
    stderr        TEXT,
    exit_code     INTEGER,
    duration_ms   INTEGER,
    command       TEXT,           -- exact command that ran
    started_at    TEXT NOT NULL
);
```

### Migration

`stackr install` reads `~/.stackr/state.json` if present and imports it into the DB on first run.

---

## Section 3: Docker Integration

### Docker SDK — observation layer

`engine/docker.py` owns all Docker SDK calls:

```python
def get_container_status(app_name: str) -> ContainerStatus
def get_image_digests(services: list[str]) -> dict[str, str]
def stream_events(app_name: str) -> Iterator[DockerEvent]
def inspect_network(name: str) -> dict | None
def inspect_volume(name: str) -> dict | None
```

### Subprocess — orchestration layer

```python
def compose_up(compose_path: Path, pull: bool) -> OperationResult
def compose_down(compose_path: Path) -> OperationResult
def compose_pull(compose_path: Path) -> OperationResult
def compose_logs(compose_path: Path, service: str | None) -> Iterator[str]
```

### OperationResult

Every subprocess call returns a structured result — no swallowed errors:

```python
@dataclass
class OperationResult:
    success: bool
    app_name: str
    event_type: str
    stdout: str
    stderr: str
    exit_code: int | None
    duration_ms: int
    command: str | None
    error: str | None        # human-readable summary if failed
```

Every `OperationResult` is written to `deploy_events` in the DB regardless of success or failure.

### Status reconciliation

`GET /api/v1/apps` calls Docker SDK for live container status and merges with DB state. Per-app `health` field:

| Value | Meaning |
|-------|---------|
| `running` | DB says deployed, Docker confirms container up |
| `stopped` | DB says deployed, Docker says container exited |
| `degraded` | Some services in the compose are down |
| `unknown` | No DB record, no Docker container |
| `drift` | Image digest in Docker differs from what was deployed |

`drift` is detected at startup and on every `GET /api/v1/apps` call (with 5s cache). The UI flags it and offers a reconcile action.

---

## Section 4: REST API

**Base URL:** `http://localhost:7274/api/v1`

FastAPI with full OpenAPI docs at `/docs`.

### Routes

```
/api/v1/apps
  GET    /                     List all apps with live Docker status
  GET    /{name}               App detail: status, vars, last error
  POST   /{name}/toggle        Enable or disable
  POST   /{name}/deploy        Deploy single app (validates first)
  POST   /{name}/rollback      Redeploy last known-good compose from DB
  GET    /{name}/logs          SSE stream of docker compose logs
  GET    /{name}/history       Deploy event history from DB
  GET    /{name}/vars          Current var overrides
  PUT    /{name}/vars          Update var overrides

/api/v1/deploy
  POST   /                     Deploy all enabled apps (validates first)
  GET    /status               Current deploy job status: running/idle + progress

/api/v1/config
  GET    /                     Full current config
  PUT    /global               Update global section
  PUT    /network              Update network section
  PUT    /security             Update security section
  PUT    /backup               Update backup section
  PUT    /alerts               Update alerts section

/api/v1/catalog
  GET    /                     All catalog apps with metadata
  GET    /{name}               Single catalog entry

/api/v1/mounts
  GET    /                     List configured mounts
  POST   /                     Add mount
  DELETE /{name}               Remove mount

/api/v1/system
  GET    /health               Doctor checks: Docker reachable, networks, secrets
  GET    /secrets              Secret names (never values)
  POST   /validate             Pre-deploy validation — returns errors and warnings
  POST   /backup               Trigger backup
  GET    /snapshots            List restic snapshots
```

### Key design decisions

- All responses are typed Pydantic models — no raw dicts
- `POST /deploy` and `POST /apps/{name}/deploy` are async-safe: start a job, return immediately with a job ID; poll `GET /deploy/status` for progress
- Config `PUT` endpoints are section-specific — writing network config cannot touch global config
- Validation always runs before any deploy — deploy is rejected with structured errors if validation fails
- `GET /apps` live status is cached for 5s to avoid hammering Docker SDK on rapid refreshes

---

## Section 5: App Catalog

### Single path

`stackr/catalog/<category>/<app>/` is the only catalog location. Ships inside the Python package. No more `catalog/` repo mirror that must be manually kept in sync.

User overlay at `~/.stackr/catalog/<app>/` still takes priority for power-user overrides.

### Strict `app.yml` schema (Pydantic-validated on load)

```yaml
name: jellyfin
display_name: Jellyfin
description: Media server
category: media
vars:
  - name: JELLYFIN_PORT
    default: "8096"
    description: Web UI port
ports: [8096, 8920]
host_ports: [8096]
volumes:
  - jellyfin_config
  - jellyfin_cache
requires: []
suggests: []
```

### CI template validation (every app, every PR)

1. Render `compose.yml.j2` with default vars and stub config
2. Parse rendered YAML — must be valid
3. Every `port` in `app.yml` appears in rendered compose
4. Every `volume` in `app.yml` appears in rendered compose
5. Every `var` in `app.yml` is referenced in the template
6. No template variable references a var not declared in `app.yml`

All 51 apps audited and fixed or removed as part of the rebuild.

---

## Section 6: Always-On Service & Web UI

### Service

The FastAPI server runs as a system service from the moment Stackr is installed.

```
stackr install      # writes systemd/launchd unit, starts service, prints URL
stackr uninstall    # stops and removes service
```

Web UI available at `http://localhost:7274` immediately after install, persistent across reboots.

On startup: connects to Docker SDK → validates config → reconciles DB state against live Docker containers → surfaces any drift in the UI.

### Web UI — full management console

Static files served by FastAPI. Alpine.js for data binding. All data via `fetch()` to `/api/v1/`. No server-side template rendering for dynamic content.

**Pages:**

| Page | Capabilities |
|------|-------------|
| Dashboard | App grid, live status badges, quick deploy/stop/restart |
| App detail | Vars editor, deploy history with full stdout/stderr, log stream, rollback |
| Catalog | Browse all available apps, enable from catalog view |
| Settings | Global / Network / Security / Backup / Alerts — section forms |
| Mounts | List, add, remove SMB/NFS/Rclone mounts |
| System | Doctor checks, secret names, pre-deploy validation output |
| Deploy console | Full log stream during deploy, per-app progress, job history |

Real-time: SSE for log streaming, 2s polling for deploy job status during active deploys.

### CLI — API client with standalone fallback

```
stackr web          # open browser (service already running)
stackr deploy       # → POST /api/v1/deploy    (if service reachable)
                    # → engine directly         (fallback, for scripting)
stackr validate     # → POST /api/v1/validate  (if service reachable)
stackr rollback     # emergency rollback without browser
stackr backup       # → POST /api/v1/system/backup
stackr install      # set up and start service
```

---

## Section 7: Error Handling & Diagnostics

### Structured errors on all operations

Every operation that touches Docker returns an `OperationResult` (see Section 3). Written to `deploy_events` DB regardless of outcome.

### Validation gate

`POST /api/v1/deploy` always runs `engine/validator.py` first. Returns structured errors before touching Docker:

```json
{
  "ok": false,
  "errors": [
    {"type": "port_conflict", "apps": ["jellyfin", "plex"], "port": 8096},
    {"type": "missing_dep", "app": "radarr", "requires": "qbittorrent"}
  ],
  "warnings": [
    {"type": "suggests", "app": "sonarr", "suggests": "radarr"}
  ]
}
```

### Per-app health in UI

Every app card shows:
- Live status badge (running/stopped/degraded/drift)
- Last deploy timestamp
- Last error message (inline, no log-diving needed)
- Link to full deploy history with stdout/stderr

### Drift detection

At service startup and on every `GET /api/v1/apps`: Docker SDK compares live image digests against `image_digests` table. Any mismatch → status `drift` → UI flags it with a reconcile button.

### Alerts

Fire on `deploy_failed` and `drift_detected` events. Delivery failure is logged to `deploy_events` but never blocks operations.

---

## Dependencies

### Added
- `docker` — Docker SDK for Python (container inspection, events)
- `sqlite3` — stdlib, no new dependency; used directly for the 3-table state schema

### Removed
- `textual` — TUI deleted entirely

### Unchanged
- `typer`, `pydantic`, `jinja2`, `pyyaml`, `rich`, `python-dotenv`
- `fastapi`, `uvicorn`, `python-multipart`

### Frontend (no new Python deps)
- Alpine.js — loaded from CDN or bundled as a single file in `web/static/`

---

## What Is Not In Scope

- Multi-host orchestration
- Plugin ecosystem
- GraphQL API
- Traefik support (already removed)
- Authentik/Authelia (already removed)
