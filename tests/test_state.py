"""Tests for state lock file."""

import pytest

from stackr.state import State, hash_content


def test_state_empty_on_init(tmp_path):
    state = State(state_dir=tmp_path)
    assert state.all_apps() == {}


def test_set_and_get_app(tmp_path):
    state = State(state_dir=tmp_path)
    state.set_app("jellyfin", "compose content here")
    app = state.get_app("jellyfin")
    assert app is not None
    assert app.name == "jellyfin"
    assert app.enabled is True
    assert app.compose_content == "compose content here"


def test_compose_content_persists(tmp_path):
    state = State(state_dir=tmp_path)
    state.set_app("jellyfin", "services:\n  jellyfin: {}")
    state.save()
    state2 = State(state_dir=tmp_path)
    app = state2.get_app("jellyfin")
    assert app is not None
    assert app.compose_content == "services:\n  jellyfin: {}"


def test_is_changed_new_app(tmp_path):
    state = State(state_dir=tmp_path)
    assert state.is_changed("jellyfin", "some content") is True


def test_is_changed_same_content(tmp_path):
    state = State(state_dir=tmp_path)
    state.set_app("jellyfin", "some content")
    assert state.is_changed("jellyfin", "some content") is False


def test_is_changed_different_content(tmp_path):
    state = State(state_dir=tmp_path)
    state.set_app("jellyfin", "old content")
    assert state.is_changed("jellyfin", "new content") is True


def test_state_persists(tmp_path):
    state = State(state_dir=tmp_path)
    state.set_app("jellyfin", "content")
    state.save()

    state2 = State(state_dir=tmp_path)
    app = state2.get_app("jellyfin")
    assert app is not None
    assert app.name == "jellyfin"


def test_remove_app(tmp_path):
    state = State(state_dir=tmp_path)
    state.set_app("jellyfin", "content")
    state.remove_app("jellyfin")
    assert state.get_app("jellyfin") is None


def test_hash_content_deterministic():
    assert hash_content("abc") == hash_content("abc")


def test_hash_content_differs():
    assert hash_content("abc") != hash_content("xyz")
