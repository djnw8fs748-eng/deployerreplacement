# Stackr Rebuild — Phase 1: Engine Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure `stackr/` into a clean `engine/` subpackage, replace the JSON state file with SQLite, add the Docker SDK hybrid module, and remove the TUI — leaving a fully working CLI that other phases build on.

**Architecture:** The `engine/` subpackage is pure Python business logic with no HTTP or CLI dependencies. All existing engine modules migrate into it with updated imports. `engine/state.py` is rebuilt on SQLite (3 tables, WAL mode). `engine/docker.py` is a new module owning all Docker interaction — SDK for inspection, subprocess for compose, `OperationResult` for every operation. The CLI updates its imports to `stackr.engine.*`.

**Tech Stack:** Python 3.11+, Pydantic v2, SQLite (`sqlite3` stdlib), `docker` SDK package, Jinja2, subprocess, Typer, Rich

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `stackr/engine/__init__.py` | Package init, re-exports |
| Move → | `stackr/engine/config.py` | Pydantic config schema (from `stackr/config.py`) |
| Move → | `stackr/engine/catalog.py` | App catalog loading (from `stackr/catalog.py`, updated path) |
| Move → | `stackr/engine/renderer.py` | Jinja2 rendering (from `stackr/renderer.py`) |
| Move → | `stackr/engine/validator.py` | Pre-deploy validation (from `stackr/validator.py`) |
| Move → | `stackr/engine/secrets.py` | Secret resolution (from `stackr/secrets.py`) |
| Move → | `stackr/engine/alerts.py` | Push notifications (from `stackr/alerts.py`) |
| Move → | `stackr/engine/backup.py` | Restic backup/restore (from `stackr/backup.py`) |
| Move → | `stackr/engine/mounts.py` | SMB/NFS/Rclone mounts (from `stackr/mounts.py`) |
| Rebuild | `stackr/engine/state.py` | SQLite state (replaces JSON `stackr/state.py`) |
| Create | `stackr/engine/docker.py` | Docker SDK + subprocess hybrid, `OperationResult` |
| Rebuild | `stackr/engine/deployer.py` | Deploy orchestration using new state + docker |
| Modify | `stackr/cli.py` | Update all imports to `stackr.engine.*` |
| Modify | `stackr/service.py` | Update imports to `stackr.engine.*` |
| Modify | `pyproject.toml` | Remove `textual` from core, add `docker` |
| Delete | `stackr/tui.py` | TUI removed entirely |
| Delete | `stackr/images.py` | Merged into `engine/docker.py` |
| Delete | `stackr/doctor.py` | Merged into `engine/docker.py` (`docker_available`, `network_exists`) |
| Delete | `stackr/status.py` | Rich status table moves to CLI; live status via Docker SDK |
| Delete | `stackr/network.py` | `ensure_networks()` moves into `engine/docker.py` |
| Delete | `stackr/state.py` | Replaced by `engine/state.py` |
| Update | `tests/test_state.py` | Rewrite for SQLite API |
| Update | `tests/test_deployer.py` | Update mocks for new docker.py interface |
| Update | `tests/test_doctor.py` | Update for `engine/docker.py` |
| Delete | `tests/test_tui.py` | TUI gone |
| Delete | `tests/test_images.py` | Merged into `tests/test_docker.py` |
| Create | `tests/test_docker.py` | Tests for new `engine/docker.py` |
| Update | All other test files | Update imports to `stackr.engine.*` |

---

## Task 1: Update dependencies and remove TUI

**Files:**
- Modify: `pyproject.toml`
- Delete: `stackr/tui.py`
- Delete: `tests/test_tui.py`
- Modify: `stackr/cli.py` (remove `ui` command)

- [ ] **Step 1.1: Update pyproject.toml**

Replace the `dependencies` and `mypy.overrides` blocks:

```toml
dependencies = [
    "typer>=0.12.0",
    "pydantic>=2.0",
    "jinja2>=3.1",
    "pyyaml>=6.0",
    "rich>=13.0,<14",
    "python-dotenv>=1.0",
    "docker>=7.0",
    "fastapi>=0.110",
    "uvicorn>=0.29",
    "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-mock>=3.14",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
    "mypy>=1.10",
    "types-PyYAML>=6.0",
    "httpx>=0.27",
]
```

Remove the `[tool.mypy.overrides]` block for `stackr.tui`. Keep the `stackr.web.*` and `uvicorn` overrides.

- [ ] **Step 1.2: Install updated dependencies**

```bash
source .venv/bin/activate && uv pip install -e ".[dev]"
```

Expected: installs `docker` package, uninstalls `textual`.

- [ ] **Step 1.3: Delete TUI files**

```bash
rm stackr/tui.py tests/test_tui.py
```

- [ ] **Step 1.4: Remove `ui` command from cli.py**

In `stackr/cli.py`, find and delete the `@app.command("ui")` function and any `from stackr.tui import ...` import.

- [ ] **Step 1.5: Verify tests still collect**

```bash
source .venv/bin/activate && pytest tests/ --collect-only -q 2>&1 | tail -5
```

Expected: no `test_tui` in output, no import errors.

- [ ] **Step 1.6: Commit**

```bash
git add pyproject.toml stackr/cli.py
git rm stackr/tui.py tests/test_tui.py
git commit -m "chore: remove TUI, add docker SDK dependency"
```

---

## Task 2: Create the engine/ package and migrate simple modules

Migrate the six modules that need no logic changes — just updated imports inside them.

**Files:**
- Create: `stackr/engine/__init__.py`
- Create: `stackr/engine/config.py` (copy of `stackr/config.py`)
- Create: `stackr/engine/catalog.py` (copy of `stackr/catalog.py`, catalog path updated)
- Create: `stackr/engine/renderer.py` (copy of `stackr/renderer.py`)
- Create: `stackr/engine/validator.py` (copy of `stackr/validator.py`)
- Create: `stackr/engine/secrets.py` (copy of `stackr/secrets.py`)
- Create: `stackr/engine/alerts.py` (copy of `stackr/alerts.py`)
- Create: `stackr/engine/backup.py` (copy of `stackr/backup.py`)
- Create: `stackr/engine/mounts.py` (copy of `stackr/mounts.py`)

