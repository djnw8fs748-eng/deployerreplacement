"""Tests for engine/docker.py — Docker SDK + subprocess hybrid."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from stackr.engine.docker import (
    OperationResult,
    compose_down,
    compose_stop,
    compose_up,
    docker_available,
    get_image_digests,
    inspect_network,
    inspect_volume,
)


def test_operation_result_has_required_fields() -> None:
    result = OperationResult(
        success=True,
        app_name="jellyfin",
        event_type="deploy",
        stdout="done",
        stderr="",
        exit_code=0,
        duration_ms=100,
        command="docker compose up -d",
    )
    assert result.success is True
    assert result.app_name == "jellyfin"
    assert result.error is None


def test_compose_up_success(tmp_path: Path) -> None:
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services:\n  test: {}\n")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="done\n", stderr="")
        result = compose_up("testapp", compose_file)
    assert result.success is True
    assert result.app_name == "testapp"
    assert result.event_type == "deploy"
    assert result.exit_code == 0
    assert "docker" in result.command


def test_compose_up_failure(tmp_path: Path) -> None:
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services:\n  test: {}\n")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="image not found"
        )
        result = compose_up("testapp", compose_file)
    assert result.success is False
    assert result.exit_code == 1
    assert result.error is not None


def test_compose_up_docker_not_found(tmp_path: Path) -> None:
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("")
    with patch("subprocess.run", side_effect=FileNotFoundError):
        result = compose_up("testapp", compose_file)
    assert result.success is False
    assert result.exit_code is None
    assert "not found" in (result.error or "")


def test_compose_down_success(tmp_path: Path) -> None:
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = compose_down("testapp", compose_file)
    assert result.success is True
    assert result.event_type == "remove"


def test_compose_stop_success(tmp_path: Path) -> None:
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = compose_stop("testapp", compose_file)
    assert result.success is True
    assert result.event_type == "stop"


def test_docker_available_true() -> None:
    with patch("stackr.engine.docker.HAS_DOCKER_SDK", True):
        mock_client = MagicMock()
        with patch("docker.from_env", return_value=mock_client):
            assert docker_available() is True


def test_docker_available_false_no_sdk() -> None:
    with patch("stackr.engine.docker.HAS_DOCKER_SDK", False):
        assert docker_available() is False


def test_inspect_network_returns_none_without_sdk() -> None:
    with patch("stackr.engine.docker.HAS_DOCKER_SDK", False):
        assert inspect_network("proxy") is None


def test_inspect_volume_returns_none_without_sdk() -> None:
    with patch("stackr.engine.docker.HAS_DOCKER_SDK", False):
        assert inspect_volume("jellyfin_config") is None


def test_get_image_digests_returns_empty_without_sdk() -> None:
    with patch("stackr.engine.docker.HAS_DOCKER_SDK", False):
        assert get_image_digests("jellyfin", ["jellyfin"]) == {}
