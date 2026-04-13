"""FastAPI route handlers for the Stackr web UI.

Routes
------
GET  /                        Full dashboard (HTML)
GET  /api/apps                JSON list of apps with enabled + deployed status
GET  /api/catalog             JSON list of all catalog apps
POST /api/toggle/{name}       Toggle app enabled state; returns HTMX partial
POST /api/deploy              Trigger full deploy; returns JSON result
POST /api/deploy/{name}       Deploy a single app; returns JSON result
GET  /api/logs/{name}         Server-Sent Events stream of live container logs
GET  /api/settings            JSON of current global/network/traefik/security/backup/alerts settings
POST /api/settings            Update all settings sections
GET  /api/mounts              JSON list of configured mounts
POST /api/mounts              Add a new mount; returns updated mounts table partial
DELETE /api/mounts/{name}     Remove a mount; returns updated mounts table partial
GET  /api/app/{name}/vars-form  HTML form for app-specific var overrides
POST /api/app/{name}/vars     Save app var overrides; returns HTMX response
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

import fastapi
import yaml
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from stackr.catalog import Catalog
from stackr.config import load_config
from stackr.state import State

_TEMPLATES_DIR = Path(__file__).parent / "templates"

# Module-level lock so concurrent web UI requests serialise config file writes.
_config_lock = threading.Lock()


def _render(template_name: str, **ctx: Any) -> str:
    """Render a Jinja2 template from the web templates directory."""
    from jinja2 import Environment, FileSystemLoader, StrictUndefined

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=True,
        undefined=StrictUndefined,
    )
    return env.get_template(template_name).render(**ctx)


def make_router(config_path: Path) -> fastapi.APIRouter:
    """Build and return the API router bound to the given config file."""
    router = fastapi.APIRouter()

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    @router.get("/", response_class=HTMLResponse)
    def dashboard() -> str:
        config = load_config(config_path)
        catalog = Catalog()
        state = State()

        # Index config apps by name so we can look up enabled state for any
        # catalog app, including ones not yet present in the config file.
        cfg_by_name = {a.name: a for a in config.apps}

        app_rows = []
        for cat_app in sorted(catalog.all(), key=lambda a: (a.category, a.name)):
            app_cfg = cfg_by_name.get(cat_app.name)
            app_state = state.get_app(cat_app.name)
            app_rows.append(
                {
                    "name": cat_app.name,
                    "display_name": cat_app.display_name,
                    "description": cat_app.description,
                    "category": cat_app.category,
                    "enabled": app_cfg.enabled if app_cfg else False,
                    "deployed": app_state is not None,
                    "deployed_at": (
                        str(app_state.deployed_at)[:19]
                        if app_state and app_state.deployed_at
                        else None
                    ),
                    "has_vars": bool(cat_app.vars),
                }
            )
        # Append any config apps that are not in the catalog (local/custom apps)
        catalog_names = {a.name for a in catalog.all()}
        for app_cfg in config.apps:
            if app_cfg.name not in catalog_names:
                app_state = state.get_app(app_cfg.name)
                app_rows.append(
                    {
                        "name": app_cfg.name,
                        "display_name": app_cfg.name,
                        "description": "",
                        "category": "custom",
                        "enabled": app_cfg.enabled,
                        "deployed": app_state is not None,
                        "deployed_at": (
                            str(app_state.deployed_at)[:19]
                            if app_state and app_state.deployed_at
                            else None
                        ),
                        "has_vars": False,
                    }
                )
        with open(config_path) as _f:
            _raw = yaml.safe_load(_f) or {}
        settings = _build_settings_dict(_raw)
        mounts = _build_mounts_list(_raw)
        return _render(
            "index.html",
            apps=app_rows,
            config_path=str(config_path),
            settings=settings,
            mounts=mounts,
        )

    # ------------------------------------------------------------------
    # JSON API
    # ------------------------------------------------------------------

    @router.get("/api/apps")
    def list_apps() -> JSONResponse:
        config = load_config(config_path)
        catalog = Catalog()
        state = State()

        cfg_by_name = {a.name: a for a in config.apps}
        result = []
        for cat_app in sorted(catalog.all(), key=lambda a: (a.category, a.name)):
            app_cfg = cfg_by_name.get(cat_app.name)
            app_state = state.get_app(cat_app.name)
            result.append(
                {
                    "name": cat_app.name,
                    "display_name": cat_app.display_name,
                    "description": cat_app.description,
                    "category": cat_app.category,
                    "enabled": app_cfg.enabled if app_cfg else False,
                    "deployed": app_state is not None,
                }
            )
        return JSONResponse(result)

    @router.get("/api/catalog")
    def list_catalog() -> JSONResponse:
        catalog = Catalog()
        return JSONResponse(
            [
                {
                    "name": a.name,
                    "display_name": a.display_name,
                    "description": a.description,
                    "category": a.category,
                }
                for a in catalog.all()
            ]
        )

    # ------------------------------------------------------------------
    # Toggle
    # ------------------------------------------------------------------

    @router.post("/api/toggle/{app_name}", response_class=HTMLResponse)
    def toggle_app(app_name: str) -> str:
        # Validate app_name against known catalog + configured apps before
        # touching the config file to prevent arbitrary injection.
        config = load_config(config_path)
        catalog = Catalog()
        known_names = {a.name for a in catalog.all()} | {a.name for a in config.apps}
        if app_name not in known_names:
            raise fastapi.HTTPException(
                status_code=404, detail=f"Unknown app '{app_name}'"
            )

        _toggle_app_in_config(config_path, app_name)

        config = load_config(config_path)
        state = State()

        app_cfg = next((a for a in config.apps if a.name == app_name), None)
        if app_cfg is None:
            raise fastapi.HTTPException(status_code=404, detail=f"App '{app_name}' not found")

        cat_app = catalog.get(app_name)
        app_state = state.get_app(app_name)
        row = {
            "name": app_cfg.name,
            "display_name": cat_app.display_name if cat_app else app_cfg.name,
            "description": cat_app.description if cat_app else "",
            "category": cat_app.category if cat_app else "custom",
            "enabled": app_cfg.enabled,
            "deployed": app_state is not None,
            "deployed_at": (
                str(app_state.deployed_at)[:19]
                if app_state and app_state.deployed_at
                else None
            ),
            "has_vars": bool(cat_app.vars) if cat_app else False,
        }
        return _render("partials/app_card.html", app=row)

    # ------------------------------------------------------------------
    # Deploy
    # ------------------------------------------------------------------

    @router.post("/api/deploy")
    def deploy_all() -> JSONResponse:
        return _run_stackr_deploy(config_path)

    @router.post("/api/deploy/{app_name}")
    def deploy_one(app_name: str) -> JSONResponse:
        return _run_stackr_deploy(config_path, app_name=app_name)

    # ------------------------------------------------------------------
    # Logs (Server-Sent Events)
    # ------------------------------------------------------------------

    @router.get("/api/logs/{app_name}")
    def stream_logs(app_name: str) -> StreamingResponse:
        return StreamingResponse(
            _log_generator(app_name),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ------------------------------------------------------------------
    # Settings (all sections)
    # ------------------------------------------------------------------

    @router.get("/api/settings")
    def get_settings() -> JSONResponse:
        with open(config_path) as f:
            raw: dict[str, Any] = yaml.safe_load(f) or {}
        return JSONResponse(_build_settings_dict(raw))

    @router.post("/api/settings", response_class=HTMLResponse)
    def save_settings(
        # Global
        data_dir: str = fastapi.Form("/opt/appdata"),
        timezone: str = fastapi.Form("UTC"),
        puid: int = fastapi.Form(1000),
        pgid: int = fastapi.Form(1000),
        # Network
        domain: str = fastapi.Form(""),
        local_domain: str = fastapi.Form(""),
        network_mode: str = fastapi.Form("external"),
        # Traefik
        traefik_enabled: str = fastapi.Form("false"),
        acme_email: str = fastapi.Form(""),
        dns_provider: str = fastapi.Form(""),
        dns_provider_env: str = fastapi.Form(""),
        # Security
        socket_proxy: str = fastapi.Form("false"),
        crowdsec: str = fastapi.Form("false"),
        auth_provider: str = fastapi.Form("none"),
        # Backup
        backup_enabled: str = fastapi.Form("false"),
        backup_destination: str = fastapi.Form("/mnt/backup"),
        backup_schedule: str = fastapi.Form("0 2 * * *"),
        # Alerts
        alerts_enabled: str = fastapi.Form("false"),
        alerts_provider: str = fastapi.Form("ntfy"),
        alerts_url: str = fastapi.Form(""),
        alerts_token: str = fastapi.Form(""),
    ) -> str:
        # Parse dns_provider_env from KEY=VALUE lines
        dns_env: dict[str, str] = {}
        for line in dns_provider_env.splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                dns_env[k.strip()] = v.strip()

        _save_all_settings(
            config_path,
            data_dir=data_dir,
            timezone=timezone,
            puid=puid,
            pgid=pgid,
            domain=domain,
            local_domain=local_domain,
            network_mode=network_mode,
            traefik_enabled=traefik_enabled.lower() in ("true", "1", "on"),
            acme_email=acme_email,
            dns_provider=dns_provider,
            dns_provider_env=dns_env,
            socket_proxy=socket_proxy.lower() in ("true", "1", "on"),
            crowdsec=crowdsec.lower() in ("true", "1", "on"),
            auth_provider=auth_provider,
            backup_enabled=backup_enabled.lower() in ("true", "1", "on"),
            backup_destination=backup_destination,
            backup_schedule=backup_schedule,
            alerts_enabled=alerts_enabled.lower() in ("true", "1", "on"),
            alerts_provider=alerts_provider,
            alerts_url=alerts_url,
            alerts_token=alerts_token or None,
        )
        return '<p style="color:#4ade80;margin:0">✓ Settings saved</p>'

    # ------------------------------------------------------------------
    # Mounts CRUD
    # ------------------------------------------------------------------

    @router.get("/api/mounts")
    def get_mounts() -> JSONResponse:
        with open(config_path) as f:
            raw: dict[str, Any] = yaml.safe_load(f) or {}
        return JSONResponse(_build_mounts_list(raw))

    @router.post("/api/mounts", response_class=HTMLResponse)
    def add_mount(
        mount_name: str = fastapi.Form(...),
        mount_type: str = fastapi.Form("smb"),
        mount_remote: str = fastapi.Form(""),
        mount_mountpoint: str = fastapi.Form(""),
        mount_options: str = fastapi.Form(""),
        mount_username: str = fastapi.Form(""),
    ) -> str:
        new_mount: dict[str, Any] = {
            "name": mount_name,
            "type": mount_type,
            "remote": mount_remote,
            "mountpoint": mount_mountpoint,
        }
        if mount_options:
            new_mount["options"] = mount_options
        if mount_username:
            new_mount["username"] = mount_username

        with _config_lock:
            with open(config_path) as fh:
                raw: dict[str, Any] = yaml.safe_load(fh) or {}
            mounts: list[dict[str, Any]] = raw.get("mounts") or []
            # Replace if name already exists
            mounts = [m for m in mounts if m.get("name") != mount_name]
            mounts.append(new_mount)
            raw["mounts"] = mounts
            _atomic_write(config_path, raw)

        with open(config_path) as f:
            raw2: dict[str, Any] = yaml.safe_load(f) or {}
        return _render("partials/mounts_table.html", mounts=_build_mounts_list(raw2))

    @router.delete("/api/mounts/{mount_name}", response_class=HTMLResponse)
    def delete_mount(mount_name: str) -> str:
        with _config_lock:
            with open(config_path) as fh:
                raw: dict[str, Any] = yaml.safe_load(fh) or {}
            mounts: list[dict[str, Any]] = raw.get("mounts") or []
            mounts = [m for m in mounts if m.get("name") != mount_name]
            raw["mounts"] = mounts
            _atomic_write(config_path, raw)

        with open(config_path) as f:
            raw2: dict[str, Any] = yaml.safe_load(f) or {}
        return _render("partials/mounts_table.html", mounts=_build_mounts_list(raw2))

    # ------------------------------------------------------------------
    # App vars
    # ------------------------------------------------------------------

    @router.get("/api/app/{app_name}/vars-form", response_class=HTMLResponse)
    def get_vars_form(app_name: str) -> str:
        catalog = Catalog()
        cat_app = catalog.get(app_name)
        if cat_app is None or not cat_app.vars:
            return (
                '<p style="color:#94a3b8;font-size:0.85rem;">'
                "No configurable vars for this app.</p>"
            )

        config = load_config(config_path)
        app_cfg = next((a for a in config.apps if a.name == app_name), None)
        current_vars = app_cfg.vars if app_cfg else {}

        var_defs = {k: v.model_dump() for k, v in cat_app.vars.items()}
        return _render(
            "partials/vars_form.html",
            app_name=app_name,
            var_defs=var_defs,
            current_vars=current_vars,
        )

    @router.post("/api/app/{app_name}/vars", response_class=HTMLResponse)
    async def save_vars(app_name: str, request: fastapi.Request) -> str:
        form = await request.form()
        new_vars: dict[str, Any] = {}
        for key, val in form.items():
            if key.startswith("var_"):
                var_name = key[4:]
                new_vars[var_name] = val

        with _config_lock:
            with open(config_path) as fh:
                raw: dict[str, Any] = yaml.safe_load(fh) or {}
            apps: list[dict[str, Any]] = raw.get("apps") or []
            found = False
            for entry in apps:
                if entry.get("name") == app_name:
                    entry["vars"] = new_vars
                    found = True
                    break
            if not found:
                apps.append({"name": app_name, "enabled": True, "vars": new_vars})
                raw["apps"] = apps
            _atomic_write(config_path, raw)

        return '<p style="color:#4ade80;margin:0">✓ Vars saved</p>'

    return router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_settings_dict(raw: dict[str, Any]) -> dict[str, Any]:
    g = raw.get("global") or {}
    n = raw.get("network") or {}
    t = raw.get("traefik") or {}
    s = raw.get("security") or {}
    b = raw.get("backup") or {}
    a = raw.get("alerts") or {}
    # Render dns_provider_env as KEY=VALUE lines
    dns_env_dict = t.get("dns_provider_env") or {}
    dns_env_text = "\n".join(f"{k}={v}" for k, v in dns_env_dict.items())
    return {
        "data_dir": str(g.get("data_dir", "/opt/appdata")),
        "timezone": str(g.get("timezone", "UTC")),
        "puid": int(g.get("puid", 1000)),
        "pgid": int(g.get("pgid", 1000)),
        "domain": str(n.get("domain", "")),
        "local_domain": str(n.get("local_domain", "")),
        "network_mode": str(n.get("mode", "external")),
        "traefik_enabled": bool(t.get("enabled", False)),
        "acme_email": str(t.get("acme_email", "")),
        "dns_provider": str(t.get("dns_provider", "")),
        "dns_provider_env": dns_env_text,
        "socket_proxy": bool(s.get("socket_proxy", True)),
        "crowdsec": bool(s.get("crowdsec", False)),
        "auth_provider": str(s.get("auth_provider", "none")),
        "backup_enabled": bool(b.get("enabled", False)),
        "backup_destination": str(b.get("destination", "/mnt/backup")),
        "backup_schedule": str(b.get("schedule", "0 2 * * *")),
        "alerts_enabled": bool(a.get("enabled", False)),
        "alerts_provider": str(a.get("provider", "ntfy")),
        "alerts_url": str(a.get("url", "")),
        "alerts_token": str(a.get("token") or ""),
    }


def _build_mounts_list(raw: dict[str, Any]) -> list[dict[str, Any]]:
    mounts = raw.get("mounts") or []
    result = []
    for m in mounts:
        if isinstance(m, dict):
            result.append(
                {
                    "name": str(m.get("name", "")),
                    "type": str(m.get("type", "smb")),
                    "remote": str(m.get("remote", "")),
                    "mountpoint": str(m.get("mountpoint", "")),
                    "options": str(m.get("options", "")),
                    "username": str(m.get("username") or ""),
                }
            )
    return result


def _save_all_settings(
    config_path: Path,
    *,
    data_dir: str,
    timezone: str,
    puid: int,
    pgid: int,
    domain: str,
    local_domain: str,
    network_mode: str,
    traefik_enabled: bool,
    acme_email: str,
    dns_provider: str,
    dns_provider_env: dict[str, str],
    socket_proxy: bool,
    crowdsec: bool,
    auth_provider: str,
    backup_enabled: bool,
    backup_destination: str,
    backup_schedule: str,
    alerts_enabled: bool,
    alerts_provider: str,
    alerts_url: str,
    alerts_token: str | None,
) -> None:
    """Atomically write all settings sections to the config file."""
    with _config_lock:
        with open(config_path) as fh:
            raw: dict[str, Any] = yaml.safe_load(fh) or {}

        g = dict(raw.get("global") or {})
        g.update({"data_dir": data_dir, "timezone": timezone, "puid": puid, "pgid": pgid})
        raw["global"] = g

        n = dict(raw.get("network") or {})
        n.update({"domain": domain, "local_domain": local_domain, "mode": network_mode})
        raw["network"] = n

        t = dict(raw.get("traefik") or {})
        t.update({
            "enabled": traefik_enabled,
            "acme_email": acme_email,
            "dns_provider": dns_provider,
            "dns_provider_env": dns_provider_env,
        })
        raw["traefik"] = t

        s = dict(raw.get("security") or {})
        s.update({
            "socket_proxy": socket_proxy,
            "crowdsec": crowdsec,
            "auth_provider": auth_provider,
        })
        raw["security"] = s

        b = dict(raw.get("backup") or {})
        b.update({
            "enabled": backup_enabled,
            "destination": backup_destination,
            "schedule": backup_schedule,
        })
        raw["backup"] = b

        a = dict(raw.get("alerts") or {})
        a.update({
            "enabled": alerts_enabled,
            "provider": alerts_provider,
            "url": alerts_url,
            "token": alerts_token,
        })
        raw["alerts"] = a

        _atomic_write(config_path, raw)


def _atomic_write(config_path: Path, raw: dict[str, Any]) -> None:
    """Write raw dict to config_path atomically via a temp file + rename."""
    tmp_fd, tmp_path = tempfile.mkstemp(dir=config_path.parent, prefix=".stackr-tmp-")
    try:
        with os.fdopen(tmp_fd, "w") as fh:
            yaml.dump(raw, fh, default_flow_style=False, sort_keys=False)
        os.replace(tmp_path, config_path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def _toggle_app_in_config(config_path: Path, app_name: str) -> None:
    """Flip `enabled` for *app_name* in the raw YAML file."""
    with _config_lock:
        with open(config_path) as fh:
            raw: dict[str, Any] = yaml.safe_load(fh) or {}

        apps: list[dict[str, Any]] = raw.get("apps", [])
        found = False
        for entry in apps:
            if entry.get("name") == app_name:
                entry["enabled"] = not entry.get("enabled", True)
                found = True
                break

        if not found:
            apps.append({"name": app_name, "enabled": True})
            raw["apps"] = apps

        _atomic_write(config_path, raw)


def _run_stackr_deploy(config_path: Path, app_name: str | None = None) -> JSONResponse:
    """Run `stackr deploy` via the current Python interpreter."""
    cmd = [sys.executable, "-m", "stackr", "deploy", "--config", str(config_path)]
    if app_name:
        cmd.append(app_name)
    result = subprocess.run(cmd, capture_output=True, text=True)
    return JSONResponse(
        {
            "ok": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    )


def _log_generator(app_name: str):  # type: ignore[return]
    """Yield SSE-formatted lines from `docker compose logs`."""
    from stackr.deployer import COMPOSE_DIR

    compose_path = COMPOSE_DIR / app_name / "docker-compose.yml"
    if not compose_path.exists():
        yield f"data: No compose file found for '{app_name}'\n\n"
        return

    cmd = ["docker", "compose", "-f", str(compose_path), "logs", "--tail=50", "-f"]
    with subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    ) as proc:
        if proc.stdout is None:
            return
        for line in proc.stdout:
            yield f"data: {line.rstrip()}\n\n"
