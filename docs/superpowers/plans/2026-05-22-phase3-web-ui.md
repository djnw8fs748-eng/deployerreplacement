# Phase 3 — Alpine.js Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a static Alpine.js single-page app served by the FastAPI REST API at `http://localhost:7274`, providing full management of apps, catalog, settings, mounts, and system health.

**Architecture:** Three static files (`index.html`, `style.css`, `app.js`) in `stackr/web/static/`, served by `stackr/api/app.py` via `StaticFiles` mount. The entire UI consumes `/api/v1/` endpoints built in Phase 2 — no server-side rendering. Alpine.js manages reactive state; a single `stackrApp()` component function drives all pages.

**Tech Stack:** Alpine.js 3.x (CDN), plain HTML5/CSS3, Fetch API, EventSource (SSE). No build step. Python: FastAPI `StaticFiles`, `FileResponse`.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `stackr/api/app.py` | Mount `/static` + catch-all `GET /` → `index.html` |
| Create | `stackr/web/static/index.html` | SPA shell: layout, nav, page markup, Alpine directives |
| Create | `stackr/web/static/style.css` | Dark blue theme, grid layout, component styles |
| Create | `stackr/web/static/app.js` | `stackrApp()` function — all state, methods, API calls |
| Modify | `stackr/service.py` | Point service to `stackr api` at port 7274 |
| Modify | `stackr/cli.py` | Update `service install` default port to 7274 |
| Modify | `tests/test_api_app.py` | Add test: `GET /` returns 200 text/html |

---

## Task 1: Static file serving infrastructure

**Files:**
- Modify: `stackr/api/app.py`
- Modify: `tests/test_api_app.py`

- [ ] **Step 1.1: Write the failing test**

Add to `tests/test_api_app.py`:

```python
@pytest.mark.asyncio
async def test_spa_root_returns_html(tmp_path: Path) -> None:
    """GET / should serve the SPA index.html."""
    # Create the static dir with a minimal index.html
    static_dir = Path(__file__).parent.parent / "stackr" / "web" / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    index = static_dir / "index.html"
    if not index.exists():
        index.write_text("<!DOCTYPE html><html><body>Stackr</body></html>")

    cfg = tmp_path / "stackr.yml"
    cfg.write_text(
        "global:\n  data_dir: /opt/appdata\n"
        "network:\n  domain: test.local\n  local_domain: home.test.local\n"
    )
    api = create_api(cfg)
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_static_files_served(tmp_path: Path) -> None:
    """GET /static/style.css and /static/app.js should return 200 when files exist."""
    static_dir = Path(__file__).parent.parent / "stackr" / "web" / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    (static_dir / "style.css").write_text("body{}")
    (static_dir / "app.js").write_text("/* js */")

    cfg = tmp_path / "stackr.yml"
    cfg.write_text(
        "global:\n  data_dir: /opt/appdata\n"
        "network:\n  domain: test.local\n  local_domain: home.test.local\n"
    )
    api = create_api(cfg)
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        css = await client.get("/static/style.css")
        js = await client.get("/static/app.js")
    assert css.status_code == 200
    assert js.status_code == 200
```

- [ ] **Step 1.2: Run failing test**

```bash
cd /Users/dominiclittler/deployerreplacement
source .venv/bin/activate && pytest tests/test_api_app.py::test_spa_root_returns_html -v
```
Expected: FAIL — `404 Not Found` (route not registered yet).

- [ ] **Step 1.3: Implement static serving in `stackr/api/app.py`**

Replace the full `create_api` function with:

```python
"""FastAPI application factory for the Stackr REST API."""
from __future__ import annotations

from pathlib import Path
from typing import Any

_STATIC_DIR = Path(__file__).parent.parent / "web" / "static"


def create_api(config_path: Path = Path("stackr.yml")) -> Any:
    """Create and return the Stackr REST API FastAPI application."""
    try:
        import fastapi
    except ImportError as exc:
        raise RuntimeError("FastAPI is not installed.") from exc

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    from stackr.api.deps import set_config_path
    from stackr.api.routes.apps import router as apps_router
    from stackr.api.routes.catalog import router as catalog_router
    from stackr.api.routes.config import router as config_router
    from stackr.api.routes.deploy import router as deploy_router
    from stackr.api.routes.mounts import router as mounts_router
    from stackr.api.routes.system import router as system_router

    set_config_path(config_path)

    app = fastapi.FastAPI(
        title="Stackr API",
        description="REST API for Stackr homelab deployment tool",
        version="2.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    api = fastapi.APIRouter(prefix="/api/v1")
    api.include_router(system_router)
    api.include_router(catalog_router)
    api.include_router(config_router)
    api.include_router(apps_router)
    api.include_router(deploy_router)
    api.include_router(mounts_router)
    app.include_router(api)

    # Serve SPA root — must be registered before StaticFiles mount
    @app.get("/")
    def spa_root() -> FileResponse:
        return FileResponse(str(_STATIC_DIR / "index.html"))

    # Mount static files only when the directory exists (skips in minimal test setups)
    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    return app
```

- [ ] **Step 1.4: Create the static directory with placeholder files**

```bash
mkdir -p /Users/dominiclittler/deployerreplacement/stackr/web/static
touch /Users/dominiclittler/deployerreplacement/stackr/web/static/index.html
touch /Users/dominiclittler/deployerreplacement/stackr/web/static/style.css
touch /Users/dominiclittler/deployerreplacement/stackr/web/static/app.js
```

- [ ] **Step 1.5: Run tests**

```bash
source .venv/bin/activate && pytest tests/test_api_app.py -v
```
Expected: all tests pass (including the two new ones — the placeholder `index.html` satisfies the content-type check since FastAPI infers `text/html` from the `.html` extension).

- [ ] **Step 1.6: Commit**

```bash
git checkout -b feat/phase3-web-ui
git add stackr/api/app.py stackr/web/static/ tests/test_api_app.py
git commit -m "feat(api): serve static SPA from /static and / → index.html"
```

---

## Task 2: style.css — dark theme

**Files:**
- Write: `stackr/web/static/style.css`

- [ ] **Step 2.1: Write the full CSS**

Write `stackr/web/static/style.css`:

