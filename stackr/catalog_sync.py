"""Download and install catalog releases from GitHub.

The user-level catalog lives at ~/.stackr/catalog/ and takes priority over
the built-in catalog shipped with the package.  `stackr catalog update`
downloads the catalog directory from a GitHub release and installs it there.
"""

from __future__ import annotations

import json
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

GITHUB_REPO = "djnw8fs748-eng/deployerreplacement"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
USER_CATALOG = Path.home() / ".stackr" / "catalog"
_VERSION_FILE = ".catalog_version"


def fetch_latest_tag() -> str:
    """Return the tag name of the latest GitHub release."""
    url = f"{GITHUB_API}/latest"
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "stackr/1.0"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
        data: dict[str, str] = json.loads(resp.read())
    return data["tag_name"]


def fetch_tarball_url(tag: str) -> str:
    """Return the source tarball URL for a given release tag."""
    url = f"{GITHUB_API}/tags/{tag}"
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "stackr/1.0"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
        data: dict[str, str | list[dict[str, str]]] = json.loads(resp.read())
    # Prefer a dedicated catalog.tar.gz asset if present, else use source tarball
    for asset in data.get("assets", []):
        if isinstance(asset, dict) and asset.get("name") == "catalog.tar.gz":
            return str(asset["browser_download_url"])
    return str(data["tarball_url"])


def download_and_install(tag: str) -> None:
    """Download a release tarball and extract its catalog/ to ~/.stackr/catalog/."""
    tarball_url = fetch_tarball_url(tag)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        archive = tmp_path / "release.tar.gz"
        _download(tarball_url, archive)
        with tarfile.open(archive) as tf:
            if sys.version_info >= (3, 12):
                tf.extractall(tmp_path, filter="data")  # type: ignore[call-arg]
            else:
                tf.extractall(tmp_path)  # noqa: S202
        # The tarball contains a top-level directory; find the catalog/ inside it
        catalog_dirs = [p for p in tmp_path.rglob("catalog") if p.is_dir()]
        if not catalog_dirs:
            raise FileNotFoundError("No 'catalog/' directory found in release tarball")
        src = catalog_dirs[0]
        if USER_CATALOG.exists():
            shutil.rmtree(USER_CATALOG)
        shutil.copytree(src, USER_CATALOG)
    _write_version(tag)


def read_installed_version() -> str | None:
    """Return the installed catalog version tag, or None if not installed."""
    vf = USER_CATALOG / _VERSION_FILE
    return vf.read_text().strip() if vf.exists() else None


def _write_version(tag: str) -> None:
    USER_CATALOG.mkdir(parents=True, exist_ok=True)
    (USER_CATALOG / _VERSION_FILE).write_text(tag)


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "stackr/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as out:  # noqa: S310
        shutil.copyfileobj(resp, out)
