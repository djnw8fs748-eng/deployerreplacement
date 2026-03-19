"""Image digest tracking for smarter update detection.

Provides utilities to:
- Inspect locally-pulled image digests via `docker inspect`
- Extract image references from rendered compose YAML
- Detect whether upstream images have changed since last deploy
"""

from __future__ import annotations

import subprocess

import yaml

from stackr.state import State


def get_local_image_digest(image: str) -> str | None:
    """Return the repo digest for a locally-pulled image, or None if unavailable."""
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{index .RepoDigests 0}}", image],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    digest = result.stdout.strip()
    return digest if digest and "@sha256:" in digest else None


def get_compose_images(compose_content: str) -> list[str]:
    """Extract all image references from rendered compose YAML."""
    try:
        parsed = yaml.safe_load(compose_content)
    except yaml.YAMLError:
        return []
    if not isinstance(parsed, dict):
        return []
    services = parsed.get("services", {})
    return [
        svc["image"]
        for svc in services.values()
        if isinstance(svc, dict) and "image" in svc
    ]


def collect_digests(compose_content: str) -> dict[str, str]:
    """Run docker inspect on every image in the compose and return an image→digest map."""
    result: dict[str, str] = {}
    for image in get_compose_images(compose_content):
        digest = get_local_image_digest(image)
        if digest:
            result[image] = digest
    return result


def images_changed(app_name: str, compose_content: str, state: State) -> bool:
    """Return True if any image digest differs from what was stored in state after last deploy.

    Returns False when:
    - No state exists for the app (handled upstream by compose-hash logic)
    - No digest info was stored (pre-Wave-3 state files)
    - Docker is unreachable (cannot collect current digests)
    """
    app_state = state.get_app(app_name)
    if app_state is None or not app_state.image_digests:
        return False
    current = collect_digests(compose_content)
    if not current:
        return False
    return current != app_state.image_digests
