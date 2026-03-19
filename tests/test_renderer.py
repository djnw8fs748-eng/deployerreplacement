"""Tests for Jinja2 compose file rendering."""

import yaml

from stackr.catalog import Catalog
from stackr.config import AppConfig, StackrConfig
from stackr.renderer import _deep_merge, render_app


def _make_config(**kwargs) -> StackrConfig:
    base = {
        "global": {"data_dir": "/opt/appdata", "timezone": "UTC", "puid": 1000, "pgid": 1000},
        "network": {"mode": "external", "domain": "test.com", "local_domain": "home.test.com"},
        "traefik": {"enabled": True, "acme_email": "test@test.com", "dns_provider": "cloudflare"},
        "security": {"socket_proxy": True},
    }
    base.update(kwargs)
    return StackrConfig.model_validate(base)


def test_render_jellyfin_default():
    catalog = Catalog()
    config = _make_config()
    app_config = AppConfig(name="jellyfin")
    catalog_app = catalog.get("jellyfin")
    rendered = render_app(app_config, catalog_app, config)
    parsed = yaml.safe_load(rendered)
    assert "services" in parsed
    assert "jellyfin" in parsed["services"]
    svc = parsed["services"]["jellyfin"]
    assert "image" in svc
    assert "jellyfin/jellyfin" in svc["image"]


def test_render_jellyfin_vaapi():
    catalog = Catalog()
    config = _make_config()
    app_config = AppConfig(name="jellyfin", vars={"hardware_accel": "vaapi"})
    catalog_app = catalog.get("jellyfin")
    rendered = render_app(app_config, catalog_app, config)
    assert "/dev/dri" in rendered


def test_render_jellyfin_no_gpu_by_default():
    catalog = Catalog()
    config = _make_config()
    app_config = AppConfig(name="jellyfin")
    catalog_app = catalog.get("jellyfin")
    rendered = render_app(app_config, catalog_app, config)
    assert "/dev/dri" not in rendered


def test_render_traefik_labels_present():
    catalog = Catalog()
    config = _make_config()
    app_config = AppConfig(name="jellyfin")
    catalog_app = catalog.get("jellyfin")
    rendered = render_app(app_config, catalog_app, config)
    assert "traefik.enable" in rendered
    assert "jellyfin.test.com" in rendered


def test_render_traefik_external_mode():
    catalog = Catalog()
    config = _make_config(
        network={"mode": "external", "domain": "mylab.io", "local_domain": "home.mylab.io"},
    )
    app_config = AppConfig(name="jellyfin")
    catalog_app = catalog.get("jellyfin")
    rendered = render_app(app_config, catalog_app, config)
    assert "jellyfin.mylab.io" in rendered


def test_render_vaultwarden():
    catalog = Catalog()
    config = _make_config()
    app_config = AppConfig(name="vaultwarden")
    catalog_app = catalog.get("vaultwarden")
    rendered = render_app(app_config, catalog_app, config)
    parsed = yaml.safe_load(rendered)
    assert "vaultwarden" in parsed["services"]


def test_render_with_overrides():
    catalog = Catalog()
    config = _make_config()
    app_config = AppConfig(
        name="jellyfin",
        overrides={"services": {"jellyfin": {"mem_limit": "4g"}}}
    )
    catalog_app = catalog.get("jellyfin")
    rendered = render_app(app_config, catalog_app, config)
    parsed = yaml.safe_load(rendered)
    assert parsed["services"]["jellyfin"]["mem_limit"] == "4g"


