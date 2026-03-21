"""Remote share mounting: SMB, NFS, and Rclone pre-deploy hooks.

Supported mount types:
  smb    — CIFS/SMB share via mount.cifs (requires cifs-utils)
  nfs    — NFS share via mount (requires nfs-common / nfs-utils)
  rclone — Rclone FUSE mount (requires rclone and fuse3)

Mounts declared in `stackr.yml` under `mounts:` are applied before deploy
by calling `mount_all(config)`.  Use `stackr mount` / `stackr umount` to
manage them interactively.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

console = Console()


@dataclass
class MountResult:
    name: str
    ok: bool
    message: str


def mount_share(
    name: str,
    mount_type: str,
    remote: str,
    mountpoint: Path,
    options: str = "",
    username: str | None = None,
    password: str | None = None,
) -> MountResult:
    """Mount a single remote share. Returns a MountResult."""
    mountpoint.mkdir(parents=True, exist_ok=True)

    # Already mounted — skip
    check = subprocess.run(["mountpoint", "-q", str(mountpoint)], capture_output=True)
    if check.returncode == 0:
        return MountResult(name, True, f"{mountpoint} already mounted")

    if mount_type == "smb":
        return _mount_smb(name, remote, mountpoint, options, username, password)
    if mount_type == "nfs":
        return _mount_nfs(name, remote, mountpoint, options)
    if mount_type == "rclone":
        return _mount_rclone(name, remote, mountpoint, options)
    return MountResult(name, False, f"Unknown mount type: {mount_type}")


def umount_share(name: str, mountpoint: Path) -> MountResult:
    """Unmount a share. Returns a MountResult."""
    check = subprocess.run(["mountpoint", "-q", str(mountpoint)], capture_output=True)
    if check.returncode != 0:
        return MountResult(name, True, f"{mountpoint} not mounted")

    result = subprocess.run(["umount", str(mountpoint)], capture_output=True, text=True)
    if result.returncode == 0:
        return MountResult(name, True, f"Unmounted {mountpoint}")
    return MountResult(name, False, f"umount failed: {result.stderr.strip()}")


def mount_all(mounts: list[object]) -> list[MountResult]:
    """Mount all configured shares.

    Accepts a list of MountConfig objects (typed as object to avoid a circular
    import — the caller passes ``config.mounts``).
    """
    results = []
    for m in mounts:
        res = mount_share(
            name=str(m.name),  # type: ignore[attr-defined]
            mount_type=str(m.type),  # type: ignore[attr-defined]
            remote=str(m.remote),  # type: ignore[attr-defined]
            mountpoint=Path(str(m.mountpoint)),  # type: ignore[attr-defined]
            options=str(m.options),  # type: ignore[attr-defined]
            username=m.username,  # type: ignore[attr-defined]
            password=m.password,  # type: ignore[attr-defined]
        )
        if res.ok:
            console.print(f"  [green]MOUNT[/green]  {res.name}: {res.message}")
        else:
            console.print(f"  [red]FAIL[/red]   {res.name}: {res.message}")
        results.append(res)
    return results


def umount_all(mounts: list[object]) -> list[MountResult]:
    """Unmount all configured shares."""
    results = []
    for m in mounts:
        res = umount_share(
            name=str(m.name),  # type: ignore[attr-defined]
            mountpoint=Path(str(m.mountpoint)),  # type: ignore[attr-defined]
        )
        if res.ok:
            console.print(f"  [green]UMOUNT[/green] {res.name}: {res.message}")
        else:
            console.print(f"  [red]FAIL[/red]   {res.name}: {res.message}")
        results.append(res)
    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _mount_smb(
    name: str,
    remote: str,
    mountpoint: Path,
    options: str,
    username: str | None,
    password: str | None,
) -> MountResult:
    if shutil.which("mount.cifs") is None:
        return MountResult(name, False, "mount.cifs not found — install cifs-utils")

    opts: list[str] = ["rw"]
    if options:
        opts.append(options)

    # Write credentials to a temporary file (mode 0600) so they are never
    # visible in process arguments or `ps` output.
    creds_fd, creds_path = tempfile.mkstemp(prefix="stackr-smb-", suffix=".creds")
    try:
        os.chmod(creds_fd, 0o600)
        with os.fdopen(creds_fd, "w") as cf:
            if username:
                cf.write(f"username={username}\n")
            if password:
                cf.write(f"password={password}\n")
        opts.append(f"credentials={creds_path}")

        cmd = ["mount", "-t", "cifs", remote, str(mountpoint), "-o", ",".join(opts)]
        result = subprocess.run(cmd, capture_output=True, text=True)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(creds_path)

    if result.returncode == 0:
        return MountResult(name, True, f"Mounted {remote} → {mountpoint}")
    return MountResult(name, False, f"mount.cifs failed: {result.stderr.strip()}")


def _mount_nfs(name: str, remote: str, mountpoint: Path, options: str) -> MountResult:
    cmd = ["mount", "-t", "nfs", remote, str(mountpoint)]
    if options:
        cmd += ["-o", options]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return MountResult(name, True, f"Mounted {remote} → {mountpoint}")
    return MountResult(name, False, f"mount nfs failed: {result.stderr.strip()}")


def _mount_rclone(name: str, remote: str, mountpoint: Path, options: str) -> MountResult:
    if shutil.which("rclone") is None:
        return MountResult(
            name, False, "rclone not found — install rclone from https://rclone.org"
        )
    cmd = ["rclone", "mount", remote, str(mountpoint), "--daemon"]
    if options:
        cmd += options.split()
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return MountResult(name, True, f"Mounted {remote} → {mountpoint}")
    return MountResult(name, False, f"rclone mount failed: {result.stderr.strip()}")
