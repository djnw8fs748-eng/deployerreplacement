"""Tests for Jinja2 compose file rendering."""

import yaml

from stackr.catalog import Catalog
from stackr.config import AppConfig, StackrConfig
from stackr.renderer import _deep_merge, render_app


def _make_config(**kwargs) -> StackrConfig:
    base = {
        "global": {"data_dir": "/opt/appdata", "timezone": "UTC", "puid": 1000, "pgid": 1000},
        "network": {"domain": "test.com", "local_domain": "home.test.com"},
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


def test_render_traefik_labels_absent():
    """Traefik removed — traefik labels must never appear in rendered output."""
    catalog = Catalog()
    config = _make_config()
    app_config = AppConfig(name="jellyfin")
    catalog_app = catalog.get("jellyfin")
    rendered = render_app(app_config, catalog_app, config)
    assert "traefik.enable" not in rendered


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
        # network
        "nginx-proxy-manager", "adguardhome", "pihole", "wireguard", "headscale",
        # ai
        "ollama", "open-webui",
        # media
        "plex", "jellyfin", "sonarr", "radarr", "lidarr", "readarr", "prowlarr",
        "bazarr", "qbittorrent", "tdarr", "seerr",
        # management
        "homepage", "flame", "heimdall", "dozzle", "portainer", "watchtower",
        # monitoring
        "uptime-kuma", "grafana", "prometheus", "loki", "netdata",
        # security
        "vaultwarden", "socket-proxy", "crowdsec", "pocket-id", "tinyauth",
        # database
        "postgres", "mariadb", "redis", "mongo",
        # gaming
        "minecraft",
        # storage
        "filebrowser", "duplicati",
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


def test_render_seerr():
    config = _make_config()
    app = Catalog().get("seerr")
    assert app is not None
    rendered = render_app(AppConfig(name="seerr"), app, config)
    parsed = yaml.safe_load(rendered)
    assert "seerr" in parsed["services"]
    assert "seerr/seerr" in parsed["services"]["seerr"]["image"]
    assert parsed["networks"]["proxy"]["external"] is True


def test_render_pocket_id():
    config = _make_config()
    app = Catalog().get("pocket-id")
    assert app is not None
    rendered = render_app(AppConfig(name="pocket-id"), app, config)
    parsed = yaml.safe_load(rendered)
    assert "pocket-id" in parsed["services"]
    assert "pocket-id/pocket-id" in parsed["services"]["pocket-id"]["image"]
    env = parsed["services"]["pocket-id"]["environment"]
    assert any("APP_URL" in e for e in env)
    assert any("ENCRYPTION_KEY" in e for e in env)


def test_render_tinyauth():
    config = _make_config()
    app = Catalog().get("tinyauth")
    assert app is not None
    rendered = render_app(AppConfig(name="tinyauth"), app, config)
    parsed = yaml.safe_load(rendered)
    assert "tinyauth" in parsed["services"]
    assert "steveiliop56/tinyauth" in parsed["services"]["tinyauth"]["image"]
    env = parsed["services"]["tinyauth"]["environment"]
    assert any("TINYAUTH_APPURL" in e for e in env)
    assert any("pocketid_CLIENTID" in e for e in env)


def test_no_traefik_in_render_context():
    """traefik and traefik_labels must not be injected into template context."""
    config = StackrConfig.model_validate({
        "global": {"data_dir": "/data", "timezone": "UTC", "puid": 1000, "pgid": 1000},
        "network": {"domain": "test.com", "local_domain": "home.test.com"},
        "security": {"socket_proxy": False},
    })
    app = Catalog().get("seerr")
    rendered = render_app(AppConfig(name="seerr"), app, config)
    assert "traefik.enable" not in rendered
    assert "traefik.http" not in rendered


def test_deep_merge():
    base = {"a": 1, "b": {"c": 2, "d": 3}}
    override = {"b": {"c": 99, "e": 4}, "f": 5}
    result = _deep_merge(base, override)
    assert result == {"a": 1, "b": {"c": 99, "d": 3, "e": 4}, "f": 5}
