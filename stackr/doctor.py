"""Compatibility shim."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from stackr.engine.docker import docker_available, network_exists  # noqa: F401


def run_doctor(config: Any, env: Any = None, *, config_dir: Path | None = None) -> bool:
    return docker_available()
