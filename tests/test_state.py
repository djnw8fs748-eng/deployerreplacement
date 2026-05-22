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
    for _i in range(25):
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
