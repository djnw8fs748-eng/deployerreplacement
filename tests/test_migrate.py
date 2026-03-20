"""Tests for stackr.migrate — Deployrr → Stackr migration helpers."""

from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]

# ---------------------------------------------------------------------------
# map_app_name
# ---------------------------------------------------------------------------


def test_map_app_name_direct_hit() -> None:
    from stackr.migrate import map_app_name

    assert map_app_name("portainer-ce") == "portainer"
    assert map_app_name("bitwarden-rs") == "vaultwarden"
    assert map_app_name("nextcloud-aio") == "nextcloud"


def test_map_app_name_suffix_strip() -> None:
    from stackr.migrate import map_app_name

    # "myapp-vpn" → strip "-vpn" → "myapp" (not in map, returned as-is after strip)
    result = map_app_name("myapp-vpn")
    assert result == "myapp"


def test_map_app_name_passthrough() -> None:
    from stackr.migrate import map_app_name

    # Completely unknown name is returned unchanged (lowercased)
    result = map_app_name("some-unknown-app")
    assert result == "some-unknown-app"


def test_map_app_name_case_insensitive() -> None:
    from stackr.migrate import map_app_name

    assert map_app_name("Portainer-CE") == "portainer"


def test_map_app_name_known_no_suffix_passthrough() -> None:
    from stackr.migrate import map_app_name

    # "traefik" is already the canonical name
    assert map_app_name("traefik") == "traefik"


# ---------------------------------------------------------------------------
# migrate_from_deployrr
# ---------------------------------------------------------------------------


def test_migrate_from_deployrr_splits_mapped_unmapped() -> None:
    from stackr.migrate import migrate_from_deployrr

    catalog_apps = {"portainer", "jellyfin", "traefik"}
    app_names = ["portainer-ce", "jellyfin", "totally-unknown-app"]

    mapped, unmapped = migrate_from_deployrr(app_names, catalog_apps)

    mapped_names = {a["name"] for a in mapped}
    assert "portainer" in mapped_names
    assert "jellyfin" in mapped_names
    assert "totally-unknown-app" not in mapped_names
    assert "totally-unknown-app" in unmapped


def test_migrate_from_deployrr_deduplicates() -> None:
    from stackr.migrate import migrate_from_deployrr

    catalog_apps = {"portainer"}
    # Both names map to "portainer" — should only appear once
    app_names = ["portainer-ce", "portainer-ee"]

    mapped, unmapped = migrate_from_deployrr(app_names, catalog_apps)

    names = [a["name"] for a in mapped]
    assert names.count("portainer") == 1
    assert len(unmapped) == 0


def test_migrate_from_deployrr_all_mapped() -> None:
    from stackr.migrate import migrate_from_deployrr

    catalog_apps = {"traefik", "jellyfin", "sonarr"}
    mapped, unmapped = migrate_from_deployrr(["traefik", "jellyfin", "sonarr"], catalog_apps)

    assert len(mapped) == 3
    assert unmapped == []


def test_migrate_from_deployrr_empty_input() -> None:
    from stackr.migrate import migrate_from_deployrr

    mapped, unmapped = migrate_from_deployrr([], {"traefik"})
    assert mapped == []
    assert unmapped == []


def test_migrate_from_deployrr_sets_enabled_true() -> None:
    from stackr.migrate import migrate_from_deployrr

    catalog_apps = {"portainer"}
    mapped, _ = migrate_from_deployrr(["portainer"], catalog_apps)
    assert mapped[0]["enabled"] is True


# ---------------------------------------------------------------------------
# write_stackr_yml
# ---------------------------------------------------------------------------


def test_write_stackr_yml_is_valid_yaml(tmp_path: Path) -> None:
    from stackr.migrate import write_stackr_yml

    output = tmp_path / "stackr.yml"
    apps = [{"name": "traefik", "enabled": True}, {"name": "portainer", "enabled": True}]
    write_stackr_yml(output, apps)

    content = output.read_text()
    parsed = yaml.safe_load(content)
    assert isinstance(parsed, dict)


def test_write_stackr_yml_contains_all_apps(tmp_path: Path) -> None:
    from stackr.migrate import write_stackr_yml

    output = tmp_path / "stackr.yml"
    apps = [{"name": "traefik", "enabled": True}, {"name": "jellyfin", "enabled": True}]
    write_stackr_yml(output, apps)

    parsed = yaml.safe_load(output.read_text())
    app_names = [a["name"] for a in parsed["apps"]]
    assert "traefik" in app_names
    assert "jellyfin" in app_names


def test_write_stackr_yml_respects_kwargs(tmp_path: Path) -> None:
    from stackr.migrate import write_stackr_yml

    output = tmp_path / "stackr.yml"
    write_stackr_yml(output, [], timezone="Europe/Berlin", domain="mylab.example.com")

    parsed = yaml.safe_load(output.read_text())
    assert parsed["global"]["timezone"] == "Europe/Berlin"
    assert parsed["network"]["domain"] == "mylab.example.com"


def test_write_stackr_yml_empty_apps(tmp_path: Path) -> None:
    from stackr.migrate import write_stackr_yml

    output = tmp_path / "stackr.yml"
    write_stackr_yml(output, [])

    parsed = yaml.safe_load(output.read_text())
    assert parsed["apps"] == []
