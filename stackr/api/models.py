"""Pydantic request/response models for the Stackr REST API."""
from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class AppStatusEnum(StrEnum):
    running = "running"
    stopped = "stopped"
    degraded = "degraded"
    unknown = "unknown"
    drift = "drift"


class AppSummary(BaseModel):
    name: str
    enabled: bool
    status: AppStatusEnum = AppStatusEnum.unknown
    deployed_at: str | None = None
    last_error: str | None = None


class AppDetail(AppSummary):
    compose_hash: str | None = None
    vars: dict[str, Any] = {}


class DeployEventOut(BaseModel):
    id: int | None = None
    app_name: str
    event_type: str
    success: bool
    stdout: str
    stderr: str
    exit_code: int | None = None
    duration_ms: int
    command: str | None = None
    started_at: str


class JobStatus(StrEnum):
    idle = "idle"
    running = "running"
    done = "done"
    failed = "failed"


class DeployJobOut(BaseModel):
    job_id: str
    status: JobStatus
    message: str


class DeployStatusOut(BaseModel):
    status: JobStatus = JobStatus.idle
    job_id: str | None = None
    app_name: str | None = None
    results: list[dict[str, Any]] = []
    error: str | None = None


class ValidationErrorOut(BaseModel):
    app: str
    message: str


class ValidationResultOut(BaseModel):
    ok: bool
    errors: list[ValidationErrorOut]
    warnings: list[ValidationErrorOut]


class GlobalUpdate(BaseModel):
    data_dir: str | None = None
    timezone: str | None = None
    puid: int | None = None
    pgid: int | None = None


class NetworkUpdate(BaseModel):
    domain: str | None = None
    local_domain: str | None = None


class SecurityUpdate(BaseModel):
    socket_proxy: bool | None = None
    crowdsec: bool | None = None


class BackupUpdate(BaseModel):
    enabled: bool | None = None
    destination: str | None = None
    schedule: str | None = None


class AlertUpdate(BaseModel):
    enabled: bool | None = None
    provider: str | None = None
    url: str | None = None
    token: str | None = None


class MountOut(BaseModel):
    name: str
    type: str
    remote: str
    mountpoint: str
    options: str
    username: str | None = None


class MountCreate(BaseModel):
    name: str
    type: str = "smb"
    remote: str
    mountpoint: str
    options: str = ""
    username: str | None = None


class VarDefOut(BaseModel):
    name: str
    default: str | None = None
    description: str | None = None
    type: str = "string"


class CatalogAppOut(BaseModel):
    name: str
    display_name: str
    description: str
    category: str
    vars: list[VarDefOut]
    ports: list[int]
    host_ports: list[int]
    requires: list[str]
    suggests: list[str]


class HealthCheck(BaseModel):
    name: str
    ok: bool
    message: str


class HealthOut(BaseModel):
    healthy: bool
    checks: list[HealthCheck]


class SecretNamesOut(BaseModel):
    names: list[str]
