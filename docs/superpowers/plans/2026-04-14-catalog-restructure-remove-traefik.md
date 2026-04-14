# Catalog Restructure + Traefik Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove 13 catalog apps, add seerr/pocket-id/tinyauth as NPM-native apps, then strip Traefik from the entire engine and all compose templates.

**Architecture:** Two-phase approach. Phase 1 is pure catalog surgery (file deletions + additions) with no engine changes — this ships as its own PR. Phase 2 removes `TraefikConfig`, `traefik_labels()`, `middleware.py`, `dns_providers.py`, and all `labels:` blocks from the 37 remaining templates — this ships as a second PR. Apps stay on the `proxy` Docker network throughout so NPM can reach them by container name.

**Tech Stack:** Python 3.11+, Pydantic v2, Jinja2, pytest, Docker Compose, GitHub Actions

---

## File Map

### Phase 1 — Created
- `catalog/media/seerr/app.yml`
- `catalog/media/seerr/compose.yml.j2`
- `catalog/security/pocket-id/app.yml`
- `catalog/security/pocket-id/compose.yml.j2`
- `catalog/security/tinyauth/app.yml`
- `catalog/security/tinyauth/compose.yml.j2`

### Phase 1 — Deleted
- `catalog/security/authelia/` (entire directory)
- `catalog/security/authentik/` (entire directory)
- `catalog/management/dasherr/` (entire directory)
- `catalog/storage/nextcloud/` (entire directory)
- `catalog/media/sabnzbd/` (entire directory)
- `catalog/media/transmission/` (entire directory)
- `catalog/media/jellyseerr/` (entire directory)
- `catalog/media/overseerr/` (entire directory)
- `catalog/network/traefik/` (entire directory)
- `catalog/productivity/` (entire category directory)

### Phase 1 — Modified
- `tests/test_catalog.py` — update `seed_apps`
- `tests/test_renderer.py` — remove deleted-app tests, add new-app smoke tests
- `tests/test_security_apps.py` — remove `TestAuthentikRendering`
- `.github/workflows/integration.yml` — remove 13 matrix entries, add 3 new ones, update env secrets

### Phase 2 — Deleted
- `stackr/middleware.py`
- `stackr/dns_providers.py`
- `tests/test_middleware.py`
- `tests/test_dns_providers.py`

### Phase 2 — Modified
- `stackr/config.py` — remove `TraefikConfig`, `NetworkConfig.mode`, `SecurityConfig.auth_provider`
- `stackr/renderer.py` — remove `traefik_labels()` and `traefik` context var
- `stackr/validator.py` — remove `_check_dns_provider`, `_check_dns_provider_env_refs`, `_check_security_stack`; rename to `_check_crowdsec`
- `stackr/doctor.py` — remove Traefik check, remove `dns_providers` import
- `stackr/tui.py` — remove Traefik settings panel
- `stackr/web/routes.py` — remove Traefik fields from settings API
- `stackr/cli.py` — remove Traefik config references
- `stackr/migrate.py` — remove `"traefik-v2": "traefik"` migration entry
- All 37 remaining `catalog/**/*.j2` — remove `labels:` block
- All 37 remaining `catalog/**/app.yml` — remove `requires: [traefik]` and `exposure`
- `stackr.yml.example` — remove `traefik:` section, remove `network.mode`
- `tests/test_config.py` — remove `TraefikConfig` tests
- `tests/test_validator.py` — remove Traefik test cases
- `tests/test_renderer.py` — remove `traefik` from all `StackrConfig` helper calls
- `tests/test_security_apps.py` — remove auth_provider references
- `tests/test_doctor.py` — remove Traefik doctor check test
- `tests/test_web.py` — remove Traefik settings assertions
- `.github/workflows/integration.yml` — simplify render step (remove `traefik:` block)
- `CLAUDE.md` — remove Traefik architecture sections

---

## ── PHASE 1: CATALOG CLEANUP ──

---

### Task 1: Delete the 13 removed apps

**Files:**
- Delete: `catalog/security/authelia/`, `catalog/security/authentik/`, `catalog/management/dasherr/`, `catalog/storage/nextcloud/`, `catalog/media/sabnzbd/`, `catalog/media/transmission/`, `catalog/media/jellyseerr/`, `catalog/media/overseerr/`, `catalog/network/traefik/`, `catalog/productivity/`
- Modify: `tests/test_catalog.py`, `tests/test_renderer.py`, `tests/test_security_apps.py`

- [ ] **Step 1: Remove the directories**

```bash
git rm -r \
  catalog/security/authelia \
  catalog/security/authentik \
  catalog/management/dasherr \
  catalog/storage/nextcloud \
  catalog/media/sabnzbd \
  catalog/media/transmission \
  catalog/media/jellyseerr \
  catalog/media/overseerr \
  catalog/network/traefik \
  catalog/productivity
```

