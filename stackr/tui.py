"""Interactive TUI for browsing and toggling catalog apps.

Launch with: stackr ui

Requires the optional ``textual`` dependency:
    pip install 'stackr[tui]'
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, ScrollableContainer
    from textual.widgets import Footer, Header, Static, Tree
    from textual.widgets.tree import TreeNode

    HAS_TEXTUAL = True
except ImportError:  # pragma: no cover
    HAS_TEXTUAL = False

_DEFAULT_CONFIG = Path("stackr.yml")


# ---------------------------------------------------------------------------
# Helpers — importable even when textual is absent
# ---------------------------------------------------------------------------


def load_enabled(config_path: Path) -> set[str]:
    """Return the set of enabled app names from an existing stackr.yml, or empty set."""
    if not config_path.exists():
        return set()
    try:
        with open(config_path) as f:
            raw: dict[str, Any] = yaml.safe_load(f) or {}
        return {
            a["name"] for a in raw.get("apps", [])
            if isinstance(a, dict) and a.get("enabled", True)
        }
    except Exception:  # noqa: BLE001
        return set()


def build_stub_config(config_path: Path) -> dict[str, Any]:
    """Return the raw YAML dict from config_path, or a minimal skeleton."""
    if config_path.exists():
        try:
            with open(config_path) as f:
                raw: dict[str, Any] = yaml.safe_load(f) or {}
            return raw
        except Exception:  # noqa: BLE001
            pass
    return {
        "global": {"data_dir": "/opt/appdata", "timezone": "UTC", "puid": 1000, "pgid": 1000},
        "network": {
            "mode": "external",
            "domain": "example.com",
            "local_domain": "home.example.com",
        },
        "traefik": {
            "enabled": True,
            "acme_email": "",
            "dns_provider": "cloudflare",
            "dns_provider_env": {"CF_DNS_API_TOKEN": "${CF_DNS_API_TOKEN}"},
        },
        "security": {"socket_proxy": True, "crowdsec": False, "auth_provider": "none"},
        "backup": {"enabled": False, "destination": "/mnt/backup", "schedule": "0 2 * * *"},
        "apps": [],
    }


# ---------------------------------------------------------------------------
# TUI — only defined when textual is available
# ---------------------------------------------------------------------------

if HAS_TEXTUAL:

    class StackrTUI(App[None]):  # type: ignore[misc]
        """Browse and toggle catalog apps interactively."""

        TITLE = "Stackr"
        SUB_TITLE = "App Catalog Browser"

        CSS = """
        #sidebar {
            width: 42;
            border-right: solid $primary;
        }
        #detail-pane {
            padding: 1 2;
        }
        Tree {
            padding: 0 1;
        }
        """

        BINDINGS = [
            Binding("space", "toggle_app", "Toggle on/off", show=True),
            Binding("s", "save_config", "Save config", show=True),
            Binding("q", "quit", "Quit", show=True),
        ]

        def __init__(
            self,
            config_path: Path = _DEFAULT_CONFIG,
            catalog: Any = None,
        ) -> None:
            super().__init__()
            self._config_path = config_path
            if catalog is None:
                from stackr.catalog import Catalog

                self._catalog = Catalog()
            else:
                self._catalog = catalog
            self._enabled: set[str] = load_enabled(config_path)

        # ------------------------------------------------------------------
        # Compose
        # ------------------------------------------------------------------

        def compose(self) -> ComposeResult:
            yield Header()
            with Horizontal():
                with ScrollableContainer(id="sidebar"):
                    yield Tree("Catalog", id="catalog-tree")
                with ScrollableContainer(id="detail-pane"):
                    yield Static(
                        "Highlight an app to see details.\n\n"
                        "[dim]Space[/dim] toggle  •  [dim]S[/dim] save  •  [dim]Q[/dim] quit",
                        id="detail-content",
                    )
            yield Footer()

        def on_mount(self) -> None:
            tree: Tree[str | None] = self.query_one("#catalog-tree", Tree)  # type: ignore[type-arg]
            tree.root.expand()

            for category in self._catalog.categories():
                cat_node: TreeNode[str | None] = tree.root.add(  # type: ignore[type-arg]
                    f"[bold]{category}[/bold]", expand=True
                )
                for app in sorted(self._catalog.by_category(category), key=lambda a: a.name):
                    marker = "✓" if app.name in self._enabled else "○"
                    label = f"{marker} {app.display_name or app.name}"
                    cat_node.add_leaf(label, data=app.name)

        # ------------------------------------------------------------------
        # Events
        # ------------------------------------------------------------------

        def on_tree_node_highlighted(  # type: ignore[override]
            self,
            event: Tree.NodeHighlighted[str | None],
        ) -> None:
            if event.node.data is None:
                return  # category node
            app_name: str = event.node.data
            ca = self._catalog.get(app_name)
            if ca is None:
                return
            self.query_one("#detail-content", Static).update(self._detail_markup(ca))

        # ------------------------------------------------------------------
        # Actions
        # ------------------------------------------------------------------

        def action_toggle_app(self) -> None:
            tree: Tree[str | None] = self.query_one("#catalog-tree", Tree)  # type: ignore[type-arg]
            node = tree.cursor_node
            if node is None or node.data is None:
                return  # no selection or category node
            app_name: str = node.data
            if app_name in self._enabled:
                self._enabled.discard(app_name)
                marker = "○"
            else:
                self._enabled.add(app_name)
                marker = "✓"
            ca = self._catalog.get(app_name)
            display = (ca.display_name or app_name) if ca else app_name
            node.set_label(f"{marker} {display}")
            if ca:
                self.query_one("#detail-content", Static).update(self._detail_markup(ca))

        def action_save_config(self) -> None:
            """Write current toggle state back to stackr.yml."""
            raw = build_stub_config(self._config_path)
            existing: dict[str, dict[str, Any]] = {
                a["name"]: a
                for a in raw.get("apps", [])
                if isinstance(a, dict) and "name" in a
            }
            apps_out: list[dict[str, Any]] = []
            catalog_names: set[str] = set()
            for category in self._catalog.categories():
                for ca in sorted(self._catalog.by_category(category), key=lambda a: a.name):
                    catalog_names.add(ca.name)
                    if ca.name in self._enabled:
                        entry = dict(existing.get(ca.name, {"name": ca.name}))
                        entry["enabled"] = True
                        apps_out.append(entry)
                    elif ca.name in existing:
                        entry = dict(existing[ca.name])
                        entry["enabled"] = False
                        apps_out.append(entry)
            # Preserve apps not present in the current catalog (e.g. local catalog_path apps)
            for name, entry in existing.items():
                if name not in catalog_names:
                    apps_out.append(dict(entry))
            raw["apps"] = apps_out
            with open(self._config_path, "w") as f:
                yaml.dump(raw, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            self.notify(f"Saved to {self._config_path}", title="Config saved")

        # ------------------------------------------------------------------
        # Helpers
        # ------------------------------------------------------------------

        def _detail_markup(self, ca: Any) -> str:
            enabled_str = (
                "[bold green]✓ ENABLED[/bold green]"
                if ca.name in self._enabled
                else "[dim]○ disabled[/dim]"
            )
            lines: list[str] = [
                f"[bold]{ca.display_name or ca.name}[/bold]  {enabled_str}",
                "",
                ca.description or "(no description)",
                "",
                f"[dim]Category:[/dim]  {ca.category}",
            ]
            if ca.homepage:
                lines.append(f"[dim]Homepage:[/dim]  {ca.homepage}")
            if ca.requires:
                lines.append(f"[dim]Requires:[/dim]  {', '.join(ca.requires)}")
            if ca.suggests:
                lines.append(f"[dim]Suggests:[/dim]  {', '.join(ca.suggests)}")
            if ca.host_ports:
                lines.append(f"[dim]Host ports:[/dim] {', '.join(str(p) for p in ca.host_ports)}")
            if ca.vars:
                lines += ["", "[dim]Variables:[/dim]"]
                for vname, vdef in ca.vars.items():
                    opts = f" ({', '.join(vdef.options)})" if vdef.options else ""
                    lines.append(f"  • [bold]{vname}[/bold] = {vdef.default!r}{opts}")
                    if vdef.description:
                        lines.append(f"    {vdef.description}")
            lines += [
                "",
                "[dim]──────────────────────────[/dim]",
                "[dim]Space[/dim] toggle  •  [dim]S[/dim] save  •  [dim]Q[/dim] quit",
            ]
            return "\n".join(lines)
