"""Tests for stackr upgrade command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from stackr.cli import app

runner = CliRunner()


def _mock_pipx(path: str = "/usr/bin/pipx") -> MagicMock:
    m = MagicMock()
    m.return_value = path
    return m


def test_upgrade_success() -> None:
    """upgrade runs pipx install --force and reports the new version."""
    with (
        patch("shutil.which", side_effect=lambda c: (
            "/usr/bin/pipx" if c == "pipx" else "/usr/bin/stackr"
        )),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),          # pipx install --force
            MagicMock(returncode=0, stdout="stackr 0.2.0\n", stderr=""),  # stackr --version
        ]
        result = runner.invoke(app, ["upgrade"])

    assert result.exit_code == 0
    assert "Upgrade complete" in result.output
    # Confirm --force was passed
    first_call_args = mock_run.call_args_list[0][0][0]
    assert "--force" in first_call_args
    assert any("github.com" in a for a in first_call_args)


def test_upgrade_fails_when_pipx_missing() -> None:
    """upgrade exits with error when pipx is not on PATH."""
    with patch("shutil.which", return_value=None):
        result = runner.invoke(app, ["upgrade"])

    assert result.exit_code != 0
    assert "pipx not found" in result.output


def test_upgrade_reports_failure_on_nonzero_exit() -> None:
    """upgrade prints stderr and exits non-zero when pipx install fails."""
    with (
        patch("shutil.which", return_value="/usr/bin/pipx"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="network error"
        )
        result = runner.invoke(app, ["upgrade"])

    assert result.exit_code != 0
    assert "Upgrade failed" in result.output
    assert "network error" in result.output


def test_upgrade_uses_correct_github_repo() -> None:
    """upgrade installs from the canonical GitHub repository URL."""
    from stackr.catalog_sync import GITHUB_REPO

    with (
        patch("shutil.which", side_effect=lambda cmd: "/usr/bin/pipx" if cmd == "pipx" else None),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        runner.invoke(app, ["upgrade"])

    install_cmd = mock_run.call_args_list[0][0][0]
    repo_url = next(a for a in install_cmd if "github.com" in a)
    assert GITHUB_REPO in repo_url
