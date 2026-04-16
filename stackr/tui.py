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
    from textual.containers import Horizontal, ScrollableContainer, Vertical
    from textual.screen import ModalScreen
    from textual.widgets import Button, Footer, Header, Input, Label, Static, Tree
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


def load_settings(config_path: Path) -> dict[str, Any]:
    """Return a dict with 'global', 'network' sections from config_path."""
    if not config_path.exists():
        return {}
    try:
        with open(config_path) as f:
            raw: dict[str, Any] = yaml.safe_load(f) or {}
        return {
            k: dict(raw[k]) for k in ("global", "network") if k in raw
        }
    except Exception:  # noqa: BLE001
        return {}


def load_app_vars(config_path: Path) -> dict[str, dict[str, Any]]:
    """Return a dict mapping app name → vars dict from an existing stackr.yml."""
    if not config_path.exists():
        return {}
    try:
        with open(config_path) as f:
            raw: dict[str, Any] = yaml.safe_load(f) or {}
        return {
            a["name"]: dict(a.get("vars") or {})
            for a in raw.get("apps", [])
            if isinstance(a, dict) and "name" in a and a.get("vars")
        }
    except Exception:  # noqa: BLE001
        return {}


def load_mounts(config_path: Path) -> list[dict[str, Any]]:
    """Return the list of mount dicts from an existing stackr.yml, or empty list."""
    if not config_path.exists():
        return []
    try:
        with open(config_path) as f:
            raw: dict[str, Any] = yaml.safe_load(f) or {}
        return [dict(m) for m in (raw.get("mounts") or []) if isinstance(m, dict)]
    except Exception:  # noqa: BLE001
        return []


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
            "domain": "example.com",
            "local_domain": "home.example.com",
        },
        "security": {"socket_proxy": True, "crowdsec": False},
        "backup": {"enabled": False, "destination": "/mnt/backup", "schedule": "0 2 * * *"},
        "apps": [],
    }


# ---------------------------------------------------------------------------
# TUI — only defined when textual is available
# ---------------------------------------------------------------------------

