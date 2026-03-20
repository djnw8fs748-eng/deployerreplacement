"""Pydantic models for stackr.yml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class GlobalConfig(BaseModel):
    data_dir: Path = Path("/opt/appdata")
    timezone: str = "UTC"
    puid: int = 1000
    pgid: int = 1000


class CatalogConfig(BaseModel):
    source: str = "github"  # github | local
    version: str = "latest"
    local_path: Path | None = None

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        if v not in ("github", "local"):
            raise ValueError("catalog.source must be 'github' or 'local'")
        return v


class NetworkConfig(BaseModel):
    mode: str = "external"  # external | internal | hybrid
    domain: str = "example.com"
    local_domain: str = "home.example.com"

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in ("external", "internal", "hybrid"):
            raise ValueError("network.mode must be 'external', 'internal', or 'hybrid'")
        return v


class TraefikConfig(BaseModel):
    enabled: bool = True
    acme_email: str = ""
    dns_provider: str = "cloudflare"
    dns_provider_env: dict[str, str] = Field(default_factory=dict)


class SecurityConfig(BaseModel):
    socket_proxy: bool = True
    crowdsec: bool = False
    auth_provider: str = "none"  # authentik | authelia | google_oauth | none | <app-name>


class BackupConfig(BaseModel):
    enabled: bool = False
    destination: Path = Path("/mnt/backup")
    schedule: str = "0 2 * * *"


class AlertConfig(BaseModel):
    enabled: bool = False
    provider: str = "ntfy"  # ntfy | gotify | webhook
    url: str = ""
    token: str | None = None

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        if v not in ("ntfy", "gotify", "webhook"):
            raise ValueError("alerts.provider must be 'ntfy', 'gotify', or 'webhook'")
        return v


class AppConfig(BaseModel):
    name: str
    enabled: bool = True
    vars: dict[str, Any] = Field(default_factory=dict)
    overrides: dict[str, Any] = Field(default_factory=dict)
    catalog_path: Path | None = None  # local override for this app's catalog entry


class StackrConfig(BaseModel):
    global_: GlobalConfig = Field(default_factory=GlobalConfig, alias="global")
    catalog: CatalogConfig = Field(default_factory=CatalogConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    traefik: TraefikConfig = Field(default_factory=TraefikConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    backup: BackupConfig = Field(default_factory=BackupConfig)
    alerts: AlertConfig = Field(default_factory=AlertConfig)
    apps: list[AppConfig] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def inject_core_apps(self) -> StackrConfig:
        """Ensure socket-proxy and traefik are prepended in the correct deploy order.

        socket-proxy must come before traefik so the socket_proxy network exists
        when traefik starts and tries to connect to socket-proxy:2375.
        """
        names = {a.name for a in self.apps}
        # Insert in reverse deploy order (each insert goes to front):
        # traefik first so socket-proxy ends up before it after both inserts.
        if self.traefik.enabled and "traefik" not in names:
            self.apps.insert(0, AppConfig(name="traefik"))
        if self.traefik.enabled and self.security.socket_proxy and "socket-proxy" not in names:
            self.apps.insert(0, AppConfig(name="socket-proxy"))
        return self

    @property
    def enabled_apps(self) -> list[AppConfig]:
        return [a for a in self.apps if a.enabled]


def load_config(path: Path) -> StackrConfig:
    with open(path) as f:
        raw = yaml.safe_load(f)
    return StackrConfig.model_validate(raw)
