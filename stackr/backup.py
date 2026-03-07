"""Backup/restore stubs — implemented in Phase 5."""

from __future__ import annotations

from rich.console import Console

console = Console()


def backup(destination: str) -> None:
    console.print("[yellow]Backup not yet implemented (Phase 5).[/yellow]")


def restore(snapshot: str) -> None:
    console.print("[yellow]Restore not yet implemented (Phase 5).[/yellow]")
