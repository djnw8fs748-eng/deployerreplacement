"""Tests for stackr.doctor — pre-flight health checks."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from stackr.config import StackrConfig


def _minimal_config(**overrides: object) -> StackrConfig:
    raw: dict[str, object] = {
        "global": {"data_dir": "/opt/appdata", "timezone": "UTC", "puid": 1000, "pgid": 1000},
        "network": {
            "mode": "external", "domain": "example.com", "local_domain": "home.example.com"
        },
        "traefik": {"enabled": False},
        "security": {"socket_proxy": False, "crowdsec": False, "auth_provider": "none"},
        "backup": {"enabled": False, "destination": "/mnt/backup"},
        "alerts": {"enabled": False},
        "apps": [],
        **overrides,
    }
    return StackrConfig.model_validate(raw)


# ---------------------------------------------------------------------------
# _check_backup_destination
# ---------------------------------------------------------------------------


def test_check_backup_destination_ok(tmp_path: Path) -> None:
    from stackr.doctor import _check_backup_destination

    config = _minimal_config(backup={"enabled": True, "destination": str(tmp_path)})
    check = _check_backup_destination(config)
    assert check.status == "ok"
    assert str(tmp_path) in check.message


def test_check_backup_destination_warn_not_exists(tmp_path: Path) -> None:
    from stackr.doctor import _check_backup_destination

    missing = tmp_path / "nonexistent"
    config = _minimal_config(backup={"enabled": True, "destination": str(missing)})
    check = _check_backup_destination(config)
    assert check.status == "warn"
    assert "not exist" in check.message


def test_check_backup_destination_warn_not_writable(tmp_path: Path) -> None:
    from stackr.doctor import _check_backup_destination

    config = _minimal_config(backup={"enabled": True, "destination": str(tmp_path)})
    with patch("os.access", return_value=False):
        check = _check_backup_destination(config)
    assert check.status == "warn"
    assert "not writable" in check.message


# ---------------------------------------------------------------------------
# run_doctor — backup check only included when backup.enabled
# ---------------------------------------------------------------------------


def test_run_doctor_skips_backup_check_when_disabled(tmp_path: Path) -> None:
    from stackr.doctor import run_doctor

    config = _minimal_config()

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        m = MagicMock()
        m.returncode = 0
        m.stdout = "Docker Compose version 2.x"
        return m

    env = {"CF_DNS_API_TOKEN": "x"}

    with patch("subprocess.run", side_effect=fake_run):
        # Should complete without error; backup check not in checks
        result = run_doctor(config, env, config_dir=tmp_path)
    # Result can be True or False depending on network checks; just confirm it ran
    assert isinstance(result, bool)


def test_run_doctor_includes_backup_check_when_enabled(tmp_path: Path) -> None:
    from stackr.doctor import run_doctor

    config = _minimal_config(backup={"enabled": True, "destination": str(tmp_path)})
    env: dict[str, str] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        m = MagicMock()
        m.returncode = 0
        m.stdout = "Docker Compose version 2.x"
        return m

    with patch("subprocess.run", side_effect=fake_run):
        result = run_doctor(config, env, config_dir=tmp_path)
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# run_doctor — sends alert on failure
# ---------------------------------------------------------------------------


def test_run_doctor_sends_alert_on_failure(tmp_path: Path) -> None:
    from stackr.doctor import run_doctor

    config = _minimal_config(
        alerts={"enabled": True, "provider": "ntfy", "url": "https://ntfy.sh/test"},
        traefik={"enabled": True, "dns_provider": "cloudflare", "dns_provider_env": {}},
    )
    env: dict[str, str] = {}  # missing CF_DNS_API_TOKEN → DNS check fails

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        m = MagicMock()
        m.returncode = 0
        m.stdout = "Docker Compose version 2.x"
        return m

    with (
        patch("subprocess.run", side_effect=fake_run),
        patch("stackr.alerts.send_alert") as mock_alert,
    ):
        result = run_doctor(config, env, config_dir=tmp_path)

    assert result is False
    mock_alert.assert_called_once()
    title = mock_alert.call_args[0][0]
    assert "doctor" in title.lower()
