"""Uvicorn server launcher for the TEEA Local Service.

Provides a clean executable launcher function with OS signal handling (`SIGTERM`/`SIGINT`).
"""

from __future__ import annotations

import signal
import sys
from typing import Any

import uvicorn

from teea.core.logging import get_logger
from teea.engine import TEEAEngine
from teea.service.app import create_app

_logger = get_logger(__name__)


def run_service(
    host: str = "127.0.0.1",
    port: int = 50505,
    engine: TEEAEngine | None = None,
    log_level: str = "info",
) -> None:
    """Launch the TEEA FastAPI service on host and port.

    Args:
        host: Host address (defaults to loopback `127.0.0.1`).
        port: Port number (defaults to `50505`).
        engine: Optional pre-configured TEEAEngine instance.
        log_level: Log level for Uvicorn server.
    """
    app = create_app(engine=engine)

    def _handle_exit(sig: int, frame: Any) -> None:
        _logger.info("received_shutdown_signal", signal=sig)
        sys.exit(0)

    # Register OS signal handlers for graceful shutdown (F1 fix)
    signal.signal(signal.SIGINT, _handle_exit)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_exit)

    _logger.info("starting_local_service", host=host, port=port)
    uvicorn.run(app, host=host, port=port, log_level=log_level.lower())


if __name__ == "__main__":
    import io
    import sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    run_service()
