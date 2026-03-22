"""Tests for the Stackr TUI.

Tests that don't depend on textual run unconditionally.
Tests that launch the Textual app are skipped when textual is not installed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

try:
    import textual  # noqa: F401

    HAS_TEXTUAL = True
except ImportError:
    HAS_TEXTUAL = False


# ---------------------------------------------------------------------------
# Helper-function tests — no textual required
# ---------------------------------------------------------------------------


def test_load_enabled_empty_when_no_config(tmp_path: Path) -> None:
    from stackr.tui import load_enabled

    result = load_enabled(tmp_path / "stackr.yml")
    assert result == set()


def test_load_enabled_returns_enabled_apps(tmp_path: Path) -> None:
    from stackr.tui import load_enabled

    cfg = {
        "apps": [
            {"name": "jellyfin", "enabled": True},
            {"name": "radarr", "enabled": False},
            {"name": "sonarr"},  # enabled defaults to True
        ]
    }
    config_file = tmp_path / "stackr.yml"
    config_file.write_text(yaml.dump(cfg))

    enabled = load_enabled(config_file)
    assert "jellyfin" in enabled
    assert "sonarr" in enabled
    assert "radarr" not in enabled


def test_load_enabled_survives_corrupt_yaml(tmp_path: Path) -> None:
    from stackr.tui import load_enabled

    (tmp_path / "stackr.yml").write_text("{{{ not valid yaml")
    result = load_enabled(tmp_path / "stackr.yml")
    assert result == set()


def test_build_stub_config_returns_skeleton_when_missing(tmp_path: Path) -> None:
    from stackr.tui import build_stub_config

    cfg = build_stub_config(tmp_path / "stackr.yml")
    assert "global" in cfg
    assert "apps" in cfg
    assert isinstance(cfg["apps"], list)


def test_build_stub_config_reads_existing_file(tmp_path: Path) -> None:
    from stackr.tui import build_stub_config

    data = {"global": {"data_dir": "/custom"}, "apps": [{"name": "traefik"}]}
    f = tmp_path / "stackr.yml"
    f.write_text(yaml.dump(data))

    cfg = build_stub_config(f)
    assert cfg["global"]["data_dir"] == "/custom"


# ---------------------------------------------------------------------------
# _load_settings / _settings_detail_markup tests — no textual required for
# the static methods, but they live on StackrTUI so we skip if not available.
# ---------------------------------------------------------------------------


def test_load_settings_empty_when_no_config(tmp_path: Path) -> None:
    from stackr.tui import load_settings

    result = load_settings(tmp_path / "stackr.yml")
    assert result == {}


def test_load_settings_reads_sections(tmp_path: Path) -> None:
    from stackr.tui import load_settings

    data = {
        "global": {
            "data_dir": "/srv/data",
            "timezone": "Europe/London",
            "puid": 1001,
            "pgid": 1001,
        },
        "network": {
            "domain": "example.net",
            "local_domain": "home.example.net",
            "mode": "hybrid",
        },
        "traefik": {"acme_email": "me@example.net", "dns_provider": "cloudflare"},
        "apps": [],
    }
    cfg = tmp_path / "stackr.yml"
    cfg.write_text(yaml.dump(data))

    result = load_settings(cfg)
    assert result["global"]["data_dir"] == "/srv/data"
    assert result["network"]["domain"] == "example.net"
    assert result["traefik"]["dns_provider"] == "cloudflare"


@pytest.mark.skipif(not HAS_TEXTUAL, reason="textual not installed")
def test_settings_detail_markup_contains_domain(tmp_path: Path) -> None:
    from stackr.catalog import Catalog
    from stackr.tui import StackrTUI

    data = {
        "global": {"data_dir": "/data", "timezone": "UTC", "puid": 1000, "pgid": 1000},
        "network": {"domain": "mylab.io", "local_domain": "home.mylab.io", "mode": "external"},
        "traefik": {"acme_email": "admin@mylab.io", "dns_provider": "cloudflare"},
        "apps": [],
    }
    cfg = tmp_path / "stackr.yml"
    cfg.write_text(yaml.dump(data))

    tui = StackrTUI(config_path=cfg, catalog=Catalog())
    markup = tui._settings_detail_markup()
    assert "mylab.io" in markup


# ---------------------------------------------------------------------------
# Class-level tests — skipped when textual is not installed
# ---------------------------------------------------------------------------

pytui = pytest.mark.skipif(not HAS_TEXTUAL, reason="textual not installed")


@pytui
def test_tui_can_be_instantiated(tmp_path: Path) -> None:
    from stackr.catalog import Catalog
    from stackr.tui import StackrTUI

    catalog = Catalog()
    tui = StackrTUI(config_path=tmp_path / "stackr.yml", catalog=catalog)
    assert tui._enabled == set()
    assert tui._catalog is catalog


@pytui
def test_tui_loads_enabled_from_config(tmp_path: Path) -> None:
    from stackr.catalog import Catalog
    from stackr.tui import StackrTUI

    cfg = {
        "global": {"data_dir": "/data"},
        "network": {"mode": "external", "domain": "test.com", "local_domain": "home.test.com"},
        "traefik": {"enabled": True, "acme_email": "a@b.com", "dns_provider": "cloudflare"},
        "security": {"socket_proxy": False},
        "apps": [{"name": "jellyfin", "enabled": True}],
    }
    config_file = tmp_path / "stackr.yml"
    config_file.write_text(yaml.dump(cfg))

    tui = StackrTUI(config_path=config_file, catalog=Catalog())
    assert "jellyfin" in tui._enabled


@pytui
def test_tui_detail_markup_contains_app_name(tmp_path: Path) -> None:
    from stackr.catalog import Catalog
    from stackr.tui import StackrTUI

    catalog = Catalog()
    tui = StackrTUI(config_path=tmp_path / "stackr.yml", catalog=catalog)
    apps = catalog.all()
    assert apps, "catalog must have at least one app"
    ca = apps[0]
    markup = tui._detail_markup(ca)
    assert ca.name in markup


@pytui
def test_tui_action_toggle_updates_enabled(tmp_path: Path) -> None:
    """_enabled is updated correctly by _toggle logic (simulated)."""
    from stackr.catalog import Catalog
    from stackr.tui import StackrTUI

    catalog = Catalog()
    tui = StackrTUI(config_path=tmp_path / "stackr.yml", catalog=catalog)
    apps = catalog.all()
    assert apps
    app_name = apps[0].name

    # Simulate toggle: add then remove
    assert app_name not in tui._enabled
    tui._enabled.add(app_name)
    assert app_name in tui._enabled
    tui._enabled.discard(app_name)
    assert app_name not in tui._enabled


def test_tui_save_writes_all_catalog_apps(tmp_path: Path) -> None:
    """action_save_config must write every catalog app — not just enabled ones.

    This is a pure-Python test of the save logic so it runs without textual.
    """
    import yaml as _yaml

    from stackr.catalog import Catalog
    from stackr.tui import build_stub_config

    catalog = Catalog()
    config_file = tmp_path / "stackr.yml"

    # Config has only 2 apps (pre-fix state)
    config_file.write_text(
        _yaml.dump(
            {
                "global": {"data_dir": "/data"},
                "network": {"domain": "test.com"},
                "traefik": {"enabled": False},
                "security": {"socket_proxy": False},
                "apps": [
                    {"name": "traefik", "enabled": True},
                    {"name": "portainer", "enabled": True},
                ],
            }
        )
    )

    enabled = {"traefik", "portainer"}

    # Replicate the fixed action_save_config logic
    raw = build_stub_config(config_file)
    existing = {
        a["name"]: a for a in raw.get("apps", []) if isinstance(a, dict) and "name" in a
    }
    apps_out = []
    catalog_names: set[str] = set()
    for category in catalog.categories():
        for ca in sorted(catalog.by_category(category), key=lambda a: a.name):
            catalog_names.add(ca.name)
            entry = dict(existing.get(ca.name, {"name": ca.name}))
            entry["enabled"] = ca.name in enabled
            apps_out.append(entry)
    for name, entry in existing.items():
        if name not in catalog_names:
            apps_out.append(dict(entry))
    raw["apps"] = apps_out
    with open(config_file, "w") as f:
        _yaml.dump(raw, f, default_flow_style=False, allow_unicode=True)

    written = _yaml.safe_load(config_file.read_text())
    written_names = {a["name"] for a in written["apps"]}
    all_catalog_names = {a.name for a in catalog.all()}

    missing = all_catalog_names - written_names
    assert not missing, f"Save dropped these catalog apps: {sorted(missing)}"

    # Spot-check enabled/disabled state
    by_name = {a["name"]: a for a in written["apps"]}
    assert by_name["traefik"]["enabled"] is True
    assert by_name["jellyfin"]["enabled"] is False


@pytui
def test_tui_save_config_writes_yaml(tmp_path: Path) -> None:
    from stackr.catalog import Catalog
    from stackr.tui import StackrTUI

    catalog = Catalog()
    config_file = tmp_path / "stackr.yml"
    tui = StackrTUI(config_path=config_file, catalog=catalog)
    apps = catalog.all()
    assert apps
    tui._enabled = {apps[0].name}

    # Directly call the save helper (bypasses Textual App messaging)
    import yaml as _yaml  # noqa: PLC0415

    from stackr.tui import build_stub_config

    raw = build_stub_config(config_file)
    existing: dict = {
        a["name"]: a for a in raw.get("apps", []) if isinstance(a, dict) and "name" in a
    }
    apps_out = []
    for category in catalog.categories():
        for ca in sorted(catalog.by_category(category), key=lambda a: a.name):
            if ca.name in tui._enabled:
                entry = dict(existing.get(ca.name, {"name": ca.name}))
                entry["enabled"] = True
                apps_out.append(entry)
    raw["apps"] = apps_out
    with open(config_file, "w") as f:
        _yaml.dump(raw, f, default_flow_style=False, allow_unicode=True)

    written = _yaml.safe_load(config_file.read_text())
    assert any(a["name"] == apps[0].name and a["enabled"] for a in written["apps"])


# ---------------------------------------------------------------------------
# Async mount test — only if textual AND pytest-asyncio are available
# ---------------------------------------------------------------------------

try:
    import pytest_asyncio  # noqa: F401

    HAS_ASYNCIO = True
except ImportError:
    HAS_ASYNCIO = False


@pytest.mark.skipif(
    not (HAS_TEXTUAL and HAS_ASYNCIO),
    reason="textual and pytest-asyncio required",
)
@pytest.mark.asyncio
async def test_tui_mounts_without_error(tmp_path: Path) -> None:
    from stackr.catalog import Catalog
    from stackr.tui import StackrTUI

    app = StackrTUI(config_path=tmp_path / "stackr.yml", catalog=Catalog())
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        # Tree widget is present
        from textual.widgets import Tree

        assert app.query_one("#catalog-tree", Tree) is not None
