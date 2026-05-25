"""Deploy routes: deploy-all async job, status polling."""
from __future__ import annotations

from pathlib import Path

import fastapi

from stackr.api.deps import ConfigPath
from stackr.api.jobs import DeployJob, finish_job, get_job_snapshot, start_job
from stackr.api.models import DeployJobOut, DeployStatusOut, JobStatus

router = fastapi.APIRouter(prefix="/deploy", tags=["deploy"])


def _run_deploy_job(job: DeployJob, config_path: Path, app_name: str | None) -> None:
    """Run in a background thread. Updates job when complete."""
    try:
        from stackr.engine.catalog import Catalog
        from stackr.engine.config import load_config
        from stackr.engine.deployer import deploy_all
        from stackr.engine.secrets import build_env
        from stackr.engine.state import StateDB
        from stackr.engine.validator import validate

        config = load_config(config_path)
        catalog = Catalog()
        env = build_env(config_path.parent)
        db = StateDB()

        validation = validate(
            config,
            catalog,
            env,
            data_dir=Path(str(config.global_.data_dir)),
        )
        if not validation.ok:
            msgs = "; ".join(f"{e.app}: {e.message}" for e in validation.errors)
            finish_job(job, results=[], error=f"Validation failed: {msgs}")
            return

        results = deploy_all(config, catalog, validation, db, app_name=app_name, pull=True)
        serialized = [
            {
                "app_name": r.app_name,
                "success": r.success,
                "error": r.error,
                "duration_ms": r.duration_ms,
            }
            for r in results
        ]
        finish_job(job, results=serialized)
        from stackr.api.routes.apps import _clear_status_cache  # local import to avoid circular
        _clear_status_cache()
    except Exception as exc:
        finish_job(job, results=[], error=str(exc))


@router.post("/", response_model=DeployJobOut, status_code=202)
def deploy_all_apps(
    background_tasks: fastapi.BackgroundTasks,
    config_path: ConfigPath,
) -> DeployJobOut:
    job = start_job(app_name=None)
    if job is None:
        raise fastapi.HTTPException(status_code=409, detail="A deploy job is already running")
    background_tasks.add_task(_run_deploy_job, job, config_path, None)
    return DeployJobOut(job_id=job.job_id, status=JobStatus.running, message="Deploy started")


@router.get("/status", response_model=DeployStatusOut)
def deploy_status() -> DeployStatusOut:
    snap = get_job_snapshot()
    if snap is None:
        return DeployStatusOut(status=JobStatus.idle)
    return DeployStatusOut(
        status=snap["status"],
        job_id=snap["job_id"],
        app_name=snap["app_name"],
        results=snap["results"],
        error=snap["error"],
    )
