"""Mounts routes: list, add, delete."""
from __future__ import annotations

import os
import tempfile
from typing import Any

import fastapi
import yaml

from stackr.api.deps import CONFIG_WRITE_LOCK, Config, ConfigPath
from stackr.api.models import MountCreate, MountOut

router = fastapi.APIRouter(prefix="/mounts", tags=["mounts"])


def _mount_to_out(m: Any) -> MountOut:
    return MountOut(
        name=m.name,
        type=m.type,
        remote=m.remote,
        mountpoint=str(m.mountpoint),
        options=m.options,
        username=m.username,
    )


def _write_raw(config_path: Any, raw: dict[str, Any]) -> None:
    fd, tmp = tempfile.mkstemp(dir=config_path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            yaml.safe_dump(raw, f, default_flow_style=False, sort_keys=False)
        os.replace(tmp, config_path)
    except Exception:
        os.unlink(tmp)
        raise


@router.get("/", response_model=list[MountOut])
def list_mounts(config: Config) -> list[MountOut]:
    return [_mount_to_out(m) for m in config.mounts]


@router.post("/", response_model=list[MountOut], status_code=201)
def add_mount(body: MountCreate, config_path: ConfigPath) -> list[MountOut]:
    with CONFIG_WRITE_LOCK:
        raw: dict[str, Any] = yaml.safe_load(config_path.read_text()) or {}
        mounts: list[dict[str, Any]] = raw.setdefault("mounts", [])
        existing = next((i for i, m in enumerate(mounts) if m.get("name") == body.name), None)
        entry: dict[str, Any] = {
            "name": body.name,
            "type": body.type,
            "remote": body.remote,
            "mountpoint": body.mountpoint,
            "options": body.options,
        }
        if body.username is not None:
            entry["username"] = body.username
        if existing is not None:
            mounts[existing] = entry
        else:
            mounts.append(entry)
        _write_raw(config_path, raw)

    from stackr.engine.config import load_config

    updated = load_config(config_path)
    return [_mount_to_out(m) for m in updated.mounts]


@router.delete("/{name}", response_model=list[MountOut])
def delete_mount(name: str, config_path: ConfigPath) -> list[MountOut]:
    with CONFIG_WRITE_LOCK:
        raw: dict[str, Any] = yaml.safe_load(config_path.read_text()) or {}
        mounts: list[dict[str, Any]] = raw.get("mounts", [])
        before = len(mounts)
        raw["mounts"] = [m for m in mounts if m.get("name") != name]
        if len(raw["mounts"]) == before:
            raise fastapi.HTTPException(status_code=404, detail=f"Mount '{name}' not found")
        _write_raw(config_path, raw)

    from stackr.engine.config import load_config

    updated = load_config(config_path)
    return [_mount_to_out(m) for m in updated.mounts]
