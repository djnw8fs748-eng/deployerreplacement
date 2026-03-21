"""FastAPI route handlers for the Stackr web UI.

Routes
------
GET  /                    Full dashboard (HTML)
GET  /api/apps            JSON list of apps with enabled + deployed status
GET  /api/catalog         JSON list of all catalog apps
POST /api/toggle/{name}   Toggle app enabled state; returns HTMX partial
POST /api/deploy          Trigger full deploy; returns JSON result
POST /api/deploy/{name}   Deploy a single app; returns JSON result
GET  /api/logs/{name}     Server-Sent Events stream of live container logs
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
                    }
                )
        return _render("index.html", apps=app_rows, config_path=str(config_path))

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

    return router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _toggle_app_in_config(config_path: Path, app_name: str) -> None:
    """Flip `enabled` for *app_name* in the raw YAML file.

    Uses a module-level threading lock and an atomic rename so that:
    - Concurrent web UI requests never interleave reads and writes.
    - A crash mid-write leaves the original file intact.
    """
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

        # Write to a sibling temp file then atomically replace the original so a
        # crash mid-write doesn't leave a truncated config file.
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=config_path.parent, prefix=".stackr-tmp-"
        )
        try:
            with os.fdopen(tmp_fd, "w") as fh:
                yaml.dump(raw, fh, default_flow_style=False, sort_keys=False)
            os.replace(tmp_path, config_path)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise


def _run_stackr_deploy(config_path: Path, app_name: str | None = None) -> JSONResponse:
    """Run `stackr deploy` via the current Python interpreter.

    Using ``sys.executable -m stackr`` instead of a bare ``stackr`` command
    ensures the correct virtualenv is used even when uvicorn is started outside
    an activated environment.
    """
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
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as proc:
        if proc.stdout is None:
            return
        for line in proc.stdout:
            yield f"data: {line.rstrip()}\n\n"
