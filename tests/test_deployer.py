"""Tests for deployer orchestration logic."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from stackr.deployer import _ensure_data_dirs, _run_compose, deploy, remove_app, rollback
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


def test_deploy_force_redeploys_unchanged_app(tmp_path: Path) -> None:
    """force=True must redeploy even when state.is_changed returns False."""
    from stackr.catalog import Catalog
    from stackr.config import StackrConfig
    from stackr.validator import ValidationResult

    config = StackrConfig.model_validate(
        {
            "global": {"data_dir": str(tmp_path)},
            "network": {"domain": "test.com", "local_domain": "home.test.com"},
            "security": {"socket_proxy": False},
            "apps": [{"name": "uptime-kuma", "enabled": True}],
        }
    )
    catalog = Catalog()
    validation = ValidationResult()

    state = MagicMock(spec=State)
    state.is_changed.return_value = False  # unchanged — would normally be skipped

    with (
        patch("stackr.deployer.COMPOSE_DIR", tmp_path),
        patch("stackr.deployer.ensure_networks"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0)
        deploy(config, catalog, validation, state, pull=False, force=True)

    all_cmds = [c[0][0] for c in mock_run.call_args_list]
    assert any("up" in cmd for cmd in all_cmds), "force=True must deploy even unchanged apps"


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


# ---------------------------------------------------------------------------
# _ensure_data_dirs
# ---------------------------------------------------------------------------


def test_ensure_data_dirs_creates_bind_mount_paths(tmp_path: Path) -> None:
    data_dir = tmp_path / "appdata"
    compose = f"""
services:
  myapp:
    image: test
    volumes:
      - {data_dir}/myapp/config:/config
      - {data_dir}/myapp/data:/data
"""
    failed = _ensure_data_dirs(compose, str(data_dir))
    assert failed == []
    assert (data_dir / "myapp" / "config").is_dir()
    assert (data_dir / "myapp" / "data").is_dir()


def test_ensure_data_dirs_ignores_paths_outside_data_dir(tmp_path: Path) -> None:
    data_dir = tmp_path / "appdata"
    outside = tmp_path / "outside"
    compose = f"""
services:
  myapp:
    image: test
    volumes:
      - {outside}/thing:/thing
      - {data_dir}/myapp/config:/config
"""
    failed = _ensure_data_dirs(compose, str(data_dir))
    assert failed == []
    assert not outside.exists()
    assert (data_dir / "myapp" / "config").is_dir()


def test_ensure_data_dirs_ignores_named_volumes(tmp_path: Path) -> None:
    data_dir = tmp_path / "appdata"
    compose = """
services:
  myapp:
    image: test
    volumes:
      - myapp_data:/data
"""
    failed = _ensure_data_dirs(compose, str(data_dir))
    assert failed == []


def test_ensure_data_dirs_tolerates_invalid_yaml(tmp_path: Path) -> None:
    data_dir = tmp_path / "appdata"
    failed = _ensure_data_dirs("not: valid: yaml: [{", str(data_dir))
    assert failed == []


def test_ensure_data_dirs_uses_sudo_on_permission_error(tmp_path: Path) -> None:
    """When mkdir fails with permission denied, sudo mkdir should be attempted."""
    from unittest.mock import call, patch

    data_dir = tmp_path / "appdata"
    data_dir.mkdir()
    target = data_dir / "myapp" / "config"
    compose = f"""
services:
  myapp:
    image: test
    volumes:
      - {target}:/config
"""
    # Simulate the normal mkdir succeeding for data_dir but failing for the subdir,
    # then sudo succeeding.
    original_mkdir = Path.mkdir

    def mock_mkdir(self: Path, *args: object, **kwargs: object) -> None:
        if self == target:
            raise PermissionError("Permission denied")
        original_mkdir(self, *args, **kwargs)  # type: ignore[arg-type]

    with (
        patch.object(Path, "mkdir", mock_mkdir),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0)
        failed = _ensure_data_dirs(compose, str(data_dir))

    # sudo mkdir -p should have been called for the failing path
    sudo_calls = [c for c in mock_run.call_args_list if "sudo" in (c[0][0] if c[0] else [])]
    assert sudo_calls, "sudo mkdir should be attempted on permission error"
    assert failed == [], "should not be in failed list when sudo succeeds"


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
