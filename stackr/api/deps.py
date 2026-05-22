"""FastAPI dependency providers for the Stackr API."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Annotated

import fastapi

from stackr.engine.catalog import Catalog
from stackr.engine.config import StackrConfig, load_config
from stackr.engine.secrets import build_env
from stackr.engine.state import DEFAULT_STATE_DIR, StateDB

# Shared lock protecting all writes to stackr.yml
CONFIG_WRITE_LOCK = threading.Lock()

_config_path: Path = Path("stackr.yml")


def set_config_path(path: Path) -> None:
    global _config_path
    _config_path = path


def get_config_path() -> Path:
    return _config_path


def get_db() -> StateDB:
    db = StateDB()
    db.migrate_from_json(DEFAULT_STATE_DIR / "state.json")
    return db


def get_catalog() -> Catalog:
    return Catalog()


def get_config() -> StackrConfig:
    return load_config(_config_path)


def get_env() -> dict[str, str]:
    return build_env(_config_path.parent)


ConfigPath = Annotated[Path, fastapi.Depends(get_config_path)]
DB = Annotated[StateDB, fastapi.Depends(get_db)]
Cat = Annotated[Catalog, fastapi.Depends(get_catalog)]
Config = Annotated[StackrConfig, fastapi.Depends(get_config)]
Env = Annotated[dict[str, str], fastapi.Depends(get_env)]
