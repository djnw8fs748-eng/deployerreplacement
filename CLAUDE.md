# Stackr — Claude guidance

Stackr is a declarative homelab deployment tool. It reads a `stackr.yml` config, renders Jinja2 Docker Compose templates from a YAML app catalog, and orchestrates deploys via `docker compose`.

## Project structure

```
stackr/          Python package — core engine
catalog/         App catalog: catalog/<category>/<app>/app.yml + compose.yml.j2
tests/           pytest test suite
pyproject.toml   Dependencies, ruff, mypy, pytest config
stackr.yml.example  Reference config
```

### Core module responsibilities

| Module | Role |
|--------|------|
| `config.py` | Pydantic v2 schema for `stackr.yml` |
| `secrets.py` | Secret resolution: shell env → `.stackr.env` → auto-generated |
| `state.py` | JSON lock file at `~/.stackr/state.json`; drift detection + image digest tracking |
| `catalog.py` | Loads `catalog/*/*/app.yml`; user catalog overlay (`~/.stackr/catalog/`) |
| `renderer.py` | Jinja2 template rendering; `traefik_labels()` helper |
| `validator.py` | Pre-deploy checks: secrets, ports, deps, volumes, DNS provider, security stack |
| `deployer.py` | validate → render → pull → `docker compose up -d` → write state + digests |
| `status.py` | Rich terminal table; compares state vs live Docker |
| `cli.py` | Typer CLI — all user-facing commands |
| `dns_providers.py` | Registry of DNS providers and their required env vars |
| `middleware.py` | Traefik forward-auth and CrowdSec middleware label generators |
| `doctor.py` | Pre-flight health checks (`stackr doctor`): Docker, networks, secrets, catalog |
| `images.py` | Image digest inspection via `docker inspect`; change detection for `stackr update` |
| `catalog_sync.py` | GitHub release download → `~/.stackr/catalog/` user overlay |
| `tui.py` | Textual TUI app browser (`stackr ui`); textual is a core dep — `HAS_TEXTUAL` guard handles import errors gracefully |
| `backup.py` | Restic-based backup/restore; `ensure_secret("STACKR_RESTIC_PASSWORD")` for repo password |
| `migrate.py` | Deployrr → stackr.yml migration; `_DEPLOYRR_MAP` dict + fuzzy suffix stripping |
| `alerts.py` | Push notifications on failures; providers: ntfy, Gotify, webhook; HTTP errors always swallowed |
| `mounts.py` | SMB/NFS/Rclone pre-deploy mounts; `mount_all(config.mounts)` / `umount_all(config.mounts)` |
| `web/__init__.py` | `HAS_FASTAPI` bool guard (mirrors `HAS_TEXTUAL` in tui.py) |
| `web/app.py` | `create_app(config_path)` — FastAPI application factory |
| `web/routes.py` | Route handlers: dashboard, `/api/apps`, `/api/toggle/{name}`, `/api/deploy`, `/api/logs/{name}` (SSE) |

## Language and tooling

- **Python 3.11+** — use `from __future__ import annotations` in every module
- **Pydantic v2** — use `model_validate`, `field_validator`, `model_validator(mode="after")`; never v1 patterns (`.dict()`, `@validator`)
- **Typer** for CLI, **Rich** for terminal output, **Jinja2** with `StrictUndefined` for templates
- **uv** for dependency management: `uv pip install -e ".[dev]"`
- Line length: **100** (enforced by ruff)
- Linting: `ruff check stackr/ tests/` — rules E, F, I, UP, B, SIM are active
- Type checking: `mypy stackr/` — strict mode enabled
- Tests: `pytest tests/ -v`

### Running tests locally

The project uses a `.venv` virtualenv. Always activate it first — `python`, `python3`, and `uv` are not on the system PATH:

```bash
source .venv/bin/activate && pytest tests/ -v
```

For linting and type-checking in the same shell:

```bash
source .venv/bin/activate && ruff check stackr/ tests/ && mypy stackr/
```

All three in one shot (typical pre-commit check):

```bash
source .venv/bin/activate && ruff check stackr/ tests/ && mypy stackr/ && pytest tests/ -v
```

## Key conventions

