"""Tests for secret resolution."""

import pytest

from stackr.secrets import (
    ensure_secret,
    find_unresolved,
    generate_secret,
    init_env_file,
    load_env_file,
    resolve,
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
    init_env_file(tmp_path)  # Should not raise or duplicate content
    content = (tmp_path / ".stackr.env").read_text()
    assert content.count("DO NOT COMMIT") == 1


def test_load_env_file(tmp_path):
    env_file = tmp_path / ".stackr.env"
    env_file.write_text("FOO=bar\nBAZ=qux\n")
    env = load_env_file(tmp_path)
    assert env["FOO"] == "bar"
    assert env["BAZ"] == "qux"


def test_load_env_file_missing(tmp_path):
    env = load_env_file(tmp_path)
    assert env == {}


def test_build_env_shell_wins_over_file(tmp_path, monkeypatch):
    """Shell environment must take priority over .stackr.env values."""
    from stackr.secrets import build_env
    env_file = tmp_path / ".stackr.env"
    env_file.write_text("MY_TOKEN=from-file\n")
    monkeypatch.setenv("MY_TOKEN", "from-shell")
    result = build_env(tmp_path)
    assert result["MY_TOKEN"] == "from-shell"


def test_build_env_file_used_when_no_shell_var(tmp_path, monkeypatch):
    """Values from .stackr.env are used when not overridden by shell env."""
    from stackr.secrets import build_env
    env_file = tmp_path / ".stackr.env"
    env_file.write_text("ONLY_IN_FILE=secret\n")
    monkeypatch.delenv("ONLY_IN_FILE", raising=False)
    result = build_env(tmp_path)
    assert result["ONLY_IN_FILE"] == "secret"


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
