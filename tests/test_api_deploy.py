"""Tests for /api/v1/deploy routes and job store."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from stackr.api.jobs import finish_job, get_job, reset_for_tests, start_job
from stackr.api.models import JobStatus

pytest.importorskip("httpx")
from httpx import ASGITransport, AsyncClient

from stackr.api.app import create_api


@pytest.fixture(autouse=True)
def clear_job() -> None:
    reset_for_tests()


@pytest.fixture
def api(tmp_path: Path):
    cfg = tmp_path / "stackr.yml"
    cfg.write_text(
        "global:\n  data_dir: /opt/appdata\n"
        "network:\n  domain: test.local\n  local_domain: home.test.local\n"
    )
    return create_api(cfg)


def test_start_job_returns_job() -> None:
    job = start_job()
    assert job is not None
    assert job.status == JobStatus.running
    assert job.app_name is None


def test_start_job_blocks_concurrent() -> None:
    job1 = start_job()
    job2 = start_job()
    assert job1 is not None
    assert job2 is None


def test_finish_job_marks_done() -> None:
    job = start_job()
    assert job is not None
    finish_job(job, results=[{"app": "app", "success": True}])
    assert job.status == JobStatus.done
    assert job.error is None


def test_finish_job_marks_failed_on_error() -> None:
    job = start_job()
    assert job is not None
    finish_job(job, results=[], error="Something went wrong")
    assert job.status == JobStatus.failed
    assert job.error == "Something went wrong"


def test_get_job_returns_none_initially() -> None:
    assert get_job() is None


def test_start_then_finish_allows_new_job() -> None:
    job = start_job()
    assert job is not None
    finish_job(job, results=[])
    job2 = start_job()
    assert job2 is not None


@pytest.mark.asyncio
async def test_deploy_status_idle(api) -> None:
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        resp = await client.get("/api/v1/deploy/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "idle"


@pytest.mark.asyncio
async def test_deploy_all_starts_job(api) -> None:
    with patch("stackr.api.routes.deploy._run_deploy_job"):
        async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
            resp = await client.post("/api/v1/deploy/")
    assert resp.status_code == 202
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "running"


@pytest.mark.asyncio
async def test_deploy_all_returns_409_when_busy(api) -> None:
    start_job()
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        resp = await client.post("/api/v1/deploy/")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_deploy_status_after_job_starts(api) -> None:
    with patch("stackr.api.routes.deploy._run_deploy_job"):
        async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
            await client.post("/api/v1/deploy/")
            resp = await client.get("/api/v1/deploy/status")
    data = resp.json()
    assert data["status"] in ("running", "done", "failed")
