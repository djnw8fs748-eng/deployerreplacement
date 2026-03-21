"""Tests for state lock file."""


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


def test_image_digests_stored_and_retrieved(tmp_path):
    state = State(state_dir=tmp_path)
    digests = {"jellyfin/jellyfin:latest": "jellyfin/jellyfin@sha256:abc123"}
    state.set_app("jellyfin", "content", image_digests=digests)
    app = state.get_app("jellyfin")
    assert app is not None
    assert app.image_digests == digests


def test_image_digests_default_empty(tmp_path):
    state = State(state_dir=tmp_path)
    state.set_app("jellyfin", "content")
    app = state.get_app("jellyfin")
    assert app is not None
    assert app.image_digests == {}


def test_image_digests_survive_round_trip(tmp_path):
    state = State(state_dir=tmp_path)
    digests = {"foo:latest": "foo@sha256:deadbeef"}
    state.set_app("myapp", "content", image_digests=digests)
    state.save()

    state2 = State(state_dir=tmp_path)
    app = state2.get_app("myapp")
    assert app is not None
    assert app.image_digests == digests


def test_image_digests_missing_in_old_state_defaults_empty(tmp_path):
    """Pre-Wave-3 state files without image_digests field should load as {}."""
    import json

    state_file = tmp_path / "state.json"
    # Write a state file without image_digests (simulating old format)
    state_file.write_text(json.dumps({
        "apps": {
            "jellyfin": {
                "enabled": True,
                "compose_hash": "abc123",
                "compose_content": "services: {}",
                "deployed_at": "2025-01-01T00:00:00+00:00",
            }
        },
        "deployed_at": "2025-01-01T00:00:00+00:00",
        "catalog_version": None,
    }))
    state = State(state_dir=tmp_path)
    app = state.get_app("jellyfin")
    assert app is not None
    assert app.image_digests == {}


def test_hash_content_is_full_sha256():
    """hash_content must return a full 64-character hex digest (not truncated)."""
    h = hash_content("some compose content")
    assert len(h) == 64, f"Expected 64-char hex digest, got {len(h)}"
    assert all(c in "0123456789abcdef" for c in h)
