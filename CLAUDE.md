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
| `state.py` | JSON lock file at `~/.stackr/state.json`; drift detection |
| `catalog.py` | Loads `catalog/*/*/app.yml`; search/filter |
| `renderer.py` | Jinja2 template rendering; `traefik_labels()` helper |
| `validator.py` | Pre-deploy checks: secrets, ports, deps, volumes, DNS provider, security stack |
| `deployer.py` | validate → render → pull → `docker compose up -d` → write state |
| `status.py` | Rich terminal table; compares state vs live Docker |
| `cli.py` | Typer CLI — all user-facing commands |
| `dns_providers.py` | Registry of DNS providers and their required env vars |
| `middleware.py` | Traefik forward-auth and CrowdSec middleware label generators |

## Language and tooling

- **Python 3.11+** — use `from __future__ import annotations` in every module
- **Pydantic v2** — use `model_validate`, `field_validator`, `model_validator(mode="after")`; never v1 patterns (`.dict()`, `@validator`)
- **Typer** for CLI, **Rich** for terminal output, **Jinja2** with `StrictUndefined` for templates
- **uv** for dependency management: `uv pip install -e ".[dev]"`
- Line length: **100** (enforced by ruff)
- Linting: `ruff check stackr/ tests/` — rules E, F, I, UP, B, SIM are active
- Type checking: `mypy stackr/` — strict mode enabled
- Tests: `pytest tests/ -v`

## Key conventions

### Secret management
- Secrets are **never stored in `stackr.yml`** — use `${VAR_NAME}` references
- Resolution order (highest to lowest priority): shell env → `.stackr.env` file → auto-generated
- Shell env must take priority: in `build_env()`, load shell env **last** so it overwrites the file
- Auto-generated secrets are written to `.stackr.env` on first deploy via `ensure_secret()`
- `.stackr.env` is always gitignored; `stackr init` adds it automatically

### State management
- State file: `~/.stackr/state.json` — tracks compose hash + timestamp per app
- State stores the **full rendered compose content** (not just a hash) to support genuine rollback
- `state.is_changed(app_name, content)` drives skip-unchanged logic in `stackr update`

### Catalog entries
Every app lives at `catalog/<category>/<name>/` and requires exactly two files:

**`app.yml`** — metadata and schema:
```yaml
name: myapp
display_name: My App
description: What it does
category: media          # media | network | security | management | dashboard | monitoring
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
  - 8096                 # MUST match the port passed to traefik_labels() in compose.yml.j2
volumes:
  - name: config
    path: /config
  - name: media
    path: /media
    external: true       # warns user to pre-mount this path
```

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
- The port passed to `traefik_labels()` **must exactly match** the port declared in `app.yml`'s `ports` list — the validator uses `app.yml` ports for conflict detection; mismatches silently break Traefik routing
- Apps that optionally use the Docker socket **must** condition it on `security.socket_proxy`, like Traefik does — never unconditionally mount `/var/run/docker.sock`
- `socket-proxy` must be deployed before `traefik` — the deploy order in `config.enabled_apps` reflects this

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
- `_run_compose()` with `capture=False` is for interactive commands (`logs`, `shell`); other commands use `capture=True` which should pass `capture_output=True` to suppress Docker output
- `remove_app()` uses `docker compose down` without `-v` — never destroy named volumes without explicit user confirmation

## Testing

- Every new module needs a corresponding `tests/test_<module>.py`
- Every test must have at least one `assert` statement — no assertion-free test functions
- Catalog smoke tests: all `app.yml` + `compose.yml.j2` pairs must render without error using the reference config in `tests/test_renderer.py::test_render_all_seed_apps`
- When adding a new catalog app, add it to the `seed_apps` list in `test_catalog.py::test_seed_apps_present`
- Port declarations in `app.yml` and `traefik_labels()` calls in `compose.yml.j2` are tested for consistency in `test_catalog.py` — keep these in sync
- Security/validator tests that call `validate()` must supply DNS provider env vars (e.g. `{"CF_DNS_API_TOKEN": "x"}`) or the DNS provider check will produce unexpected failures

## Adding a new catalog app — checklist

1. Create `catalog/<category>/<name>/app.yml` with all required fields
2. Create `catalog/<category>/<name>/compose.yml.j2` — port in `traefik_labels()` must match `app.yml`
3. If the app uses the Docker socket, condition it on `{% if security.socket_proxy %}`
4. Add the app name to `seed_apps` in `tests/test_catalog.py`
5. Add a render test in `tests/test_renderer.py` if the app has non-trivial var combinations
6. Run `pytest tests/ -v` and confirm all tests pass
7. Run `ruff check stackr/ tests/` and `mypy stackr/`

## Common pitfalls

- **Duplicate YAML keys in templates**: when using `{% if %} / {% else %}` inside a service block, ensure both branches don't emit the same top-level key (e.g. `volumes:`). Use a single block with conditional content inside it instead.
- **Port mismatch**: `app.yml` ports are used by the validator; `traefik_labels(port)` is used at runtime. They must agree or conflicts go undetected and Traefik routes to the wrong port.
- **Secret priority**: `.stackr.env` must be loaded before shell env in `build_env()` so shell env wins — the order is `env.update(file)` then `env.update(os.environ)`.
- **Rollback requires stored content**: `state.json` must store the full rendered compose YAML (not just a hash) for `stackr rollback` to work — a hash alone cannot be used to restore a previous version.
- **Import ordering**: stdlib imports must be alphabetically sorted within their block (ruff rule `I` enforces this).
