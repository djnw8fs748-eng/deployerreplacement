"""Tests for image digest tracking."""

from __future__ import annotations

from stackr.images import (
    collect_digests,
    get_compose_images,
    get_local_image_digest,
    images_changed,
)
from stackr.state import State

# ---------------------------------------------------------------------------
# get_local_image_digest
# ---------------------------------------------------------------------------


def test_get_local_image_digest_returns_digest(mocker):
    mocker.patch(
        "subprocess.run",
        return_value=mocker.Mock(
            returncode=0,
            stdout="jellyfin/jellyfin@sha256:abc123def456\n",
        ),
    )
    result = get_local_image_digest("jellyfin/jellyfin:latest")
    assert result == "jellyfin/jellyfin@sha256:abc123def456"


def test_get_local_image_digest_returns_none_on_failure(mocker):
    mocker.patch("subprocess.run", return_value=mocker.Mock(returncode=1, stdout=""))
    result = get_local_image_digest("nonexistent:latest")
    assert result is None


def test_get_local_image_digest_returns_none_without_sha(mocker):
    mocker.patch(
        "subprocess.run",
        return_value=mocker.Mock(returncode=0, stdout="<no value>\n"),
    )
    result = get_local_image_digest("localimage:latest")
    assert result is None


# ---------------------------------------------------------------------------
# get_compose_images
# ---------------------------------------------------------------------------


def test_get_compose_images_single_service():
    content = """
services:
  jellyfin:
    image: jellyfin/jellyfin:latest
"""
    assert get_compose_images(content) == ["jellyfin/jellyfin:latest"]


def test_get_compose_images_multiple_services():
    content = """
services:
  app:
    image: foo/app:1.0
  db:
    image: postgres:16-alpine
"""
    images = get_compose_images(content)
    assert "foo/app:1.0" in images
    assert "postgres:16-alpine" in images
    assert len(images) == 2


def test_get_compose_images_skips_services_without_image():
    content = """
services:
  app:
    image: foo/app:latest
  sidecar:
    build: .
"""
    images = get_compose_images(content)
    assert images == ["foo/app:latest"]


def test_get_compose_images_invalid_yaml():
    assert get_compose_images("not: valid: yaml: {{{") == []


def test_get_compose_images_empty():
    assert get_compose_images("") == []


# ---------------------------------------------------------------------------
# collect_digests
# ---------------------------------------------------------------------------


def test_collect_digests_returns_map(mocker):
    mocker.patch(
        "subprocess.run",
        return_value=mocker.Mock(
            returncode=0,
            stdout="jellyfin/jellyfin@sha256:abc123\n",
        ),
    )
    content = "services:\n  jellyfin:\n    image: jellyfin/jellyfin:latest\n"
    result = collect_digests(content)
    assert result == {"jellyfin/jellyfin:latest": "jellyfin/jellyfin@sha256:abc123"}


def test_collect_digests_skips_unavailable(mocker):
    mocker.patch("subprocess.run", return_value=mocker.Mock(returncode=1, stdout=""))
    content = "services:\n  app:\n    image: foo:latest\n"
    result = collect_digests(content)
    assert result == {}


# ---------------------------------------------------------------------------
# images_changed
# ---------------------------------------------------------------------------


def test_images_changed_returns_false_no_state(tmp_path):
    state = State(state_dir=tmp_path)
    content = "services:\n  app:\n    image: foo:latest\n"
    # No state for this app yet — falls back to False (compose-hash handles new apps)
    assert images_changed("myapp", content, state) is False


def test_images_changed_returns_false_no_stored_digests(tmp_path):
    state = State(state_dir=tmp_path)
    state.set_app("myapp", "content", image_digests={})
    content = "services:\n  app:\n    image: foo:latest\n"
    assert images_changed("myapp", content, state) is False


def test_images_changed_detects_change(mocker, tmp_path):
    state = State(state_dir=tmp_path)
    # Stored with old digest
    state.set_app("myapp", "old", image_digests={"foo:latest": "foo@sha256:old"})

    # Current inspect returns new digest
    mocker.patch(
        "subprocess.run",
        return_value=mocker.Mock(returncode=0, stdout="foo@sha256:new\n"),
    )
    content = "services:\n  myapp:\n    image: foo:latest\n"
    assert images_changed("myapp", content, state) is True


def test_images_changed_returns_false_when_same(mocker, tmp_path):
    state = State(state_dir=tmp_path)
    state.set_app("myapp", "content", image_digests={"foo:latest": "foo@sha256:abc"})

    mocker.patch(
        "subprocess.run",
        return_value=mocker.Mock(returncode=0, stdout="foo@sha256:abc\n"),
    )
    content = "services:\n  myapp:\n    image: foo:latest\n"
    assert images_changed("myapp", content, state) is False


def test_images_changed_returns_false_when_docker_unavailable(mocker, tmp_path):
    state = State(state_dir=tmp_path)
    state.set_app("myapp", "content", image_digests={"foo:latest": "foo@sha256:abc"})

    mocker.patch("subprocess.run", return_value=mocker.Mock(returncode=1, stdout=""))
    content = "services:\n  myapp:\n    image: foo:latest\n"
    # Cannot get current digest — do not trigger false positive
    assert images_changed("myapp", content, state) is False
