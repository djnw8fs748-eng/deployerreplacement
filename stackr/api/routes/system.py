"""System routes: health, validate, secrets, backup, snapshots."""
from __future__ import annotations

from pathlib import Path

import fastapi

import stackr.engine.docker as _docker
from stackr.api.deps import Cat, Config, Env, get_config_path
from stackr.api.models import (
    HealthCheck,
    HealthOut,
    SecretNamesOut,
    ValidationErrorOut,
    ValidationResultOut,
)

router = fastapi.APIRouter(prefix="/system", tags=["system"])


@router.get("/health", response_model=HealthOut)
def health(config: Config) -> HealthOut:
    checks: list[HealthCheck] = []

    docker_ok = _docker.docker_available()
    checks.append(HealthCheck(
        name="docker",
        ok=docker_ok,
        message="reachable" if docker_ok else "Docker daemon not reachable",
    ))

    proxy_ok = _docker.network_exists("proxy")
    checks.append(HealthCheck(
        name="proxy_network",
        ok=proxy_ok,
        message=(
            "exists"
            if proxy_ok
            else "Docker network 'proxy' not found — run: docker network create proxy"
        ),
    ))

    if config.security.socket_proxy:
        sp_ok = _docker.network_exists("socket_proxy")
        checks.append(HealthCheck(
            name="socket_proxy_network",
            ok=sp_ok,
            message="exists" if sp_ok else "Docker network 'socket_proxy' not found",
        ))

    return HealthOut(healthy=all(c.ok for c in checks), checks=checks)


@router.post("/validate", response_model=ValidationResultOut)
def validate(config: Config, catalog: Cat, env: Env) -> ValidationResultOut:
    from stackr.engine.validator import validate as run_validate

    result = run_validate(
        config,
        catalog,
        env,
        data_dir=Path(str(config.global_.data_dir)),
    )
    return ValidationResultOut(
        ok=result.ok,
        errors=[ValidationErrorOut(app=e.app, message=e.message) for e in result.errors],
        warnings=[ValidationErrorOut(app=w.app, message=w.message) for w in result.warnings],
    )


@router.get("/secrets", response_model=SecretNamesOut)
def secret_names(env: Env) -> SecretNamesOut:
    return SecretNamesOut(names=sorted(env.keys()))


@router.post("/backup")
def trigger_backup(config: Config, env: Env) -> dict:
    from stackr.engine.backup import backup as run_backup
    config_path = get_config_path()
    run_backup(config, env, config_dir=config_path.parent)
    return {"status": "backup started"}


@router.get("/snapshots")
def list_snapshots(config: Config, env: Env) -> list:
    from stackr.engine.backup import list_snapshots as run_snapshots
    return run_snapshots(config, env)
