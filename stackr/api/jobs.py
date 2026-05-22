"""Thread-safe deploy job store. Only one deploy job runs at a time."""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any

from stackr.api.models import JobStatus


@dataclass
class DeployJob:
    job_id: str
    status: JobStatus = JobStatus.running
    app_name: str | None = None
    results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


_lock = threading.Lock()
_current_job: DeployJob | None = None


def start_job(app_name: str | None = None) -> DeployJob | None:
    """Create and register a new running job. Returns None if already running."""
    global _current_job
    with _lock:
        if _current_job is not None and _current_job.status == JobStatus.running:
            return None
        _current_job = DeployJob(job_id=str(uuid.uuid4()), app_name=app_name)
        return _current_job


def finish_job(
    job: DeployJob,
    results: list[dict[str, Any]],
    error: str | None = None,
) -> None:
    with _lock:
        job.results = results
        job.error = error
        job.status = JobStatus.failed if error else JobStatus.done


def get_job() -> DeployJob | None:
    with _lock:
        return _current_job


def get_job_snapshot() -> dict | None:
    """Return a consistent snapshot of the current job state, or None if idle."""
    with _lock:
        if _current_job is None:
            return None
        return {
            "job_id": _current_job.job_id,
            "status": _current_job.status,
            "app_name": _current_job.app_name,
            "results": list(_current_job.results),
            "error": _current_job.error,
        }


def reset_for_tests() -> None:
    """Test helper — clears job state between tests."""
    global _current_job
    with _lock:
        _current_job = None