```css
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg: #0a0e1a;
  --surface: #111827;
  --surface2: #161d2e;
  --surface3: #1e2740;
  --border: rgba(99,120,180,.15);
  --border2: rgba(99,120,180,.28);
  --text: #e8edf8;
  --muted: #6b7faa;
  --accent: #4f7cff;
  --accent2: #38d9a9;
  --warn: #f59e0b;
  --danger: #f87171;
  --purple: #a78bfa;
  --mono: 'JetBrains Mono', monospace;
}

html, body { height: 100%; }
body {
  font-family: system-ui, -apple-system, sans-serif;
  background: var(--bg);
  color: var(--text);
  font-size: 14px;
  line-height: 1.5;
  display: grid;
  grid-template-columns: 200px 1fr;
  grid-template-rows: 52px 1fr;
  grid-template-areas: "topbar topbar" "sidebar main";
  height: 100vh;
  overflow: hidden;
}

/* ── Top bar ── */
.topbar {
  grid-area: topbar;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 0 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.logo {
  font-weight: 700;
  font-size: 18px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.logo-mark {
  width: 26px; height: 26px;
  background: var(--accent);
  border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  font-family: var(--mono); font-size: 11px; font-weight: 800; color: #fff;
}

/* ── Sidebar ── */
.sidebar {
  grid-area: sidebar;
  background: var(--surface);
  border-right: 1px solid var(--border);
  padding: 12px 8px;
  display: flex; flex-direction: column; gap: 2px;
  overflow-y: auto;
}
.nav-item {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  cursor: pointer;
  color: var(--muted);
  font-size: 13px; font-weight: 500;
  transition: all .15s;
  border: none; background: none; width: 100%; text-align: left;
}
.nav-item:hover { background: var(--surface2); color: var(--text); }
.nav-item.active { background: var(--surface3); color: var(--text); }

/* ── Main content ── */
.main {
  grid-area: main;
  overflow-y: auto;
  padding: 24px;
}

/* ── Page header ── */
.page-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 20px;
}
.page-title { font-size: 20px; font-weight: 700; }

/* ── Buttons ── */
.btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 7px 14px; border-radius: 8px;
  font-size: 13px; font-weight: 600;
  cursor: pointer; border: none; transition: all .15s;
}
.btn-primary { background: var(--accent); color: #fff; }
.btn-primary:hover { background: #3d6ef0; }
.btn-secondary { background: var(--surface3); color: var(--text); border: 1px solid var(--border2); }
.btn-secondary:hover { background: var(--surface2); }
.btn-danger { background: rgba(248,113,113,.15); color: var(--danger); border: 1px solid rgba(248,113,113,.3); }
.btn-danger:hover { background: rgba(248,113,113,.25); }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.btn:disabled { opacity: .5; cursor: not-allowed; }

/* ── Status badges ── */
.badge {
  display: inline-flex; align-items: center;
  padding: 2px 8px; border-radius: 12px;
  font-size: 11px; font-weight: 600;
  text-transform: uppercase; letter-spacing: .04em;
}
.badge-running  { background: rgba(56,217,169,.15); color: var(--accent2); }
.badge-stopped  { background: rgba(248,113,113,.15); color: var(--danger); }
.badge-degraded { background: rgba(245,158,11,.15);  color: var(--warn); }
.badge-drift    { background: rgba(167,139,250,.15); color: var(--purple); }
.badge-unknown  { background: rgba(107,127,170,.12); color: var(--muted); }

/* ── App grid ── */
.app-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}
.app-card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 12px; padding: 16px;
  cursor: pointer; transition: border-color .15s;
}
.app-card:hover { border-color: var(--border2); }
.app-card-header {
  display: flex; align-items: flex-start; justify-content: space-between;
  margin-bottom: 10px;
}
.app-name { font-weight: 600; font-size: 15px; }
.app-meta { font-size: 12px; color: var(--muted); margin-top: 2px; }
.app-error { font-size: 12px; color: var(--danger); margin-top: 6px; }
.app-actions { display: flex; gap: 6px; margin-top: 12px; align-items: center; }

/* ── Toggle ── */
.toggle-track {
  width: 32px; height: 18px; border-radius: 9px;
  background: var(--surface3); border: 1px solid var(--border2);
  position: relative; transition: background .2s; cursor: pointer; flex-shrink: 0;
}
.toggle-track.on { background: var(--accent); border-color: var(--accent); }
.toggle-thumb {
  position: absolute; width: 12px; height: 12px;
  border-radius: 50%; background: #fff;
  top: 2px; left: 2px; transition: left .2s;
}
.toggle-track.on .toggle-thumb { left: 16px; }

/* ── Card ── */
.card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 12px; padding: 20px; margin-bottom: 16px;
}
.card-title { font-weight: 600; margin-bottom: 14px; }

/* ── Forms ── */
.form-row { margin-bottom: 12px; }
.form-label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; font-weight: 500; }
.form-input, .form-select {
  width: 100%; background: var(--surface2); border: 1px solid var(--border);
  border-radius: 8px; color: var(--text); padding: 8px 12px;
  font-size: 13px; outline: none; font-family: inherit;
}
.form-input:focus, .form-select:focus { border-color: var(--accent); }

/* ── Table ── */
.table { width: 100%; border-collapse: collapse; font-size: 13px; }
.table th {
  text-align: left; color: var(--muted); font-weight: 500;
  padding: 8px 12px; border-bottom: 1px solid var(--border);
}
.table td { padding: 10px 12px; border-bottom: 1px solid var(--border); }
.table tr:last-child td { border-bottom: none; }

/* ── Deploy console ── */
.deploy-console {
  background: var(--surface2); border: 1px solid var(--border);
  border-radius: 8px; padding: 12px;
  font-family: var(--mono); font-size: 12px;
  max-height: 260px; overflow-y: auto; line-height: 1.6;
}

/* ── Slide panel ── */
.panel-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,.55); z-index: 100;
}
.panel {
  position: fixed; top: 0; right: 0;
  width: 520px; height: 100vh;
  background: var(--surface); border-left: 1px solid var(--border);
  z-index: 101; overflow-y: auto; padding: 24px;
}

/* ── Catalog ── */
.catalog-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 10px; margin-bottom: 4px;
}
.catalog-card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 10px; padding: 14px;
}
.catalog-name { font-weight: 600; font-size: 14px; }
.catalog-desc { font-size: 12px; color: var(--muted); margin-top: 3px; line-height: 1.4; }

/* ── Section header (catalog categories) ── */
.section-header {
  font-size: 11px; color: var(--muted); text-transform: uppercase;
  letter-spacing: .05em; margin: 18px 0 8px; font-weight: 600;
}
.section-header:first-child { margin-top: 0; }

/* ── Health checks ── */
.check-row {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 0; border-bottom: 1px solid var(--border);
}
.check-row:last-child { border-bottom: none; }
.dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.dot-ok   { background: var(--accent2); }
.dot-fail { background: var(--danger); }

/* ── Utilities ── */
.spinner {
  display: inline-block; width: 14px; height: 14px;
  border: 2px solid var(--surface3); border-top-color: var(--accent);
  border-radius: 50%; animation: spin .7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.empty { text-align: center; color: var(--muted); padding: 48px 0; font-size: 13px; }

.error-banner {
  background: rgba(248,113,113,.1); border: 1px solid rgba(248,113,113,.3);
  border-radius: 8px; color: var(--danger);
  padding: 10px 14px; font-size: 13px; margin-bottom: 16px;
}

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--surface3); border-radius: 3px; }
```

