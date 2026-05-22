"""Compatibility shim — use stackr.engine.renderer directly."""
from stackr.engine.renderer import *  # noqa: F401, F403
from stackr.engine.renderer import (  # noqa: F401
    _apply_overrides,
    _deep_merge,
    _strip_empty_labels,
    render_app,
)
