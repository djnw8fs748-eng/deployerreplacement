"""Compatibility shim — use stackr.engine.validator directly."""
from stackr.engine.validator import *  # noqa: F401, F403
from stackr.engine.validator import (  # noqa: F401
    ValidationError,
    ValidationResult,
    validate,
)
