"""Tests for catalog sync (GitHub release download)."""

from __future__ import annotations

import json

from stackr.catalog_sync import (
    _write_version,
    fetch_latest_tag,
    fetch_tarball_url,
    read_installed_version,
)


def _make_urlopen_mock(mocker, payload: dict):
    """Return a context-manager mock that yields a response with JSON payload."""

    response = mocker.MagicMock()
    response.read.return_value = json.dumps(payload).encode()
    response.__enter__ = lambda s: s
    response.__exit__ = mocker.MagicMock(return_value=False)
    mocker.patch("urllib.request.urlopen", return_value=response)


def test_fetch_latest_tag(mocker):
    _make_urlopen_mock(mocker, {"tag_name": "v1.2.0"})
    assert fetch_latest_tag() == "v1.2.0"


def test_fetch_tarball_url_uses_asset(mocker):
    _make_urlopen_mock(
        mocker,
        {
            "tarball_url": "https://github.com/org/repo/tarball/v1.0",
            "assets": [
                {"name": "catalog.tar.gz", "browser_download_url": "https://example.com/catalog.tar.gz"},
            ],
        },
    )
    url = fetch_tarball_url("v1.0")
    assert url == "https://example.com/catalog.tar.gz"


def test_fetch_tarball_url_falls_back_to_source(mocker):
    _make_urlopen_mock(
        mocker,
        {
            "tarball_url": "https://github.com/org/repo/tarball/v1.0",
            "assets": [],
        },
    )
    url = fetch_tarball_url("v1.0")
    assert url == "https://github.com/org/repo/tarball/v1.0"


def test_read_installed_version_none(tmp_path, mocker):
    mocker.patch("stackr.catalog_sync.USER_CATALOG", tmp_path / "catalog")
    assert read_installed_version() is None


def test_write_and_read_version(tmp_path, mocker):
    catalog_dir = tmp_path / "catalog"
    mocker.patch("stackr.catalog_sync.USER_CATALOG", catalog_dir)
    _write_version("v2.0.0")
    assert read_installed_version() == "v2.0.0"
