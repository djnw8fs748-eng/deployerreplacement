"""Stackr REST API — FastAPI shell over the engine."""
try:
    import fastapi as _fastapi  # noqa: F401
    HAS_API = True
except ImportError:
    HAS_API = False
