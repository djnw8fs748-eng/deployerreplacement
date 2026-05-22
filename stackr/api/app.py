"""FastAPI application factory for the Stackr REST API."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def create_api(config_path: Path = Path("stackr.yml")) -> Any:
    """Create and return the Stackr REST API FastAPI application."""
    try:
        import fastapi
    except ImportError as exc:
        raise RuntimeError("FastAPI is not installed.") from exc

    from stackr.api.deps import set_config_path
    from stackr.api.routes.catalog import router as catalog_router
    from stackr.api.routes.system import router as system_router

    set_config_path(config_path)

    app = fastapi.FastAPI(
        title="Stackr API",
        description="REST API for Stackr homelab deployment tool",
        version="2.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    api = fastapi.APIRouter(prefix="/api/v1")
    api.include_router(system_router)
    api.include_router(catalog_router)
    app.include_router(api)

    return app