- [ ] **Step 2: Update `seed_apps` in `tests/test_catalog.py`**

Find the `seed_apps` list (it currently includes `"traefik"`, `"overseerr"`, etc.) and replace it with:

```python
seed_apps = [
    # network
    "nginx-proxy-manager", "adguardhome", "pihole", "wireguard", "headscale",
    # ai
    "ollama", "open-webui",
    # media
    "plex", "jellyfin", "sonarr", "radarr", "lidarr", "readarr", "prowlarr",
    "bazarr", "seerr", "qbittorrent", "tdarr",
    # management
    "homepage", "flame", "heimdall", "dozzle", "portainer", "watchtower",
    # monitoring
    "uptime-kuma", "grafana", "prometheus", "loki", "netdata",
    # security
    "vaultwarden", "socket-proxy", "crowdsec", "pocket-id", "tinyauth",
    # database
    "postgres", "mariadb", "redis", "mongo",
    # gaming
    "minecraft",
    # storage
    "filebrowser", "duplicati",
]
```

- [ ] **Step 3: Run the seed_apps test to verify it fails for new apps (expected — they don't exist yet)**

```bash
source .venv/bin/activate && pytest tests/test_catalog.py -v -k "seed"
```

Expected: FAIL — `seerr`, `pocket-id`, `tinyauth` not found in catalog.

- [ ] **Step 4: Remove deleted-app tests from `tests/test_renderer.py`**

Delete these functions entirely:
- `test_render_nextcloud_has_db_sidecar`
- `test_render_miniflux_has_db_sidecar`

Also remove all deleted apps from the `seed_apps` list inside `test_render_all_seed_apps` (it has its own copy — update it to match the list in step 2 above, minus `pocket-id`, `tinyauth`, `seerr` which will be added in later tasks).

- [ ] **Step 5: Remove `TestAuthentikRendering` from `tests/test_security_apps.py`**

Delete the entire `TestAuthentikRendering` class. Leave `TestCrowdSecRendering` intact.

- [ ] **Step 6: Run tests to confirm only expected failures remain**

```bash
source .venv/bin/activate && pytest tests/test_catalog.py tests/test_renderer.py tests/test_security_apps.py -v --tb=short
```

Expected: failures only for `seerr`, `pocket-id`, `tinyauth` not in catalog. All other tests pass.

---

### Task 2: Add seerr catalog entry

**Files:**
- Create: `catalog/media/seerr/app.yml`
- Create: `catalog/media/seerr/compose.yml.j2`
- Modify: `tests/test_renderer.py`

- [ ] **Step 1: Create `catalog/media/seerr/app.yml`**

```yaml
name: seerr
display_name: Seerr
description: Open-source media request and discovery manager for Jellyfin, Plex, and Emby
category: media
homepage: https://seerr.dev
version: latest
exposure: external
requires: []
suggests:
  - sonarr
  - radarr
vars:
  version:
    type: string
    default: latest
    description: Docker image tag
ports:
  - 5055
host_ports: []
volumes:
  - name: config
    path: /app/config
```

- [ ] **Step 2: Create `catalog/media/seerr/compose.yml.j2`**

```jinja2
services:
  seerr:
    image: seerr/seerr:{{ vars.version | default('latest') }}
    container_name: seerr
    restart: unless-stopped
    environment:
      - TZ={{ global.timezone }}
    volumes:
      - {{ global.data_dir }}/seerr/config:/app/config
    networks:
      - proxy

networks:
  proxy:
    external: true
```

- [ ] **Step 3: Add seerr smoke test to `tests/test_renderer.py`**

Add this test alongside the other render tests:

```python
def test_render_seerr():
    config = _make_config()
    app = Catalog().get("seerr")
    assert app is not None
    rendered = render_app(AppConfig(name="seerr"), app, config)
    parsed = yaml.safe_load(rendered)
    assert "seerr" in parsed["services"]
    assert "seerr/seerr" in parsed["services"]["seerr"]["image"]
    assert parsed["networks"]["proxy"]["external"] is True
```

(`_make_config` is the existing helper in `test_renderer.py` that builds a `StackrConfig` with `traefik.enabled: True` — use it as-is for now; Phase 2 will update it.)

- [ ] **Step 4: Also add `"seerr"` to the `seed_apps` list inside `test_render_all_seed_apps`**

- [ ] **Step 5: Run tests**

```bash
source .venv/bin/activate && pytest tests/test_catalog.py tests/test_renderer.py -v -k "seerr"
```

Expected: PASS

---

### Task 3: Add pocket-id catalog entry

**Files:**
- Create: `catalog/security/pocket-id/app.yml`
- Create: `catalog/security/pocket-id/compose.yml.j2`
- Modify: `tests/test_renderer.py`

- [ ] **Step 1: Create `catalog/security/pocket-id/app.yml`**

```yaml
name: pocket-id
display_name: Pocket ID
description: Simple OIDC provider with passkey-only authentication for self-hosted services
category: security
homepage: https://pocket-id.org
version: v2
exposure: external
requires: []
suggests:
  - tinyauth
vars:
  version:
    type: string
    default: v2
    description: Docker image tag
ports:
  - 1411
host_ports: []
volumes:
  - name: data
    path: /app/data
```

- [ ] **Step 2: Create `catalog/security/pocket-id/compose.yml.j2`**

```jinja2
services:
  pocket-id:
    image: ghcr.io/pocket-id/pocket-id:{{ vars.version | default('v2') }}
    container_name: pocket-id
    restart: unless-stopped
    environment:
      - TZ={{ global.timezone }}
      - APP_URL=https://pocket-id.{{ network.domain }}
      - ENCRYPTION_KEY=${POCKET_ID_ENCRYPTION_KEY}
      - TRUST_PROXY=true
    volumes:
      - {{ global.data_dir }}/pocket-id/data:/app/data
    networks:
      - proxy

networks:
  proxy:
    external: true
```

- [ ] **Step 3: Add pocket-id smoke test to `tests/test_renderer.py`**

```python
def test_render_pocket_id():
    config = _make_config()
    app = Catalog().get("pocket-id")
    assert app is not None
    rendered = render_app(AppConfig(name="pocket-id"), app, config)
    parsed = yaml.safe_load(rendered)
    assert "pocket-id" in parsed["services"]
    assert "pocket-id/pocket-id" in parsed["services"]["pocket-id"]["image"]
    env = parsed["services"]["pocket-id"]["environment"]
    assert any("APP_URL" in e for e in env)
    assert any("ENCRYPTION_KEY" in e for e in env)
```

- [ ] **Step 4: Add `"pocket-id"` to the `seed_apps` list inside `test_render_all_seed_apps`**

- [ ] **Step 5: Run tests**

```bash
source .venv/bin/activate && pytest tests/test_catalog.py tests/test_renderer.py -v -k "pocket"
```

Expected: PASS

---

### Task 4: Add tinyauth catalog entry

**Files:**
- Create: `catalog/security/tinyauth/app.yml`
- Create: `catalog/security/tinyauth/compose.yml.j2`
- Modify: `tests/test_renderer.py`

- [ ] **Step 1: Create `catalog/security/tinyauth/app.yml`**

```yaml
name: tinyauth
display_name: TinyAuth
description: Lightweight forward-auth proxy for Nginx Proxy Manager with OIDC support
category: security
homepage: https://github.com/steveiliop56/tinyauth
version: latest
exposure: internal
requires:
  - pocket-id
vars:
  version:
    type: string
    default: latest
    description: Docker image tag
ports:
  - 3000
host_ports: []
volumes:
  - name: data
    path: /data
```

- [ ] **Step 2: Create `catalog/security/tinyauth/compose.yml.j2`**

```jinja2
services:
  tinyauth:
    image: ghcr.io/steveiliop56/tinyauth:{{ vars.version | default('latest') }}
    container_name: tinyauth
    restart: unless-stopped
    environment:
      - TZ={{ global.timezone }}
      - TINYAUTH_APPURL=https://tinyauth.{{ network.domain }}
      - TINYAUTH_DATABASE_PATH=/data/tinyauth.db
      - TINYAUTH_OAUTH_PROVIDERS_pocketid_NAME=Pocket ID
      - TINYAUTH_OAUTH_PROVIDERS_pocketid_CLIENTID=${TINYAUTH_OAUTH_CLIENT_ID}
      - TINYAUTH_OAUTH_PROVIDERS_pocketid_CLIENTSECRET=${TINYAUTH_OAUTH_CLIENT_SECRET}
      - TINYAUTH_OAUTH_PROVIDERS_pocketid_SCOPES=openid email profile
      - TINYAUTH_OAUTH_PROVIDERS_pocketid_AUTHURL=https://pocket-id.{{ network.domain }}/authorize
      - TINYAUTH_OAUTH_PROVIDERS_pocketid_TOKENURL=https://pocket-id.{{ network.domain }}/api/oidc/token
      - TINYAUTH_OAUTH_PROVIDERS_pocketid_USERINFOURL=https://pocket-id.{{ network.domain }}/api/oidc/userinfo
      - TINYAUTH_OAUTH_PROVIDERS_pocketid_REDIRECTURL=https://tinyauth.{{ network.domain }}/oauth/callback
    volumes:
      - {{ global.data_dir }}/tinyauth/data:/data
    networks:
      - proxy

networks:
  proxy:
    external: true
```

- [ ] **Step 3: Add tinyauth smoke test to `tests/test_renderer.py`**

```python
def test_render_tinyauth():
    config = _make_config()
    app = Catalog().get("tinyauth")
    assert app is not None
    rendered = render_app(AppConfig(name="tinyauth"), app, config)
    parsed = yaml.safe_load(rendered)
    assert "tinyauth" in parsed["services"]
    assert "steveiliop56/tinyauth" in parsed["services"]["tinyauth"]["image"]
    env = parsed["services"]["tinyauth"]["environment"]
    assert any("TINYAUTH_APPURL" in e for e in env)
    assert any("pocketid_CLIENTID" in e for e in env)
```

- [ ] **Step 4: Add `"tinyauth"` to the `seed_apps` list inside `test_render_all_seed_apps`**

- [ ] **Step 5: Run full test suite to confirm Phase 1 catalog is clean**

```bash
source .venv/bin/activate && pytest tests/ -v --tb=short
```

Expected: all pass (some skips are fine, no failures)

---

### Task 5: Update integration workflow for Phase 1

**Files:**
- Modify: `.github/workflows/integration.yml`

- [ ] **Step 1: Remove all 13 deleted apps from the matrix**

Delete these `include` entries from the `matrix`:
- `adguardhome` (already skipped but in matrix — leave the skip comment, confirm it's removed from include)
- `headscale` (same)
- `dasherr`
- `authentik`
- `authelia` (was already skipped — remove if still in matrix)
- `nextcloud`
- `sabnzbd`
- `transmission`
- `jellyseerr`
- `overseerr`
- `traefik` (was already skipped — remove if present)
- `freshrss`
- `gitea`
- `miniflux`
- `paperless-ngx`

- [ ] **Step 2: Remove no-longer-needed CI env secrets from the `env:` block**

Remove these keys:
```yaml
# remove these:
AUTHENTIK_POSTGRES_PASSWORD: ci-integration-test
AUTHENTIK_SECRET_KEY: ci-integration-test-secret-key-at-least-fifty-chars-x
MINIFLUX_DB_PASSWORD: ci-integration-test
MINIFLUX_ADMIN_PASSWORD: ci-integration-test-12345
NEXTCLOUD_DB_PASSWORD: ci-integration-test
NEXTCLOUD_DB_ROOT_PASSWORD: ci-integration-test
NEXTCLOUD_ADMIN_PASSWORD: ci-integration-test
PAPERLESS_DB_PASSWORD: ci-integration-test
PAPERLESS_SECRET_KEY: ci-integration-test-paperless-secret-key-32chars-min
PAPERLESS_ADMIN_PASSWORD: ci-integration-test
TRANSMISSION_PASS: ci-integration-test
```

- [ ] **Step 3: Add new matrix entries and CI env secrets**

Add to the `env:` block:
```yaml
POCKET_ID_ENCRYPTION_KEY: ci-integration-test-encryption-key-32ch
TINYAUTH_OAUTH_CLIENT_ID: ci-integration-test
TINYAUTH_OAUTH_CLIENT_SECRET: ci-integration-test
```

Add to the matrix `include:` list:

```yaml
          - app: seerr
            container_port: 5055
            health_path: "/"

          - app: pocket-id
            container_port: 1411
            health_path: "/"

          - app: tinyauth
            container_port: 3000
            health_path: "/"
```

Also add `pocket-id` and `tinyauth` to the "Create required host directories" step's pre-create logic (they need `/opt/appdata/pocket-id/data` and `/opt/appdata/tinyauth/data` created with 777 permissions — the existing generic `mkdir -p /opt/appdata/${{ matrix.app }}/data` already handles this).

- [ ] **Step 4: Update the skip list comment at the top of integration.yml**

Remove `adguardhome` and `headscale` comments that reference apps being in the skip list (they were already skipped from a previous fix) — keep the comments for apps that are now removed from the catalog entirely, noting "removed from catalog":

```yaml
# Skipped / removed apps:
#   traefik          — removed from catalog; NPM is the sole reverse proxy
#   pihole           — conflicts with adguardhome on host port 53
#   adguardhome      — conflicts with systemd-resolved on host port 53
#   authelia         — removed from catalog
#   authentik        — removed from catalog
#   headscale        — requires a config.yaml file pre-mounted at /etc/headscale
#   gluetun          — requires live VPN credentials
#   dasherr          — removed from catalog
```

- [ ] **Step 5: Commit Phase 1**

```bash
source .venv/bin/activate && pytest tests/ -v --tb=short -q
```

Expected: all pass.

```bash
git add -A
git commit -m "feat: catalog restructure — remove 13 apps, add seerr/pocket-id/tinyauth

Removed: authelia, authentik, dasherr, nextcloud, sabnzbd, transmission,
jellyseerr, overseerr, traefik, freshrss, gitea, miniflux, paperless-ngx.
Added: seerr (replaces overseerr+jellyseerr), pocket-id (OIDC provider),
tinyauth (forward-auth for NPM). New apps are NPM-native with no Traefik
labels. Updates test_catalog, test_renderer, test_security_apps, and
integration.yml matrix."
```

> **→ Open PR for Phase 1 here before continuing to Phase 2.**

---

## ── PHASE 2: REMOVE TRAEFIK FROM THE ENGINE ──

---

### Task 6: Remove TraefikConfig from config.py

**Files:**
- Modify: `stackr/config.py`
- Modify: `stackr.yml.example`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write a failing test asserting TraefikConfig is gone**

In `tests/test_config.py`, add:

```python
def test_no_traefik_config():
    """TraefikConfig and traefik field must not exist after removal."""
    import stackr.config as cfg
    assert not hasattr(cfg, "TraefikConfig")
    config = StackrConfig.model_validate({
        "global": {"data_dir": "/data", "timezone": "UTC", "puid": 1000, "pgid": 1000},
        "network": {"domain": "test.com", "local_domain": "home.test.com"},
        "security": {"socket_proxy": False},
    })
    assert not hasattr(config, "traefik")
    assert not hasattr(config.network, "mode")
```

- [ ] **Step 2: Run to verify it fails**

```bash
source .venv/bin/activate && pytest tests/test_config.py::test_no_traefik_config -v
```

Expected: FAIL — `TraefikConfig` still exists.

- [ ] **Step 3: Edit `stackr/config.py`**

Make these changes:

1. Delete the entire `TraefikConfig` class (lines ~45-75, the class with `enabled`, `acme_email`, `dns_provider`, `dns_provider_env` fields).

2. Remove `mode` from `NetworkConfig`:
   ```python
   # BEFORE
   class NetworkConfig(BaseModel):
       mode: str = "external"
       domain: str = "example.com"
       local_domain: str = "home.example.com"
       # ... validator for mode ...

   # AFTER
   class NetworkConfig(BaseModel):
       domain: str = "example.com"
       local_domain: str = "home.example.com"
   ```

3. Remove `auth_provider` from `SecurityConfig` (it was used only for Traefik forward-auth middleware selection):
   ```python
   # BEFORE
   class SecurityConfig(BaseModel):
       socket_proxy: bool = False
       crowdsec: bool = False
       auth_provider: str = "none"

   # AFTER
   class SecurityConfig(BaseModel):
       socket_proxy: bool = False
       crowdsec: bool = False
   ```

4. Remove `traefik: TraefikConfig = Field(default_factory=TraefikConfig)` from `StackrConfig`.

5. Remove the `model_validator` logic that auto-inserts `traefik` into `enabled_apps` (the block starting with `if self.traefik.enabled:`). Keep the NPM auto-insert logic if present.

- [ ] **Step 4: Update `stackr.yml.example`**

Remove the entire `traefik:` section:
```yaml
# remove this whole block:
traefik:
  enabled: true
  acme_email: you@example.com
  dns_provider: cloudflare
  dns_provider_env:
    CF_DNS_API_TOKEN: ${CF_DNS_API_TOKEN}
```

Also remove `network.mode` from the network section:
```yaml
# BEFORE
network:
  mode: external
  domain: example.com
  local_domain: home.example.com

# AFTER
network:
  domain: example.com
  local_domain: home.example.com
```

- [ ] **Step 5: Remove existing TraefikConfig test cases from `tests/test_config.py`**

Delete any test functions or classes that construct `TraefikConfig` directly or test `traefik.enabled`, `traefik.dns_provider`, `network.mode`, or `SecurityConfig.auth_provider`. Keep all other config tests.

- [ ] **Step 6: Run tests**

```bash
source .venv/bin/activate && pytest tests/test_config.py -v
```

Expected: all pass including `test_no_traefik_config`.

---

### Task 7: Remove traefik_labels() from renderer.py

**Files:**
- Modify: `stackr/renderer.py`
- Modify: `tests/test_renderer.py`

- [ ] **Step 1: Write a failing test**

In `tests/test_renderer.py`, add:

```python
def test_no_traefik_in_render_context():
    """traefik_labels and traefik must not be injected into template context."""
    from stackr.renderer import render_app
    from stackr.catalog import Catalog
    # Use a template that would expose an error if traefik_labels is called
    config = StackrConfig.model_validate({
        "global": {"data_dir": "/data", "timezone": "UTC", "puid": 1000, "pgid": 1000},
        "network": {"domain": "test.com", "local_domain": "home.test.com"},
        "security": {"socket_proxy": False},
    })
    app = Catalog().get("seerr")
    rendered = render_app(AppConfig(name="seerr"), app, config)
    assert "traefik.enable" not in rendered
    assert "traefik.http" not in rendered
```

- [ ] **Step 2: Run to verify it fails**

```bash
source .venv/bin/activate && pytest tests/test_renderer.py::test_no_traefik_in_render_context -v
```

This may already pass for seerr (which has no labels). Adjust to use a remaining app like `jellyfin` that still has labels, and assert labels are gone (they won't be until Task 12 strips the templates — so hold this test until Task 12, or write it for a new NPM-only app like `seerr`).

- [ ] **Step 3: Edit `stackr/renderer.py`**

1. Delete the `_traefik_labels()` internal function (the one that builds the `labels` dict).
2. Delete the `traefik_labels_helper()` closure inside `render_app`.
3. Remove `"traefik": stackr_config.traefik` and `"traefik_labels": traefik_labels_helper` from the Jinja2 context dict.
4. Remove the `_strip_empty_labels` post-processing call and its helper function (this was only needed because `traefik_labels()` could return `{}` when Traefik was disabled). Delete `_strip_empty_labels` entirely.
5. Remove any import of `TraefikConfig` if present.

The context dict in `render_app` after changes:
```python
context = {
    "global": stackr_config.global_,
    "network": stackr_config.network,
    "security": stackr_config.security,
    "vars": merged_vars,
    "app": catalog_app,
}
```

- [ ] **Step 4: Update `_make_config` helper in `tests/test_renderer.py`**

The helper currently passes `traefik={"enabled": True, "acme_email": "test@test.com", "dns_provider": "cloudflare"}`. Remove the `traefik` kwarg entirely:

```python
def _make_config(**kwargs) -> StackrConfig:
    base = {
        "global": {"data_dir": "/opt/appdata", "timezone": "UTC", "puid": 1000, "pgid": 1000},
        "network": {"domain": "test.com", "local_domain": "home.test.com"},
        "security": {"socket_proxy": False},
    }
    base.update(kwargs)
    return StackrConfig.model_validate(base)
```

- [ ] **Step 5: Remove `test_render_traefik_labels_present` and `test_render_traefik_external_mode` from `tests/test_renderer.py`**

- [ ] **Step 6: Run tests**

```bash
source .venv/bin/activate && pytest tests/test_renderer.py -v
```

Expected: all pass. (Templates with `traefik_labels()` calls will now raise `UndefinedError` — that's fine, they get fixed in Task 12.)

---

### Task 8: Delete middleware.py, dns_providers.py, and their tests

**Files:**
- Delete: `stackr/middleware.py`
- Delete: `stackr/dns_providers.py`
- Delete: `tests/test_middleware.py`
- Delete: `tests/test_dns_providers.py`
- Modify: `stackr/doctor.py`, `stackr/validator.py` (remove imports)

- [ ] **Step 1: Delete the files**

```bash
git rm stackr/middleware.py stackr/dns_providers.py
git rm tests/test_middleware.py tests/test_dns_providers.py
```

- [ ] **Step 2: Remove the import from `stackr/doctor.py`**

```python
# Remove this line:
from stackr.dns_providers import get_provider
```

- [ ] **Step 3: Remove the import from `stackr/validator.py`**

```python
# Remove this line:
from stackr.dns_providers import get_provider
```

- [ ] **Step 4: Run tests to surface any remaining import errors**

```bash
source .venv/bin/activate && pytest tests/ -v --tb=short 2>&1 | grep -E "ERROR|FAILED|ImportError"
```

Expected: errors only from Traefik-related functions that reference the deleted imports (those get fixed in the next task).

---

### Task 9: Remove Traefik checks from validator.py

**Files:**
- Modify: `stackr/validator.py`
- Modify: `tests/test_validator.py`

- [ ] **Step 1: Edit `stackr/validator.py`**

1. Delete `_check_dns_provider()` — the function that calls `get_provider(config.traefik.dns_provider)`.
2. Delete `_check_dns_provider_env_refs()` — checks for unresolved `${VAR}` in `traefik.dns_provider_env`.
3. Delete `_check_security_stack()` — validates `auth_provider` against authentik/authelia.
4. Add a simple `_check_crowdsec()` to preserve the crowdsec validation:

```python
def _check_crowdsec(
    config: StackrConfig,
    enabled_names: set[str],
    result: ValidationResult,
) -> None:
    """crowdsec: true requires the crowdsec app to be enabled."""
    if config.security.crowdsec and "crowdsec" not in enabled_names:
        result.errors.append(
            ValidationError(
                app="crowdsec",
                message="security.crowdsec is true but 'crowdsec' is not in apps",
            )
        )
```

5. Remove the `_check_dns_provider`, `_check_dns_provider_env_refs`, and `_check_security_stack` calls from `validate()`. Add `_check_crowdsec(config, enabled_names, result)` in their place.

6. Remove the `traefik_suggests` logic from `_check_app_deps` — the block that suppressed suggests warnings for traefik and socket-proxy. Delete those lines; let the normal deps logic run.

7. Remove `("traefik", "nginx-proxy-manager", "both bind host ports 80 and 443")` from the mutually-exclusive app pairs list (if it exists as a hard-coded pair).

8. Update the module docstring to remove deleted checks and add `crowdsec`.

- [ ] **Step 2: Remove Traefik test cases from `tests/test_validator.py`**

Delete these test functions:
- `test_traefik_suggests_suppressed_when_npm`
- `test_shared_traefik_port_no_conflict` (if it constructs a Traefik config)
- Any test that passes `traefik={"enabled": True, "dns_provider": "cloudflare", ...}` and tests DNS provider validation

Update all remaining test helpers that use `traefik={...}` in `StackrConfig.model_validate(...)` — remove the `traefik` key from those dicts. The standard base config for validator tests becomes:

```python
def _base_config(**kwargs):
    return {
        "global": {"data_dir": "/data", "timezone": "UTC", "puid": 1000, "pgid": 1000},
        "network": {"domain": "test.com", "local_domain": "home.test.com"},
        "security": {"socket_proxy": False},
        **kwargs,
    }
```

- [ ] **Step 3: Run tests**

```bash
source .venv/bin/activate && pytest tests/test_validator.py -v
```

Expected: all pass.

---

### Task 10: Strip Traefik from doctor.py, tui.py, web/routes.py, cli.py, migrate.py

**Files:**
- Modify: `stackr/doctor.py`
- Modify: `stackr/tui.py`
- Modify: `stackr/web/routes.py`
- Modify: `stackr/cli.py`
- Modify: `stackr/migrate.py`
- Modify: `tests/test_doctor.py`
- Modify: `tests/test_web.py`

- [ ] **Step 1: Edit `stackr/doctor.py`**

Remove the Traefik connectivity check (the function that calls `get_provider` and checks `config.traefik.enabled`). It's the check introduced around line 146. Remove its call from `run_doctor()` as well.

- [ ] **Step 2: Edit `stackr/tui.py`**

Remove the `traefik` settings section from the settings panel display. Search for `traefik` and delete any display rows for `traefik.enabled`, `traefik.dns_provider`, `traefik.acme_email`. Keep all other config display rows.

- [ ] **Step 3: Edit `stackr/web/routes.py`**

1. Remove `network_mode` and all `traefik_*` / `dns_provider*` parameters from `_save_all_settings()`.
2. Remove the `traefik` section from the `GET /api/settings` response dict (around line 433–451).
3. Remove the `traefik_enabled`, `dns_provider`, `dns_provider_env`, `network_mode` form parameters from the POST handler.
4. Remove the DNS env parsing block (the `for line in dns_provider_env.splitlines()` loop).

The settings API now handles: `global`, `network` (domain + local_domain only), `security`, `backup`, `alerts`.

- [ ] **Step 4: Edit `stackr/migrate.py`**

Remove `"traefik-v2": "traefik"` from `_DEPLOYRR_MAP`.

- [ ] **Step 5: Edit `stackr/cli.py`**

Search for `traefik` references. Remove any prompts or config display logic that references `traefik.enabled`, `traefik.dns_provider`, etc.

- [ ] **Step 6: Update `tests/test_doctor.py`**

Remove the test case for the Traefik DNS provider doctor check (the one that asserts a fail check when `dns_provider` is not in registry).

- [ ] **Step 7: Update `tests/test_web.py`**

Remove assertions that check for `traefik_enabled`, `dns_provider`, or `network_mode` in the settings API response. Update any POST `/api/settings` test payloads to remove Traefik fields.

- [ ] **Step 8: Run tests**

```bash
source .venv/bin/activate && pytest tests/test_doctor.py tests/test_web.py -v
```

Expected: all pass.

---

### Task 11: Strip labels from all 37 remaining compose templates

**Files:**
- Modify: all `catalog/**/*.j2` that still contain `traefik_labels`
- Modify: all `catalog/**/app.yml` that still contain `requires: [traefik]` or `exposure`

- [ ] **Step 1: Verify which templates still have traefik_labels calls**

```bash
grep -rl "traefik_labels" catalog/ --include="*.j2"
```

Expected: ~37 files listed.

- [ ] **Step 2: Strip labels blocks from all templates**

Run this Python script to remove the `labels:` block from each template:

```bash
python3 - << 'EOF'
import re
from pathlib import Path

pattern = re.compile(
    r'\n    labels:\n'
    r'(?:.*\n)*?'          # label entries
    r'(?=\n[a-zA-Z]|\Z)',  # stop at next top-level key or EOF
    re.MULTILINE
)

# More targeted: remove just the labels block from service definitions
label_block = re.compile(
    r'    labels:\n({% for k, v in traefik_labels\([^)]+\)\.items\(\) %}\n'
    r'      - "{{ k }}={{ v }}"\n'
    r'{% endfor %}\n?)',
    re.MULTILINE
)

for path in sorted(Path("catalog").rglob("compose.yml.j2")):
    content = path.read_text()
    if "traefik_labels" not in content:
        continue
    new_content = label_block.sub("", content)
    if new_content != content:
        path.write_text(new_content)
        print(f"Stripped: {path}")
    else:
        print(f"WARNING - manual fix needed: {path}")
EOF
```

- [ ] **Step 3: Manually verify any templates flagged as needing manual fixes**

Open each flagged file, remove the `labels:` block by hand. The block always looks like:

```yaml
    labels:
{% for k, v in traefik_labels(PORT).items() %}
      - "{{ k }}={{ v }}"
{% endfor %}
```

Delete it entirely.

- [ ] **Step 4: Confirm no templates still call traefik_labels**

```bash
grep -r "traefik_labels" catalog/
```

Expected: no output.

- [ ] **Step 5: Remove `requires: [traefik]` and `exposure` from all app.yml files**

```bash
python3 - << 'EOF'
import re
from pathlib import Path

for path in sorted(Path("catalog").rglob("app.yml")):
    content = path.read_text()
    original = content
    # Remove "exposure: ..." line
    content = re.sub(r'^exposure:.*\n', '', content, flags=re.MULTILINE)
    # Remove "  - traefik" from requires list
    content = re.sub(r'^  - traefik\n', '', content, flags=re.MULTILINE)
    # Remove "requires:\n" if it becomes empty (no entries left)
    content = re.sub(r'^requires:\n(?=\S|\Z)', '', content, flags=re.MULTILINE)
    if content != original:
        path.write_text(content)
        print(f"Updated: {path}")
EOF
```

- [ ] **Step 6: Verify no app.yml still references traefik or exposure**

```bash
grep -r "requires:.*traefik\|  - traefik\|^exposure:" catalog/ --include="app.yml"
```

Expected: no output. (Apps that have `requires: [pocket-id]` — like tinyauth — must be preserved; the script only removes `traefik` entries.)

- [ ] **Step 7: Run the full render smoke test**

```bash
source .venv/bin/activate && pytest tests/test_renderer.py::test_render_all_seed_apps -v
```

Expected: PASS — all seed apps render without `UndefinedError`.

- [ ] **Step 8: Run full test suite**

```bash
source .venv/bin/activate && ruff check stackr/ tests/ && mypy stackr/ && pytest tests/ -v --tb=short -q
```

Expected: all pass.

---

### Task 12: Update integration workflow for Phase 2

**Files:**
- Modify: `.github/workflows/integration.yml`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Simplify the Python render step in integration.yml**

Find the `StackrConfig.model_validate({...})` call in the "Render compose via stackr" step and remove the `traefik` block:

```python
# BEFORE
config = StackrConfig.model_validate({
    "global": {...},
    "network": {
        "mode": "external",
        "domain": "test.com",
        "local_domain": "home.test.com",
    },
    "traefik": {
        "enabled": True,
        "acme_email": "ci@test.com",
        "dns_provider": "cloudflare",
    },
    "security": {"socket_proxy": False},
})

# AFTER
config = StackrConfig.model_validate({
    "global": {
        "data_dir": "/opt/appdata",
        "timezone": "UTC",
        "puid": 1000,
        "pgid": 1000,
    },
    "network": {
        "domain": "test.com",
        "local_domain": "home.test.com",
    },
    "security": {"socket_proxy": False},
})
```

- [ ] **Step 2: Update CLAUDE.md**

Remove or trim these sections that are now obsolete:
- The "Cert resolvers and networking modes" section (external/internal/hybrid)
- The "DNS provider registry" section
- The "Security stack (Phase 2)" section (auth_provider, crowdsec-shares-traefik-logs)
- The `middleware.py` and `dns_providers.py` rows from the module responsibilities table
- The `traefik` row from the module responsibilities table
- References to `traefik_labels()` in the "Jinja2 templates" section — replace with a note that templates use the `proxy` network for NPM routing
- The `traefik` entry in "Adding a new catalog app — checklist" step 2

Keep the CrowdSec NPM bouncer note if you add one; keep all non-Traefik sections intact.

- [ ] **Step 3: Final full test run**

```bash
source .venv/bin/activate && ruff check stackr/ tests/ && mypy stackr/ && pytest tests/ -v -q
```

Expected: all pass (skips fine, zero failures).

- [ ] **Step 4: Commit Phase 2**

```bash
git add -A
git commit -m "feat: remove Traefik from engine and all compose templates

Deletes TraefikConfig, traefik_labels(), middleware.py, dns_providers.py.
Strips labels blocks from all 37 remaining compose templates and removes
requires:[traefik] + exposure from all app.yml files. Simplifies
NetworkConfig (no mode), SecurityConfig (no auth_provider), and the
integration CI render step. Updates validator, doctor, tui, web/routes,
cli, migrate accordingly. Updates CLAUDE.md."
```

> **→ Open PR for Phase 2.**
