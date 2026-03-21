"""Deployed state tracking via a JSON lock file."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_STATE_DIR = Path.home() / ".stackr"
STATE_FILE = "state.json"


class AppState:
    def __init__(
        self,
        name: str,
        enabled: bool,
        compose_hash: str,
        compose_content: str,
        deployed_at: str,
        image_digests: dict[str, str] | None = None,
    ) -> None:
        self.name = name
        self.enabled = enabled
        self.compose_hash = compose_hash
        self.compose_content = compose_content
        self.deployed_at = deployed_at
        self.image_digests: dict[str, str] = image_digests or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "compose_hash": self.compose_hash,
            "compose_content": self.compose_content,
            "deployed_at": self.deployed_at,
            "image_digests": self.image_digests,
        }

    @classmethod
    def from_dict(cls, name: str, d: dict[str, Any]) -> AppState:
        return cls(
            name=name,
            enabled=d.get("enabled", True),
            compose_hash=d.get("compose_hash", ""),
            compose_content=d.get("compose_content", ""),
            deployed_at=d.get("deployed_at", ""),
            image_digests=d.get("image_digests", {}),
        )


class State:
    def __init__(self, state_dir: Path = DEFAULT_STATE_DIR) -> None:
        self._path = state_dir / STATE_FILE
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if self._path.exists():
            with open(self._path) as f:
                data: dict[str, Any] = json.load(f)
                return data
        return {"apps": {}, "deployed_at": None, "catalog_version": None}

    def save(self) -> None:
        with open(self._path, "w") as f:
            json.dump(self._data, f, indent=2)

    def get_app(self, name: str) -> AppState | None:
        apps = self._data.get("apps", {})
        if name not in apps:
            return None
        return AppState.from_dict(name, apps[name])

    def set_app(
        self,
        name: str,
        compose_content: str,
        enabled: bool = True,
        image_digests: dict[str, str] | None = None,
    ) -> None:
        self._data.setdefault("apps", {})[name] = AppState(
            name=name,
            enabled=enabled,
            compose_hash=hash_content(compose_content),
            compose_content=compose_content,
            deployed_at=now_iso(),
            image_digests=image_digests or {},
        ).to_dict()
        self._data["deployed_at"] = now_iso()

    def remove_app(self, name: str) -> None:
        self._data.get("apps", {}).pop(name, None)

    def all_apps(self) -> dict[str, AppState]:
        return {
            name: AppState.from_dict(name, d)
            for name, d in self._data.get("apps", {}).items()
        }

    def is_changed(self, name: str, compose_content: str) -> bool:
        app = self.get_app(name)
        if app is None:
            return True
        return app.compose_hash != hash_content(compose_content)


def hash_content(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
