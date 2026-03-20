"""Deployrr → Stackr migration helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# Canonical name mapping: Deployrr app name → Stackr catalog name
_DEPLOYRR_MAP: dict[str, str] = {
    "portainer-ce": "portainer",
    "portainer-ee": "portainer",
    "adguard-home": "adguardhome",
    "bitwarden": "vaultwarden",
    "bitwarden-rs": "vaultwarden",
    "plex-media-server": "plex",
    "transmission-vpn": "transmission",
    "qbittorrent-vpn": "qbittorrent",
    "wireguard-easy": "wireguard",
    "grafana-oss": "grafana",
    "uptimekuma": "uptime-kuma",
    "uptime-kuma": "uptime-kuma",
    "paperless": "paperless-ngx",
    "miniflux-v2": "miniflux",
    "nextcloud-aio": "nextcloud",
    "traefik-v2": "traefik",
    "heimdall": "heimdall",
    "organizr-v2": "organizr",
    "organizr": "organizr",
    "jellyfin": "jellyfin",
    "emby": "emby",
    "sonarr": "sonarr",
    "radarr": "radarr",
    "prowlarr": "prowlarr",
    "lidarr": "lidarr",
    "readarr": "readarr",
    "bazarr": "bazarr",
    "overseerr": "overseerr",
    "requestrr": "requestrr",
    "sabnzbd": "sabnzbd",
    "nzbget": "nzbget",
    "deluge": "deluge",
    "rutorrent": "rutorrent",
    "jackett": "jackett",
    "flaresolverr": "flaresolverr",
    "tautulli": "tautulli",
    "ombi": "ombi",
    "duplicati": "duplicati",
    "vaultwarden": "vaultwarden",
    "mealie": "mealie",
    "grocy": "grocy",
    "filebrowser": "filebrowser",
    "nginx-proxy-manager": "nginx-proxy-manager",
    "whoami": "whoami",
    "watchtower": "watchtower",
    "prometheus": "prometheus",
    "grafana": "grafana",
}

# Suffixes to strip when no direct map hit is found
_STRIP_SUFFIXES = ("-ce", "-ee", "-vpn", "-media", "-v2", "-oss", "-aio")


def map_app_name(deployrr_name: str) -> str:
    """Map one Deployrr app name to a Stackr catalog name.

    Priority: direct map → suffix-strip → passthrough.
    """
    normalized = deployrr_name.lower().strip()

    # Direct hit
    if normalized in _DEPLOYRR_MAP:
        return _DEPLOYRR_MAP[normalized]

    # Strip known suffixes and try again
    for suffix in _STRIP_SUFFIXES:
        if normalized.endswith(suffix):
            stripped = normalized[: -len(suffix)]
            if stripped in _DEPLOYRR_MAP:
                return _DEPLOYRR_MAP[stripped]
            return stripped

    return normalized


def migrate_from_deployrr(
    app_names: list[str],
    catalog_apps: set[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Return (mapped_app_dicts, unmapped_names).

    mapped_app_dicts: list of app entries suitable for stackr.yml, deduplicated.
    unmapped_names: input names whose mapped result is not in the catalog.
    """
    mapped: list[dict[str, Any]] = []
    unmapped: list[str] = []
    seen: set[str] = set()

    for raw_name in app_names:
        raw_name = raw_name.strip()
        if not raw_name:
            continue
        stackr_name = map_app_name(raw_name)
        if stackr_name in seen:
            continue
        seen.add(stackr_name)
        if stackr_name in catalog_apps:
            mapped.append({"name": stackr_name, "enabled": True})
        else:
            unmapped.append(raw_name)

    return mapped, unmapped


def write_stackr_yml(
    output_path: Path,
    apps: list[dict[str, Any]],
    *,
    data_dir: str = "/opt/appdata",
    timezone: str = "UTC",
    domain: str = "example.com",
    dns_provider: str = "cloudflare",
) -> None:
    """Emit a minimal stackr.yml skeleton with the given apps."""
    config: dict[str, Any] = {
        "global": {
            "data_dir": data_dir,
            "timezone": timezone,
            "puid": 1000,
            "pgid": 1000,
        },
        "network": {
            "mode": "external",
            "domain": domain,
            "local_domain": f"home.{domain}",
        },
        "traefik": {
            "enabled": True,
            "acme_email": "",
            "dns_provider": dns_provider,
            "dns_provider_env": {
                "CF_DNS_API_TOKEN": "${CF_DNS_API_TOKEN}",
            },
        },
        "security": {
            "socket_proxy": True,
            "crowdsec": False,
            "auth_provider": "none",
        },
        "backup": {
            "enabled": False,
            "destination": "/mnt/backup",
            "schedule": "0 2 * * *",
        },
        "apps": apps,
    }
    with open(output_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
