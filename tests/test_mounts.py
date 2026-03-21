"""Tests for stackr.mounts — remote share mounting helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from stackr.mounts import (
    MountResult,
    _mount_nfs,
    _mount_rclone,
    _mount_smb,
    mount_all,
    mount_share,
    umount_all,
    umount_share,
)

# ---------------------------------------------------------------------------
# mount_share — already-mounted path
# ---------------------------------------------------------------------------


def test_mount_share_already_mounted(tmp_path: Path) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = mount_share("media", "smb", "//server/media", tmp_path)
    assert result.ok
    assert "already mounted" in result.message


# ---------------------------------------------------------------------------
# SMB
# ---------------------------------------------------------------------------


def test_mount_smb_ok(tmp_path: Path) -> None:
    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        m = MagicMock()
        # mountpoint -q returns 1 (not mounted), then mount.cifs returns 0
        m.returncode = 1 if "mountpoint" in cmd else 0
        return m

    with (
        patch("subprocess.run", side_effect=fake_run),
        patch("shutil.which", return_value="/usr/sbin/mount.cifs"),
    ):
        result = mount_share("media", "smb", "//server/share", tmp_path, username="user")
    assert result.ok


def test_mount_smb_no_cifs_utils(tmp_path: Path) -> None:
    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        m = MagicMock()
        m.returncode = 1  # not mounted
        return m

    with (
        patch("subprocess.run", side_effect=fake_run),
        patch("shutil.which", return_value=None),
    ):
        result = _mount_smb("media", "//server/share", tmp_path, "", None, None)
    assert not result.ok
    assert "cifs-utils" in result.message


def test_mount_smb_fail(tmp_path: Path) -> None:
    m = MagicMock(returncode=1, stderr="permission denied")
    with (
        patch("shutil.which", return_value="/usr/sbin/mount.cifs"),
        patch("subprocess.run", return_value=m),
    ):
        result = _mount_smb("media", "//server/share", tmp_path, "", None, None)
    assert not result.ok
    assert "failed" in result.message


# ---------------------------------------------------------------------------
# NFS
# ---------------------------------------------------------------------------


def test_mount_nfs_ok(tmp_path: Path) -> None:
    with patch("subprocess.run", return_value=MagicMock(returncode=0, stderr="")):
        result = _mount_nfs("nfs-share", "server:/export", tmp_path, "")
    assert result.ok


def test_mount_nfs_fail(tmp_path: Path) -> None:
    with patch("subprocess.run", return_value=MagicMock(returncode=1, stderr="refused")):
        result = _mount_nfs("nfs-share", "server:/export", tmp_path, "")
    assert not result.ok


# ---------------------------------------------------------------------------
# Rclone
# ---------------------------------------------------------------------------


def test_mount_rclone_no_binary(tmp_path: Path) -> None:
    with patch("shutil.which", return_value=None):
        result = _mount_rclone("gdrive", "gdrive:", tmp_path, "")
    assert not result.ok
    assert "rclone" in result.message


def test_mount_rclone_ok(tmp_path: Path) -> None:
    with (
        patch("shutil.which", return_value="/usr/bin/rclone"),
        patch("subprocess.run", return_value=MagicMock(returncode=0, stderr="")),
    ):
        result = _mount_rclone("gdrive", "gdrive:", tmp_path, "")
    assert result.ok


# ---------------------------------------------------------------------------
# umount_share
# ---------------------------------------------------------------------------


def test_umount_share_not_mounted(tmp_path: Path) -> None:
    with patch("subprocess.run", return_value=MagicMock(returncode=1)):
        result = umount_share("media", tmp_path)
    assert result.ok
    assert "not mounted" in result.message


def test_umount_share_ok(tmp_path: Path) -> None:
    call_count = 0

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        m = MagicMock()
        m.returncode = 0 if call_count == 1 else 0  # mountpoint ok, then umount ok
        m.stderr = ""
        return m

    with patch("subprocess.run", side_effect=fake_run):
        result = umount_share("media", tmp_path)
    assert result.ok


def test_umount_share_fail(tmp_path: Path) -> None:
    call_count = 0

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        m = MagicMock()
        m.returncode = 0 if call_count == 1 else 1  # mounted, then umount fails
        m.stderr = "device busy"
        return m

    with patch("subprocess.run", side_effect=fake_run):
        result = umount_share("media", tmp_path)
    assert not result.ok


# ---------------------------------------------------------------------------
# mount_all / umount_all
# ---------------------------------------------------------------------------


class _FakeMount:
    def __init__(self, name: str, mountpoint: Path) -> None:
        self.name = name
        self.type = "smb"
        self.remote = "//server/share"
        self.mountpoint = mountpoint
        self.options = ""
        self.username = None
        self.password = None


def test_mount_all_returns_results(tmp_path: Path) -> None:
    fake_mounts = [_FakeMount("m1", tmp_path / "m1"), _FakeMount("m2", tmp_path / "m2")]
    with patch("subprocess.run", return_value=MagicMock(returncode=0)):
        results = mount_all(fake_mounts)  # type: ignore[arg-type]
    assert len(results) == 2
    assert all(isinstance(r, MountResult) for r in results)


def test_umount_all_returns_results(tmp_path: Path) -> None:
    fake_mounts = [_FakeMount("m1", tmp_path / "m1"), _FakeMount("m2", tmp_path / "m2")]
    with patch("subprocess.run", return_value=MagicMock(returncode=1)):
        results = umount_all(fake_mounts)  # type: ignore[arg-type]
    assert len(results) == 2