### Secret management
- Secrets are **never stored in `stackr.yml`** — use `${VAR_NAME}` references
- Resolution order (highest to lowest priority): shell env → `.stackr.env` file → auto-generated
- Shell env must take priority: in `build_env()`, load shell env **last** so it overwrites the file
- Auto-generated secrets are written to `.stackr.env` on first deploy via `ensure_secret()`
- `.stackr.env` is always gitignored; `stackr init` adds it automatically

### State management
- State file: `~/.stackr/state.json` — tracks compose hash + timestamp + image digests per app
- State stores the **full rendered compose content** (not just a hash) to support genuine rollback
- `state.is_changed(app_name, content)` drives skip-unchanged logic in `stackr update`
- `AppState.image_digests` is a `dict[str, str]` mapping image name → RepoDigest (`@sha256:…`); stored after each deploy, read by `images.images_changed()` to detect upstream changes
- Old state files without `image_digests` load cleanly — the field defaults to `{}` via `.get("image_digests", {})`

### Catalog entries
Every app lives at `catalog/<category>/<name>/` and requires exactly two files:

**`app.yml`** — metadata and schema:
```yaml
name: myapp
display_name: My App
description: What it does
# Valid categories: media | network | security | management | dashboard | monitoring
#                  database | ai | storage | productivity | gaming
category: media
homepage: https://...
version: latest
exposure: external       # external | internal | hybrid
requires: [traefik]      # hard deps — error if missing
suggests: []             # soft deps — warning if missing
vars:
  my_var:
    type: select         # string | select | boolean | integer
    options: [a, b, c]
    default: a
    description: What this var does
ports:
  - 8096                 # Traefik routing port — MUST match traefik_labels() in compose.yml.j2
host_ports:
  - 9090                 # Actual host-bound ports — checked for conflicts by the validator
volumes:
  - name: config
    path: /config
  - name: media
    path: /media
    external: true       # warns user to pre-mount this path
```

**Port semantics — critical distinction:**
- `ports`: the container port passed to `traefik_labels()`. Traefik-proxied apps share container ports without conflict — multiple apps can all use port 8080 internally. This list is NOT used for conflict detection.
- `host_ports`: actual ports bound on the host (e.g. `53` for DNS, `80`/`443` for Traefik, game ports). Only these are checked for conflicts by the validator.
- Apps that have no host-bound ports (typical Traefik-proxied web apps) should have `host_ports: []`.

**`compose.yml.j2`** — Jinja2 Docker Compose template:
```jinja2
services:
  myapp:
    image: org/myapp:{{ vars.version | default('latest') }}
    container_name: myapp
    restart: unless-stopped
    environment:
      - PUID={{ global.puid }}
      - PGID={{ global.pgid }}
      - TZ={{ global.timezone }}
    volumes:
      - {{ global.data_dir }}/myapp/config:/config
    networks:
      - proxy
    labels:
{% for k, v in traefik_labels(8096).items() %}
      - "{{ k }}={{ v }}"
{% endfor %}

networks:
  proxy:
    external: true
```

### Critical catalog rules
- The port passed to `traefik_labels()` **must exactly match** the port declared in `app.yml`'s `ports` list — mismatches silently break Traefik routing and go undetected
- Apps that optionally use the Docker socket **must** condition it on `security.socket_proxy`, like Traefik does — never unconditionally mount `/var/run/docker.sock`
- `socket-proxy` must be deployed before `traefik` — the deploy order in `config.enabled_apps` reflects this

### No-Traefik app pattern
Database, daemon, VPN, and gaming apps have no web UI to proxy. These apps:
- Omit the `proxy` network entirely from their compose template
- Do not call `traefik_labels()` — no `labels:` block
- Set `host_ports:` in `app.yml` for any ports they bind on the host (e.g. `5432` for Postgres, `51820` for Wireguard)
- Leave `ports: []` since there is no Traefik routing port

Examples: `database/postgres`, `database/mariadb`, `database/redis`, `database/mongo`, `management/watchtower`, `network/wireguard`, `gaming/minecraft`.

### Sidecar / backend network pattern
Apps with embedded sidecars (DB, cache, worker) use an isolated `<app>-backend` network to prevent those sidecars from being reachable on the `proxy` network. The network is defined as `external: false` (Docker creates it). Only the primary service joins both the `proxy` and the backend network.

