"""Tests for drift detection in _live_status()."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from stackr.api.models import AppStatusEnum
from stackr.api.routes.apps import _clear_status_cache, _live_status


@pytest.fixture(autouse=True)
def clear_cache():
    _clear_status_cache()
    yield
    _clear_status_cache()


def _mock_cs(status: str) -> MagicMock:
    cs = MagicMock()
    cs.status = status
    return cs


def test_live_status_returns_running_when_container_up():
    with patch(
        "stackr.api.routes.apps.get_container_status", return_value=_mock_cs("running")
    ), patch("stackr.api.routes.apps.get_image_digests", return_value={}):
        assert _live_status("myapp", {}) == AppStatusEnum.running


def test_live_status_returns_stopped_when_container_down():
    with patch("stackr.api.routes.apps.get_container_status", return_value=_mock_cs("stopped")):
        assert _live_status("myapp", {}) == AppStatusEnum.stopped


def test_live_status_returns_drift_when_digests_differ():
    stored = {"myapp": "sha256:aaa"}
    live = {"myapp": "sha256:bbb"}
    with patch(
        "stackr.api.routes.apps.get_container_status", return_value=_mock_cs("running")
    ), patch("stackr.api.routes.apps.get_image_digests", return_value=live):
        assert _live_status("myapp", stored) == AppStatusEnum.drift


def test_live_status_no_drift_when_digests_match():
    stored = {"myapp": "sha256:aaa"}
    live = {"myapp": "sha256:aaa"}
    with patch(
        "stackr.api.routes.apps.get_container_status", return_value=_mock_cs("running")
    ), patch("stackr.api.routes.apps.get_image_digests", return_value=live):
        assert _live_status("myapp", stored) == AppStatusEnum.running


def test_live_status_no_drift_when_stored_digests_empty():
    """Apps never deployed have no stored digests — no drift check fires."""
    with patch(
        "stackr.api.routes.apps.get_container_status", return_value=_mock_cs("running")
    ), patch("stackr.api.routes.apps.get_image_digests") as mock_gid:
        result = _live_status("myapp", {})
    assert result == AppStatusEnum.running
    mock_gid.assert_not_called()


def test_live_status_cached_for_five_seconds():
    stored = {"s": "sha256:aaa"}
    call_count = 0

    def counting_gcs(name):
        nonlocal call_count
        call_count += 1
        return _mock_cs("running")

    with patch(
        "stackr.api.routes.apps.get_container_status", side_effect=counting_gcs
    ), patch("stackr.api.routes.apps.get_image_digests", return_value={"s": "sha256:aaa"}):
        _live_status("myapp", stored)
        _live_status("myapp", stored)
    assert call_count == 1  # second call hit cache


def test_live_status_cache_expires_after_five_seconds():
    stored = {"s": "sha256:aaa"}
    call_count = 0

    def counting_gcs(name):
        nonlocal call_count
        call_count += 1
        return _mock_cs("running")

    with patch(
        "stackr.api.routes.apps.get_container_status", side_effect=counting_gcs
    ), patch(
        "stackr.api.routes.apps.get_image_digests", return_value={"s": "sha256:aaa"}
    ), patch(
        "stackr.api.routes.apps.time.monotonic"
    ) as mock_monotonic:
        mock_monotonic.side_effect = [0.0, 6.0]
        _live_status("myapp", stored)
        _live_status("myapp", stored)
    assert call_count == 2  # cache expired, second call hit Docker


def test_live_status_returns_unknown_on_exception():
    with patch(
        "stackr.api.routes.apps.get_container_status",
        side_effect=RuntimeError("no docker"),
    ):
        assert _live_status("myapp", {}) == AppStatusEnum.unknown
