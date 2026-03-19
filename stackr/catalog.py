"""App catalog loader.

The catalog is a directory tree:
  catalog/<category>/<app-name>/app.yml
  catalog/<category>/<app-name>/compose.yml.j2
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

BUILTIN_CATALOG = Path(__file__).parent.parent / "catalog"


class VarDef(BaseModel):
    type: str = "string"  # string | select | boolean | integer
    options: list[str] = Field(default_factory=list)
    default: Any = None
    description: str = ""


class VolumeSpec(BaseModel):
    name: str
    path: str
    external: bool = False


class CatalogApp(BaseModel):
    name: str
    display_name: str = ""
    description: str = ""
    category: str = ""
    icon: str = ""
    homepage: str = ""
    version: str = "latest"
    exposure: str = "external"  # external | internal | hybrid
    requires: list[str] = Field(default_factory=list)
    suggests: list[str] = Field(default_factory=list)
    vars: dict[str, VarDef] = Field(default_factory=dict)
    ports: list[int] = Field(default_factory=list)
    host_ports: list[int] = Field(default_factory=list)
    volumes: list[VolumeSpec] = Field(default_factory=list)
    catalog_dir: Path = Field(exclude=True, default=Path("."))

    model_config = {"arbitrary_types_allowed": True}

    @property
    def compose_template_path(self) -> Path:
        return self.catalog_dir / "compose.yml.j2"

    def has_compose_template(self) -> bool:
        return self.compose_template_path.exists()


class Catalog:
    def __init__(self, catalog_dir: Path = BUILTIN_CATALOG) -> None:
        self._dir = catalog_dir
        self._apps: dict[str, CatalogApp] = {}
        self._load()

    def _load(self) -> None:
        if not self._dir.exists():
            return
        for app_yml in sorted(self._dir.glob("*/*/app.yml")):
            app = _load_app(app_yml)
            self._apps[app.name] = app

    def get(self, name: str) -> CatalogApp | None:
        return self._apps.get(name)

    def all(self) -> list[CatalogApp]:
        return list(self._apps.values())

    def by_category(self, category: str) -> list[CatalogApp]:
        return [a for a in self._apps.values() if a.category == category]

    def search(self, query: str) -> list[CatalogApp]:
        q = query.lower()
        return [
            a for a in self._apps.values()
            if q in a.name.lower() or q in a.display_name.lower() or q in a.description.lower()
        ]

    def categories(self) -> list[str]:
        return sorted({a.category for a in self._apps.values()})


def _load_app(app_yml: Path) -> CatalogApp:
    with open(app_yml) as f:
        data = yaml.safe_load(f)

    # Normalise volume entries
    raw_vols = data.pop("volumes", [])
    volumes = []
    for v in raw_vols:
        if isinstance(v, dict):
            volumes.append(VolumeSpec(**v))
        else:
            volumes.append(VolumeSpec(name=str(v), path=str(v)))
    data["volumes"] = volumes

    # Normalise var definitions
    raw_vars = data.pop("vars", {})
    var_defs = {}
    for k, v in raw_vars.items():
        if isinstance(v, dict):
            var_defs[k] = VarDef(**v)
        else:
            var_defs[k] = VarDef(default=v)
    data["vars"] = var_defs

    app = CatalogApp(**data, catalog_dir=app_yml.parent)
    return app