Examples: `storage/nextcloud` (mariadb + redis sidecars), `productivity/paperless-ngx` (postgres + redis + gotenberg + tika), `productivity/miniflux` (postgres sidecar).

```jinja2
networks:
  proxy:
    external: true
  nextcloud-backend:
    external: false      # isolated — sidecars only
```

### User catalog overlay
- `~/.stackr/catalog/` takes priority over the built-in catalog shipped with the package
- `catalog.py::_effective_catalog()` checks for `~/.stackr/catalog/` first — if it contains any `*/*/app.yml` files, it is used exclusively
- `stackr catalog update` downloads a GitHub release tarball and installs its `catalog/` to `~/.stackr/catalog/`
- To revert to the built-in catalog, delete `~/.stackr/catalog/`
- `catalog_sync.py::read_installed_version()` reads `~/.stackr/catalog/.catalog_version` to report the installed tag

### Jinja2 templates
- Renderer uses `trim_blocks=True` and `lstrip_blocks=True` — block tags eat the newline after them
- Use `{% if %} / {% elif %} / {% endif %}` without `-` whitespace trimming in compose templates (the environment already handles it)
- Template context variables: `global`, `network`, `traefik`, `security`, `vars`, `app`, `traefik_labels(port, exposure=None)`
- `traefik_labels(port)` returns a `dict[str, str]` — always iterate it with `{% for k, v in traefik_labels(port).items() %}`

### DNS provider registry
- All supported DNS providers are declared in `dns_providers.py` — add new providers there first
- `validator.py` automatically checks that every `required_env` var is present before deploy
- If a provider is unknown (not in the registry), validation issues a **warning** (not an error) so that custom providers still work
- The Traefik compose template must also handle the provider's env vars in its `environment:` block

### Security stack (Phase 2)
- `security.auth_provider` accepts any string at config parse time — validation is deferred to `_check_security_stack()` in `validator.py` so that custom app-based auth providers work without changing `config.py`
- `security.auth_provider` must either be `none`/`google_oauth` or match an app name in `apps:`
- `security.crowdsec: true` requires a `crowdsec` app in `apps:`
- Both checks are enforced by `_check_security_stack()` in `validator.py`
- CrowdSec shares Traefik access logs — the Traefik compose mounts a `logs/` volume when `security.crowdsec: true`
- Forward-auth middleware labels are generated by `middleware.py` — use `combined_middleware_labels()` when you need both CrowdSec and auth on one router

### Cert resolvers and networking modes
- In `external` mode: cert resolver name = `traefik.dns_provider` (e.g. `cloudflare`)
- In `internal` mode: requires a separately configured internal resolver — do not hardcode `"internal"` as a resolver name without defining it in the Traefik compose template
- In `hybrid` mode: both resolvers must be defined and named consistently between `renderer.py` and the Traefik template

### Validation
- `validator.py` must stay in sync with its module docstring — every check listed in the docstring must have a corresponding `_check_*` function
- Add new checks both to the implementation **and** the docstring
- Local-catalog apps (`catalog_path` set) must go through the same validation as catalog apps — do not skip them

### Deploy pipeline
- The deploy flow is: `validate()` (caller) → `deploy()` (engine) — `deploy()` accepts a pre-computed `ValidationResult` and must not be called without running validation first
- `stackr doctor` runs pre-flight checks before any deploy; `run_doctor()` returns `True` if no `fail` checks
- `_run_compose()` with `capture=False` is for interactive commands (`logs`, `shell`); other commands use `capture=True` which should pass `capture_output=True` to suppress Docker output
- `remove_app()` uses `docker compose down` without `-v` — never destroy named volumes without explicit user confirmation
- After a successful pull + deploy, `images.collect_digests(compose_content)` fetches RepoDigests for all services and stores them in `state.set_app(..., image_digests=digests)`
- `stackr update` passes `check_image_updates=True` to `deploy()` — skips an app only when both the compose content and all image digests are unchanged

### TUI (`stackr ui`)

- `textual` is a **core dependency** — `stackr ui` works out of the box with no extras.
- `HAS_TEXTUAL` bool guards the class definition — the module can always be imported safely even if textual is somehow absent.
- `load_enabled(config_path)` and `build_stub_config(config_path)` are standalone helpers
  (no textual dependency) that can be tested unconditionally.
