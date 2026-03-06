"""Docker network setup."""

from __future__ import annotations

import subprocess


PROXY_NETWORK = "proxy"
SOCKET_PROXY_NETWORK = "socket_proxy"


def ensure_networks(socket_proxy: bool = True) -> None:
    _ensure_network(PROXY_NETWORK)
    if socket_proxy:
        _ensure_network(SOCKET_PROXY_NETWORK)


def _ensure_network(name: str) -> None:
    result = subprocess.run(
        ["docker", "network", "inspect", name],
        capture_output=True,
    )
    if result.returncode != 0:
        subprocess.run(
            ["docker", "network", "create", name],
            check=True,
        )
