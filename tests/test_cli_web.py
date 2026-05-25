"""Tests for 'stackr web' CLI command."""
from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from stackr.cli import app

runner = CliRunner()


def test_web_opens_browser_when_api_reachable():
    with patch("urllib.request.urlopen"), patch("webbrowser.open") as mock_browser:
        result = runner.invoke(app, ["web"])
    assert result.exit_code == 0
    mock_browser.assert_called_once_with("http://127.0.0.1:7274")


def test_web_exits_with_error_when_api_not_reachable():
    with patch("urllib.request.urlopen", side_effect=Exception("connection refused")):
        result = runner.invoke(app, ["web"])
    assert result.exit_code == 1
    assert "not running" in result.output.lower() or "stackr api" in result.output


def test_web_respects_custom_host_and_port():
    with patch("urllib.request.urlopen"), patch("webbrowser.open") as mock_browser:
        result = runner.invoke(app, ["web", "--host", "0.0.0.0", "--port", "8080"])
    assert result.exit_code == 0
    mock_browser.assert_called_once_with("http://0.0.0.0:8080")
