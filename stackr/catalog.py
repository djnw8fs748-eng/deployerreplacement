"""Compatibility shim — use stackr.engine.catalog directly."""
from stackr.engine.catalog import *  # noqa: F401, F403
from stackr.engine.catalog import (  # noqa: F401
    BUILTIN_CATALOG,
    USER_CATALOG,
    Catalog,
    CatalogApp,
    VarDef,
    VolumeSpec,
    _load_app,
)