if HAS_TEXTUAL:

    class SettingsEditorScreen(ModalScreen):  # type: ignore[misc]
        """Modal dialog for editing global/network settings."""

        CSS = """
        SettingsEditorScreen {
            align: center middle;
        }
        #settings-dialog {
            width: 64;
            background: $surface;
            border: solid $primary;
            padding: 1 2;
        }
        #settings-buttons {
            margin-top: 1;
            align: right middle;
        }
        #settings-buttons Button {
            margin-left: 1;
        }
        """

        def __init__(self, settings: dict[str, Any]) -> None:
            super().__init__()
            self._settings = settings

        def compose(self) -> ComposeResult:
            g = self._settings.get("global") or {}
            n = self._settings.get("network") or {}
            with Vertical(id="settings-dialog"):
                yield Label("[bold]Global[/bold]")
                yield Input(
                    placeholder="Data directory",
                    value=str(g.get("data_dir", "/opt/appdata")),
                    id="inp-data-dir",
                )
                yield Input(
                    placeholder="Timezone (e.g. UTC)",
                    value=str(g.get("timezone", "UTC")),
                    id="inp-timezone",
                )
                yield Input(
                    placeholder="PUID",
                    value=str(g.get("puid", 1000)),
                    id="inp-puid",
                )
                yield Input(
                    placeholder="PGID",
                    value=str(g.get("pgid", 1000)),
                    id="inp-pgid",
                )
                yield Label("[bold]Network[/bold]")
                yield Input(
                    placeholder="Public domain",
                    value=str(n.get("domain", "")),
                    id="inp-domain",
                )
                yield Input(
                    placeholder="Local domain",
                    value=str(n.get("local_domain", "")),
                    id="inp-local-domain",
                )
                with Horizontal(id="settings-buttons"):
                    yield Button("Save", variant="primary", id="btn-save")
                    yield Button("Cancel", variant="default", id="btn-cancel")

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "btn-cancel":
                self.dismiss(None)
                return
            # Save — collect all field values
            g = dict(self._settings.get("global") or {})
            n = dict(self._settings.get("network") or {})

            g["data_dir"] = self.query_one("#inp-data-dir", Input).value
            g["timezone"] = self.query_one("#inp-timezone", Input).value
            try:
                g["puid"] = int(self.query_one("#inp-puid", Input).value)
            except ValueError:
                g["puid"] = 1000
            try:
                g["pgid"] = int(self.query_one("#inp-pgid", Input).value)
            except ValueError:
                g["pgid"] = 1000

            n["domain"] = self.query_one("#inp-domain", Input).value
            n["local_domain"] = self.query_one("#inp-local-domain", Input).value

            self.dismiss({"global": g, "network": n})

    class MountEditorScreen(ModalScreen):  # type: ignore[misc]
        """Modal dialog for adding or editing a mount entry."""

        CSS = """
        MountEditorScreen {
            align: center middle;
        }
        #mount-dialog {
            width: 64;
            height: auto;
            border: solid $primary;
            background: $surface;
            padding: 1 2;
        }
        #mount-dialog Label {
            margin-bottom: 1;
        }
        #mount-dialog Input {
            margin-bottom: 1;
        }
        #mount-buttons {
            margin-top: 1;
            height: auto;
        }
        """

        def __init__(self, mount: dict[str, Any] | None = None) -> None:
            super().__init__()
            self._existing: dict[str, Any] = mount or {}

        def compose(self) -> ComposeResult:
            m = self._existing
            with Vertical(id="mount-dialog"):
                yield Label("[bold]Mount Editor[/bold]")
                yield Input(
                    placeholder="name (e.g. media)",
                    value=str(m.get("name", "")),
                    id="inp-name",
                )
                yield Input(
                    placeholder="type: smb | nfs | rclone",
                    value=str(m.get("type", "smb")),
                    id="inp-type",
                )
                yield Input(
                    placeholder="remote (e.g. //192.168.1.10/share)",
                    value=str(m.get("remote", "")),
                    id="inp-remote",
                )
                yield Input(
                    placeholder="mountpoint (e.g. /mnt/media)",
                    value=str(m.get("mountpoint", "")),
                    id="inp-mountpoint",
                )
                yield Input(
                    placeholder="options (optional, e.g. ro,noatime)",
                    value=str(m.get("options", "")),
                    id="inp-options",
                )
                yield Input(
                    placeholder="username (optional)",
                    value=str(m.get("username", "")),
                    id="inp-username",
                )
                with Horizontal(id="mount-buttons"):
                    yield Button("Save", variant="primary", id="btn-save")
                    yield Button("Cancel", variant="default", id="btn-cancel")

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "btn-cancel":
                self.dismiss(None)
                return
            name = self.query_one("#inp-name", Input).value.strip()
            if not name:
                self.notify("Name is required", severity="error")
                return
            mount_type = self.query_one("#inp-type", Input).value.strip() or "smb"
            remote = self.query_one("#inp-remote", Input).value.strip()
            mountpoint = self.query_one("#inp-mountpoint", Input).value.strip()
            options = self.query_one("#inp-options", Input).value.strip()
            username = self.query_one("#inp-username", Input).value.strip()
            result: dict[str, Any] = {
                "name": name,
                "type": mount_type,
                "remote": remote,
                "mountpoint": mountpoint,
            }
            if options:
                result["options"] = options
            if username:
                result["username"] = username
            self.dismiss(result)

    class VarEditorScreen(ModalScreen):  # type: ignore[misc]
        """Modal dialog for editing per-app variables."""

        CSS = """
        VarEditorScreen {
            align: center middle;
        }
        #var-dialog {
            width: 70;
            height: auto;
            max-height: 80%;
            border: solid $primary;
            background: $surface;
            padding: 1 2;
        }
        #var-dialog Label {
            margin-bottom: 0;
        }
        .var-label {
            color: $text-muted;
        }
        #var-dialog Input {
            margin-bottom: 1;
        }
        #var-buttons {
            margin-top: 1;
            height: auto;
        }
        """

        def __init__(self, app_name: str, var_defs: Any, current_vars: dict[str, Any]) -> None:
            super().__init__()
            self._app_name = app_name
            self._var_defs = var_defs  # dict[str, VarDef]
            self._current_vars = current_vars

        def compose(self) -> ComposeResult:
            with ScrollableContainer(id="var-dialog"):
                yield Label(f"[bold]Variables — {self._app_name}[/bold]")
                for vname, vdef in self._var_defs.items():
                    current = self._current_vars.get(vname, vdef.default)
                    hint = f"{vname}"
                    if vdef.options:
                        hint += f"  ({' | '.join(str(o) for o in vdef.options)})"
                    elif vdef.type == "boolean":
                        hint += "  (true | false)"
                    elif vdef.type == "integer":
                        hint += "  (integer)"
                    if vdef.description:
                        hint += f"  — {vdef.description}"
                    yield Label(hint, classes="var-label")
                    yield Input(
                        placeholder=str(vdef.default) if vdef.default is not None else "",
                        value=str(current) if current is not None else "",
                        id=f"var-{vname}",
                    )
                with Horizontal(id="var-buttons"):
                    yield Button("Save", variant="primary", id="btn-save")
                    yield Button("Cancel", variant="default", id="btn-cancel")

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "btn-cancel":
                self.dismiss(None)
                return
            result: dict[str, Any] = {}
            for vname, vdef in self._var_defs.items():
                raw = self.query_one(f"#var-{vname}", Input).value.strip()
                if not raw:
                    # Use default when field is cleared
                    result[vname] = vdef.default
                    continue
                if vdef.type == "boolean":
                    result[vname] = raw.lower() in ("true", "yes", "1", "on")
                elif vdef.type == "integer":
                    try:
                        result[vname] = int(raw)
                    except ValueError:
                        result[vname] = vdef.default
                else:
                    result[vname] = raw
            self.dismiss(result)

    class StackrTUI(App[None]):  # type: ignore[misc]
        """Browse and toggle catalog apps, and manage remote mounts."""

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
            Binding("space", "toggle_app", "Toggle on/off", show=True, priority=True),
            Binding("enter", "toggle_app", "Toggle on/off", show=False, priority=True),
            Binding("a", "add_mount", "Add mount", show=True),
            Binding("e", "edit", "Edit", show=True),
            Binding("v", "edit_vars", "App vars", show=True),
            Binding("d", "delete_mount", "Del mount", show=True),
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
            self._settings: dict[str, Any] = load_settings(config_path)
            self._settings_node: Any = None
            self._mounts: list[dict[str, Any]] = load_mounts(config_path)
            self._mounts_node: Any = None  # set in on_mount
            self._app_vars: dict[str, dict[str, Any]] = load_app_vars(config_path)

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
                        "Highlight an app, mount, or [bold]Settings[/bold] to see details.\n\n"
                        "[dim]Space[/dim] toggle  •  [dim]A[/dim] add mount  •  "
                        "[dim]E[/dim] edit  •  [dim]D[/dim] del mount\n"
                        "[dim]S[/dim] save  •  [dim]Q[/dim] quit",
                        id="detail-content",
                    )
            yield Footer()

        def on_mount(self) -> None:
            tree: Tree[Any] = self.query_one("#catalog-tree", Tree)
            tree.root.expand()

            # Settings node (top of tree)
            self._settings_node = tree.root.add_leaf(
                "⚙  Settings", data={"_type": "settings"}
            )

            # Mounts section
            self._mounts_node = tree.root.add("[bold]mounts[/bold]", expand=True)
            self._refresh_mount_nodes()

            # Apps sections by category
            for category in self._catalog.categories():
                cat_node: TreeNode[Any] = tree.root.add(
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
            event: Tree.NodeHighlighted[Any],
        ) -> None:
            node = event.node
            if node.data is None:
                return  # section header node
            if isinstance(node.data, dict):
                if node.data.get("_type") == "settings":
                    self.query_one("#detail-content", Static).update(
                        self._settings_detail_markup()
                    )
                elif node.data.get("_type") == "mount":
                    self.query_one("#detail-content", Static).update(
                        self._mount_detail_markup(node.data)
                    )
                return
            # String data → app node
            app_name: str = node.data
            ca = self._catalog.get(app_name)
            if ca is None:
                return
            self.query_one("#detail-content", Static).update(self._detail_markup(ca))

        # ------------------------------------------------------------------
        # Actions — apps
        # ------------------------------------------------------------------

        def action_toggle_app(self) -> None:
            tree: Tree[Any] = self.query_one("#catalog-tree", Tree)
            node = tree.cursor_node
            if node is None or not isinstance(node.data, str):
                return  # not an app node
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

        # ------------------------------------------------------------------
        # Actions — edit (context-sensitive: settings or mount)
        # ------------------------------------------------------------------

        def action_edit(self) -> None:
            """Edit the currently highlighted settings node or mount node."""
            tree: Tree[Any] = self.query_one("#catalog-tree", Tree)
            node = tree.cursor_node
            if node is None or not isinstance(node.data, dict):
                self.notify(
                    "Select the Settings entry or a mount to edit", severity="warning"
                )
                return
            if node.data.get("_type") == "settings":
                self._do_edit_settings()
            elif node.data.get("_type") == "mount":
                self._do_edit_mount(node.data)
            else:
                self.notify(
                    "Select the Settings entry or a mount to edit", severity="warning"
                )

        def _do_edit_settings(self) -> None:
            def _on_result(result: dict[str, Any] | None) -> None:
                if result is None:
                    return
                self._settings = result
                self.query_one("#detail-content", Static).update(
                    self._settings_detail_markup()
                )
                self.notify("Settings updated — press S to save", title="Settings updated")

            self.push_screen(SettingsEditorScreen(self._settings), _on_result)

        def _do_edit_mount(self, data: dict[str, Any]) -> None:
            idx: int = data["_idx"]
            existing = {k: v for k, v in data.items() if not k.startswith("_")}

            def _on_result(result: dict[str, Any] | None) -> None:
                if result is None:
                    return
                self._mounts[idx] = result
                self._refresh_mount_nodes()
                self.notify(
                    f"Mount '{result['name']}' updated — press S to save",
                    title="Mount updated",
                )

            self.push_screen(MountEditorScreen(mount=existing), _on_result)

        # ------------------------------------------------------------------
        # Actions — app vars
        # ------------------------------------------------------------------

        def action_edit_vars(self) -> None:
            """Open the var editor for the currently highlighted app."""
            tree: Tree[Any] = self.query_one("#catalog-tree", Tree)
            node = tree.cursor_node
            if node is None or not isinstance(node.data, str):
                self.notify("Select an app to edit its variables", severity="warning")
                return
            app_name: str = node.data
            ca = self._catalog.get(app_name)
            if ca is None:
                return
            if not ca.vars:
                self.notify(f"'{app_name}' has no configurable variables", severity="information")
                return
            current = self._app_vars.get(app_name, {})
            app_name_ref = app_name  # capture for closure

            def _on_result(result: dict[str, Any] | None) -> None:
                if result is None:
                    return
                # Strip vars that match the default — no need to store them
                cleaned: dict[str, Any] = {}
                for k, v in result.items():
                    vdef = ca.vars.get(k)
                    if vdef is None or v != vdef.default:
                        cleaned[k] = v
                if cleaned:
                    self._app_vars[app_name_ref] = cleaned
                elif app_name_ref in self._app_vars:
                    del self._app_vars[app_name_ref]
                self.query_one("#detail-content", Static).update(self._detail_markup(ca))
                self.notify(
                    f"Vars for '{app_name_ref}' updated — press S to save",
                    title="Vars updated",
                )

            self.push_screen(VarEditorScreen(app_name, ca.vars, current), _on_result)

        # ------------------------------------------------------------------
        # Actions — mounts
        # ------------------------------------------------------------------

        def action_add_mount(self) -> None:
            def _on_result(result: dict[str, Any] | None) -> None:
                if result is None:
                    return
                self._mounts.append(result)
                self._refresh_mount_nodes()
                self.notify(
                    f"Mount '{result['name']}' added — press S to save",
                    title="Mount added",
                )

            self.push_screen(MountEditorScreen(), _on_result)

        def action_delete_mount(self) -> None:
            tree: Tree[Any] = self.query_one("#catalog-tree", Tree)
            node = tree.cursor_node
            if (
                node is None
                or not isinstance(node.data, dict)
                or node.data.get("_type") != "mount"
            ):
                self.notify("Select a mount entry to delete", severity="warning")
                return
            idx: int = node.data["_idx"]
            name = node.data.get("name", "?")
            self._mounts.pop(idx)
            self._refresh_mount_nodes()
            self.query_one("#detail-content", Static).update(
                "Mount deleted. Press [bold]S[/bold] to save."
            )
            self.notify(f"Mount '{name}' deleted — press S to save", title="Mount deleted")

        def action_save_config(self) -> None:
            """Write current toggle state, settings, and mounts back to stackr.yml."""
            raw = build_stub_config(self._config_path)
            existing: dict[str, dict[str, Any]] = {
                a["name"]: a
                for a in raw.get("apps", [])
                if isinstance(a, dict) and "name" in a
            }

            # Track which apps were previously enabled so we can stop containers
            # for any that are being disabled in this save.
            previously_enabled: set[str] = {
                name
                for name, entry in existing.items()
                if entry.get("enabled", True)
            }

            apps_out: list[dict[str, Any]] = []
            catalog_names: set[str] = set()
            for category in self._catalog.categories():
                for ca in sorted(self._catalog.by_category(category), key=lambda a: a.name):
                    catalog_names.add(ca.name)
                    entry = dict(existing.get(ca.name, {"name": ca.name}))
                    entry["enabled"] = ca.name in self._enabled
                    if ca.name in self._app_vars and self._app_vars[ca.name]:
                        entry["vars"] = self._app_vars[ca.name]
                    elif "vars" in entry and ca.name not in self._app_vars:
                        del entry["vars"]
                    apps_out.append(entry)
            # Preserve apps not present in the current catalog (e.g. local catalog_path apps)
            for name, entry in existing.items():
                if name not in catalog_names:
                    apps_out.append(dict(entry))
            raw["apps"] = apps_out
            for section in ("global", "network"):
                if section in self._settings:
                    raw[section] = self._settings[section]
            raw["mounts"] = self._mounts
            with open(self._config_path, "w") as f:
                yaml.dump(raw, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

            # Stop containers and clear state for apps that were just disabled,
            # so that re-enabling them triggers a fresh deploy rather than SKIP.
            newly_disabled = previously_enabled - self._enabled
            if newly_disabled:
                import subprocess as _sp

                from stackr.deployer import COMPOSE_DIR
                from stackr.state import State as _State
                state = _State()
                for app_name in newly_disabled:
                    compose_path = COMPOSE_DIR / app_name / "docker-compose.yml"
                    if compose_path.exists():
                        _sp.run(
                            ["docker", "compose", "-f", str(compose_path), "stop"],
                            capture_output=True,
                        )
                    state.remove_app(app_name)
                state.save()

            self.notify(f"Saved to {self._config_path}", title="Config saved")

        # ------------------------------------------------------------------
        # Helpers
        # ------------------------------------------------------------------

        def _refresh_mount_nodes(self) -> None:
            """Rebuild the mounts subtree from self._mounts."""
            self._mounts_node.remove_children()
            for i, m in enumerate(self._mounts):
                label = (
                    f"⊞ {m.get('name', '?')}  "
                    f"[{m.get('type', 'smb')}] → {m.get('mountpoint', '')}"
                )
                self._mounts_node.add_leaf(
                    label, data={"_type": "mount", "_idx": i, **m}
                )
            if not self._mounts:
                self._mounts_node.add_leaf(
                    "[dim]No mounts — press A to add one[/dim]",
                    data={"_type": "mount-empty"},
                )

        def _settings_detail_markup(self) -> str:
            g = self._settings.get("global") or {}
            n = self._settings.get("network") or {}
            lines = [
                "[bold]Settings[/bold]",
                "",
                "[dim]── Global ──[/dim]",
                f"  data_dir   {g.get('data_dir', '/opt/appdata')}",
                f"  timezone   {g.get('timezone', 'UTC')}",
                f"  puid/pgid  {g.get('puid', 1000)} / {g.get('pgid', 1000)}",
                "",
                "[dim]── Network ──[/dim]",
                f"  domain       {n.get('domain', '')}",
                f"  local_domain {n.get('local_domain', '')}",
                "",
                "[dim]──────────────────────────[/dim]",
                "[dim]E[/dim] edit  •  [dim]S[/dim] save  •  [dim]Q[/dim] quit",
            ]
            return "\n".join(lines)

        def _mount_detail_markup(self, data: dict[str, Any]) -> str:
            name = data.get("name", "?")
            lines: list[str] = [
                f"[bold]{name}[/bold]  [dim](mount)[/dim]",
                "",
                f"[dim]Type:[/dim]       {data.get('type', 'smb')}",
                f"[dim]Remote:[/dim]     {data.get('remote', '')}",
                f"[dim]Mountpoint:[/dim] {data.get('mountpoint', '')}",
            ]
            if data.get("options"):
                lines.append(f"[dim]Options:[/dim]    {data['options']}")
            if data.get("username"):
                lines.append(f"[dim]Username:[/dim]   {data['username']}")
            lines += [
                "",
                "[dim]──────────────────────────[/dim]",
                "[dim]E[/dim] edit  •  [dim]D[/dim] delete  •  "
                "[dim]S[/dim] save  •  [dim]Q[/dim] quit",
            ]
            return "\n".join(lines)

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
                current_vars = self._app_vars.get(ca.name, {})
                lines += ["", "[dim]Variables:[/dim]"]
                for vname, vdef in ca.vars.items():
                    opts = f" ({' | '.join(str(o) for o in vdef.options)})" if vdef.options else ""
                    # Show current value if overridden, otherwise show default
                    if vname in current_vars:
                        val_str = f"[green]{current_vars[vname]!r}[/green]"
                    else:
                        val_str = f"[dim]{vdef.default!r}[/dim]"
                    lines.append(f"  • [bold]{vname}[/bold] = {val_str}{opts}")
                    if vdef.description:
                        lines.append(f"    [dim]{vdef.description}[/dim]")
            lines += [
                "",
                "[dim]──────────────────────────[/dim]",
                "[dim]Space[/dim] toggle  •  [dim]V[/dim] edit vars  •  "
                "[dim]S[/dim] save  •  [dim]Q[/dim] quit",
            ]
            return "\n".join(lines)
