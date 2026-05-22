"""Apps routes: list, get, toggle, history, vars, logs."""
from __future__ import annotations

import os
import tempfile
from typing import Any

import fastapi
import yaml
from fastapi.responses import StreamingResponse

from stackr.api.deps import CONFIG_WRITE_LOCK, DB, Config, ConfigPath
from stackr.api.models import AppDetail, AppStatusEnum, AppSummary, DeployEventOut
from stackr.engine.docker import get_container_status
from stackr.engine.state import AppState

router = fastapi.APIRouter(prefix="/apps", tags=["apps"])


def _live_status(app_name: str) -> AppStatusEnum:
    try:
        cs = get_container_status(app_name)
        return AppStatusEnum(cs.status)
    except Exception:
        return AppStatusEnum.unknown


def _to_summary(app_name: str, app_state: AppState | None, enabled: bool) -> AppSummary:
    status = _live_status(app_name) if app_state else AppStatusEnum.unknown
    return AppSummary(
        name=app_name,
        enabled=enabled,
        status=status,
        deployed_at=app_state.deployed_at if app_state else None,
        last_error=app_state.last_error if app_state else None,
    )


@router.get("/", response_model=list[AppSummary])
def list_apps(db: DB, config: Config) -> list[AppSummary]:
    cfg_by_name = {a.name: a for a in config.apps}
    db_by_name = {a.name: a for a in db.list_apps()}
    all_names = sorted(set(cfg_by_name) | set(db_by_name))
    return [
        _to_summary(
            name,
            db_by_name.get(name),
            cfg_by_name[name].enabled if name in cfg_by_name else False,
        )
        for name in all_names
    ]


@router.get("/{name}", response_model=AppDetail)
def get_app(name: str, db: DB, config: Config) -> AppDetail:
    app_state = db.get_app(name)
    app_cfg = next((a for a in config.apps if a.name == name), None)
    enabled = app_cfg.enabled if app_cfg else False
    summary = _to_summary(name, app_state, enabled)
    return AppDetail(
        **summary.model_dump(),
        compose_hash=app_state.compose_hash if app_state else None,
        vars=app_cfg.vars if app_cfg else {},
    )


@router.post("/{name}/toggle", response_model=AppSummary)
def toggle_app(name: str, config_path: ConfigPath, db: DB) -> AppSummary:
    with CONFIG_WRITE_LOCK:
        raw: dict[str, Any] = yaml.safe_load(config_path.read_text()) or {}
        apps = raw.setdefault("apps", [])
        found = next((a for a in apps if a.get("name") == name), None)
        if found is None:
            apps.append({"name": name, "enabled": True})
            enabled = True
        else:
            found["enabled"] = not found.get("enabled", True)
            enabled = found["enabled"]
        fd, tmp = tempfile.mkstemp(dir=config_path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                yaml.safe_dump(raw, f, default_flow_style=False, sort_keys=False)
            os.replace(tmp, config_path)
        except Exception:
            os.unlink(tmp)
            raise
    return _to_summary(name, db.get_app(name), enabled)


@router.get("/{name}/history", response_model=list[DeployEventOut])
def get_history(name: str, db: DB, limit: int = 20) -> list[DeployEventOut]:
    return [
        DeployEventOut(
            id=e.id,
            app_name=e.app_name,
            event_type=e.event_type,
            success=e.success,
            stdout=e.stdout,
            stderr=e.stderr,
            exit_code=e.exit_code,
            duration_ms=e.duration_ms,
            command=e.command,
            started_at=e.started_at,
        )
        for e in db.get_app_history(name, limit=limit)
    ]


@router.get("/{name}/vars")
def get_vars(name: str, config: Config) -> dict[str, Any]:
    app_cfg = next((a for a in config.apps if a.name == name), None)
    return app_cfg.vars if app_cfg else {}


@router.put("/{name}/vars")
def update_vars(name: str, vars: dict[str, Any], config_path: ConfigPath) -> dict[str, Any]:
    with CONFIG_WRITE_LOCK:
        raw: dict[str, Any] = yaml.safe_load(config_path.read_text()) or {}
        apps = raw.setdefault("apps", [])
        found = next((a for a in apps if a.get("name") == name), None)
        if found is None:
            apps.append({"name": name, "enabled": True, "vars": vars})
        else:
            found.setdefault("vars", {}).update(vars)
        fd, tmp = tempfile.mkstemp(dir=config_path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                yaml.safe_dump(raw, f, default_flow_style=False, sort_keys=False)
            os.replace(tmp, config_path)
        except Exception:
            os.unlink(tmp)
            raise
    updated_raw: dict[str, Any] = yaml.safe_load(config_path.read_text()) or {}
    updated_app = next(
        (a for a in updated_raw.get("apps", []) if a.get("name") == name), {}
    )
    return updated_app.get("vars", {})


@router.get("/{name}/logs")
def stream_logs(name: str, service: str | None = None) -> StreamingResponse:
    from stackr.engine.deployer import COMPOSE_DIR

    compose_path = COMPOSE_DIR / name / "docker-compose.yml"
    if not compose_path.exists():
        raise fastapi.HTTPException(status_code=404, detail=f"No compose file for '{name}'")

    import subprocess

    def generate():  # type: ignore[return]
        cmd = ["docker", "compose", "-f", str(compose_path), "logs", "-f", "--no-color"]
        if service:
            cmd.append(service)
        with subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        ) as proc:
            try:
                assert proc.stdout is not None
                for line in proc.stdout:
                    yield f"data: {line.rstrip()}\n\n"
            finally:
                proc.kill()
                proc.wait()

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/{name}/deploy", status_code=202)
def deploy_single_app(
    name: str,
    background_tasks: fastapi.BackgroundTasks,
    config_path: ConfigPath,
):
    from stackr.api.jobs import start_job
    from stackr.api.models import DeployJobOut, JobStatus
    from stackr.api.routes.deploy import _run_deploy_job

    job = start_job(app_name=name)
    if job is None:
        raise fastapi.HTTPException(status_code=409, detail="A deploy job is already running")
    background_tasks.add_task(_run_deploy_job, job, config_path, name)
    return DeployJobOut(job_id=job.job_id, status=JobStatus.running, message=f"Deploying {name}")


@router.post("/{name}/rollback", response_model=AppSummary)
def rollback_app_endpoint(name: str, db: DB, config: Config) -> AppSummary:
    from stackr.engine.deployer import rollback_app

    result = rollback_app(name, db)
    if not result.success:
        raise fastapi.HTTPException(status_code=500, detail=result.error or "Rollback failed")
    app_cfg = next((a for a in config.apps if a.name == name), None)
    enabled = app_cfg.enabled if app_cfg else False
    return _to_summary(name, db.get_app(name), enabled)