- [ ] **Step 2.2: Commit**

```bash
git add stackr/web/static/style.css
git commit -m "feat(web): dark theme CSS for Alpine.js SPA"
```

---

## Task 3: app.js — Alpine.js component

**Files:**
- Write: `stackr/web/static/app.js`

This is the single `stackrApp()` function that drives all pages. No placeholders — write the entire file.

- [ ] **Step 3.1: Write `stackr/web/static/app.js`**

```javascript
/* Stackr Alpine.js SPA — all state and API calls for the management console. */

const API = '/api/v1';

async function apiFetch(path, options = {}) {
  const r = await fetch(API + path, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try { const d = await r.json(); msg = d.detail || JSON.stringify(d); } catch (_) {}
    throw new Error(msg);
  }
  if (r.status === 204) return null;
  return r.json();
}

function stackrApp() {
  return {
    // ── Global ──────────────────────────────────────────────────────────────
    page: 'dashboard',
    error: null,

    // ── Dashboard ───────────────────────────────────────────────────────────
    apps: [],
    appsLoading: false,
    deployJob: null,
    deployPolling: null,

    // ── App detail panel ────────────────────────────────────────────────────
    panelOpen: false,
    panelApp: null,
    panelDetail: null,
    panelHistory: [],
    panelVars: {},
    panelVarsSaving: false,
    panelLogs: [],
    panelLogsRunning: false,
    panelLogsSource: null,

    // ── Catalog ─────────────────────────────────────────────────────────────
    catalog: [],
    catalogSearch: '',
    catalogLoading: false,

    // ── Settings ────────────────────────────────────────────────────────────
    configData: null,
    configSaving: {},

    // ── Mounts ──────────────────────────────────────────────────────────────
    mounts: [],
    mountForm: { name: '', type: 'smb', remote: '', mountpoint: '', options: '', username: '' },
    mountAdding: false,

    // ── System ──────────────────────────────────────────────────────────────
    health: null,
    healthLoading: false,
    validationResult: null,
    validating: false,
    secrets: [],
    backupRunning: false,
    snapshots: [],

    // ── Lifecycle ───────────────────────────────────────────────────────────

    async init() {
      await this.loadApps();
      // Keep dashboard fresh every 10s (light poll — Docker status only)
      setInterval(() => { if (this.page === 'dashboard') this.loadApps(); }, 10000);
    },

    setError(msg) {
      this.error = String(msg);
      setTimeout(() => { if (this.error === String(msg)) this.error = null; }, 5000);
    },

    async navigate(p) {
      this.page = p;
      this.error = null;
      if (p === 'dashboard') await this.loadApps();
      if (p === 'catalog')   await this.loadCatalog();
      if (p === 'settings')  await this.loadConfig();
      if (p === 'mounts')    await this.loadMounts();
      if (p === 'system')    await this.loadSystem();
    },

    // ── Dashboard ───────────────────────────────────────────────────────────

    async loadApps() {
      this.appsLoading = true;
      try {
        this.apps = await apiFetch('/apps/');
      } catch (e) {
        this.setError(e.message);
      } finally {
        this.appsLoading = false;
      }
    },

    badgeClass(status) {
      return 'badge badge-' + (status || 'unknown');
    },

    async deployAll() {
      try {
        this.deployJob = await apiFetch('/deploy/', { method: 'POST' });
        this.startPolling();
      } catch (e) {
        this.setError(e.message);
      }
    },

    startPolling() {
      if (this.deployPolling) return;
      this.deployPolling = setInterval(async () => {
        try {
          const s = await apiFetch('/deploy/status');
          this.deployJob = s;
          if (s.status === 'done' || s.status === 'failed') {
            clearInterval(this.deployPolling);
            this.deployPolling = null;
            await this.loadApps();
          }
        } catch (_) { /* ignore transient errors during polling */ }
      }, 2000);
    },

    async toggleApp(app, e) {
      e.stopPropagation();
      try {
        await apiFetch('/apps/' + app.name + '/toggle', { method: 'POST' });
        await this.loadApps();
      } catch (e) {
        this.setError(e.message);
      }
    },

    async deploySingle(app, e) {
      e.stopPropagation();
      try {
        this.deployJob = await apiFetch('/apps/' + app.name + '/deploy', { method: 'POST' });
        this.startPolling();
      } catch (e) {
        this.setError(e.message);
      }
    },

    // ── App detail panel ────────────────────────────────────────────────────

    async openPanel(app) {
      this.panelApp = app;
      this.panelOpen = true;
      this.panelDetail = null;
      this.panelHistory = [];
      this.panelLogs = [];
      this.panelVars = {};
      try {
        const [detail, history] = await Promise.all([
          apiFetch('/apps/' + app.name),
          apiFetch('/apps/' + app.name + '/history'),
        ]);
        this.panelDetail = detail;
        this.panelHistory = history;
        this.panelVars = detail.vars ? { ...detail.vars } : {};
      } catch (e) {
        this.setError(e.message);
      }
    },

    closePanel() {
      this.stopLogs();
      this.panelOpen = false;
      this.panelApp = null;
      this.panelDetail = null;
    },

    async saveVars() {
      if (!this.panelApp) return;
      this.panelVarsSaving = true;
      try {
        await apiFetch('/apps/' + this.panelApp.name + '/vars', {
          method: 'PUT',
          body: JSON.stringify(this.panelVars),
        });
      } catch (e) {
        this.setError(e.message);
      } finally {
        this.panelVarsSaving = false;
      }
    },

    async rollbackApp() {
      if (!this.panelApp) return;
      try {
        await apiFetch('/apps/' + this.panelApp.name + '/rollback', { method: 'POST' });
        await this.loadApps();
        const updated = await apiFetch('/apps/' + this.panelApp.name);
        this.panelDetail = updated;
        this.panelApp = { ...this.panelApp, status: updated.status };
      } catch (e) {
        this.setError(e.message);
      }
    },

    startLogs() {
      if (this.panelLogsRunning || !this.panelApp) return;
      this.panelLogs = [];
      this.panelLogsRunning = true;
      this.panelLogsSource = new EventSource('/api/v1/apps/' + this.panelApp.name + '/logs');
      this.panelLogsSource.onmessage = (ev) => {
        this.panelLogs.push(ev.data);
        if (this.panelLogs.length > 500) this.panelLogs.shift();
      };
      this.panelLogsSource.onerror = () => this.stopLogs();
    },

    stopLogs() {
      if (this.panelLogsSource) {
        this.panelLogsSource.close();
        this.panelLogsSource = null;
      }
      this.panelLogsRunning = false;
    },

    // ── Catalog ─────────────────────────────────────────────────────────────

    async loadCatalog() {
      this.catalogLoading = true;
      try {
        this.catalog = await apiFetch('/catalog/');
      } catch (e) {
        this.setError(e.message);
      } finally {
        this.catalogLoading = false;
      }
    },

    get filteredCatalog() {
      if (!this.catalogSearch) return this.catalog;
      const q = this.catalogSearch.toLowerCase();
      return this.catalog.filter(a =>
        a.name.includes(q) ||
        a.display_name.toLowerCase().includes(q) ||
        a.description.toLowerCase().includes(q)
      );
    },

    catalogByCategory() {
      const groups = {};
      for (const a of this.filteredCatalog) {
        (groups[a.category] = groups[a.category] || []).push(a);
      }
      return groups;
    },

    isEnabled(name) {
      return this.apps.some(a => a.name === name && a.enabled);
    },

    async enableFromCatalog(name) {
      try {
        await apiFetch('/apps/' + name + '/toggle', { method: 'POST' });
        await this.loadApps();
      } catch (e) {
        this.setError(e.message);
      }
    },

    // ── Settings ────────────────────────────────────────────────────────────

    async loadConfig() {
      try {
        const raw = await apiFetch('/config/');
        // Rename 'global' key to 'globalCfg' to avoid shadowing in Alpine templates
        this.configData = { ...raw, globalCfg: raw['global'] };
      } catch (e) {
        this.setError(e.message);
      }
    },

    async saveConfigSection(section, payload) {
      this.configSaving = { ...this.configSaving, [section]: true };
      try {
        await apiFetch('/config/' + section, {
          method: 'PUT',
          body: JSON.stringify(payload),
        });
      } catch (e) {
        this.setError(e.message);
      } finally {
        const next = { ...this.configSaving };
        delete next[section];
        this.configSaving = next;
      }
    },

    // ── Mounts ──────────────────────────────────────────────────────────────

    async loadMounts() {
      try {
        this.mounts = await apiFetch('/mounts/');
      } catch (e) {
        this.setError(e.message);
      }
    },

    async addMount() {
      this.mountAdding = true;
      try {
        await apiFetch('/mounts/', {
          method: 'POST',
          body: JSON.stringify(this.mountForm),
        });
        this.mountForm = { name: '', type: 'smb', remote: '', mountpoint: '', options: '', username: '' };
        await this.loadMounts();
      } catch (e) {
        this.setError(e.message);
      } finally {
        this.mountAdding = false;
      }
    },

    async deleteMount(name) {
      try {
        await apiFetch('/mounts/' + name, { method: 'DELETE' });
        await this.loadMounts();
      } catch (e) {
        this.setError(e.message);
      }
    },

    // ── System ──────────────────────────────────────────────────────────────

    async loadSystem() {
      this.healthLoading = true;
      try {
        const [h, s] = await Promise.all([
          apiFetch('/system/health'),
          apiFetch('/system/secrets'),
        ]);
        this.health = h;
        this.secrets = s.names;
      } catch (e) {
        this.setError(e.message);
      } finally {
        this.healthLoading = false;
      }
    },

    async runValidate() {
      this.validating = true;
      this.validationResult = null;
      try {
        this.validationResult = await apiFetch('/system/validate', { method: 'POST' });
      } catch (e) {
        this.setError(e.message);
      } finally {
        this.validating = false;
      }
    },

    async runBackup() {
      this.backupRunning = true;
      try {
        await apiFetch('/system/backup', { method: 'POST' });
      } catch (e) {
        this.setError(e.message);
      } finally {
        this.backupRunning = false;
      }
    },

    async loadSnapshots() {
      try {
        this.snapshots = await apiFetch('/system/snapshots');
      } catch (e) {
        this.setError(e.message);
      }
    },
  };
}
```

