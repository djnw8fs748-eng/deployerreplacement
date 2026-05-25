"""Tests for CLI API-client behaviour: probe, deploy proxy, fallback."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from stackr.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# _api_base probe
# ---------------------------------------------------------------------------

def test_api_base_returns_url_when_reachable():
    from stackr.cli import _api_base
    with patch("urllib.request.urlopen"):
        result = _api_base()
    assert result == "http://127.0.0.1:7274/api/v1"


def test_api_base_returns_none_when_not_reachable():
    from stackr.cli import _api_base
    with patch("urllib.request.urlopen", side_effect=Exception("refused")):
        result = _api_base()
    assert result is None


# ---------------------------------------------------------------------------
# stackr deploy — API proxy path
# ---------------------------------------------------------------------------

def _fake_urlopen_sequence(responses):
    """Build a side_effect list for urllib.request.urlopen."""
    mocks = []
    for body in responses:
        m = MagicMock()
        m.__enter__ = lambda s: s
        m.__exit__ = MagicMock(return_value=False)
        m.read.return_value = json.dumps(body).encode()
        mocks.append(m)
    return mocks


def test_deploy_uses_api_when_reachable():
    responses = _fake_urlopen_sequence([
        {"job_id": "abc12345", "status": "running"},  # POST /deploy
        {"status": "done", "results": [{"app_name": "myapp", "success": True}]},  # GET /status
    ])
    # First call (health probe) is a plain mock (no body needed)
    health = MagicMock()
    health.__enter__ = lambda s: s
    health.__exit__ = MagicMock(return_value=False)

    with (
        patch("urllib.request.urlopen", side_effect=[health] + responses),
        patch("stackr.engine.deployer.deploy_all") as mock_engine,
    ):
        result = runner.invoke(app, ["deploy"])

    assert result.exit_code == 0
    mock_engine.assert_not_called()
    assert "Done" in result.output


def test_deploy_falls_back_to_engine_when_api_not_reachable(tmp_path):
    cfg = tmp_path / "stackr.yml"
    cfg.write_text(
        "global:\n  data_dir: /tmp\n  timezone: UTC\n  puid: 1000\n  pgid: 1000\n"
        "network:\n  domain: test.com\n  local_domain: home.test.com\n"
        "security:\n  socket_proxy: false\napps: []\n"
    )
    with (
        patch("urllib.request.urlopen", side_effect=Exception("refused")),
        patch("stackr.engine.deployer.deploy_all", return_value=[]) as mock_engine,
        patch("stackr.engine.validator.validate") as mock_val,
    ):
        mock_val.return_value = MagicMock(ok=True, errors=[], warnings=[])
        result = runner.invoke(app, ["deploy", "--config", str(cfg)])

    assert result.exit_code == 0
    mock_engine.assert_called_once()


def test_deploy_skip_pull_always_uses_engine(tmp_path):
    """--skip-pull bypasses API even when it is reachable."""
    cfg = tmp_path / "stackr.yml"
    cfg.write_text(
        "global:\n  data_dir: /tmp\n  timezone: UTC\n  puid: 1000\n  pgid: 1000\n"
        "network:\n  domain: test.com\n  local_domain: home.test.com\n"
        "security:\n  socket_proxy: false\napps: []\n"
    )
    health = MagicMock()
    health.__enter__ = lambda s: s
    health.__exit__ = MagicMock(return_value=False)

    with (
        patch("urllib.request.urlopen", side_effect=[health]),
        patch("stackr.engine.deployer.deploy_all", return_value=[]) as mock_engine,
        patch("stackr.engine.validator.validate") as mock_val,
    ):
        mock_val.return_value = MagicMock(ok=True, errors=[], warnings=[])
        runner.invoke(app, ["deploy", "--skip-pull", "--config", str(cfg)])

    mock_engine.assert_called_once()


# ---------------------------------------------------------------------------
# stackr validate — API proxy path
# ---------------------------------------------------------------------------

def test_validate_uses_api_when_reachable():
    health = MagicMock()
    health.__enter__ = lambda s: s
    health.__exit__ = MagicMock(return_value=False)

    val_m = MagicMock()
    val_m.__enter__ = lambda s: s
    val_m.__exit__ = MagicMock(return_value=False)
    val_m.read.return_value = json.dumps({"ok": True, "errors": [], "warnings": []}).encode()

    with (
        patch("urllib.request.urlopen", side_effect=[health, val_m]),
        patch("stackr.engine.validator.validate") as mock_engine,
    ):
        result = runner.invoke(app, ["validate"])

    assert result.exit_code == 0
    mock_engine.assert_not_called()
    assert "passed" in result.output.lower()


def test_validate_shows_api_errors():
    health = MagicMock()
    health.__enter__ = lambda s: s
    health.__exit__ = MagicMock(return_value=False)

    val_m = MagicMock()
    val_m.__enter__ = lambda s: s
    val_m.__exit__ = MagicMock(return_value=False)
    val_m.read.return_value = json.dumps({
        "ok": False,
        "errors": [{"app": "plex", "message": "port conflict on 32400"}],
        "warnings": [],
    }).encode()

    with patch("urllib.request.urlopen", side_effect=[health, val_m]):
        result = runner.invoke(app, ["validate"])

    assert result.exit_code == 1
    assert "plex" in result.output
    assert "port conflict" in result.output


# ---------------------------------------------------------------------------
# stackr status — API proxy path
# ---------------------------------------------------------------------------

def test_status_uses_api_when_reachable():
    health = MagicMock()
    health.__enter__ = lambda s: s
    health.__exit__ = MagicMock(return_value=False)

    apps_m = MagicMock()
    apps_m.__enter__ = lambda s: s
    apps_m.__exit__ = MagicMock(return_value=False)
    apps_m.read.return_value = json.dumps([
        {
            "name": "plex",
            "status": "running",
            "enabled": True,
            "deployed_at": None,
            "last_error": None,
        },
    ]).encode()

    with (
        patch("urllib.request.urlopen", side_effect=[health, apps_m]),
        patch("stackr.status.show_status") as mock_ss,
    ):
        result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    mock_ss.assert_not_called()
    assert "plex" in result.output
