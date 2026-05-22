"""Compatibility shim."""
from stackr.engine.docker import get_image_digests  # noqa: F401


def images_changed(app_name: str, compose_content: str, state: object) -> bool:  # type: ignore[return]
    """Legacy function — always returns True to force re-check."""
    return True