- [ ] **Step 3.2: Commit**

```bash
git add stackr/web/static/app.js
git commit -m "feat(web): Alpine.js stackrApp() component — all pages and API calls"
```

---

## Task 4: index.html — SPA markup

**Files:**
- Write: `stackr/web/static/index.html`

- [ ] **Step 4.1: Write `stackr/web/static/index.html`**

Write the full file. Every Alpine.js directive references properties/methods defined in Task 3's `app.js`.

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Stackr</title>
  <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.14.1/dist/cdn.min.js"></script>
  <link rel="stylesheet" href="/static/style.css">
  <script src="/static/app.js"></script>
</head>
<body x-data="stackrApp()" x-init="init()">

  <!-- ── Top bar ── -->
  <header class="topbar">
    <div class="logo">
      <div class="logo-mark">S</div>
      Stackr
    </div>
    <div style="display:flex;align-items:center;gap:12px">
      <template x-if="deployJob && deployJob.status === 'running'">
        <div style="display:flex;align-items:center;gap:7px;font-size:13px;color:var(--muted)">
          <span class="spinner"></span> Deploying…
        </div>
      </template>
      <template x-if="deployJob && deployJob.status === 'done'">
        <span style="color:var(--accent2);font-size:13px;font-weight:600">✓ Done</span>
      </template>
      <template x-if="deployJob && deployJob.status === 'failed'">
        <span style="color:var(--danger);font-size:13px;font-weight:600">✗ Failed</span>
      </template>
      <button class="btn btn-primary"
        @click="deployAll()"
        :disabled="deployJob && deployJob.status === 'running'">
        ⬆ Deploy All
      </button>
    </div>
  </header>

  <!-- ── Sidebar ── -->
  <nav class="sidebar">
    <button class="nav-item" :class="page==='dashboard' && 'active'" @click="navigate('dashboard')">
      ▦ Dashboard
    </button>
    <button class="nav-item" :class="page==='catalog' && 'active'" @click="navigate('catalog')">
      ⊞ Catalog
    </button>
    <button class="nav-item" :class="page==='settings' && 'active'" @click="navigate('settings')">
      ⚙ Settings
    </button>
    <button class="nav-item" :class="page==='mounts' && 'active'" @click="navigate('mounts')">
      ⛁ Mounts
    </button>
    <button class="nav-item" :class="page==='system' && 'active'" @click="navigate('system')">
      ◎ System
    </button>
  </nav>

  <!-- ── Main ── -->
  <main class="main">

    <!-- Error banner -->
    <template x-if="error">
      <div class="error-banner" x-text="error"></div>
    </template>

    <!-- ══════════════════════════════════════════════════════════════════════
         DASHBOARD PAGE
    ══════════════════════════════════════════════════════════════════════════ -->
    <div x-show="page === 'dashboard'" x-cloak>
      <div class="page-header">
        <h1 class="page-title">Dashboard</h1>
        <button class="btn btn-secondary btn-sm" @click="loadApps()">↺ Refresh</button>
      </div>

      <!-- Deploy console (shown when a deploy job exists) -->
      <template x-if="deployJob && deployJob.status !== 'idle'">
        <div class="card" style="margin-bottom:20px">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
            <span x-show="deployJob.status === 'running'" class="spinner"></span>
            <strong>
              <span x-show="deployJob.status === 'running'">Deploying…</span>
              <span x-show="deployJob.status === 'done'" style="color:var(--accent2)">✓ Deploy complete</span>
              <span x-show="deployJob.status === 'failed'" style="color:var(--danger)">✗ Deploy failed</span>
            </strong>
            <span x-show="deployJob.error" style="color:var(--danger);font-size:12px" x-text="deployJob.error"></span>
          </div>
          <template x-if="deployJob.results && deployJob.results.length">
            <div class="deploy-console">
              <template x-for="r in deployJob.results" :key="r.app_name">
                <div :style="`color:${r.success ? 'var(--accent2)' : 'var(--danger)'}`">
                  <span x-text="r.success ? '✓ ' : '✗ '"></span>
                  <span x-text="r.app_name"></span>
                  <span x-show="!r.success && r.error" x-text="' — ' + r.error" style="color:var(--danger)"></span>
                  <span x-show="r.duration_ms" x-text="` (${r.duration_ms}ms)`" style="color:var(--muted)"></span>
                </div>
              </template>
            </div>
          </template>
        </div>
      </template>

      <div x-show="appsLoading && apps.length === 0" class="empty">
        <span class="spinner"></span>
      </div>
      <div x-show="!appsLoading && apps.length === 0" class="empty">
        No apps configured. Enable apps from the <strong>Catalog</strong> or edit <code>stackr.yml</code>.
      </div>

      <div class="app-grid">
        <template x-for="app in apps" :key="app.name">
          <div class="app-card" @click="openPanel(app)">
            <div class="app-card-header">
              <div>
                <div class="app-name" x-text="app.name"></div>
                <div class="app-meta"
                  x-text="app.deployed_at ? 'Deployed ' + app.deployed_at.slice(0,10) : 'Never deployed'">
                </div>
              </div>
              <span :class="badgeClass(app.status)" x-text="app.status"></span>
            </div>
            <template x-if="app.last_error">
              <div class="app-error" x-text="app.last_error.slice(0, 120)"></div>
            </template>
            <div class="app-actions" @click.stop>
              <!-- enabled toggle -->
              <div class="toggle-track"
                :class="app.enabled && 'on'"
                @click="toggleApp(app, $event)"
                title="Toggle enabled">
                <div class="toggle-thumb"></div>
              </div>
              <span style="font-size:12px;color:var(--muted)" x-text="app.enabled ? 'On' : 'Off'"></span>
              <!-- deploy button -->
              <button class="btn btn-primary btn-sm"
                x-show="app.enabled"
                @click.stop="deploySingle(app, $event)">
                Deploy
              </button>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- ══════════════════════════════════════════════════════════════════════
         CATALOG PAGE
    ══════════════════════════════════════════════════════════════════════════ -->
    <div x-show="page === 'catalog'" x-cloak>
      <div class="page-header">
        <h1 class="page-title">Catalog</h1>
        <input type="text" class="form-input" style="width:260px"
          placeholder="Search apps…" x-model="catalogSearch">
      </div>

      <div x-show="catalogLoading" class="empty"><span class="spinner"></span></div>

      <template x-if="!catalogLoading && catalog.length > 0">
        <div>
          <template x-for="[cat, catApps] in Object.entries(catalogByCategory())" :key="cat">
            <div>
              <div class="section-header" x-text="cat"></div>
              <div class="catalog-grid">
                <template x-for="app in catApps" :key="app.name">
                  <div class="catalog-card">
                    <div class="catalog-name" x-text="app.display_name || app.name"></div>
                    <div class="catalog-desc" x-text="app.description"></div>
                    <div style="margin-top:10px;display:flex;align-items:center;justify-content:space-between;gap:8px">
                      <span x-show="app.requires.length > 0"
                        style="font-size:11px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
                        x-text="'Needs: ' + app.requires.join(', ')"></span>
                      <button
                        class="btn btn-sm"
                        style="flex-shrink:0"
                        :class="isEnabled(app.name) ? 'btn-secondary' : 'btn-primary'"
                        @click="enableFromCatalog(app.name)"
                        x-text="isEnabled(app.name) ? '✓ Enabled' : 'Enable'">
                      </button>
                    </div>
                  </div>
                </template>
              </div>
            </div>
          </template>
        </div>
      </template>

      <div x-show="!catalogLoading && catalog.length === 0" class="empty">
        No catalog apps found.
      </div>
    </div>

    <!-- ══════════════════════════════════════════════════════════════════════
         SETTINGS PAGE
    ══════════════════════════════════════════════════════════════════════════ -->
    <div x-show="page === 'settings'" x-cloak>
      <div class="page-header">
        <h1 class="page-title">Settings</h1>
      </div>

      <div x-show="!configData" class="empty"><span class="spinner"></span></div>

      <template x-if="configData">
        <div>

          <!-- Global -->
          <div class="card">
            <div class="card-title">Global</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:0 16px">
              <div class="form-row" style="grid-column:1/-1">
                <label class="form-label">Data directory</label>
                <input type="text" class="form-input" x-model="configData.globalCfg.data_dir">
              </div>
              <div class="form-row" style="grid-column:1/-1">
                <label class="form-label">Timezone</label>
                <input type="text" class="form-input" x-model="configData.globalCfg.timezone"
                  placeholder="UTC">
              </div>
              <div class="form-row">
                <label class="form-label">PUID</label>
                <input type="number" class="form-input" x-model.number="configData.globalCfg.puid">
              </div>
              <div class="form-row">
                <label class="form-label">PGID</label>
                <input type="number" class="form-input" x-model.number="configData.globalCfg.pgid">
              </div>
            </div>
            <button class="btn btn-primary btn-sm"
              :disabled="configSaving['global']"
              @click="saveConfigSection('global', {
                data_dir: configData.globalCfg.data_dir,
                timezone: configData.globalCfg.timezone,
                puid: configData.globalCfg.puid,
                pgid: configData.globalCfg.pgid
              })">
              <span x-show="configSaving['global']" class="spinner"></span>
              Save
            </button>
          </div>

          <!-- Network -->
          <div class="card">
            <div class="card-title">Network</div>
            <div class="form-row">
              <label class="form-label">Public domain</label>
              <input type="text" class="form-input" x-model="configData.network.domain"
                placeholder="example.com">
            </div>
            <div class="form-row">
              <label class="form-label">Local domain</label>
              <input type="text" class="form-input" x-model="configData.network.local_domain"
                placeholder="home.example.com">
            </div>
            <button class="btn btn-primary btn-sm"
              :disabled="configSaving['network']"
              @click="saveConfigSection('network', {
                domain: configData.network.domain,
                local_domain: configData.network.local_domain
              })">
              <span x-show="configSaving['network']" class="spinner"></span>
              Save
            </button>
          </div>

          <!-- Security -->
          <div class="card">
            <div class="card-title">Security</div>
            <div class="form-row" style="display:flex;align-items:center;gap:10px">
              <div class="toggle-track"
                :class="configData.security.socket_proxy && 'on'"
                @click="configData.security.socket_proxy = !configData.security.socket_proxy">
                <div class="toggle-thumb"></div>
              </div>
              <span>Socket proxy (recommended)</span>
            </div>
            <div class="form-row" style="display:flex;align-items:center;gap:10px">
              <div class="toggle-track"
                :class="configData.security.crowdsec && 'on'"
                @click="configData.security.crowdsec = !configData.security.crowdsec">
                <div class="toggle-thumb"></div>
              </div>
              <span>CrowdSec</span>
            </div>
            <button class="btn btn-primary btn-sm"
              :disabled="configSaving['security']"
              @click="saveConfigSection('security', {
                socket_proxy: configData.security.socket_proxy,
                crowdsec: configData.security.crowdsec
              })">
              <span x-show="configSaving['security']" class="spinner"></span>
              Save
            </button>
          </div>

          <!-- Backup -->
          <div class="card">
            <div class="card-title">Backup</div>
            <div class="form-row" style="display:flex;align-items:center;gap:10px">
              <div class="toggle-track"
                :class="configData.backup.enabled && 'on'"
                @click="configData.backup.enabled = !configData.backup.enabled">
                <div class="toggle-thumb"></div>
              </div>
              <span>Enable backups</span>
            </div>
            <div class="form-row">
              <label class="form-label">Destination</label>
              <input type="text" class="form-input" x-model="configData.backup.destination"
                placeholder="/mnt/backup">
            </div>
            <div class="form-row">
              <label class="form-label">Schedule (cron)</label>
              <input type="text" class="form-input" x-model="configData.backup.schedule"
                placeholder="0 2 * * *">
            </div>
            <button class="btn btn-primary btn-sm"
              :disabled="configSaving['backup']"
              @click="saveConfigSection('backup', {
                enabled: configData.backup.enabled,
                destination: configData.backup.destination,
                schedule: configData.backup.schedule
              })">
              <span x-show="configSaving['backup']" class="spinner"></span>
              Save
            </button>
          </div>

          <!-- Alerts -->
          <div class="card">
            <div class="card-title">Alerts</div>
            <div class="form-row" style="display:flex;align-items:center;gap:10px">
              <div class="toggle-track"
                :class="configData.alerts.enabled && 'on'"
                @click="configData.alerts.enabled = !configData.alerts.enabled">
                <div class="toggle-thumb"></div>
              </div>
              <span>Enable alerts</span>
            </div>
            <div class="form-row">
              <label class="form-label">Provider</label>
              <select class="form-input form-select" x-model="configData.alerts.provider">
                <option value="ntfy">ntfy</option>
                <option value="gotify">Gotify</option>
                <option value="webhook">Webhook</option>
              </select>
            </div>
            <div class="form-row">
              <label class="form-label">URL</label>
              <input type="text" class="form-input" x-model="configData.alerts.url"
                placeholder="https://ntfy.sh/my-topic">
            </div>
            <button class="btn btn-primary btn-sm"
              :disabled="configSaving['alerts']"
              @click="saveConfigSection('alerts', {
                enabled: configData.alerts.enabled,
                provider: configData.alerts.provider,
                url: configData.alerts.url
              })">
              <span x-show="configSaving['alerts']" class="spinner"></span>
              Save
            </button>
          </div>

        </div>
      </template>
    </div>

    <!-- ══════════════════════════════════════════════════════════════════════
         MOUNTS PAGE
    ══════════════════════════════════════════════════════════════════════════ -->
    <div x-show="page === 'mounts'" x-cloak>
      <div class="page-header">
        <h1 class="page-title">Mounts</h1>
      </div>

      <!-- Add form -->
      <div class="card">
        <div class="card-title">Add mount</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:0 16px">
          <div class="form-row">
            <label class="form-label">Name</label>
            <input type="text" class="form-input" x-model="mountForm.name" placeholder="media">
          </div>
          <div class="form-row">
            <label class="form-label">Type</label>
            <select class="form-input form-select" x-model="mountForm.type">
              <option value="smb">SMB / CIFS</option>
              <option value="nfs">NFS</option>
              <option value="rclone">Rclone</option>
            </select>
          </div>
          <div class="form-row">
            <label class="form-label">Remote</label>
            <input type="text" class="form-input" x-model="mountForm.remote"
              placeholder="//server/share or remote:path">
          </div>
          <div class="form-row">
            <label class="form-label">Mountpoint</label>
            <input type="text" class="form-input" x-model="mountForm.mountpoint"
              placeholder="/mnt/media">
          </div>
          <div class="form-row">
            <label class="form-label">Options (optional)</label>
            <input type="text" class="form-input" x-model="mountForm.options"
              placeholder="uid=1000,gid=1000">
          </div>
          <div class="form-row">
            <label class="form-label">Username (optional)</label>
            <input type="text" class="form-input" x-model="mountForm.username">
          </div>
        </div>
        <button class="btn btn-primary btn-sm"
          :disabled="mountAdding || !mountForm.name || !mountForm.remote || !mountForm.mountpoint"
          @click="addMount()">
          <span x-show="mountAdding" class="spinner"></span>
          Add mount
        </button>
      </div>

      <!-- List -->
      <div class="card">
        <div class="card-title">Configured mounts</div>
        <div x-show="mounts.length === 0" style="color:var(--muted);font-size:13px">
          No mounts configured.
        </div>
        <table class="table" x-show="mounts.length > 0">
          <thead>
            <tr>
              <th>Name</th><th>Type</th><th>Remote</th><th>Mountpoint</th><th></th>
            </tr>
          </thead>
          <tbody>
            <template x-for="m in mounts" :key="m.name">
              <tr>
                <td x-text="m.name"></td>
                <td x-text="m.type"></td>
                <td style="font-family:var(--mono);font-size:12px" x-text="m.remote"></td>
                <td style="font-family:var(--mono);font-size:12px" x-text="m.mountpoint"></td>
                <td>
                  <button class="btn btn-danger btn-sm" @click="deleteMount(m.name)">Remove</button>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ══════════════════════════════════════════════════════════════════════
         SYSTEM PAGE
    ══════════════════════════════════════════════════════════════════════════ -->
    <div x-show="page === 'system'" x-cloak>
      <div class="page-header">
        <h1 class="page-title">System</h1>
        <button class="btn btn-secondary btn-sm" @click="loadSystem()">↺ Refresh</button>
      </div>

      <!-- Health -->
      <div class="card">
        <div class="card-title">Health checks</div>
        <div x-show="healthLoading" class="empty"><span class="spinner"></span></div>
        <template x-if="health">
          <div>
            <div style="margin-bottom:12px">
              <span :class="health.healthy ? 'badge badge-running' : 'badge badge-stopped'"
                x-text="health.healthy ? 'All checks passed' : 'Issues detected'">
              </span>
            </div>
            <template x-for="c in health.checks" :key="c.name">
              <div class="check-row">
                <div class="dot" :class="c.ok ? 'dot-ok' : 'dot-fail'"></div>
                <strong style="font-size:13px" x-text="c.name"></strong>
                <span style="color:var(--muted);font-size:12px;flex:1" x-text="c.message"></span>
              </div>
            </template>
          </div>
        </template>
      </div>

      <!-- Validate -->
      <div class="card">
        <div class="card-title">Pre-deploy validation</div>
        <button class="btn btn-secondary btn-sm" @click="runValidate()" :disabled="validating">
          <span x-show="validating" class="spinner"></span>
          Run validation
        </button>
        <template x-if="validationResult">
          <div style="margin-top:14px">
            <span :class="validationResult.ok ? 'badge badge-running' : 'badge badge-stopped'"
              x-text="validationResult.ok ? '✓ Validation passed' : '✗ Validation failed'">
            </span>
            <template x-if="validationResult.errors.length > 0">
              <div style="margin-top:12px">
                <div style="font-size:12px;font-weight:600;color:var(--danger);margin-bottom:6px">
                  Errors
                </div>
                <template x-for="e in validationResult.errors" :key="e.app + e.message">
                  <div style="font-size:12px;color:var(--danger);margin-bottom:3px">
                    <strong x-text="e.app"></strong>: <span x-text="e.message"></span>
                  </div>
                </template>
              </div>
            </template>
            <template x-if="validationResult.warnings.length > 0">
              <div style="margin-top:12px">
                <div style="font-size:12px;font-weight:600;color:var(--warn);margin-bottom:6px">
                  Warnings
                </div>
                <template x-for="w in validationResult.warnings" :key="w.app + w.message">
                  <div style="font-size:12px;color:var(--warn);margin-bottom:3px">
                    <strong x-text="w.app"></strong>: <span x-text="w.message"></span>
                  </div>
                </template>
              </div>
            </template>
          </div>
        </template>
      </div>

      <!-- Secrets -->
      <div class="card">
        <div class="card-title">Resolved secret names</div>
        <div x-show="secrets.length === 0" style="color:var(--muted);font-size:13px">
          No secrets loaded. Set vars in <code>.stackr.env</code>.
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:6px">
          <template x-for="s in secrets" :key="s">
            <span style="background:var(--surface2);border:1px solid var(--border);border-radius:6px;
              padding:3px 8px;font-family:var(--mono);font-size:12px;color:var(--muted)"
              x-text="s">
            </span>
          </template>
        </div>
      </div>

      <!-- Backup -->
      <div class="card">
        <div class="card-title">Backup</div>
        <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
          <button class="btn btn-secondary btn-sm" @click="runBackup()" :disabled="backupRunning">
            <span x-show="backupRunning" class="spinner"></span>
            Run backup now
          </button>
          <button class="btn btn-secondary btn-sm" @click="loadSnapshots()">
            List snapshots
          </button>
        </div>
        <template x-if="snapshots.length > 0">
          <div style="margin-top:14px">
            <table class="table">
              <thead>
                <tr><th>ID</th><th>Time</th><th>Hostname</th></tr>
              </thead>
              <tbody>
                <template x-for="s in snapshots" :key="s.id || s.short_id">
                  <tr>
                    <td style="font-family:var(--mono);font-size:12px"
                      x-text="(s.short_id || s.id || '').slice(0,8)">
                    </td>
                    <td x-text="s.time ? s.time.slice(0,19).replace('T',' ') : '—'"></td>
                    <td x-text="s.hostname || '—'"></td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
        </template>
      </div>
    </div>

  </main>

  <!-- ══════════════════════════════════════════════════════════════════════
       APP DETAIL SLIDE PANEL
  ══════════════════════════════════════════════════════════════════════════ -->
  <template x-if="panelOpen">
    <div>
      <div class="panel-overlay" @click="closePanel()"></div>
      <div class="panel">

        <!-- Panel header -->
        <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:20px">
          <div>
            <h2 style="font-size:18px;font-weight:700;margin-bottom:6px" x-text="panelApp.name"></h2>
            <span :class="badgeClass(panelApp.status)" x-text="panelApp.status"></span>
          </div>
          <button class="btn btn-secondary btn-sm" @click="closePanel()">✕ Close</button>
        </div>

        <div x-show="!panelDetail" class="empty"><span class="spinner"></span></div>

        <template x-if="panelDetail">
          <div>

            <!-- Actions -->
            <div style="display:flex;gap:8px;margin-bottom:20px;flex-wrap:wrap">
              <button class="btn btn-primary btn-sm"
                @click="deploySingle(panelApp, $event)">
                ⬆ Deploy
              </button>
              <button class="btn btn-secondary btn-sm"
                x-show="panelDetail.compose_hash"
                @click="rollbackApp()">
                ↩ Rollback
              </button>
            </div>

            <!-- Variables -->
            <template x-if="Object.keys(panelVars).length > 0">
              <div style="margin-bottom:20px">
                <div class="card-title">Variables</div>
                <template x-for="[k, v] in Object.entries(panelVars)" :key="k">
                  <div class="form-row">
                    <label class="form-label" x-text="k"></label>
                    <input type="text" class="form-input"
                      :value="panelVars[k]"
                      @input="panelVars[k] = $event.target.value">
                  </div>
                </template>
                <button class="btn btn-primary btn-sm"
                  :disabled="panelVarsSaving"
                  @click="saveVars()">
                  <span x-show="panelVarsSaving" class="spinner"></span>
                  Save vars
                </button>
              </div>
            </template>

            <!-- Logs -->
            <div style="margin-bottom:20px">
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
                <strong style="font-size:14px">Logs</strong>
                <button class="btn btn-secondary btn-sm"
                  x-show="!panelLogsRunning"
                  @click="startLogs()">
                  ▶ Stream
                </button>
                <button class="btn btn-danger btn-sm"
                  x-show="panelLogsRunning"
                  @click="stopLogs()">
                  ■ Stop
                </button>
              </div>
              <template x-if="panelLogsRunning || panelLogs.length > 0">
                <div class="deploy-console" style="height:180px" id="log-scroll">
                  <template x-for="(line, i) in panelLogs" :key="i">
                    <div x-text="line"></div>
                  </template>
                </div>
              </template>
            </div>

            <!-- Deploy history -->
            <div>
              <strong style="font-size:14px;display:block;margin-bottom:10px">Deploy history</strong>
              <div x-show="panelHistory.length === 0"
                style="color:var(--muted);font-size:13px">No history yet.</div>
              <template x-for="ev in panelHistory" :key="ev.id">
                <div style="border:1px solid var(--border);border-radius:8px;padding:10px;
                  margin-bottom:8px">
                  <div style="display:flex;align-items:center;justify-content:space-between;
                    margin-bottom:4px">
                    <span :style="`color:${ev.success ? 'var(--accent2)' : 'var(--danger)'}`"
                      x-text="(ev.success ? '✓ ' : '✗ ') + ev.event_type">
                    </span>
                    <span style="font-size:11px;color:var(--muted)"
                      x-text="ev.started_at ? ev.started_at.slice(0,19).replace('T',' ') : ''">
                    </span>
                  </div>
                  <span x-show="ev.duration_ms"
                    style="font-size:11px;color:var(--muted)"
                    x-text="ev.duration_ms + 'ms'">
                  </span>
                  <template x-if="!ev.success && ev.stderr">
                    <pre style="font-size:11px;color:var(--danger);white-space:pre-wrap;
                      margin-top:6px;max-height:100px;overflow-y:auto"
                      x-text="ev.stderr.slice(0,400)">
                    </pre>
                  </template>
                </div>
              </template>
            </div>

          </div>
        </template>
      </div>
    </div>
  </template>

  <style>[x-cloak] { display: none !important; }</style>
