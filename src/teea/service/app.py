"""FastAPI application factory for the TEEA Local Service.

Mounts REST routes, CORS middleware, lifespan events, and static assets for
the Local Test UI workbench.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from teea import __version__
from teea.core.logging import get_logger
from teea.engine import TEEAEngine
from teea.service.endpoints import router as api_router

_logger = get_logger(__name__)

#: Location of the local UI static directory.
LOCAL_UI_DIR = Path(__file__).parent.parent.parent.parent / "local_ui"


def create_app(engine: TEEAEngine | None = None) -> FastAPI:
    """Create and configure the TEEA FastAPI service.

    Args:
        engine: Optional TEEAEngine instance override.

    Returns:
        Configured FastAPI application instance.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        _logger.info("service_starting", version=__version__)
        if not hasattr(app.state, "engine") or app.state.engine is None:
            app.state.engine = engine or TEEAEngine()
        _logger.info("service_ready", engine_version=app.state.engine.version)
        yield
        _logger.info("service_shutting_down")

    app = FastAPI(
        title="TEEA Local AI Service",
        description="Local REST API for Tibetan Editor Enterprise Architecture",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.engine = engine or TEEAEngine()

    # Configure CORS for local frontends (Word Add-in, local browser workbench, VS Code, etc.)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include REST API endpoints
    app.include_router(api_router)

    # Serve Local Test UI at /ui and /
    if LOCAL_UI_DIR.exists() and LOCAL_UI_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(LOCAL_UI_DIR)), name="static")

        @app.get("/ui", response_class=HTMLResponse)
        @app.get("/", response_class=HTMLResponse)
        async def serve_ui() -> FileResponse:
            index_path = LOCAL_UI_DIR / "index.html"
            return FileResponse(index_path)

    return app
