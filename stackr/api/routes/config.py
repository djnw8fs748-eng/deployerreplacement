"""Config routes: read and update config sections."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import fastapi
import yaml

from stackr.api.deps import CONFIG_WRITE_LOCK, Config, ConfigPath
from stackr.api.models import AlertUpdate, BackupUpdate, GlobalUpdate, NetworkUpdate, SecurityUpdate

router = fastapi.APIRouter(prefix="/config", tags=["config"])


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
        os.replace(tmp, path)
    except Exception:
        os.unlink(tmp)
        raise


def _patch_section(config_path: Path, section: str, updates: dict[str, Any]) -> dict[str, Any]:
    with CONFIG_WRITE_LOCK:
        raw: dict[str, Any] = yaml.safe_load(config_path.read_text()) or {}
        raw.setdefault(section, {})
        for k, v in updates.items():
            if v is not None:
                raw[section][k] = v
        _atomic_write(config_path, raw)
        return raw


@router.get("/", response_model=dict)
def get_config(config: Config) -> dict[str, Any]:
    return config.model_dump(by_alias=True)


@router.put("/global", response_model=dict)
def update_global(body: GlobalUpdate, config_path: ConfigPath) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if body.data_dir is not None:
        updates["data_dir"] = body.data_dir
    if body.timezone is not None:
        updates["timezone"] = body.timezone
    if body.puid is not None:
        updates["puid"] = body.puid
    if body.pgid is not None:
        updates["pgid"] = body.pgid
    return _patch_section(config_path, "global", updates)


@router.put("/network", response_model=dict)
def update_network(body: NetworkUpdate, config_path: ConfigPath) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if body.domain is not None:
        updates["domain"] = body.domain
    if body.local_domain is not None:
        updates["local_domain"] = body.local_domain
    return _patch_section(config_path, "network", updates)


@router.put("/security", response_model=dict)
def update_security(body: SecurityUpdate, config_path: ConfigPath) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if body.socket_proxy is not None:
        updates["socket_proxy"] = body.socket_proxy
    if body.crowdsec is not None:
        updates["crowdsec"] = body.crowdsec
    return _patch_section(config_path, "security", updates)


@router.put("/backup", response_model=dict)
def update_backup(body: BackupUpdate, config_path: ConfigPath) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if body.enabled is not None:
        updates["enabled"] = body.enabled
    if body.destination is not None:
        updates["destination"] = body.destination
    if body.schedule is not None:
        updates["schedule"] = body.schedule
    return _patch_section(config_path, "backup", updates)


@router.put("/alerts", response_model=dict)
def update_alerts(body: AlertUpdate, config_path: ConfigPath) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if body.enabled is not None:
        updates["enabled"] = body.enabled
    if body.provider is not None:
        updates["provider"] = body.provider
    if body.url is not None:
        updates["url"] = body.url
    if body.token is not None:
        updates["token"] = body.token
    return _patch_section(config_path, "alerts", updates)