</body>
</html>
```

- [ ] **Step 4.2: Run the full test suite**

```bash
source .venv/bin/activate && pytest tests/test_api_app.py -v
```
Expected: all tests pass.

- [ ] **Step 4.3: Commit**

```bash
git add stackr/web/static/index.html
git commit -m "feat(web): complete Alpine.js SPA — dashboard, catalog, settings, mounts, system"
```

---

## Task 5: Update service.py to point at `stackr api`

The persistent service should run the new API server (port 7274) rather than the old HTMX web UI (port 8000).

**Files:**
- Modify: `stackr/service.py`
- Modify: `stackr/cli.py` (service install default port)

- [ ] **Step 5.1: Write a failing test**

Add to `tests/test_api_app.py` (or create `tests/test_service.py` if it doesn't exist):

```python
def test_service_systemd_unit_uses_api_command() -> None:
    from pathlib import Path
    from stackr.service import _systemd_unit
    unit = _systemd_unit(Path("/home/user/stackr.yml"), "127.0.0.1", 7274)
    assert "stackr api" in unit
    assert "7274" in unit
    assert "stackr web" not in unit


def test_service_launchd_plist_uses_api_command() -> None:
    from pathlib import Path
    from stackr.service import _launchd_plist
    plist = _launchd_plist(Path("/home/user/stackr.yml"), "127.0.0.1", 7274)
    assert "stackr" in plist
    assert "api" in plist
    assert "web" not in plist
