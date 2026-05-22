"""Catalog routes: browse available apps."""
from __future__ import annotations

import fastapi

from stackr.api.deps import Cat
from stackr.api.models import CatalogAppOut, VarDefOut

router = fastapi.APIRouter(prefix="/catalog", tags=["catalog"])


def _to_out(app: object) -> CatalogAppOut:
    vars_out = [
        VarDefOut(
            name=name,
            default=str(v.default) if v.default is not None else None,
            description=v.description,
            type=v.type,
        )
        for name, v in (getattr(app, "vars", None) or {}).items()
    ]
    return CatalogAppOut(
        name=app.name,
        display_name=app.display_name,
        description=app.description,
        category=app.category,
        vars=vars_out,
        ports=app.ports,
        host_ports=app.host_ports,
        requires=app.requires,
        suggests=app.suggests,
    )


@router.get("/", response_model=list[CatalogAppOut])
def list_catalog(catalog: Cat, search: str | None = None) -> list[CatalogAppOut]:
    apps = catalog.search(search) if search else catalog.all()
    return [_to_out(a) for a in sorted(apps, key=lambda a: (a.category, a.name))]


@router.get("/{name}", response_model=CatalogAppOut)
def get_catalog_app(name: str, catalog: Cat) -> CatalogAppOut:
    app = catalog.get(name)
    if app is None:
        raise fastapi.HTTPException(status_code=404, detail=f"Catalog app '{name}' not found")
    return _to_out(app)
