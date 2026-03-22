"""Tests for catalog loading."""



from stackr.catalog import Catalog


def test_builtin_catalog_loads():
    catalog = Catalog()
    apps = catalog.all()
    assert len(apps) >= 10, "Expected at least 10 seed apps"


def test_seed_apps_present():
    catalog = Catalog()
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
        # Gluetun VPN gateway
        "gluetun",
        # Phase 3 — productivity
        "gitea", "paperless-ngx", "freshrss", "miniflux",
        # Phase 3 — gaming
        "minecraft",
    ]
    missing = [name for name in seed_apps if catalog.get(name) is None]
    assert missing == [], f"Missing seed apps: {missing}"


def test_traefik_host_ports():
    catalog = Catalog()
    traefik = catalog.get("traefik")
    assert 80 in traefik.host_ports
    assert 443 in traefik.host_ports


def test_adguardhome_host_ports():
    catalog = Catalog()
    adguardhome = catalog.get("adguardhome")
    assert 53 in adguardhome.host_ports
    # Traefik target port is 3000, not 53
    assert 3000 in adguardhome.ports
    assert 53 not in adguardhome.ports


def test_database_apps_have_no_host_ports():
    catalog = Catalog()
    for name in ("postgres", "mariadb", "redis", "mongo"):
        app = catalog.get(name)
        assert app is not None
        assert app.host_ports == [], f"{name} should not have host_ports"


def test_wireguard_host_ports():
    catalog = Catalog()
    wireguard = catalog.get("wireguard")
    assert 51820 in wireguard.host_ports


def test_qbittorrent_host_ports():
    catalog = Catalog()
    qbt = catalog.get("qbittorrent")
    assert 6881 in qbt.host_ports


def test_all_apps_have_compose_templates():
    catalog = Catalog()
    missing = [a.name for a in catalog.all() if not a.has_compose_template()]
    assert missing == [], f"Apps missing compose templates: {missing}"


def test_catalog_search():
    catalog = Catalog()
    results = catalog.search("media")
    names = [a.name for a in results]
    assert any(n in names for n in ("jellyfin", "radarr", "sonarr"))


def test_catalog_by_category():
    catalog = Catalog()
    media_apps = catalog.by_category("media")
    assert len(media_apps) > 0
    assert all(a.category == "media" for a in media_apps)


def test_catalog_categories():
    catalog = Catalog()
    cats = catalog.categories()
    assert "media" in cats
    assert "network" in cats
    assert "security" in cats


def test_app_metadata_complete():
    catalog = Catalog()
    for app in catalog.all():
        assert app.name, "App has no name"
        assert app.category, f"{app.name} has no category"
        assert app.description, f"{app.name} has no description"


def test_jellyfin_vars():
    catalog = Catalog()
    jellyfin = catalog.get("jellyfin")
    assert jellyfin is not None
    assert "hardware_accel" in jellyfin.vars
    var = jellyfin.vars["hardware_accel"]
    assert "vaapi" in var.options
    assert var.default == "none"


def test_jellyfin_ports():
    catalog = Catalog()
    jellyfin = catalog.get("jellyfin")
    assert 8096 in jellyfin.ports


def test_traefik_requires_nothing():
    catalog = Catalog()
    traefik = catalog.get("traefik")
    assert traefik.requires == []


def test_portainer_suggests_traefik():
    """traefik is a soft dependency (suggests) for portainer, not a hard one."""
    catalog = Catalog()
    portainer = catalog.get("portainer")
    assert "traefik" not in portainer.requires
    assert "traefik" in portainer.suggests
