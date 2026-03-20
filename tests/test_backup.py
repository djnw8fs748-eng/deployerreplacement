"""Tests for stackr.backup — restic-based backup/restore."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# _check_restic
# ---------------------------------------------------------------------------


def test_check_restic_raises_when_not_on_path() -> None:
    from stackr.backup import _check_restic

    with patch("shutil.which", return_value=None):
        try:
            _check_restic()
        except RuntimeError as exc:
            assert "restic" in str(exc).lower()
        else:
            raise AssertionError("Expected RuntimeError when restic is missing")


def test_check_restic_passes_when_found() -> None:
    from stackr.backup import _check_restic

    with patch("shutil.which", return_value="/usr/bin/restic"):
        _check_restic()  # must not raise


# ---------------------------------------------------------------------------
# _ensure_repo_initialized
# ---------------------------------------------------------------------------


def test_ensure_repo_initialized_skips_init_when_repo_exists() -> None:
    from stackr.backup import _ensure_repo_initialized

    env: dict[str, str] = {}
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        _ensure_repo_initialized("/mnt/backup", env)
        # Only snapshots check, no init
        assert mock_run.call_count == 1
        cmd = mock_run.call_args[0][0]
        assert "snapshots" in cmd


def test_ensure_repo_initialized_runs_init_when_repo_missing() -> None:
    from stackr.backup import _ensure_repo_initialized

    env: dict[str, str] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        mock = MagicMock()
        mock.returncode = 1 if "snapshots" in cmd else 0
        return mock

    with patch("subprocess.run", side_effect=fake_run) as mock_run:
        _ensure_repo_initialized("/mnt/backup", env)
        assert mock_run.call_count == 2
        first_cmd = mock_run.call_args_list[0][0][0]
        second_cmd = mock_run.call_args_list[1][0][0]
        assert "snapshots" in first_cmd
        assert "init" in second_cmd


# ---------------------------------------------------------------------------
# backup()
# ---------------------------------------------------------------------------


def test_backup_happy_path(tmp_path: Path) -> None:
    from stackr.backup import backup

    data_dir = tmp_path / "data"
    state_dir = tmp_path / "state"
    config_dir = tmp_path / "config"
    for d in (data_dir, state_dir, config_dir):
        d.mkdir()

    env: dict[str, str] = {"STACKR_RESTIC_PASSWORD": "secret"}

    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        calls.append(cmd)
        mock = MagicMock()
        mock.returncode = 0
        return mock

    with (
        patch("shutil.which", return_value="/usr/bin/restic"),
        patch("subprocess.run", side_effect=fake_run),
    ):
        backup(
            destination="/mnt/backup",
            data_dir=data_dir,
            state_dir=state_dir,
            config_dir=config_dir,
            env=env,
        )

    backup_call = next(c for c in calls if "backup" in c)
    assert str(data_dir) in backup_call
    assert str(state_dir) in backup_call
    assert str(config_dir) in backup_call


def test_backup_raises_on_restic_failure(tmp_path: Path) -> None:
    from stackr.backup import backup

    env: dict[str, str] = {"STACKR_RESTIC_PASSWORD": "secret"}

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        mock = MagicMock()
        mock.returncode = 1 if "backup" in cmd else 0
        mock.stderr = b"some error"
        return mock

    with (
        patch("shutil.which", return_value="/usr/bin/restic"),
        patch("subprocess.run", side_effect=fake_run),
    ):
        try:
            backup(
                destination="/mnt/backup",
                data_dir=tmp_path,
                state_dir=tmp_path,
                config_dir=tmp_path,
                env=env,
            )
        except RuntimeError as exc:
            assert "restic backup failed" in str(exc)
        else:
            raise AssertionError("Expected RuntimeError on restic failure")


# ---------------------------------------------------------------------------
# restore()
# ---------------------------------------------------------------------------


def test_restore_delegates_correct_args(tmp_path: Path) -> None:
    from stackr.backup import restore

    env: dict[str, str] = {"STACKR_RESTIC_PASSWORD": "secret"}

    with (
        patch("shutil.which", return_value="/usr/bin/restic"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0)
        restore(
            snapshot="abc12345",
            destination="/mnt/backup",
            target=tmp_path,
            config_dir=tmp_path,
            env=env,
        )

    cmd = mock_run.call_args[0][0]
    assert "restore" in cmd
    assert "abc12345" in cmd
    assert str(tmp_path) in cmd


def test_restore_raises_on_failure(tmp_path: Path) -> None:
    from stackr.backup import restore

    env: dict[str, str] = {"STACKR_RESTIC_PASSWORD": "secret"}

    with (
        patch("shutil.which", return_value="/usr/bin/restic"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=1, stderr=b"err")
        try:
            restore("latest", "/mnt/backup", tmp_path, tmp_path, env)
        except RuntimeError as exc:
            assert "restic restore failed" in str(exc)
        else:
            raise AssertionError("Expected RuntimeError")


# ---------------------------------------------------------------------------
# list_snapshots()
# ---------------------------------------------------------------------------


def test_list_snapshots_returns_parsed_json(tmp_path: Path) -> None:
    from stackr.backup import list_snapshots

    sample = [
        {
            "id": "abc123def456",
            "short_id": "abc123de",
            "time": "2026-03-20T02:00:00.000Z",
            "hostname": "myhost",
            "paths": ["/opt/appdata"],
        }
    ]
    env: dict[str, str] = {"STACKR_RESTIC_PASSWORD": "secret"}

    with (
        patch("shutil.which", return_value="/usr/bin/restic"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps(sample).encode()
        )
        result = list_snapshots("/mnt/backup", tmp_path, env)

    assert len(result) == 1
    assert result[0]["short_id"] == "abc123de"
    assert result[0]["hostname"] == "myhost"


def test_list_snapshots_raises_on_failure(tmp_path: Path) -> None:
    from stackr.backup import list_snapshots

    env: dict[str, str] = {"STACKR_RESTIC_PASSWORD": "secret"}

    with (
        patch("shutil.which", return_value="/usr/bin/restic"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=1, stderr=b"repo not found")
        try:
            list_snapshots("/mnt/backup", tmp_path, env)
        except RuntimeError as exc:
            assert "restic snapshots failed" in str(exc)
        else:
            raise AssertionError("Expected RuntimeError")