- The CLI `stackr ui` command wraps the import in `try/except ImportError` and prints an
  install hint if textual is missing.
- `StackrTUI.__init__` accepts `catalog: Any = None` so tests can inject a `Catalog`
  without running the full app.
- `pyproject.toml` has `[[tool.mypy.overrides]]` with `ignore_missing_imports = true` and
  `ignore_errors = true` for `stackr.tui` since textual stubs are not available in the dev
  environment (textual is installed but has no py.typed marker).
- TUI tests in `tests/test_tui.py` use `pytest.mark.skipif(not HAS_TEXTUAL, ...)` to
  skip class-level tests; the async mount test additionally skips without `pytest-asyncio`.

### Web UI (`stackr web`)

- `fastapi` and `uvicorn` are **core dependencies** — `stackr web` works out of the box with no extras.
- `web/__init__.py` exports `HAS_FASTAPI` — import guard retained for graceful degradation if fastapi is somehow absent.
- `web/app.py::create_app(config_path)` returns a FastAPI app; raises `RuntimeError` if fastapi is not installed.
- `web/routes.py::make_router(config_path)` builds all routes bound to a specific config file.
- Templates live in `stackr/web/templates/` and are rendered with Jinja2 `FileSystemLoader`.
- `pyproject.toml` has `[[tool.mypy.overrides]]` with `ignore_errors = true` for `stackr.web.*` and `ignore_missing_imports = true` for `uvicorn` (no type stubs).
- Tests in `tests/test_web.py` skip route tests when fastapi/httpx are absent; `HAS_FASTAPI` import guard test always runs.
- The `toggle` route (`POST /api/toggle/{name}`) validates `app_name` against the catalog before writing, uses `threading.Lock` + `tempfile`/`os.replace` for atomic concurrent-safe config writes, and returns HTMX partial HTML.
- The logs route (`GET /api/logs/{name}`) returns a `StreamingResponse` with `text/event-stream` (Server-Sent Events).
- The deploy route uses `sys.executable -m stackr` (not bare `stackr`) to ensure the correct virtualenv is used.

### Backup (`stackr backup` / `restore` / `snapshots`)

- `backup.py` requires `restic` on PATH — raises `RuntimeError` if not found.
- The restic repository password is auto-generated via `ensure_secret("STACKR_RESTIC_PASSWORD", config_dir, env)` and stored in `.stackr.env`.
- `_ensure_repo_initialized()` runs `restic snapshots` first; only calls `restic init` on failure.
- `backup()` backs up `data_dir`, `state_dir`, and `config_dir` in a single restic invocation.

### Mounts (`stackr mount` / `umount`)

- `mounts.py` functions take plain string arguments; `mount_all()` / `umount_all()` accept `list[object]` to avoid circular imports (caller passes `config.mounts`).
- `mount_share()` always calls `mountpoint -q <path>` first and no-ops if already mounted.
- Mount type requirements: `smb` → `mount.cifs` (cifs-utils); `nfs` → system `mount`; `rclone` → `rclone` binary + configured remote.
- `MountConfig` lives in `config.py`; `mounts: list[MountConfig]` field on `StackrConfig`.

### Alerts (`config.alerts`)

- `AlertConfig` in `config.py`: `enabled`, `provider` (ntfy/gotify/webhook), `url`, `token`.
- `alerts.py::send_alert(title, message, config)` never raises — all HTTP errors are caught.
- Called by `deployer.py` on `_run_compose` failure and by `doctor.py::run_doctor` when any check status is `"fail"`.

### Upgrade (`stackr upgrade`)

- Implemented in `cli.py` — no separate module.
- Runs `pipx install --force git+https://github.com/<GITHUB_REPO>.git` to pull the latest commit from main.
- Uses `--force` (not `pipx upgrade`) because `pipx upgrade` compares version metadata which never changes for git-installed packages — it always reports "already at latest version" and does nothing.
- Reads `GITHUB_REPO` from `catalog_sync.py` — single source of truth for the repo URL.
- Reports the new version from `stackr --version` after install; reminds user to reload shell if it appears unchanged.
- Exits non-zero with a clear error if `pipx` is not found on PATH.

### Uninstall (`stackr uninstall`)