- [ ] **Step 2.1: Create engine package directory and __init__.py**

```bash
mkdir -p stackr/engine
```

Create `stackr/engine/__init__.py`:

```python
"""Stackr engine — pure business logic, no HTTP or CLI dependencies."""
```

- [ ] **Step 2.2: Copy modules into engine/**

```bash
cp stackr/config.py stackr/engine/config.py
cp stackr/catalog.py stackr/engine/catalog.py
cp stackr/renderer.py stackr/engine/renderer.py
cp stackr/validator.py stackr/engine/validator.py
cp stackr/secrets.py stackr/engine/secrets.py
cp stackr/alerts.py stackr/engine/alerts.py
cp stackr/backup.py stackr/engine/backup.py
cp stackr/mounts.py stackr/engine/mounts.py
```

- [ ] **Step 2.3: Fix imports inside each engine/ module**

In every file under `stackr/engine/`, replace all `from stackr.X import` and `import stackr.X` with `from stackr.engine.X import` / `import stackr.engine.X`.

Run this to find what needs changing:

```bash
grep -rn "from stackr\." stackr/engine/ | grep -v "engine\."
```

Fix each occurrence. For example in `stackr/engine/catalog.py`:
- `from stackr.config import ...` → `from stackr.engine.config import ...`

In `stackr/engine/catalog.py`, also update `BUILTIN_CATALOG` to point to the new `engine/catalog/` path (Task 6 will move the actual catalog files; for now, keep it pointing to `app_catalog` so tests still pass):

```python
BUILTIN_CATALOG = Path(__file__).parent.parent / "app_catalog"
```

This stays the same for now — catalog path migration happens in Phase 4.

- [ ] **Step 2.4: Add shim imports to old locations**

So existing code (CLI, tests) doesn't break yet, add shims in the old module locations that re-export from `engine/`:

In `stackr/config.py`, replace the entire file with:
```python
"""Compatibility shim — use stackr.engine.config directly."""
from stackr.engine.config import *  # noqa: F401, F403
from stackr.engine.config import StackrConfig, AppConfig, GlobalConfig, NetworkConfig  # noqa: F401
```

Repeat for `stackr/catalog.py`, `stackr/renderer.py`, `stackr/validator.py`, `stackr/secrets.py`, `stackr/alerts.py`, `stackr/backup.py`, `stackr/mounts.py` — each shimming their `engine/` counterpart.

- [ ] **Step 2.5: Run tests to confirm nothing broke**

```bash
source .venv/bin/activate && pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all previously passing tests still pass.

- [ ] **Step 2.6: Commit**

```bash
git add stackr/engine/ stackr/config.py stackr/catalog.py stackr/renderer.py stackr/validator.py stackr/secrets.py stackr/alerts.py stackr/backup.py stackr/mounts.py
git commit -m "refactor: create engine/ package, migrate modules with shims"
```

---

## Task 3: Build engine/state.py (SQLite)

Replace the JSON lock file with a 3-table SQLite database.

**Files:**
- Create: `stackr/engine/state.py`
- Rewrite: `tests/test_state.py`

- [ ] **Step 3.1: Write failing tests for the new state module**

Replace `tests/test_state.py` with:

```python
"""Tests for SQLite-backed state management."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from stackr.engine.state import AppState, DeployEvent, StateDB


@pytest.fixture
def db(tmp_path: Path) -> StateDB:
    return StateDB(db_path=tmp_path / "test.db")


def test_get_app_returns_none_for_unknown(db: StateDB) -> None:
    assert db.get_app("jellyfin") is None


def test_set_and_get_app(db: StateDB) -> None:
    state = AppState(
        name="jellyfin",
        enabled=True,
        compose_hash="abc123",
        compose_yaml="services:\n  jellyfin: {}",
        status="running",
        deployed_at="2026-01-01T00:00:00+00:00",
        image_digests={"jellyfin": "sha256:abc"},
    )
    db.set_app(state)
    result = db.get_app("jellyfin")
    assert result is not None
    assert result.name == "jellyfin"
    assert result.enabled is True
    assert result.compose_hash == "abc123"
    assert result.status == "running"
    assert result.image_digests == {"jellyfin": "sha256:abc"}


def test_set_app_overwrites(db: StateDB) -> None:
    db.set_app(AppState(name="jellyfin", enabled=True, status="running"))
    db.set_app(AppState(name="jellyfin", enabled=False, status="stopped"))
    result = db.get_app("jellyfin")
    assert result is not None
    assert result.enabled is False
    assert result.status == "stopped"


def test_set_app_replaces_image_digests(db: StateDB) -> None:
    db.set_app(AppState(name="app", image_digests={"svc": "old-digest"}))
    db.set_app(AppState(name="app", image_digests={"svc": "new-digest"}))
    result = db.get_app("app")
    assert result is not None
    assert result.image_digests == {"svc": "new-digest"}


def test_list_apps(db: StateDB) -> None:
    db.set_app(AppState(name="jellyfin", enabled=True))
    db.set_app(AppState(name="radarr", enabled=False))
    apps = db.list_apps()
    assert len(apps) == 2
    names = {a.name for a in apps}
    assert names == {"jellyfin", "radarr"}


def test_is_changed_returns_true_for_unknown_app(db: StateDB) -> None:
    assert db.is_changed("unknown", "hash") is True


def test_is_changed_returns_false_when_hash_matches(db: StateDB) -> None:
    db.set_app(AppState(name="app", compose_hash="hash123"))
    assert db.is_changed("app", "hash123") is False


def test_is_changed_returns_true_when_hash_differs(db: StateDB) -> None:
    db.set_app(AppState(name="app", compose_hash="old"))
    assert db.is_changed("app", "new") is True


def test_record_event_and_get_history(db: StateDB) -> None:
    event = DeployEvent(
        app_name="jellyfin",
        event_type="deploy",
        success=True,
        stdout="done",
        stderr="",
        exit_code=0,
        duration_ms=1234,
        command="docker compose up -d",
    )
    event_id = db.record_event(event)
    assert event_id is not None

    history = db.get_app_history("jellyfin")
    assert len(history) == 1
    assert history[0].success is True
    assert history[0].stdout == "done"
    assert history[0].duration_ms == 1234


def test_get_app_history_empty(db: StateDB) -> None:
    assert db.get_app_history("unknown") == []


def test_get_app_history_limit(db: StateDB) -> None:
    for i in range(25):
        db.record_event(DeployEvent(app_name="app", event_type="deploy", success=True))
    history = db.get_app_history("app", limit=10)
    assert len(history) == 10


def test_migrate_from_json(db: StateDB, tmp_path: Path) -> None:
    legacy = tmp_path / "state.json"
    legacy.write_text(json.dumps({
        "apps": {
            "jellyfin": {
                "enabled": True,
                "compose_hash": "abc",
                "compose_content": "services:\n  jellyfin: {}",
                "deployed_at": "2026-01-01T00:00:00",
                "image_digests": {"jellyfin": "sha256:abc"},
            }
        }
    }))
    db.migrate_from_json(legacy)
    result = db.get_app("jellyfin")
    assert result is not None
    assert result.compose_hash == "abc"
    assert result.image_digests == {"jellyfin": "sha256:abc"}


def test_migrate_from_json_no_op_if_missing(db: StateDB, tmp_path: Path) -> None:
    db.migrate_from_json(tmp_path / "nonexistent.json")  # must not raise
```

- [ ] **Step 3.2: Run tests to confirm they fail**

```bash
source .venv/bin/activate && pytest tests/test_state.py -v 2>&1 | tail -15
```

Expected: `ImportError` or `ModuleNotFoundError` — `stackr.engine.state` does not exist yet.

- [ ] **Step 3.3: Implement stackr/engine/state.py**

Create `stackr/engine/state.py`:

```python
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
                   ORDER BY started_at DESC LIMIT ?""",
                (app_name, limit),
            ).fetchall()
            return [self._row_to_deploy_event(row) for row in rows]

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
```

- [ ] **Step 3.4: Run the state tests**

```bash
source .venv/bin/activate && pytest tests/test_state.py -v
```

Expected: all tests PASS.

- [ ] **Step 3.5: Add shim to old stackr/state.py**

Replace `stackr/state.py` with a compatibility shim so existing CLI code keeps working during migration:

```python
"""Compatibility shim — use stackr.engine.state directly."""
from stackr.engine.state import AppState, DeployEvent, StateDB  # noqa: F401

# Legacy alias: old code used State, new code uses StateDB
State = StateDB
```

- [ ] **Step 3.6: Run full test suite**

```bash
source .venv/bin/activate && pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 3.7: Commit**

```bash
git add stackr/engine/state.py stackr/state.py tests/test_state.py
git commit -m "feat: SQLite state management (StateDB replaces JSON State)"
```

---

## Task 4: Build engine/docker.py

New module owning all Docker interaction — SDK for inspection, subprocess for compose, `OperationResult` for every operation.

**Files:**
- Create: `stackr/engine/docker.py`
- Create: `tests/test_docker.py`
- Delete: `stackr/images.py`, `stackr/doctor.py`, `stackr/network.py`, `tests/test_images.py`, `tests/test_doctor.py`

- [ ] **Step 4.1: Write failing tests**

Create `tests/test_docker.py`:

```python
"""Tests for engine/docker.py — Docker SDK + subprocess hybrid."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from stackr.engine.docker import (
    OperationResult,
    compose_down,
    compose_stop,
    compose_up,
    docker_available,
    get_image_digests,
    inspect_network,
    inspect_volume,
)


def test_operation_result_has_required_fields() -> None:
    result = OperationResult(
        success=True,
        app_name="jellyfin",
        event_type="deploy",
        stdout="done",
        stderr="",
        exit_code=0,
        duration_ms=100,
        command="docker compose up -d",
    )
    assert result.success is True
    assert result.app_name == "jellyfin"
    assert result.error is None


def test_compose_up_success(tmp_path: Path) -> None:
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services:\n  test: {}\n")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="done\n", stderr="")
        result = compose_up("testapp", compose_file)
    assert result.success is True
    assert result.app_name == "testapp"
    assert result.event_type == "deploy"
    assert result.exit_code == 0
    assert "docker" in result.command


def test_compose_up_failure(tmp_path: Path) -> None:
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services:\n  test: {}\n")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="image not found"
        )
        result = compose_up("testapp", compose_file)
    assert result.success is False
    assert result.exit_code == 1
    assert result.error is not None


def test_compose_up_docker_not_found(tmp_path: Path) -> None:
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("")
    with patch("subprocess.run", side_effect=FileNotFoundError):
        result = compose_up("testapp", compose_file)
    assert result.success is False
    assert result.exit_code is None
    assert "not found" in (result.error or "")


def test_compose_down_success(tmp_path: Path) -> None:
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = compose_down("testapp", compose_file)
    assert result.success is True
    assert result.event_type == "remove"


def test_compose_stop_success(tmp_path: Path) -> None:
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = compose_stop("testapp", compose_file)
    assert result.success is True
    assert result.event_type == "stop"


def test_docker_available_true() -> None:
    with patch("stackr.engine.docker.HAS_DOCKER_SDK", True):
        mock_client = MagicMock()
        with patch("docker.from_env", return_value=mock_client):
            assert docker_available() is True


def test_docker_available_false_no_sdk() -> None:
    with patch("stackr.engine.docker.HAS_DOCKER_SDK", False):
        assert docker_available() is False


def test_inspect_network_returns_none_without_sdk() -> None:
    with patch("stackr.engine.docker.HAS_DOCKER_SDK", False):
        assert inspect_network("proxy") is None


def test_inspect_volume_returns_none_without_sdk() -> None:
    with patch("stackr.engine.docker.HAS_DOCKER_SDK", False):
        assert inspect_volume("jellyfin_config") is None


def test_get_image_digests_returns_empty_without_sdk() -> None:
    with patch("stackr.engine.docker.HAS_DOCKER_SDK", False):
        assert get_image_digests("jellyfin", ["jellyfin"]) == {}
```

- [ ] **Step 4.2: Run to confirm tests fail**

```bash
source .venv/bin/activate && pytest tests/test_docker.py -v 2>&1 | tail -10
```

Expected: `ImportError` — `stackr.engine.docker` does not exist yet.

- [ ] **Step 4.3: Implement stackr/engine/docker.py**

Create `stackr/engine/docker.py`:

```python
"""Docker SDK + subprocess hybrid.

SDK (docker package)  — observation: container status, image digests, network/volume inspection.
subprocess            — orchestration: compose up/down/stop/pull, log streaming.
"""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

try:
    import docker as _docker_sdk

    HAS_DOCKER_SDK = True
except ImportError:
    HAS_DOCKER_SDK = False


# ---------------------------------------------------------------------------
# Shared result type
# ---------------------------------------------------------------------------


@dataclass
class OperationResult:
    success: bool
    app_name: str
    event_type: str
    stdout: str
    stderr: str
    exit_code: int | None
    duration_ms: int
    command: str | None
    error: str | None = None


# ---------------------------------------------------------------------------
# Docker SDK — observation layer
# ---------------------------------------------------------------------------


@dataclass
class ContainerStatus:
    app_name: str
    status: str  # 'running' | 'stopped' | 'degraded' | 'unknown'
    services: dict[str, str] = field(default_factory=dict)


def get_container_status(app_name: str) -> ContainerStatus:
    """Return live container status from Docker daemon."""
    if not HAS_DOCKER_SDK:
        return ContainerStatus(app_name=app_name, status="unknown")
    try:
        client = _docker_sdk.from_env()
        containers = client.containers.list(
            all=True,
            filters={"label": f"com.docker.compose.project={app_name}"},
        )
        if not containers:
            return ContainerStatus(app_name=app_name, status="unknown")
        services = {c.name: c.status for c in containers}
        running = sum(1 for s in services.values() if s == "running")
        if running == len(services):
            status = "running"
        elif running == 0:
            status = "stopped"
        else:
            status = "degraded"
        return ContainerStatus(app_name=app_name, status=status, services=services)
    except Exception:
        return ContainerStatus(app_name=app_name, status="unknown")


def get_image_digests(app_name: str, services: list[str]) -> dict[str, str]:
    """Return RepoDigests for each service from local Docker image metadata."""
    if not HAS_DOCKER_SDK:
        return {}
    digests: dict[str, str] = {}
    try:
        client = _docker_sdk.from_env()
        for service in services:
            containers = client.containers.list(
                all=True,
                filters={
                    "label": [
                        f"com.docker.compose.project={app_name}",
                        f"com.docker.compose.service={service}",
                    ]
                },
            )
            if not containers:
                continue
            image = client.images.get(containers[0].image.id)
            repo_digests: list[str] = image.attrs.get("RepoDigests", [])
            if repo_digests:
                digests[service] = repo_digests[0]
    except Exception:
        pass
    return digests


def inspect_network(name: str) -> dict | None:  # type: ignore[type-arg]
    """Return Docker network attributes, or None if not found."""
    if not HAS_DOCKER_SDK:
        return None
    try:
        return _docker_sdk.from_env().networks.get(name).attrs  # type: ignore[no-any-return]
    except Exception:
        return None


def inspect_volume(name: str) -> dict | None:  # type: ignore[type-arg]
    """Return Docker volume attributes, or None if not found."""
    if not HAS_DOCKER_SDK:
        return None
    try:
        return _docker_sdk.from_env().volumes.get(name).attrs  # type: ignore[no-any-return]
    except Exception:
        return None


def docker_available() -> bool:
    """Return True if the Docker daemon is reachable."""
    if not HAS_DOCKER_SDK:
        return False
    try:
        _docker_sdk.from_env().ping()
        return True
    except Exception:
        return False


def network_exists(name: str) -> bool:
    """Return True if a Docker network with this name exists."""
    return inspect_network(name) is not None


def ensure_networks(*, socket_proxy: bool = False) -> None:
    """Create required Docker networks if they do not exist."""
    _ensure_network("proxy")
    if socket_proxy:
        _ensure_network("socket_proxy")


def _ensure_network(name: str) -> None:
    if network_exists(name):
        return
    subprocess.run(
        ["docker", "network", "create", name],
        capture_output=True,
        check=False,
    )


# ---------------------------------------------------------------------------
# Subprocess — orchestration layer
# ---------------------------------------------------------------------------


def compose_up(app_name: str, compose_path: Path, *, pull: bool = True) -> OperationResult:
    """Run docker compose up -d --remove-orphans."""
    cmd = ["docker", "compose", "-f", str(compose_path), "up", "-d", "--remove-orphans"]
    return _run(app_name, "deploy", cmd)


def compose_pull(app_name: str, compose_path: Path) -> OperationResult:
    """Run docker compose pull."""
    cmd = ["docker", "compose", "-f", str(compose_path), "pull"]
    return _run(app_name, "pull", cmd)


def compose_down(app_name: str, compose_path: Path) -> OperationResult:
    """Run docker compose down (no -v; volumes are never destroyed automatically)."""
    cmd = ["docker", "compose", "-f", str(compose_path), "down"]
    return _run(app_name, "remove", cmd)


def compose_stop(app_name: str, compose_path: Path) -> OperationResult:
    """Run docker compose stop."""
    cmd = ["docker", "compose", "-f", str(compose_path), "stop"]
    return _run(app_name, "stop", cmd)


def compose_logs(compose_path: Path, service: str | None = None) -> Iterator[str]:
    """Stream log lines from docker compose logs -f."""
    cmd = ["docker", "compose", "-f", str(compose_path), "logs", "-f", "--no-color"]
    if service:
        cmd.append(service)
    with subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    ) as proc:
        assert proc.stdout is not None
        for line in proc.stdout:
            yield line.rstrip()


def _run(app_name: str, event_type: str, cmd: list[str]) -> OperationResult:
    command_str = " ".join(cmd)
    start = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        duration_ms = int((time.monotonic() - start) * 1000)
        success = proc.returncode == 0
        error: str | None = None
        if not success:
            last_line = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else ""
            error = last_line or f"exit code {proc.returncode}"
        return OperationResult(
            success=success,
            app_name=app_name,
            event_type=event_type,
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
            duration_ms=duration_ms,
            command=command_str,
            error=error,
        )
    except FileNotFoundError:
        duration_ms = int((time.monotonic() - start) * 1000)
        return OperationResult(
            success=False,
            app_name=app_name,
            event_type=event_type,
            stdout="",
            stderr="docker not found on PATH",
            exit_code=None,
            duration_ms=duration_ms,
            command=command_str,
            error="docker compose not found on PATH",
        )
```

- [ ] **Step 4.4: Run docker tests**

```bash
source .venv/bin/activate && pytest tests/test_docker.py -v
```

Expected: all tests PASS.

- [ ] **Step 4.5: Add shims for deleted modules**

Replace `stackr/network.py` with:
```python
"""Compatibility shim."""
from stackr.engine.docker import ensure_networks  # noqa: F401
```

Replace `stackr/images.py` with:
```python
"""Compatibility shim."""
from stackr.engine.docker import get_image_digests  # noqa: F401

def images_changed(app_name: str, compose_content: str, state: object) -> bool:  # type: ignore[return]
    """Legacy function — always returns True to force re-check."""
    return True
```

Replace `stackr/doctor.py` with:
```python
"""Compatibility shim."""
from stackr.engine.docker import docker_available, network_exists  # noqa: F401

def run_doctor(config: object) -> bool:
    from stackr.engine.docker import docker_available
    return docker_available()
```

Delete the old test files for merged modules:
```bash
git rm tests/test_images.py tests/test_doctor.py
```

- [ ] **Step 4.6: Run full test suite**

```bash
source .venv/bin/activate && pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 4.7: Commit**

```bash
git add stackr/engine/docker.py stackr/network.py stackr/images.py stackr/doctor.py tests/test_docker.py
git rm tests/test_images.py tests/test_doctor.py
git commit -m "feat: engine/docker.py — SDK inspection + subprocess compose with OperationResult"
```

---

## Task 5: Rebuild engine/deployer.py

Replace the current deployer with a version that uses `StateDB` and `OperationResult` from the new modules.

**Files:**
- Create: `stackr/engine/deployer.py`
- Update: `tests/test_deployer.py`

- [ ] **Step 5.1: Write failing tests for new deployer interface**

Add these tests to `tests/test_deployer.py` (keep existing tests, add below them):

```python
"""Additional tests for new deployer interface using StateDB and OperationResult."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from stackr.engine.docker import OperationResult
from stackr.engine.state import AppState, StateDB


def _make_op_result(success: bool = True, app_name: str = "app") -> OperationResult:
    return OperationResult(
        success=success,
        app_name=app_name,
        event_type="deploy",
        stdout="done" if success else "",
        stderr="" if success else "error",
        exit_code=0 if success else 1,
        duration_ms=100,
        command="docker compose up -d",
        error=None if success else "error",
    )


def test_deploy_records_success_event(tmp_path: Path, mocker: object) -> None:
    from stackr.engine.deployer import deploy_app

    db = StateDB(db_path=tmp_path / "test.db")
    mocker.patch("stackr.engine.deployer.compose_up", return_value=_make_op_result(True))
    mocker.patch("stackr.engine.deployer.compose_pull", return_value=_make_op_result(True, "pull"))
    mocker.patch("stackr.engine.deployer.get_image_digests", return_value={})
    mocker.patch("stackr.engine.deployer._write_compose", return_value=tmp_path / "compose.yml")
    mocker.patch("stackr.engine.deployer._ensure_data_dirs", return_value=[])

    app_state = AppState(name="app", enabled=True)
    result = deploy_app("app", "services:\n  app: {}", db, tmp_path)

    assert result.success is True
    history = db.get_app_history("app")
    assert len(history) == 1
    assert history[0].success is True


def test_deploy_records_failure_event(tmp_path: Path, mocker: object) -> None:
    from stackr.engine.deployer import deploy_app

    db = StateDB(db_path=tmp_path / "test.db")
    mocker.patch("stackr.engine.deployer.compose_pull", return_value=_make_op_result(True))
    mocker.patch("stackr.engine.deployer.compose_up", return_value=_make_op_result(False))
    mocker.patch("stackr.engine.deployer._write_compose", return_value=tmp_path / "compose.yml")
    mocker.patch("stackr.engine.deployer._ensure_data_dirs", return_value=[])

    result = deploy_app("app", "services:\n  app: {}", db, tmp_path)

    assert result.success is False
    history = db.get_app_history("app")
    assert len(history) == 1
    assert history[0].success is False


def test_deploy_updates_app_state_on_success(tmp_path: Path, mocker: object) -> None:
    from stackr.engine.deployer import deploy_app

    db = StateDB(db_path=tmp_path / "test.db")
    mocker.patch("stackr.engine.deployer.compose_pull", return_value=_make_op_result(True))
    mocker.patch("stackr.engine.deployer.compose_up", return_value=_make_op_result(True))
    mocker.patch("stackr.engine.deployer.get_image_digests", return_value={"app": "sha256:abc"})
    mocker.patch("stackr.engine.deployer._write_compose", return_value=tmp_path / "compose.yml")
    mocker.patch("stackr.engine.deployer._ensure_data_dirs", return_value=[])

    deploy_app("app", "services:\n  app: {}", db, tmp_path)

    state = db.get_app("app")
    assert state is not None
    assert state.status == "running"
    assert state.last_error is None
    assert state.image_digests == {"app": "sha256:abc"}


def test_deploy_sets_error_on_failure(tmp_path: Path, mocker: object) -> None:
    from stackr.engine.deployer import deploy_app

    db = StateDB(db_path=tmp_path / "test.db")
    mocker.patch("stackr.engine.deployer.compose_pull", return_value=_make_op_result(True))
    mocker.patch(
        "stackr.engine.deployer.compose_up",
        return_value=_make_op_result(False),
    )
    mocker.patch("stackr.engine.deployer._write_compose", return_value=tmp_path / "compose.yml")
    mocker.patch("stackr.engine.deployer._ensure_data_dirs", return_value=[])

    deploy_app("app", "services:\n  app: {}", db, tmp_path)

    state = db.get_app("app")
    assert state is not None
    assert state.status == "failed"
    assert state.last_error is not None
```

- [ ] **Step 5.2: Run tests to confirm they fail**

```bash
source .venv/bin/activate && pytest tests/test_deployer.py -k "test_deploy_records" -v 2>&1 | tail -10
```

Expected: `ImportError` — `stackr.engine.deployer.deploy_app` does not exist.

- [ ] **Step 5.3: Implement stackr/engine/deployer.py**

Create `stackr/engine/deployer.py`:

```python
"""Deploy orchestration using StateDB and OperationResult."""
from __future__ import annotations

import hashlib
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import yaml
from rich.console import Console

from stackr.engine.catalog import Catalog, CatalogApp
from stackr.engine.config import AppConfig, StackrConfig
from stackr.engine.docker import (
    OperationResult,
    compose_down,
    compose_pull,
    compose_stop,
    compose_up,
    ensure_networks,
    get_image_digests,
)
from stackr.engine.renderer import render_app
from stackr.engine.state import AppState, DeployEvent, StateDB
from stackr.engine.validator import ValidationResult

console = Console()
COMPOSE_DIR = Path.home() / ".stackr" / "compose"


def deploy_app(
    app_name: str,
    compose_content: str,
    db: StateDB,
    compose_base_dir: Path = COMPOSE_DIR,
    *,
    pull: bool = True,
) -> OperationResult:
    """Deploy a single app. Always records result in DB."""
    compose_path = _write_compose(app_name, compose_content, compose_base_dir)

    if pull:
        pull_result = compose_pull(app_name, compose_path)
        if not pull_result.success:
            db.record_event(_to_event(pull_result))

    result = compose_up(app_name, compose_path)
    db.record_event(_to_event(result))

    compose_hash = hashlib.sha256(compose_content.encode()).hexdigest()
    image_digests = get_image_digests(app_name, _services(compose_content)) if result.success else {}

    existing = db.get_app(app_name)
    db.set_app(AppState(
        name=app_name,
        enabled=existing.enabled if existing else True,
        compose_hash=compose_hash,
        compose_yaml=compose_content,
        status="running" if result.success else "failed",
        deployed_at=datetime.now(UTC).isoformat() if result.success else (existing.deployed_at if existing else None),
        last_error=None if result.success else result.error,
        image_digests=image_digests,
    ))
    return result


def stop_app(app_name: str, db: StateDB, compose_base_dir: Path = COMPOSE_DIR) -> OperationResult:
    """Stop an app's containers without removing them."""
    compose_path = _compose_path(app_name, compose_base_dir)
    result = compose_stop(app_name, compose_path)
    db.record_event(_to_event(result))
    existing = db.get_app(app_name)
    if existing and result.success:
        db.set_app(AppState(
            **{**existing.__dict__, "status": "stopped"}
        ))
    return result


def remove_app(app_name: str, db: StateDB, compose_base_dir: Path = COMPOSE_DIR) -> OperationResult:
    """Run docker compose down (no -v; volumes are preserved)."""
    compose_path = _compose_path(app_name, compose_base_dir)
    result = compose_down(app_name, compose_path)
    db.record_event(_to_event(result))
    return result


def rollback_app(app_name: str, db: StateDB, compose_base_dir: Path = COMPOSE_DIR) -> OperationResult:
    """Redeploy the last stored compose content from DB."""
    existing = db.get_app(app_name)
    if existing is None or not existing.compose_yaml:
        return OperationResult(
            success=False,
            app_name=app_name,
            event_type="rollback",
            stdout="",
            stderr="No stored compose content for rollback",
            exit_code=None,
            duration_ms=0,
            command=None,
            error="No stored compose content for rollback",
        )
    return deploy_app(app_name, existing.compose_yaml, db, compose_base_dir, pull=False)


def deploy_all(
    config: StackrConfig,
    catalog: Catalog,
    validation: ValidationResult,
    db: StateDB,
    *,
    app_name: str | None = None,
    pull: bool = True,
    force: bool = False,
) -> list[OperationResult]:
    """Deploy all enabled apps (or a single app if app_name is given)."""
    if not validation.ok:
        console.print("[bold red]Validation failed — aborting deploy.[/bold red]")
        for err in validation.errors:
            console.print(f"  [red]ERROR[/red] {err}")
        raise SystemExit(1)

    for warn in validation.warnings:
        console.print(f"  [yellow]WARN[/yellow]  {warn}")

    ensure_networks(socket_proxy=config.security.socket_proxy)

    apps = config.enabled_apps
    if app_name:
        apps = [a for a in apps if a.name == app_name]
        if not apps:
            console.print(f"[red]App '{app_name}' not found or not enabled.[/red]")
            raise SystemExit(1)

    results: list[OperationResult] = []
    for app_config in apps:
        catalog_app = _get_catalog_app(app_config, catalog)
        if catalog_app is None:
            continue

        compose_content = render_app(app_config, catalog_app, config)
        failed_dirs = _ensure_data_dirs(compose_content, str(config.global_.data_dir))
        if failed_dirs:
            paths_str = " ".join(str(p) for p in failed_dirs)
            console.print(
                f"  [red]ERROR[/red]  {app_config.name} — could not create data dirs.\n"
                f"         [bold]sudo mkdir -p {paths_str}[/bold]"
            )
            continue

        compose_hash = hashlib.sha256(compose_content.encode()).hexdigest()
        if not force and not db.is_changed(app_config.name, compose_hash):
            console.print(f"  [dim]SKIP[/dim]   {app_config.name} (unchanged)")
            continue

        console.print(f"  [cyan]DEPLOY[/cyan] {app_config.name}")
        result = deploy_app(app_config.name, compose_content, db, pull=pull)
        results.append(result)

        if result.success:
            console.print(f"  [green]OK[/green]     {app_config.name}")
        else:
            console.print(f"  [red]FAIL[/red]   {app_config.name}: {result.error}")

    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _write_compose(app_name: str, content: str, base_dir: Path = COMPOSE_DIR) -> Path:
    path = _compose_path(app_name, base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _compose_path(app_name: str, base_dir: Path = COMPOSE_DIR) -> Path:
    return base_dir / app_name / "docker-compose.yml"


def _services(compose_content: str) -> list[str]:
    try:
        data = yaml.safe_load(compose_content)
        return list((data or {}).get("services", {}).keys())
    except Exception:
        return []


def _to_event(result: OperationResult) -> DeployEvent:
    return DeployEvent(
        app_name=result.app_name,
        event_type=result.event_type,
        success=result.success,
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.exit_code,
        duration_ms=result.duration_ms,
        command=result.command,
    )


def _get_catalog_app(app_config: AppConfig, catalog: Catalog) -> CatalogApp | None:
    try:
        return catalog.get(app_config.name)
    except KeyError:
        console.print(f"  [yellow]WARN[/yellow]  {app_config.name} not in catalog — skipping")
        return None


def _ensure_data_dirs(compose_content: str, data_dir: str) -> list[Path]:
    """Create volume bind-mount directories. Returns list of dirs that could not be created."""
    failed: list[Path] = []
    try:
        data = yaml.safe_load(compose_content) or {}
        for svc in data.get("services", {}).values():
            for vol in svc.get("volumes", []):
                host_path_str = str(vol).split(":")[0] if ":" in str(vol) else ""
                if not host_path_str or not host_path_str.startswith("/"):
                    continue
                host_path = Path(host_path_str)
                if host_path.exists():
                    continue
                try:
                    host_path.mkdir(parents=True, exist_ok=True)
                except PermissionError:
                    result = subprocess.run(
                        ["sudo", "mkdir", "-p", str(host_path)],
                        capture_output=True,
                    )
                    if result.returncode != 0:
                        failed.append(host_path)
    except Exception:
        pass
    return failed
```

- [ ] **Step 5.4: Run new deployer tests**

```bash
source .venv/bin/activate && pytest tests/test_deployer.py -v --tb=short 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 5.5: Update stackr/deployer.py shim**

Replace `stackr/deployer.py` with:

```python
"""Compatibility shim — use stackr.engine.deployer directly."""
from stackr.engine.deployer import deploy_all, deploy_app, remove_app, rollback_app, stop_app  # noqa: F401

# Legacy alias for existing CLI code
deploy = deploy_all
```

- [ ] **Step 5.6: Run full test suite**

```bash
source .venv/bin/activate && pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 5.7: Commit**

```bash
git add stackr/engine/deployer.py stackr/deployer.py tests/test_deployer.py
git commit -m "feat: engine/deployer.py — deploy with OperationResult and StateDB"
```

---

## Task 6: Update CLI to use engine imports

Update `stackr/cli.py` to import from `stackr.engine.*` directly. Remove references to deleted modules.

**Files:**
- Modify: `stackr/cli.py`

- [ ] **Step 6.1: Replace all shim imports in cli.py**

In `stackr/cli.py`, replace every `from stackr.X import` (where X is a migrated module) with `from stackr.engine.X import`. Run:

```bash
grep -n "from stackr\." stackr/cli.py | grep -v "engine\.\|web\.\|service\.\|migrate\."
```

For each match, update the import to use `stackr.engine.*`. Key replacements:

```python
# Before                                    # After
from stackr.config import ...           →   from stackr.engine.config import ...
from stackr.catalog import ...          →   from stackr.engine.catalog import ...
from stackr.renderer import ...         →   from stackr.engine.renderer import ...
from stackr.validator import ...        →   from stackr.engine.validator import ...
from stackr.secrets import ...          →   from stackr.engine.secrets import ...
from stackr.deployer import ...         →   from stackr.engine.deployer import ...
from stackr.state import ...            →   from stackr.engine.state import ...
from stackr.alerts import ...           →   from stackr.engine.alerts import ...
from stackr.backup import ...           →   from stackr.engine.backup import ...
from stackr.mounts import ...           →   from stackr.engine.mounts import ...
from stackr.doctor import run_doctor    →   from stackr.engine.docker import docker_available
from stackr.images import ...           →   from stackr.engine.docker import get_image_digests
from stackr.network import ...          →   from stackr.engine.docker import ensure_networks
```

Also update any `State(...)` usages to `StateDB(...)` and `deploy(...)` to `deploy_all(...)`.

- [ ] **Step 6.2: Update _load() helper in cli.py**

Find the `_load()` helper function. Replace `State(...)` with `StateDB(...)` and add migration call:

```python
def _load(config_path: Path) -> tuple[StackrConfig, Catalog, dict[str, str], StateDB]:
    from stackr.engine.state import StateDB, DEFAULT_STATE_DIR
    config = StackrConfig.from_yaml(config_path)
    catalog = Catalog.load()
    env = build_env(config_path.parent)
    db = StateDB()
    # Migrate legacy JSON state on first use
    db.migrate_from_json(DEFAULT_STATE_DIR / "state.json")
    return config, catalog, env, db
```

- [ ] **Step 6.3: Run CLI smoke test**

```bash
source .venv/bin/activate && python -m stackr --help
```

Expected: help text displayed without errors.

- [ ] **Step 6.4: Run full test suite**

```bash
source .venv/bin/activate && pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 6.5: Commit**

```bash
git add stackr/cli.py
git commit -m "refactor: cli.py uses stackr.engine.* imports directly"
```

---

## Task 7: Update remaining test files and clean up shims

All tests should now import from `stackr.engine.*`. Remove the old module files (shims have served their purpose).

**Files:**
- Update: all `tests/test_*.py` files that import from old locations
- Delete: `stackr/config.py`, `stackr/catalog.py`, `stackr/renderer.py`, `stackr/validator.py`, `stackr/secrets.py`, `stackr/alerts.py`, `stackr/backup.py`, `stackr/mounts.py`, `stackr/state.py`, `stackr/deployer.py`, `stackr/images.py`, `stackr/doctor.py`, `stackr/network.py`

- [ ] **Step 7.1: Update test imports**

Find all tests still importing from old locations:

```bash
grep -rn "from stackr\." tests/ | grep -v "engine\.\|web\.\|service\.\|migrate\.\|cli\.\|__init__"
```

For each match, update to `stackr.engine.*`. Key replacements are the same as Task 6 Step 1.

- [ ] **Step 7.2: Run full test suite to confirm all pass**

```bash
source .venv/bin/activate && pytest tests/ -v --tb=short
```

Expected: all tests pass.

- [ ] **Step 7.3: Delete old module shims**

```bash
git rm stackr/config.py stackr/catalog.py stackr/renderer.py stackr/validator.py \
       stackr/secrets.py stackr/alerts.py stackr/backup.py stackr/mounts.py \
       stackr/state.py stackr/deployer.py stackr/images.py stackr/doctor.py stackr/network.py
```

- [ ] **Step 7.4: Run linter and type checker**

```bash
source .venv/bin/activate && ruff check stackr/ tests/ && mypy stackr/
```

Fix any issues before proceeding.

- [ ] **Step 7.5: Run full test suite one final time**

```bash
source .venv/bin/activate && pytest tests/ -v
```

Expected: all tests pass, no import errors.

- [ ] **Step 7.6: Final commit**

```bash
git add -A
git commit -m "chore: remove old module shims, tests use engine.* imports"
```

---

## Task 8: Verify complete Phase 1

- [ ] **Step 8.1: Confirm package structure**

```bash
find stackr/engine/ -name "*.py" | sort
```

Expected output:
```
stackr/engine/__init__.py
stackr/engine/alerts.py
stackr/engine/backup.py
stackr/engine/catalog.py
stackr/engine/config.py
stackr/engine/deployer.py
stackr/engine/docker.py
stackr/engine/mounts.py
stackr/engine/renderer.py
stackr/engine/secrets.py
stackr/engine/state.py
stackr/engine/validator.py
```

- [ ] **Step 8.2: Confirm TUI is gone**

```bash
ls stackr/tui.py 2>/dev/null && echo "FAIL: tui.py still exists" || echo "PASS: tui.py removed"
```

- [ ] **Step 8.3: Confirm docker SDK is installed**

```bash
source .venv/bin/activate && python -c "import docker; print('docker SDK:', docker.__version__)"
```

- [ ] **Step 8.4: Confirm SQLite state works**

```bash
source .venv/bin/activate && python -c "
from stackr.engine.state import StateDB, AppState
import tempfile, pathlib
with tempfile.TemporaryDirectory() as tmp:
    db = StateDB(pathlib.Path(tmp) / 'test.db')
    db.set_app(AppState(name='test', enabled=True, status='running'))
    result = db.get_app('test')
    assert result is not None and result.status == 'running'
    print('PASS: SQLite state works')
"
```

- [ ] **Step 8.5: Run complete test suite**

```bash
source .venv/bin/activate && pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 8.6: Push branch and open PR**

```bash
git push -u origin docs/rebuild-design-spec
gh pr create --title "feat: Phase 1 — engine foundation (SQLite state, Docker SDK, no TUI)" \
  --body "$(cat <<'EOF'
## Summary
- Restructures `stackr/` into clean `engine/` subpackage
- Replaces JSON lock file with SQLite (`engine/state.py`, 3 tables, WAL mode)
- Adds Docker SDK + subprocess hybrid module (`engine/docker.py`) with `OperationResult`
- Removes TUI (Textual) entirely
- All existing tests updated to use `stackr.engine.*` imports

## Test plan
- [ ] `pytest tests/ -v` passes fully
- [ ] `python -m stackr --help` works
- [ ] `python -m stackr validate` works against a real stackr.yml
- [ ] SQLite DB is created at `~/.stackr/stackr.db` on first run
- [ ] Legacy `state.json` is imported on first run if present

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

## Phase Summary

After Phase 1 is complete:

| Component | Status |
|-----------|--------|
| `stackr/engine/` | New, clean subpackage |
| TUI | Deleted |
| State | SQLite (`StateDB`) |
| Docker | SDK + subprocess (`OperationResult`) |
| CLI | Works, uses `engine.*` |
| Tests | All pass |

**Phase 2 (REST API)** builds FastAPI routes on top of this engine.
**Phase 3 (Web UI)** adds the Alpine.js static frontend.
**Phase 4 (Catalog)** adds template validation CI and audits all 51 apps.
**Phase 5 (Service)** makes the server always-on and adds install/uninstall.
