"""Tests for stackr doctor health checks."""

from __future__ import annotations

from stackr.config import StackrConfig
from stackr.doctor import (
    _check_catalog_apps,
    _check_compose_plugin,
    _check_dns_env,
    _check_docker_daemon,
    _check_proxy_network,
    _check_socket_proxy_network,
    _check_stackr_env,
    _check_state_file,
    run_doctor,
)


def _make_config(**kwargs) -> StackrConfig:
    base = {
        "global": {"data_dir": "/data"},
        "network": {"mode": "external", "domain": "test.com", "local_domain": "home.test.com"},
        "traefik": {"enabled": True, "acme_email": "a@b.com", "dns_provider": "cloudflare"},
        "security": {"socket_proxy": False},
        "apps": [],
    }
    base.update(kwargs)
    return StackrConfig.model_validate(base)


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def test_docker_daemon_ok(mocker):
    mocker.patch("subprocess.run", return_value=mocker.Mock(returncode=0))
    check = _check_docker_daemon()
    assert check.status == "ok"


def test_docker_daemon_fail(mocker):
    mocker.patch("subprocess.run", return_value=mocker.Mock(returncode=1))
    check = _check_docker_daemon()
    assert check.status == "fail"


def test_compose_plugin_ok(mocker):
    mocker.patch(
        "subprocess.run",
        return_value=mocker.Mock(returncode=0, stdout="Docker Compose version v2.27.0\n"),
    )
    check = _check_compose_plugin()
    assert check.status == "ok"
    assert "v2" in check.message


def test_compose_plugin_fail(mocker):
    mocker.patch("subprocess.run", return_value=mocker.Mock(returncode=1, stdout=""))
    check = _check_compose_plugin()
    assert check.status == "fail"


def test_proxy_network_ok(mocker):
    mocker.patch("subprocess.run", return_value=mocker.Mock(returncode=0))
    check = _check_proxy_network()
    assert check.status == "ok"


def test_proxy_network_warn(mocker):
    mocker.patch("subprocess.run", return_value=mocker.Mock(returncode=1))
    check = _check_proxy_network()
    assert check.status == "warn"


def test_socket_proxy_network_ok(mocker):
    mocker.patch("subprocess.run", return_value=mocker.Mock(returncode=0))
    check = _check_socket_proxy_network()
    assert check.status == "ok"


def test_state_file_ok(mocker, tmp_path):
    state_file = tmp_path / "state.json"
    state_file.write_text('{"apps": {}, "deployed_at": null, "catalog_version": null}')
    mocker.patch("stackr.doctor.DEFAULT_STATE_DIR", tmp_path)
    check = _check_state_file()
    assert check.status == "ok"


def test_state_file_missing(mocker, tmp_path):
    mocker.patch("stackr.doctor.DEFAULT_STATE_DIR", tmp_path)
    check = _check_state_file()
    assert check.status == "warn"
    assert "Not found" in check.message


def test_state_file_corrupt(mocker, tmp_path):
    state_file = tmp_path / "state.json"
    state_file.write_text("NOT VALID JSON {{{")
    mocker.patch("stackr.doctor.DEFAULT_STATE_DIR", tmp_path)
    check = _check_state_file()
    assert check.status == "fail"
    assert "Corrupt" in check.message


def test_dns_env_ok():
    config = _make_config()
    env = {"CF_DNS_API_TOKEN": "mytoken"}
    checks = _check_dns_env(config, env)
    assert all(c.status == "ok" for c in checks)


def test_dns_env_missing():
    config = _make_config()
    checks = _check_dns_env(config, {})
    assert any(c.status == "fail" for c in checks)
    assert any("CF_DNS_API_TOKEN" in c.name for c in checks)


def test_dns_env_skipped_when_traefik_disabled():
    config = _make_config(traefik={"enabled": False})
    checks = _check_dns_env(config, {})
    assert checks == []


def test_dns_env_unknown_provider_warns():
    config = _make_config(
        traefik={"enabled": True, "acme_email": "a@b.com", "dns_provider": "my-custom-dns"}
    )
    checks = _check_dns_env(config, {})
    assert len(checks) == 1
    assert checks[0].status == "warn"


def test_stackr_env_ok(tmp_path):
    env_file = tmp_path / ".stackr.env"
    env_file.write_text("CF_DNS_API_TOKEN=abc\n")
    check = _check_stackr_env(tmp_path)
    assert check.status == "ok"


def test_stackr_env_missing(tmp_path):
    check = _check_stackr_env(tmp_path)
    assert check.status == "warn"


def test_catalog_apps_ok():
    config = _make_config(
        apps=[{"name": "jellyfin", "enabled": True}],
        traefik={"enabled": True, "acme_email": "a@b.com", "dns_provider": "cloudflare"},
    )
    check = _check_catalog_apps(config)
    assert check.status == "ok"


def test_catalog_apps_unknown():
    config = _make_config(
        apps=[{"name": "definitely-not-real", "enabled": True}],
    )
    check = _check_catalog_apps(config)
    assert check.status == "fail"
    assert "definitely-not-real" in check.message


# ---------------------------------------------------------------------------
# run_doctor integration
# ---------------------------------------------------------------------------


def test_run_doctor_passes_with_all_ok(mocker, tmp_path):
    # Mock Docker as available
    mocker.patch("subprocess.run", return_value=mocker.Mock(returncode=0, stdout="v2.27.0\n"))
    # Mock state file
    state_file = tmp_path / "state.json"
    state_file.write_text('{"apps": {}, "deployed_at": null, "catalog_version": null}')
    mocker.patch("stackr.doctor.DEFAULT_STATE_DIR", tmp_path)

    config = _make_config(
        traefik={"enabled": True, "acme_email": "a@b.com", "dns_provider": "cloudflare"}
    )
    env = {"CF_DNS_API_TOKEN": "token"}
    ok = run_doctor(config, env, config_dir=tmp_path)
    assert ok is True


def test_run_doctor_fails_with_docker_down(mocker, tmp_path):
    mocker.patch("subprocess.run", return_value=mocker.Mock(returncode=1, stdout=""))
    mocker.patch("stackr.doctor.DEFAULT_STATE_DIR", tmp_path)

    config = _make_config(traefik={"enabled": False})
    ok = run_doctor(config, {}, config_dir=tmp_path)
    assert ok is False
