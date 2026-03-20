"""Restic-based backup and restore.

`restic` must be installed on the host.  The repository password is
auto-generated on first use via `ensure_secret("STACKR_RESTIC_PASSWORD", ...)`
and stored in `.stackr.env`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from rich.console import Console

console = Console()


def _check_restic() -> None:
    """Raise RuntimeError if restic is not on PATH."""
    if shutil.which("restic") is None:
        raise RuntimeError(
            "restic is not installed or not on PATH. "
            "Install it from https://restic.net/ and try again."
        )


def _restic_env(destination: str, config_dir: Path, env: dict[str, str]) -> dict[str, str]:
    """Build the environment dict for restic subprocess calls."""
    from stackr.secrets import ensure_secret

    password = ensure_secret("STACKR_RESTIC_PASSWORD", config_dir, env)
    result = dict(os.environ)
    result["RESTIC_REPOSITORY"] = destination
    result["RESTIC_PASSWORD"] = password
    return result


def _ensure_repo_initialized(destination: str, restic_env: dict[str, str]) -> None:
    """Run `restic init` only when the repository does not yet exist."""
    check = subprocess.run(
        ["restic", "snapshots", "--json"],
        env=restic_env,
        capture_output=True,
    )
    if check.returncode != 0:
        subprocess.run(
            ["restic", "init"],
            env=restic_env,
            check=True,
            capture_output=True,
        )


def backup(
    destination: str,
    data_dir: Path,
    state_dir: Path,
    config_dir: Path,
    env: dict[str, str],
) -> None:
    """Back up data_dir, state_dir, and config_dir to destination."""
    _check_restic()
    restic_env = _restic_env(destination, config_dir, env)
    _ensure_repo_initialized(destination, restic_env)

    paths = [str(data_dir), str(state_dir), str(config_dir)]
    result = subprocess.run(
        ["restic", "backup", "--json", *paths],
        env=restic_env,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"restic backup failed:\n{result.stderr.decode(errors='replace')}")
    console.print("[green]Backup complete.[/green]")


def restore(
    snapshot: str,
    destination: str,
    target: Path,
    config_dir: Path,
    env: dict[str, str],
) -> None:
    """Restore snapshot to target directory."""
    _check_restic()
    restic_env = _restic_env(destination, config_dir, env)

    result = subprocess.run(
        ["restic", "restore", snapshot, "--target", str(target)],
        env=restic_env,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"restic restore failed:\n{result.stderr.decode(errors='replace')}")
    console.print(f"[green]Restore complete — files written to {target}[/green]")


def list_snapshots(
    destination: str,
    config_dir: Path,
    env: dict[str, str],
) -> list[dict[str, Any]]:
    """Return parsed restic snapshot list (JSON)."""
    _check_restic()
    restic_env = _restic_env(destination, config_dir, env)

    result = subprocess.run(
        ["restic", "snapshots", "--json"],
        env=restic_env,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"restic snapshots failed:\n{result.stderr.decode(errors='replace')}"
        )
    data: list[dict[str, Any]] = json.loads(result.stdout)
    return data
