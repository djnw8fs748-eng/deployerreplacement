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
    domain: str = "example.com"
    local_domain: str = "home.example.com"


class SecurityConfig(BaseModel):
    socket_proxy: bool = True
    crowdsec: bool = False


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


class MountConfig(BaseModel):
    name: str
    type: str = "smb"  # smb | nfs | rclone
    remote: str
    mountpoint: Path
    options: str = ""
    username: str | None = None
    password: str | None = None  # resolved from env at mount time

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in ("smb", "nfs", "rclone"):
            raise ValueError("mount type must be 'smb', 'nfs', or 'rclone'")
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
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    backup: BackupConfig = Field(default_factory=BackupConfig)
    alerts: AlertConfig = Field(default_factory=AlertConfig)
    mounts: list[MountConfig] = Field(default_factory=list)
    apps: list[AppConfig] = Field(default_factory=list)

    @field_validator("apps", "mounts", mode="before")
    @classmethod
    def coerce_none_to_list(cls, v: object) -> object:
        # PyYAML parses an empty key (e.g. `apps:` with no value) as None.
        # Pydantic's default_factory only fires when the key is absent, not when
        # it is explicitly None, so we coerce None → [] here.
        return v if v is not None else []

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def inject_core_apps(self) -> StackrConfig:
        """Ensure nginx-proxy-manager is prepended as the default reverse proxy."""
        names = {a.name for a in self.apps}
        if "nginx-proxy-manager" not in names:
            self.apps.insert(0, AppConfig(name="nginx-proxy-manager"))
        return self

    @property
    def enabled_apps(self) -> list[AppConfig]:
        return [a for a in self.apps if a.enabled]


def load_config(path: Path) -> StackrConfig:
    with open(path) as f:
        raw = yaml.safe_load(f)
    return StackrConfig.model_validate(raw)
