"""Stackr web UI — optional FastAPI + HTMX interface.

Import guard::

    from stackr.web import HAS_FASTAPI
    if HAS_FASTAPI:
        from stackr.web.app import create_app
"""

from __future__ import annotations

HAS_FASTAPI: bool
try:
    import fastapi as _fastapi  # noqa: F401

    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