def test_render_all_seed_apps():
    """Smoke test: every seed app must render without error."""
    catalog = Catalog()
    config = _make_config()
    seed_apps = [
        # Phase 1 original apps
        "traefik", "portainer", "jellyfin", "radarr", "sonarr",
        "prowlarr", "homepage", "uptime-kuma", "adguardhome", "vaultwarden",
        "socket-proxy",
        # Phase 3 — database
        "postgres", "mariadb", "redis", "mongo",
        # Phase 3 — AI
        "ollama", "open-webui",
        # Phase 3 — monitoring
        "grafana", "prometheus", "loki", "netdata",
        # Phase 3 — media
        "plex", "bazarr", "lidarr", "readarr", "overseerr", "jellyseerr",
        "tdarr", "sabnzbd", "qbittorrent", "transmission",
        # Phase 3 — management
        "dozzle", "watchtower", "heimdall", "dasherr", "flame",
        # Phase 3 — storage
        "nextcloud", "filebrowser", "duplicati",
        # Phase 3 — network
        "pihole", "wireguard", "headscale", "nginx-proxy-manager",
        # Phase 3 — productivity
        "gitea", "paperless-ngx", "freshrss", "miniflux",
        # Phase 3 — gaming
        "minecraft",
    ]
    for name in seed_apps:
        catalog_app = catalog.get(name)
        assert catalog_app is not None, f"Missing catalog entry: {name}"
        app_config = AppConfig(name=name)
        rendered = render_app(app_config, catalog_app, config)
        assert rendered.strip(), f"Empty render for {name}"
        parsed = yaml.safe_load(rendered)
        assert "services" in parsed, f"No 'services' key in {name} compose"


def test_render_watchtower_no_proxy_network():
    """Watchtower has no web UI — it must not have a proxy network."""
    catalog = Catalog()
    config = _make_config()
    app_config = AppConfig(name="watchtower")
    catalog_app = catalog.get("watchtower")
    rendered = render_app(app_config, catalog_app, config)
    parsed = yaml.safe_load(rendered)
    svc = parsed["services"]["watchtower"]
    networks = svc.get("networks", [])
    # Should only be on socket_proxy when socket_proxy=True, never on proxy
    assert "proxy" not in networks


def test_render_tdarr_has_node_service():
    """Tdarr compose must include both tdarr and tdarr-node services."""
    catalog = Catalog()
    config = _make_config()
    app_config = AppConfig(name="tdarr")
    catalog_app = catalog.get("tdarr")
    rendered = render_app(app_config, catalog_app, config)
    parsed = yaml.safe_load(rendered)
    assert "tdarr" in parsed["services"]
    assert "tdarr-node" in parsed["services"]


def test_render_ollama_nvidia():
    """Ollama with nvidia GPU should include deploy.resources block."""
    catalog = Catalog()
    config = _make_config()
    app_config = AppConfig(name="ollama", vars={"gpu_type": "nvidia"})
    catalog_app = catalog.get("ollama")
    rendered = render_app(app_config, catalog_app, config)
    assert "nvidia" in rendered
    assert "capabilities" in rendered


def test_render_nextcloud_has_db_sidecar():
    """Nextcloud compose must include its MariaDB and Redis sidecars."""
    catalog = Catalog()
    config = _make_config()
    app_config = AppConfig(name="nextcloud")
    catalog_app = catalog.get("nextcloud")
    rendered = render_app(app_config, catalog_app, config)
    parsed = yaml.safe_load(rendered)
    assert "nextcloud" in parsed["services"]
    assert "nextcloud-db" in parsed["services"]
    assert "nextcloud-redis" in parsed["services"]


def test_render_miniflux_has_db_sidecar():
    """Miniflux compose must include its Postgres sidecar."""
    catalog = Catalog()
    config = _make_config()
    app_config = AppConfig(name="miniflux")
    catalog_app = catalog.get("miniflux")
    rendered = render_app(app_config, catalog_app, config)
    parsed = yaml.safe_load(rendered)
    assert "miniflux" in parsed["services"]
    assert "miniflux-db" in parsed["services"]


def test_render_wireguard_no_proxy_network():
    """Wireguard is a VPN tunnel — it has no proxy network or Traefik labels."""
    catalog = Catalog()
    config = _make_config()
    app_config = AppConfig(name="wireguard")
    catalog_app = catalog.get("wireguard")
    rendered = render_app(app_config, catalog_app, config)
    assert "traefik.enable" not in rendered
    parsed = yaml.safe_load(rendered)
    assert "networks" not in parsed.get("services", {}).get("wireguard", {})


def test_deep_merge():
    base = {"a": 1, "b": {"c": 2, "d": 3}}
    override = {"b": {"c": 99, "e": 4}, "f": 5}
    result = _deep_merge(base, override)
    assert result == {"a": 1, "b": {"c": 99, "d": 3, "e": 4}, "f": 5}
