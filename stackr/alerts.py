"""Health alert notifications.

Sends a notification to the configured provider (ntfy, Gotify, or webhook)
when a deploy fails or `stackr doctor` finds failures.

Failures in the HTTP call are always caught and logged as warnings so that
a broken alert endpoint never aborts a deploy or doctor run.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from stackr.config import AlertConfig

console = Console()


def send_alert(title: str, message: str, config: AlertConfig) -> None:
    """POST a notification to the configured provider.

    Exceptions from the HTTP call are caught and printed as warnings —
    a failed alert must never abort the caller.
    """
    if not config.enabled:
        return
    try:
        _dispatch(title, message, config)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[yellow]Alert could not be sent: {exc}[/yellow]")


def _dispatch(title: str, message: str, config: AlertConfig) -> None:
    """Build and send the provider-specific HTTP request."""
    url = str(config.url)
    token = config.token

    if config.provider == "ntfy":
        req = urllib.request.Request(url, data=message.encode(), method="POST")
        req.add_header("Title", title)
        if token:
            req.add_header("Authorization", f"Bearer {token}")

    elif config.provider == "gotify":
        payload = json.dumps({"title": title, "message": message, "priority": 5}).encode()
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("X-Gotify-Key", token)

    elif config.provider == "webhook":
        payload = json.dumps({"title": title, "message": message}).encode()
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")

    else:
        raise ValueError(f"Unknown alert provider: {config.provider!r}")

    with urllib.request.urlopen(req, timeout=10) as _:  # noqa: S310
        pass
