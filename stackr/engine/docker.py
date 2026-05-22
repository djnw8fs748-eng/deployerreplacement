"""Docker SDK + subprocess hybrid.

SDK (docker package)  — observation: container status, image digests, network/volume inspection.
subprocess            — orchestration: compose up/down/stop/pull, log streaming.
"""
from __future__ import annotations

import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

try:
    import docker as _docker_sdk

    HAS_DOCKER_SDK = True
except ImportError:
    HAS_DOCKER_SDK = False


# ---------------------------------------------------------------------------
# Shared result type
# ---------------------------------------------------------------------------


@dataclass
class OperationResult:
    success: bool
    app_name: str
    event_type: str
    stdout: str
    stderr: str
    exit_code: int | None
    duration_ms: int
    command: str | None
    error: str | None = None


# ---------------------------------------------------------------------------
# Docker SDK — observation layer
# ---------------------------------------------------------------------------


@dataclass
class ContainerStatus:
    app_name: str
    status: str  # 'running' | 'stopped' | 'degraded' | 'unknown'
    services: dict[str, str] = field(default_factory=dict)


def get_container_status(app_name: str) -> ContainerStatus:
    """Return live container status from Docker daemon."""
    if not HAS_DOCKER_SDK:
        return ContainerStatus(app_name=app_name, status="unknown")
    try:
        client = _docker_sdk.from_env()
        containers = client.containers.list(
            all=True,
            filters={"label": f"com.docker.compose.project={app_name}"},
        )
        if not containers:
            return ContainerStatus(app_name=app_name, status="unknown")
        services = {c.name: c.status for c in containers}
        running = sum(1 for s in services.values() if s == "running")
        if running == len(services):
            status = "running"
        elif running == 0:
            status = "stopped"
        else:
            status = "degraded"
        return ContainerStatus(app_name=app_name, status=status, services=services)
    except Exception:
        return ContainerStatus(app_name=app_name, status="unknown")


def get_image_digests(app_name: str, services: list[str]) -> dict[str, str]:
    """Return RepoDigests for each service from local Docker image metadata."""
    if not HAS_DOCKER_SDK:
        return {}
    digests: dict[str, str] = {}
    try:
        client = _docker_sdk.from_env()
        for service in services:
            containers = client.containers.list(
                all=True,
                filters={
                    "label": [
                        f"com.docker.compose.project={app_name}",
                        f"com.docker.compose.service={service}",
                    ]
                },
            )
            if not containers:
                continue
            image = client.images.get(containers[0].image.id)
            repo_digests: list[str] = image.attrs.get("RepoDigests", [])
            if repo_digests:
                digests[service] = repo_digests[0]
    except Exception:
        pass
    return digests


def inspect_network(name: str) -> dict | None:  # type: ignore[type-arg]
    """Return Docker network attributes, or None if not found."""
    if not HAS_DOCKER_SDK:
        return None
    try:
        return _docker_sdk.from_env().networks.get(name).attrs  # type: ignore[no-any-return]
    except Exception:
        return None


def inspect_volume(name: str) -> dict | None:  # type: ignore[type-arg]
    """Return Docker volume attributes, or None if not found."""
    if not HAS_DOCKER_SDK:
        return None
    try:
        return _docker_sdk.from_env().volumes.get(name).attrs  # type: ignore[no-any-return]
    except Exception:
        return None


def docker_available() -> bool:
    """Return True if the Docker daemon is reachable."""
    if not HAS_DOCKER_SDK:
        return False
    try:
        _docker_sdk.from_env().ping()
        return True
    except Exception:
        return False


def network_exists(name: str) -> bool:
    """Return True if a Docker network with this name exists."""
    return inspect_network(name) is not None


def ensure_networks(*, socket_proxy: bool = False) -> None:
    """Create required Docker networks if they do not exist."""
    _ensure_network("proxy")
    if socket_proxy:
        _ensure_network("socket_proxy")


def _ensure_network(name: str) -> None:
    if network_exists(name):
        return
    subprocess.run(
        ["docker", "network", "create", name],
        capture_output=True,
        check=False,
    )


# ---------------------------------------------------------------------------
# Subprocess — orchestration layer
# ---------------------------------------------------------------------------


def compose_up(app_name: str, compose_path: Path) -> OperationResult:
    """Run docker compose up -d --remove-orphans."""
    cmd = ["docker", "compose", "-f", str(compose_path), "up", "-d", "--remove-orphans"]
    return _run(app_name, "deploy", cmd)


def compose_pull(app_name: str, compose_path: Path) -> OperationResult:
    """Run docker compose pull."""
    cmd = ["docker", "compose", "-f", str(compose_path), "pull"]
    return _run(app_name, "pull", cmd)


def compose_down(app_name: str, compose_path: Path) -> OperationResult:
    """Run docker compose down (no -v; volumes are never destroyed automatically)."""
    cmd = ["docker", "compose", "-f", str(compose_path), "down"]
    return _run(app_name, "remove", cmd)


def compose_stop(app_name: str, compose_path: Path) -> OperationResult:
    """Run docker compose stop."""
    cmd = ["docker", "compose", "-f", str(compose_path), "stop"]
    return _run(app_name, "stop", cmd)


def compose_logs(compose_path: Path, service: str | None = None) -> Iterator[str]:
    """Stream log lines from docker compose logs -f."""
    cmd = ["docker", "compose", "-f", str(compose_path), "logs", "-f", "--no-color"]
    if service:
        cmd.append(service)
    with subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    ) as proc:
        assert proc.stdout is not None
        for line in proc.stdout:
            yield line.rstrip()


def _run(app_name: str, event_type: str, cmd: list[str]) -> OperationResult:
    command_str = " ".join(cmd)
    start = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        duration_ms = int((time.monotonic() - start) * 1000)
        success = proc.returncode == 0
        error: str | None = None
        if not success:
            last_line = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else ""
            error = last_line or f"exit code {proc.returncode}"
        return OperationResult(
            success=success,
            app_name=app_name,
            event_type=event_type,
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
            duration_ms=duration_ms,
            command=command_str,
            error=error,
        )
    except FileNotFoundError:
        duration_ms = int((time.monotonic() - start) * 1000)
        return OperationResult(
            success=False,
            app_name=app_name,
            event_type=event_type,
            stdout="",
            stderr="docker not found on PATH",
            exit_code=None,
            duration_ms=duration_ms,
            command=command_str,
            error="docker compose not found on PATH",
        )
