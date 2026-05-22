"""Compatibility shim — use stackr.engine.secrets directly."""
from stackr.engine.secrets import *  # noqa: F401, F403
from stackr.engine.secrets import (  # noqa: F401
    ENV_FILE_NAME,
    _append_to_env_file,
    build_env,
    ensure_secret,
    find_unresolved,
    generate_secret,
    init_env_file,
    load_env_file,
    resolve,
    resolve_dict,
)
