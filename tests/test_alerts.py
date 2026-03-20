"""Tests for stackr.alerts — health alert notifications."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from stackr.config import AlertConfig

# ---------------------------------------------------------------------------
# send_alert — enabled=False guard
# ---------------------------------------------------------------------------


def test_send_alert_does_nothing_when_disabled() -> None:
    from stackr.alerts import send_alert

    config = AlertConfig(enabled=False, provider="ntfy", url="https://ntfy.sh/test")
    with patch("urllib.request.urlopen") as mock_open:
        send_alert("title", "message", config)
        mock_open.assert_not_called()


# ---------------------------------------------------------------------------
# send_alert — exception swallowing
# ---------------------------------------------------------------------------


def test_send_alert_swallows_http_errors() -> None:
    """A broken endpoint must never raise — it should only warn."""
    import urllib.error

    from stackr.alerts import send_alert

    config = AlertConfig(enabled=True, provider="ntfy", url="https://ntfy.sh/test")
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
        # Must not raise
        send_alert("title", "message", config)


# ---------------------------------------------------------------------------
# ntfy provider
# ---------------------------------------------------------------------------


def test_send_alert_ntfy_posts_to_url() -> None:
    from stackr.alerts import send_alert

    config = AlertConfig(enabled=True, provider="ntfy", url="https://ntfy.sh/my-topic")
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
        send_alert("Deploy failed", "traefik is down", config)
        mock_open.assert_called_once()
        req = mock_open.call_args[0][0]
        assert req.full_url == "https://ntfy.sh/my-topic"
        assert req.get_header("Title") == "Deploy failed"


def test_send_alert_ntfy_includes_bearer_token_when_set() -> None:
    from stackr.alerts import send_alert

    config = AlertConfig(
        enabled=True, provider="ntfy", url="https://ntfy.sh/private", token="mytoken"
    )
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
        send_alert("t", "m", config)
        req = mock_open.call_args[0][0]
        assert "Bearer mytoken" in req.get_header("Authorization")


# ---------------------------------------------------------------------------
# gotify provider
# ---------------------------------------------------------------------------


def test_send_alert_gotify_sends_json_body() -> None:
    import json

    from stackr.alerts import send_alert

    config = AlertConfig(
        enabled=True, provider="gotify", url="https://gotify.example.com/message", token="tok"
    )
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
        send_alert("Hello", "World", config)
        req = mock_open.call_args[0][0]
        body = json.loads(req.data)
        assert body["title"] == "Hello"
        assert body["message"] == "World"
        assert req.get_header("X-gotify-key") == "tok"


# ---------------------------------------------------------------------------
# webhook provider
# ---------------------------------------------------------------------------


def test_send_alert_webhook_sends_json_body() -> None:
    import json

    from stackr.alerts import send_alert

    config = AlertConfig(
        enabled=True, provider="webhook", url="https://hooks.example.com/notify"
    )
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
        send_alert("Alert", "Something happened", config)
        req = mock_open.call_args[0][0]
        body = json.loads(req.data)
        assert body["title"] == "Alert"
        assert body["message"] == "Something happened"


# ---------------------------------------------------------------------------
# AlertConfig validation
# ---------------------------------------------------------------------------


def test_alert_config_rejects_unknown_provider() -> None:
    with pytest.raises(ValidationError):
        AlertConfig(enabled=True, provider="slack", url="https://example.com")


def test_alert_config_accepts_valid_providers() -> None:
    for provider in ("ntfy", "gotify", "webhook"):
        cfg = AlertConfig(enabled=True, provider=provider, url="https://example.com")
        assert cfg.provider == provider