```

- [ ] **Step 5.2: Run the failing tests**

```bash
source .venv/bin/activate && pytest tests/ -k "test_service" -v
```
Expected: FAIL — current unit uses `stackr web`.

- [ ] **Step 5.3: Update `stackr/service.py`**

In `_systemd_unit`, change `stackr web` → `stackr api`:

```python
def _systemd_unit(config_path: Path, host: str, port: int) -> str:
    executable = sys.executable
    return f"""\
[Unit]
Description=Stackr API & Web UI
After=network.target

[Service]
Type=simple
ExecStart={executable} -m stackr api --config {config_path.resolve()} --host {host} --port {port}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""
```

In `_launchd_plist`, change `web` → `api` in the ProgramArguments array:

```python
    <array>
        <string>{executable}</string>
        <string>-m</string>
        <string>stackr</string>
        <string>api</string>
        <string>--config</string>
        <string>{config_abs}</string>
        <string>--host</string>
        <string>{host}</string>
        <string>--port</string>
        <string>{port}</string>
    </array>
```

- [ ] **Step 5.4: Update the default port in `stackr/cli.py`**

Find the `service install` command in `cli.py` and update the default port from `8000` to `7274`:

```python
@service_app.command("install")
def service_install(
    config_path: Path = _DEFAULT_CONFIG,
    host: Annotated[str, typer.Option()] = "127.0.0.1",
    port: Annotated[int, typer.Option()] = 7274,
) -> None:
```

- [ ] **Step 5.5: Run tests**

```bash
source .venv/bin/activate && pytest tests/ -k "test_service" -v
```
Expected: pass.

- [ ] **Step 5.6: Run full suite**

```bash
source .venv/bin/activate && ruff check stackr/ tests/ && mypy stackr/ && pytest tests/ -v
```
Expected: all pass, no ruff/mypy errors.

- [ ] **Step 5.7: Commit**

```bash
git add stackr/service.py stackr/cli.py
git commit -m "feat(service): run stackr api at port 7274 instead of stackr web"
```

---

## Task 6: Open PR

- [ ] **Step 6.1: Push branch and open PR**

```bash
git push -u origin feat/phase3-web-ui
gh pr create \
  --title "feat: Phase 3 — Alpine.js web UI served by API at port 7274" \
  --body "$(cat <<'EOF'
## Summary
- Adds static Alpine.js SPA to `stackr/web/static/` (index.html, style.css, app.js)
- FastAPI API now mounts `/static` and serves SPA at `GET /`
- Full management console: Dashboard, Catalog, Settings, Mounts, System pages
- App detail slide panel with vars editor, deploy history, live log stream, rollback
- Service updated to run `stackr api` at port 7274 (was `stackr web` at 8000)

## Test plan
- [ ] `pytest tests/test_api_app.py` — new static serving tests pass
- [ ] `pytest tests/ -v` — full suite passes
- [ ] `ruff check stackr/ tests/ && mypy stackr/` — clean
- [ ] Manual: run `stackr api`, open http://localhost:7274, verify all pages load

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Spec coverage check

| Spec requirement | Covered by |
|-----------------|------------|
| Static files served by FastAPI | Task 1 — StaticFiles mount |
| Alpine.js, all data via `/api/v1/` | Task 3 — `apiFetch` helper |
| Dashboard: app grid, status, deploy | Task 3+4 — `apps`, `deployAll`, `deploySingle` |
| App detail: vars, history, logs, rollback | Task 3+4 — panel methods |
| Catalog: browse/search, enable | Task 3+4 — `catalogByCategory`, `enableFromCatalog` |
| Settings: all config sections | Task 3+4 — `saveConfigSection` |
| Mounts: CRUD | Task 3+4 — `addMount`, `deleteMount` |
| System: health, validate, backup | Task 3+4 — `loadSystem`, `runValidate`, `runBackup` |
| Real-time: SSE logs, 2s deploy poll | Task 3 — `startLogs`, `startPolling` |
| Service runs API at 7274 | Task 5 |
