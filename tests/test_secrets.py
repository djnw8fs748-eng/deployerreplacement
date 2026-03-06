"""Tests for secret resolution."""

import pytest

from stackr.secrets import (
    find_unresolved,
    resolve,
    generate_secret,
    ensure_secret,
    init_env_file,
    load_env_file,
)


def test_resolve_simple():
    assert resolve("${FOO}", {"FOO": "bar"}) == "bar"


def test_resolve_multiple():
    assert resolve("${A} and ${B}", {"A": "1", "B": "2"}) == "1 and 2"


def test_resolve_raises_on_missing():
    with pytest.raises(KeyError, match="MISSING"):
        resolve("${MISSING}", {})


def test_find_unresolved():
    missing = find_unresolved("${GOOD} ${BAD}", {"GOOD": "ok"})
    assert missing == ["BAD"]


def test_find_unresolved_all_present():
    assert find_unresolved("${A}", {"A": "1"}) == []


def test_generate_secret_length():
    s = generate_secret(32)
    # token_urlsafe(32) produces ~43 chars
    assert len(s) >= 32


def test_generate_secret_unique():
    assert generate_secret() != generate_secret()


def test_init_env_file_creates_file(tmp_path):
    env_file = init_env_file(tmp_path)
    assert env_file.exists()
    assert "DO NOT COMMIT" in env_file.read_text()


def test_init_env_file_idempotent(tmp_path):
    init_env_file(tmp_path)
    init_env_file(tmp_path)  # Should not raise or duplicate
    count = tmp_path.read_text() if (tmp_path / ".stackr.env").exists() else ""


def test_load_env_file(tmp_path):
    env_file = tmp_path / ".stackr.env"
    env_file.write_text("FOO=bar\nBAZ=qux\n")
    env = load_env_file(tmp_path)
    assert env["FOO"] == "bar"
    assert env["BAZ"] == "qux"


def test_load_env_file_missing(tmp_path):
    env = load_env_file(tmp_path)
    assert env == {}


def test_ensure_secret_generates_and_persists(tmp_path):
    env: dict[str, str] = {}
    init_env_file(tmp_path)
    value = ensure_secret("MY_SECRET", tmp_path, env)
    assert len(value) > 0
    assert env["MY_SECRET"] == value
    # Should be persisted in .stackr.env
    loaded = load_env_file(tmp_path)
    assert loaded["MY_SECRET"] == value


def test_ensure_secret_returns_existing(tmp_path):
    env = {"MY_SECRET": "existing-value"}
    init_env_file(tmp_path)
    value = ensure_secret("MY_SECRET", tmp_path, env)
    assert value == "existing-value"
