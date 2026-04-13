"""Persistent background service management for Stackr web UI.

Supports:
- Linux: systemd user services (~/.config/systemd/user/)
- macOS: launchd LaunchAgents (~/Library/LaunchAgents/)
"""

from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path

_LINUX_UNIT_DIR = Path.home() / ".config" / "systemd" / "user"
_MACOS_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
_SERVICE_NAME = "stackr-web"
_MACOS_LABEL = "dev.stackr.web"


def _platform() -> str:
    return platform.system()  # "Linux" or "Darwin"


def _unit_path() -> Path:
    return _LINUX_UNIT_DIR / f"{_SERVICE_NAME}.service"


def _plist_path() -> Path:
    return _MACOS_AGENTS_DIR / f"{_MACOS_LABEL}.plist"


def _systemd_unit(config_path: Path, host: str, port: int) -> str:
    executable = sys.executable
    return f"""\
[Unit]
Description=Stackr Web UI
After=network.target

[Service]
Type=simple
ExecStart={executable} -m stackr web --config {config_path.resolve()} --host {host} --port {port}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""


def _launchd_plist(config_path: Path, host: str, port: int) -> str:
    executable = sys.executable
    config_abs = str(config_path.resolve())
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{_MACOS_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{executable}</string>
        <string>-m</string>
        <string>stackr</string>
        <string>web</string>
        <string>--config</string>
        <string>{config_abs}</string>
        <string>--host</string>
        <string>{host}</string>
        <string>--port</string>
        <string>{port}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{Path.home()}/.stackr/web-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{Path.home()}/.stackr/web-stderr.log</string>
</dict>
</plist>
"""


def install(config_path: Path, host: str = "127.0.0.1", port: int = 8000) -> None:
    """Write and enable the service unit for the current platform."""
    system = _platform()
    if system == "Linux":
        _install_systemd(config_path, host, port)
    elif system == "Darwin":
        _install_launchd(config_path, host, port)
    else:
        raise RuntimeError(f"Unsupported platform: {system}")


def uninstall() -> None:
    """Stop, disable, and remove the service unit."""
    system = _platform()
    if system == "Linux":
        _uninstall_systemd()
    elif system == "Darwin":
        _uninstall_launchd()
    else:
        raise RuntimeError(f"Unsupported platform: {system}")


def start() -> None:
    system = _platform()
    if system == "Linux":
        subprocess.run(["systemctl", "--user", "start", _SERVICE_NAME], check=True)
    elif system == "Darwin":
        subprocess.run(["launchctl", "load", str(_plist_path())], check=True)
    else:
        raise RuntimeError(f"Unsupported platform: {system}")


def stop() -> None:
    system = _platform()
    if system == "Linux":
        subprocess.run(["systemctl", "--user", "stop", _SERVICE_NAME], check=True)
    elif system == "Darwin":
        subprocess.run(["launchctl", "unload", str(_plist_path())], check=True)
    else:
        raise RuntimeError(f"Unsupported platform: {system}")


def restart() -> None:
    system = _platform()
    if system == "Linux":
        subprocess.run(["systemctl", "--user", "restart", _SERVICE_NAME], check=True)
    elif system == "Darwin":
        stop()
        start()
    else:
        raise RuntimeError(f"Unsupported platform: {system}")


def status() -> str:
    """Return a human-readable status string."""
    system = _platform()
    if system == "Linux":
        result = subprocess.run(
            ["systemctl", "--user", "status", _SERVICE_NAME],
            capture_output=True,
            text=True,
        )
        return result.stdout + result.stderr
    elif system == "Darwin":
        result = subprocess.run(
            ["launchctl", "list", _MACOS_LABEL],
            capture_output=True,
            text=True,
        )
        return result.stdout + result.stderr
    else:
        raise RuntimeError(f"Unsupported platform: {system}")


def is_installed() -> bool:
    system = _platform()
    if system == "Linux":
        return _unit_path().exists()
    elif system == "Darwin":
        return _plist_path().exists()
    return False


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _install_systemd(config_path: Path, host: str, port: int) -> None:
    _LINUX_UNIT_DIR.mkdir(parents=True, exist_ok=True)
    unit = _unit_path()
    unit.write_text(_systemd_unit(config_path, host, port))
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", _SERVICE_NAME], check=True)


def _uninstall_systemd() -> None:
    unit = _unit_path()
    if not unit.exists():
        raise FileNotFoundError(f"Service unit not found: {unit}")
    subprocess.run(["systemctl", "--user", "disable", "--now", _SERVICE_NAME], check=False)
    unit.unlink()
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)


def _install_launchd(config_path: Path, host: str, port: int) -> None:
    _MACOS_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    # Ensure log directory exists
    (Path.home() / ".stackr").mkdir(parents=True, exist_ok=True)
    plist = _plist_path()
    plist.write_text(_launchd_plist(config_path, host, port))
    subprocess.run(["launchctl", "load", str(plist)], check=True)


def _uninstall_launchd() -> None:
    plist = _plist_path()
    if not plist.exists():
        raise FileNotFoundError(f"LaunchAgent plist not found: {plist}")
    subprocess.run(["launchctl", "unload", str(plist)], check=False)
    plist.unlink()
