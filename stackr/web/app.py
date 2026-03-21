"""FastAPI application factory for the Stackr web UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def create_app(config_path: Path = Path("stackr.yml")) -> Any:
    """Create and return the FastAPI application.

    Raises RuntimeError if FastAPI is not installed.
    """
    try:
        import fastapi
    except ImportError as exc:
        raise RuntimeError(
            "FastAPI is not installed. Run: pip install 'stackr[web]'"
        ) from exc

    from stackr.web.routes import make_router

    application = fastapi.FastAPI(
        title="Stackr Web UI",
        description="Browser-based management for Stackr",
        version="0.1.0",
        docs_url=None,  # disable Swagger UI for production-ish feel
    )
    application.include_router(make_router(config_path))
    return application