- Implemented in `cli.py` — no separate module.
- Removes the pipx package (`pipx uninstall stackr`), prompts before deleting `~/.stackr`.
- `--yes` / `-y` flag skips all confirmation prompts for scripted use.
- Leaves `.stackr.env` files in project directories — only reminds the user to delete them manually.
- Also available via `install.sh --uninstall` for users who no longer have `stackr` on PATH.

### Installation / installer (`install.sh`)

- Bootstraps pipx via `apt-get`/`apt`/`brew` first to avoid PEP 668 on Debian 12+ / Ubuntu 22.04+; falls back to `pip --break-system-packages`.
- Calls `python3 -m pipx ensurepath --force` to write `~/.local/bin` into shell rc files.
- Prints PATH reload instructions when `stackr` is not found after install (subshell cannot propagate `export PATH` to the parent shell).
- `--uninstall` flag mirrors `stackr uninstall` for users without the command.

## Testing

- Every new module needs a corresponding `tests/test_<module>.py`
- Every test must have at least one `assert` statement — no assertion-free test functions
- Catalog smoke tests: all `app.yml` + `compose.yml.j2` pairs must render without error using the reference config in `tests/test_renderer.py::test_render_all_seed_apps`
- When adding a new catalog app, add it to the `seed_apps` list in `test_catalog.py::test_seed_apps_present`
- Port declarations in `app.yml` and `traefik_labels()` calls in `compose.yml.j2` are tested for consistency in `test_catalog.py` — keep these in sync
- Security/validator tests that call `validate()` must supply DNS provider env vars (e.g. `{"CF_DNS_API_TOKEN": "x"}`) or the DNS provider check will produce unexpected failures

## Adding a new catalog app — checklist

1. Create `catalog/<category>/<name>/app.yml` with all required fields
   - Use `ports` for the Traefik container routing port (matches `traefik_labels()` call)
   - Use `host_ports` for any ports actually bound on the host (DNS, game ports, etc.)
   - If no host ports, set `host_ports: []`
2. Create `catalog/<category>/<name>/compose.yml.j2` — port in `traefik_labels()` must match `app.yml`'s `ports`
3. If the app has no web UI (database, daemon, VPN, game server): omit `proxy` network and `traefik_labels()` entirely — see No-Traefik app pattern above
4. If the app has embedded sidecars: use an isolated `<app>-backend` network — see Sidecar pattern above
5. If the app uses the Docker socket, condition it on `{% if security.socket_proxy %}`
6. Add the app name to `seed_apps` in `tests/test_catalog.py`
7. Add a render test in `tests/test_renderer.py` if the app has non-trivial var combinations
8. Run `pytest tests/ -v` and confirm all tests pass
9. Run `ruff check stackr/ tests/` and `mypy stackr/`

## Common pitfalls

- **Duplicate YAML keys in templates**: when using `{% if %} / {% else %}` inside a service block, ensure both branches don't emit the same top-level key (e.g. `volumes:`). Use a single block with conditional content inside it instead.
- **Port mismatch**: `app.yml` ports are used by the validator; `traefik_labels(port)` is used at runtime. They must agree or conflicts go undetected and Traefik routes to the wrong port.
- **`ports` vs `host_ports` confusion**: putting a Traefik-proxied port (e.g. 8080) in `host_ports` will produce false port conflict errors because multiple apps share that container port. Only real host-bound ports belong in `host_ports`.
- **Secret priority**: `.stackr.env` must be loaded before shell env in `build_env()` so shell env wins — the order is `env.update(file)` then `env.update(os.environ)`.
- **Rollback requires stored content**: `state.json` must store the full rendered compose YAML (not just a hash) for `stackr rollback` to work — a hash alone cannot be used to restore a previous version.
- **Image digests only available after pull**: `collect_digests()` reads local Docker image metadata — it returns `{}` if images haven't been pulled yet. `images_changed()` returns `False` when stored digests are empty, so the first deploy always goes through.
- **User catalog overlay is all-or-nothing**: if `~/.stackr/catalog/` exists and has any `*/*/app.yml`, it replaces the entire built-in catalog. Partial overlays are not supported — the user catalog must contain all apps they want to use.
- **Import ordering**: stdlib imports must be alphabetically sorted within their block (ruff rule `I` enforces this).
