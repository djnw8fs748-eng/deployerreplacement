"""Tests for deployer orchestration logic."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from stackr.deployer import _run_compose, deploy, remove_app, rollback
from stackr.state import State

# ---------------------------------------------------------------------------
# _run_compose
# ---------------------------------------------------------------------------


def test_run_compose_capture_passes_capture_output(tmp_path: Path) -> None:
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services: {}")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        _run_compose(compose_file, ["ps"], capture=True)
        _, kwargs = mock_run.call_args
        assert kwargs.get("capture_output") is True
        assert kwargs.get("check") is True


def test_run_compose_no_capture_is_interactive(tmp_path: Path) -> None:
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services: {}")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        _run_compose(compose_file, ["logs"], capture=False)
        _, kwargs = mock_run.call_args
        assert not kwargs.get("capture_output", False)
        assert kwargs.get("check") is True


# ---------------------------------------------------------------------------
# remove_app — must NOT use -v (would destroy named volumes)
# ---------------------------------------------------------------------------


def test_remove_app_does_not_destroy_volumes(tmp_path: Path) -> None:
    compose_file = tmp_path / "myapp" / "docker-compose.yml"
    compose_file.parent.mkdir(parents=True)
    compose_file.write_text("services: {}")

    state = MagicMock(spec=State)

    with (
        patch("stackr.deployer.COMPOSE_DIR", tmp_path),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0)
        remove_app("myapp", state)

    called_cmd = mock_run.call_args[0][0]
    assert "-v" not in called_cmd, "remove_app must not pass -v (would destroy named volumes)"
    assert "down" in called_cmd


# ---------------------------------------------------------------------------
# deploy skip-unchanged logic
# ---------------------------------------------------------------------------


def test_deploy_skips_unchanged_app(tmp_path: Path) -> None:
    """An app whose compose content hasn't changed should not be restarted."""
    from stackr.catalog import Catalog
    from stackr.config import StackrConfig
    from stackr.validator import ValidationResult

    config = StackrConfig.model_validate(
        {
            "global": {"data_dir": str(tmp_path)},
            "network": {"mode": "external", "domain": "test.com", "local_domain": "home.test.com"},
            "traefik": {"enabled": False},
            "security": {"socket_proxy": False},
            "apps": [{"name": "uptime-kuma", "enabled": True}],
        }
    )
    catalog = Catalog()
    validation = ValidationResult()  # ok=True

    state = MagicMock(spec=State)
    state.is_changed.return_value = False  # nothing changed

    with (
        patch("stackr.deployer.COMPOSE_DIR", tmp_path),
        patch("stackr.deployer.ensure_networks"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0)
        deploy(config, catalog, validation, state, pull=False)

    # up -d should NOT have been called
    up_calls = [
        c for c in mock_run.call_args_list if "up" in (c[0][0] if c[0] else [])
    ]
    assert up_calls == [], "unchanged app should not trigger 'up -d'"


def test_deploy_restarts_changed_app(tmp_path: Path) -> None:
    """An app whose compose content has changed should be (re)deployed."""
    from stackr.catalog import Catalog
    from stackr.config import StackrConfig
    from stackr.validator import ValidationResult

    config = StackrConfig.model_validate(
        {
            "global": {"data_dir": str(tmp_path)},
            "network": {"mode": "external", "domain": "test.com", "local_domain": "home.test.com"},
            "traefik": {"enabled": False},
            "security": {"socket_proxy": False},
            "apps": [{"name": "uptime-kuma", "enabled": True}],
        }
    )
    catalog = Catalog()
    validation = ValidationResult()

    state = MagicMock(spec=State)
    state.is_changed.return_value = True  # content changed

    with (
        patch("stackr.deployer.COMPOSE_DIR", tmp_path),
        patch("stackr.deployer.ensure_networks"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0)
        deploy(config, catalog, validation, state, pull=False)

    all_cmds = [c[0][0] for c in mock_run.call_args_list]
    assert any("up" in cmd for cmd in all_cmds), "changed app should trigger 'up -d'"


# ---------------------------------------------------------------------------
# rollback
# ---------------------------------------------------------------------------


def test_rollback_no_state_exits(tmp_path: Path) -> None:
    from stackr.catalog import Catalog
    from stackr.config import StackrConfig

    config = StackrConfig.model_validate(
        {
            "global": {"data_dir": str(tmp_path)},
            "network": {"mode": "external", "domain": "test.com", "local_domain": "home.test.com"},
            "traefik": {"enabled": False},
            "security": {"socket_proxy": False},
            "apps": [],
        }
    )
    catalog = Catalog()
    state = MagicMock(spec=State)
    state.get_app.return_value = None

    with pytest.raises(SystemExit):
        rollback("nonexistent-app", config, catalog, state)


def test_rollback_applies_stored_compose(tmp_path: Path) -> None:
    from stackr.catalog import Catalog
    from stackr.config import StackrConfig
    from stackr.state import AppState

    config = StackrConfig.model_validate(
        {
            "global": {"data_dir": str(tmp_path)},
            "network": {"mode": "external", "domain": "test.com", "local_domain": "home.test.com"},
            "traefik": {"enabled": False},
            "security": {"socket_proxy": False},
            "apps": [],
        }
    )
    catalog = Catalog()
    stored = AppState(
        name="myapp",
        enabled=True,
        compose_hash="abc123",
        compose_content="services:\n  myapp:\n    image: test\n",
        deployed_at="2024-01-01T00:00:00+00:00",
    )
    state = MagicMock(spec=State)
    state.get_app.return_value = stored

    with (
        patch("stackr.deployer.COMPOSE_DIR", tmp_path),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0)
        rollback("myapp", config, catalog, state)

    all_cmds = [c[0][0] for c in mock_run.call_args_list]
    assert any("up" in cmd for cmd in all_cmds), "rollback should run 'up -d' with stored compose"
