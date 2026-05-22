"""Tests for API Pydantic models."""
from __future__ import annotations

import pytest

from stackr.api.jobs import finish_job, get_job, reset_for_tests, start_job
from stackr.api.models import (
    AppDetail,
    AppStatusEnum,
    AppSummary,
    CatalogAppOut,
    DeployEventOut,
    DeployStatusOut,
    GlobalUpdate,
    HealthCheck,
    HealthOut,
    JobStatus,
    MountCreate,
    ValidationErrorOut,
    ValidationResultOut,
)


def test_app_status_enum_values() -> None:
    assert set(AppStatusEnum) == {"running", "stopped", "degraded", "unknown", "drift"}


def test_app_summary_requires_name_and_status() -> None:
    s = AppSummary(name="jellyfin", enabled=True, status=AppStatusEnum.running)
    assert s.name == "jellyfin"
    assert s.deployed_at is None
    assert s.last_error is None


def test_app_detail_extends_summary() -> None:
    d = AppDetail(
        name="jellyfin",
        enabled=True,
        status=AppStatusEnum.stopped,
        compose_hash="abc123",
        vars={"port": "8096"},
    )
    assert d.compose_hash == "abc123"
    assert d.vars == {"port": "8096"}


def test_deploy_event_out_round_trip() -> None:
    e = DeployEventOut(
        id=1,
        app_name="radarr",
        event_type="deploy",
        success=True,
        stdout="done",
        stderr="",
        exit_code=0,
        duration_ms=1234,
        command="docker compose up -d",
        started_at="2026-01-01T00:00:00+00:00",
    )
    assert e.success is True
    assert e.duration_ms == 1234


def test_job_status_enum_values() -> None:
    assert set(JobStatus) == {"idle", "running", "done", "failed"}


def test_deploy_status_out_idle() -> None:
    s = DeployStatusOut(status=JobStatus.idle)
    assert s.job_id is None
    assert s.app_name is None
    assert s.results == []
    assert s.error is None


def test_validation_result_out() -> None:
    r = ValidationResultOut(
        ok=False,
        errors=[ValidationErrorOut(app="radarr", message="missing dep")],
        warnings=[],
    )
    assert not r.ok
    assert len(r.errors) == 1


def test_catalog_app_out() -> None:
    c = CatalogAppOut(
        name="jellyfin",
        display_name="Jellyfin",
        description="Media server",
        category="media",
        vars=[],
        ports=[8096],
        host_ports=[],
        requires=[],
        suggests=[],
    )
    assert c.category == "media"


def test_health_out() -> None:
    h = HealthOut(
        healthy=True,
        checks=[HealthCheck(name="docker", ok=True, message="reachable")],
    )
    assert h.healthy is True


def test_mount_create_defaults() -> None:
    m = MountCreate(name="nas", remote="//nas/share", mountpoint="/mnt/nas")
    assert m.type == "smb"
    assert m.options == ""


def test_global_update_all_optional() -> None:
    u = GlobalUpdate()
    assert u.data_dir is None
    assert u.timezone is None
    assert u.puid is None
    assert u.pgid is None


@pytest.fixture(autouse=True)
def clear_jobs() -> None:
    reset_for_tests()


def test_start_job_creates_running_job() -> None:
    job = start_job()
    assert job is not None
    assert job.status == JobStatus.running
    assert job.job_id != ""


def test_start_job_returns_none_when_already_running() -> None:
    job1 = start_job()
    job2 = start_job()
    assert job1 is not None
    assert job2 is None


def test_finish_job_marks_done() -> None:
    job = start_job()
    assert job is not None
    finish_job(job, results=[{"app": "test", "success": True}])
    assert job.status == JobStatus.done
    assert job.error is None
    assert job.results[0]["app"] == "test"


def test_finish_job_marks_failed_on_error() -> None:
    job = start_job()
    assert job is not None
    finish_job(job, results=[], error="boom")
    assert job.status == JobStatus.failed
    assert job.error == "boom"


def test_get_job_returns_none_initially() -> None:
    assert get_job() is None


def test_get_job_returns_current_job() -> None:
    job = start_job()
    assert get_job() is job


def test_finished_job_allows_new_start() -> None:
    job = start_job()
    assert job is not None
    finish_job(job, results=[])
    job2 = start_job()
    assert job2 is not None
    assert job2.job_id != job.job_id


def test_start_job_with_app_name() -> None:
    job = start_job(app_name="jellyfin")
    assert job is not None
    assert job.app_name == "jellyfin"


def test_reset_for_tests_clears_state() -> None:
    start_job()
    reset_for_tests()
    assert get_job() is None
    new_job = start_job()
    assert new_job is not None
