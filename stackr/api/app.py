"""FastAPI application factory for the Stackr REST API."""
from __future__ import annotations

from pathlib import Path
from typing import Any

# Two levels up from stackr/api/app.py -> stackr/ -> web/static/
_STATIC_DIR = Path(__file__).parent.parent / "web" / "static"


def create_api(config_path: Path = Path("stackr.yml")) -> Any:
    """Create and return the Stackr REST API FastAPI application."""
    try:
        import fastapi
    except ImportError as exc:
        raise RuntimeError("FastAPI is not installed.") from exc

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    from stackr.api.deps import set_config_path
    from stackr.api.routes.apps import router as apps_router
    from stackr.api.routes.catalog import router as catalog_router
    from stackr.api.routes.config import router as config_router
    from stackr.api.routes.deploy import router as deploy_router
    from stackr.api.routes.mounts import router as mounts_router
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
    api.include_router(config_router)
    api.include_router(apps_router)
    api.include_router(deploy_router)
    api.include_router(mounts_router)
    app.include_router(api)

    # Serve static SPA — only when files are present
    if _STATIC_DIR.exists():
        @app.get("/", response_class=FileResponse, include_in_schema=False)
        def spa_root() -> FileResponse:
            return FileResponse(str(_STATIC_DIR / "index.html"))

        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    return app
