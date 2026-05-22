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
