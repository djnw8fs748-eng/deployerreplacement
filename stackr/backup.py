"""Compatibility shim — use stackr.engine.backup directly."""
from stackr.engine.backup import *  # noqa: F401, F403
from stackr.engine.backup import (  # noqa: F401
    _check_restic,
    _ensure_repo_initialized,
    _restic_env,
    backup,
    list_snapshots,
    restore,
)
