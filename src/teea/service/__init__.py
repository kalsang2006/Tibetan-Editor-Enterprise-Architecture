"""Local Service Layer for TEEA.

Provides a FastAPI REST server exposing the Core Engine over HTTP.
"""

from __future__ import annotations

from teea.service.app import create_app
from teea.service.server import run_service

__all__ = ["create_app", "run_service"]
