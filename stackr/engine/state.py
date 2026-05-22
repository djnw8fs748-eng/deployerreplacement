"""SQLite-backed deploy state management."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Generator

DEFAULT_STATE_DIR = Path.home() / ".stackr"
DEFAULT_DB_PATH = DEFAULT_STATE_DIR / "stackr.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_state (
    name          TEXT PRIMARY KEY,
    enabled       INTEGER NOT NULL DEFAULT 0,
    compose_hash  TEXT,
    compose_yaml  TEXT,
    status        TEXT DEFAULT 'unknown',
    deployed_at   TEXT,
    last_error    TEXT
);

CREATE TABLE IF NOT EXISTS image_digests (
    app_name      TEXT NOT NULL,
    service_name  TEXT NOT NULL,
    digest        TEXT NOT NULL,
    checked_at    TEXT NOT NULL,
    PRIMARY KEY (app_name, service_name)
);

CREATE TABLE IF NOT EXISTS deploy_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    app_name      TEXT NOT NULL,
    event_type    TEXT NOT NULL,
    success       INTEGER NOT NULL,
    stdout        TEXT,
    stderr        TEXT,
    exit_code     INTEGER,
    duration_ms   INTEGER,
    command       TEXT,
    started_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_deploy_events_app ON deploy_events (app_name, started_at DESC);
"""


@dataclass
class AppState:
    name: str
    enabled: bool = False
    compose_hash: str | None = None
    compose_yaml: str | None = None
    status: str = "unknown"
    deployed_at: str | None = None
    last_error: str | None = None
    image_digests: dict[str, str] = field(default_factory=dict)


@dataclass
class DeployEvent:
    app_name: str
    event_type: str
    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    duration_ms: int = 0
    command: str | None = None
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    id: int | None = None


class StateDB:
    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        self._path = db_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _init(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA)
            conn.execute("PRAGMA journal_mode=WAL")

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_app(self, name: str) -> AppState | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM app_state WHERE name = ?", (name,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_app_state(conn, row)

    def list_apps(self) -> list[AppState]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM app_state").fetchall()
            return [self._row_to_app_state(conn, row) for row in rows]

    def set_app(self, state: AppState) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO app_state
                   (name, enabled, compose_hash, compose_yaml, status, deployed_at, last_error)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    state.name,
                    int(state.enabled),
                    state.compose_hash,
                    state.compose_yaml,
                    state.status,
                    state.deployed_at,
                    state.last_error,
                ),
            )
            conn.execute(
                "DELETE FROM image_digests WHERE app_name = ?", (state.name,)
            )
            now = datetime.now(UTC).isoformat()
            for service, digest in state.image_digests.items():
                conn.execute(
                    """INSERT INTO image_digests (app_name, service_name, digest, checked_at)
                       VALUES (?, ?, ?, ?)""",
                    (state.name, service, digest, now),
                )

    def record_event(self, event: DeployEvent) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO deploy_events
                   (app_name, event_type, success, stdout, stderr,
                    exit_code, duration_ms, command, started_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.app_name,
                    event.event_type,
                    int(event.success),
                    event.stdout,
                    event.stderr,
                    event.exit_code,
                    event.duration_ms,
                    event.command,
                    event.started_at,
                ),
            )
            return int(cur.lastrowid)  # type: ignore[arg-type]

    def get_app_history(self, app_name: str, limit: int = 20) -> list[DeployEvent]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM deploy_events WHERE app_name = ?
                   ORDER BY started_at DESC, id DESC LIMIT ?""",
                (app_name, limit),
            ).fetchall()
            return [self._row_to_deploy_event(row) for row in rows]

    def remove_app(self, name: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM app_state WHERE name = ?", (name,))
            conn.execute("DELETE FROM image_digests WHERE app_name = ?", (name,))

    def is_changed(self, name: str, compose_hash: str) -> bool:
        app = self.get_app(name)
        if app is None:
            return True
        return app.compose_hash != compose_hash

    def migrate_from_json(self, json_path: Path) -> None:
        """Import legacy ~/.stackr/state.json into SQLite on first run."""
        if not json_path.exists():
            return
        data = json.loads(json_path.read_text())
        for name, app_data in data.get("apps", {}).items():
            if self.get_app(name) is not None:
                continue
            state = AppState(
                name=name,
                enabled=app_data.get("enabled", False),
                compose_hash=app_data.get("compose_hash"),
                compose_yaml=app_data.get("compose_content"),
                status="unknown",
                deployed_at=app_data.get("deployed_at"),
                image_digests=app_data.get("image_digests", {}),
            )
            self.set_app(state)

    def _row_to_app_state(self, conn: sqlite3.Connection, row: sqlite3.Row) -> AppState:
        digests = {
            r["service_name"]: r["digest"]
            for r in conn.execute(
                "SELECT service_name, digest FROM image_digests WHERE app_name = ?",
                (row["name"],),
            ).fetchall()
        }
        return AppState(
            name=row["name"],
            enabled=bool(row["enabled"]),
            compose_hash=row["compose_hash"],
            compose_yaml=row["compose_yaml"],
            status=row["status"] or "unknown",
            deployed_at=row["deployed_at"],
            last_error=row["last_error"],
            image_digests=digests,
        )

    @staticmethod
    def _row_to_deploy_event(row: sqlite3.Row) -> DeployEvent:
        return DeployEvent(
            id=row["id"],
            app_name=row["app_name"],
            event_type=row["event_type"],
            success=bool(row["success"]),
            stdout=row["stdout"] or "",
            stderr=row["stderr"] or "",
            exit_code=row["exit_code"],
            duration_ms=row["duration_ms"] or 0,
            command=row["command"],
            started_at=row["started_at"],
        )
