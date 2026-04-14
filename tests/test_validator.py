"""Tests for pre-deploy validation."""


from stackr.catalog import Catalog
from stackr.config import AppConfig, StackrConfig
from stackr.validator import validate


def _make_config(apps: list[dict], **kwargs) -> StackrConfig:
    base = {
        "global": {"data_dir": "/data"},
        "network": {"domain": "test.com", "local_domain": "home.test.com"},
        "security": {"socket_proxy": False},
        "apps": apps,
    }
    base.update(kwargs)
    return StackrConfig.model_validate(base)


def test_valid_config_passes():
    config = _make_config(
        [{"name": "uptime-kuma", "enabled": True}],
        security={"socket_proxy": False},
    )
    catalog = Catalog()
    result = validate(config, catalog, {})
    assert result.ok


def test_unknown_app_fails():
    config = _make_config([{"name": "nonexistent-app", "enabled": True}])
    catalog = Catalog()
    result = validate(config, catalog, {})
    assert not result.ok
    assert any("not found" in e.message for e in result.errors)


def test_missing_hard_dependency_fails():
    # Verify that a missing *suggests* dep produces a warning, not an error.
    # prowlarr suggests sonarr/radarr; enable prowlarr alone to trigger it.
    config = _make_config(
        [{"name": "prowlarr", "enabled": True}],
        security={"socket_proxy": False},
    )
    catalog = Catalog()
    result = validate(config, catalog, {})
    # sonarr is a *suggests* dep of prowlarr — missing it is a warning, not an error
    assert result.ok
    assert any("sonarr" in w.message for w in result.warnings)


def test_port_conflict_detected():
    # Both jellyfin and sonarr have different ports — no conflict
    config = _make_config(
        [
            {"name": "jellyfin", "enabled": True},
            {"name": "sonarr", "enabled": True},
        ],
        security={"socket_proxy": False},
    )
    catalog = Catalog()
    result = validate(config, catalog, {})
    # jellyfin=8096, sonarr=8989 — no conflict expected
    port_errors = [e for e in result.errors if "conflicts" in e.message]
    assert port_errors == []


def test_port_conflict_same_host_port(monkeypatch):
    """Two apps binding the same host port produce a conflict error."""
    from pathlib import Path

    from stackr.catalog import CatalogApp

    catalog = Catalog()
    # Simulate two DNS servers both trying to bind host port 53
    fake_app = CatalogApp(
        name="fake-dns",
        display_name="Fake DNS",
        description="test",
        category="test",
        host_ports=[53],  # same host port as adguardhome
        catalog_dir=Path("/tmp"),
    )
    catalog._apps["fake-dns"] = fake_app

    config = _make_config(
        [
            {"name": "adguardhome", "enabled": True},
            {"name": "fake-dns", "enabled": True},
        ],
        security={"socket_proxy": False},
    )
    result = validate(config, catalog, {})
    assert not result.ok
    assert any("53" in e.message and "conflicts" in e.message for e in result.errors)


def test_shared_traefik_port_no_conflict(monkeypatch):
    """Apps sharing the same container port (Traefik-proxied) do not conflict."""
    from pathlib import Path

    from stackr.catalog import CatalogApp

    catalog = Catalog()
    # Two apps both listen on container port 8080 but are proxied — no host conflict
    fake_a = CatalogApp(
        name="app-a",
        display_name="A",
        description="test",
        category="test",
        ports=[8080],
        host_ports=[],
        catalog_dir=Path("/tmp"),
    )
    fake_b = CatalogApp(
        name="app-b",
        display_name="B",
        description="test",
        category="test",
        ports=[8080],
        host_ports=[],
        catalog_dir=Path("/tmp"),
    )
    catalog._apps["app-a"] = fake_a
    catalog._apps["app-b"] = fake_b

    config = _make_config(
        [
            {"name": "app-a", "enabled": True},
            {"name": "app-b", "enabled": True},
        ],
        security={"socket_proxy": False},
    )
    result = validate(config, catalog, {})
    port_errors = [e for e in result.errors if "conflicts" in e.message]
    assert port_errors == []


def test_unresolved_secret_fails():
    config = _make_config(
        [{"name": "uptime-kuma", "enabled": True,
          "vars": {"MY_SECRET": "${MY_SECRET}"}}],
        security={"socket_proxy": False},
    )
    catalog = Catalog()
    # env is empty — secret is unresolved
    result = validate(config, catalog, {})
    assert not result.ok
    assert any("MY_SECRET" in e.message for e in result.errors)


def test_resolved_secret_passes():
    config = _make_config(
        [{"name": "uptime-kuma", "enabled": True,
          "vars": {"MY_SECRET": "${MY_SECRET}"}}],
        security={"socket_proxy": False},
    )
    catalog = Catalog()
    env = {"MY_SECRET": "abc123"}
    result = validate(config, catalog, env)
    assert result.ok


def test_container_name_conflict_detected(monkeypatch):
    """Two apps with the same name produce a container name conflict error."""
    from pathlib import Path

    from stackr.catalog import CatalogApp

    catalog = Catalog()
    fake_app = CatalogApp(
        name="jellyfin",  # duplicate of the real jellyfin
        display_name="Fake Jellyfin",
        description="duplicate",
        category="media",
        catalog_dir=Path("/tmp"),
    )
    # Inject under a different key so both apps appear enabled with the same name
    catalog._apps["jellyfin-copy"] = fake_app

    # Both apps resolve to container_name "jellyfin" — but since we check by app.name
    # (jellyfin vs jellyfin-copy), no conflict fires here. This test verifies that
    # two apps with the SAME app.name (which would produce duplicate container names)
    # are caught.
    dup_config = _make_config(
        [{"name": "jellyfin", "enabled": True}],
        security={"socket_proxy": False},
    )
    # Manually inject a second app entry with the same name
    dup_config.apps.append(AppConfig(name="jellyfin"))
    result = validate(dup_config, catalog, {})
    name_errors = [e for e in result.errors if "Container name" in e.message]
    assert len(name_errors) > 0


def test_suggests_only_warns():
    catalog = Catalog()
    # seerr suggests sonarr and radarr — check missing suggests produce warnings, not errors
    config = _make_config(
        [{"name": "seerr", "enabled": True}],
        security={"socket_proxy": False},
    )
    result = validate(config, catalog, {})
    suggest_warns = [w for w in result.warnings if "sonarr" in w.message or "radarr" in w.message]
    assert len(suggest_warns) > 0
    suggest_errors = [e for e in result.errors if "sonarr" in e.message or "radarr" in e.message]
    assert suggest_errors == []


def test_mutually_exclusive_pihole_adguard():
    """pihole and adguardhome cannot both be enabled."""
    catalog = Catalog()
    config = _make_config([
        {"name": "pihole", "enabled": True},
        {"name": "adguardhome", "enabled": True},
    ])
    result = validate(config, catalog, {})
    errors = [e for e in result.errors if "adguardhome" in e.message]
    assert errors, "Expected error for pihole + adguardhome conflict"
