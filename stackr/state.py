"""Compatibility shim — use stackr.engine.state directly.

This module bridges the old JSON-file State API to the new SQLite StateDB.
New code should import from stackr.engine.state.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from stackr.engine.state import (  # noqa: F401
    DEFAULT_STATE_DIR,
    DeployEvent,
    StateDB,
)
from stackr.engine.state import (
    AppState as _NewAppState,
)

# Legacy constant
STATE_FILE = "state.json"

# Provide a backward-compatible AppState that accepts both old `compose_content`
# and new `compose_yaml` kwargs so existing tests/code keep working.
class AppState(_NewAppState):
    """Backward-compatible AppState — accepts `compose_content` as alias for `compose_yaml`."""

    def __init__(self, **kwargs: Any) -> None:  # type: ignore[override]
        if "compose_content" in kwargs and "compose_yaml" not in kwargs:
            kwargs["compose_yaml"] = kwargs.pop("compose_content")
        else:
            kwargs.pop("compose_content", None)
        super().__init__(**kwargs)

    @property
    def compose_content(self) -> str | None:
        return self.compose_yaml


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def hash_content(content: str) -> str:
    """Legacy helper — kept for tests/external callers."""
    return _hash(content)


def now_iso() -> str:
    from datetime import UTC, datetime
    return datetime.now(UTC).isoformat()


class State:
    """Backward-compatible wrapper around StateDB.

    Supports the old API:
      - State(state_dir=Path(...))
      - state.set_app(name, compose_content, enabled=True, image_digests={})
      - state.get_app(name)  → object with .compose_content attribute
      - state.is_changed(name, compose_content)
      - state.remove_app(name)
      - state.save()   (no-op — SQLite commits immediately)
      - state.all_apps()
    """

    def __init__(self, state_dir: Path = DEFAULT_STATE_DIR) -> None:
        db_path = state_dir / "stackr.db"
        self._db = StateDB(db_path=db_path)

    # ------------------------------------------------------------------
    # Compat API
    # ------------------------------------------------------------------

    def get_app(self, name: str) -> _LegacyAppState | None:
        result = self._db.get_app(name)
        if result is None:
            return None
        return _LegacyAppState._from_new(result)

    def set_app(
        self,
        name: str,
        compose_content: str,
        enabled: bool = True,
        image_digests: dict[str, str] | None = None,
    ) -> None:
        from stackr.engine.state import AppState as NewAppState
        state = NewAppState(
            name=name,
            enabled=enabled,
            compose_hash=_hash(compose_content),
            compose_yaml=compose_content,
            deployed_at=now_iso(),
            image_digests=image_digests or {},
        )
        self._db.set_app(state)

    def remove_app(self, name: str) -> None:
        self._db.remove_app(name)

    def all_apps(self) -> dict[str, _LegacyAppState]:
        return {a.name: _LegacyAppState._from_new(a) for a in self._db.list_apps()}

    def is_changed(self, name: str, compose_content: str) -> bool:
        return self._db.is_changed(name, _hash(compose_content))

    def save(self) -> None:
        """No-op — SQLite commits are immediate."""


class _LegacyAppState:
    """Wraps the new AppState dataclass to expose the old .compose_content attribute."""

    def __init__(self, **kwargs: Any) -> None:
        self.name: str = kwargs["name"]
        self.enabled: bool = kwargs.get("enabled", True)
        self.compose_hash: str = kwargs.get("compose_hash", "")
        self.compose_content: str = kwargs.get("compose_content", "")
        self.deployed_at: str = kwargs.get("deployed_at", "")
        self.image_digests: dict[str, str] = kwargs.get("image_digests", {})

    @classmethod
    def _from_new(cls, new: _NewAppState) -> _LegacyAppState:
        return cls(
            name=new.name,
            enabled=new.enabled,
            compose_hash=new.compose_hash or "",
            compose_content=new.compose_yaml or "",
            deployed_at=new.deployed_at or "",
            image_digests=new.image_digests,
        )
