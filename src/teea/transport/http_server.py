"""Loopback HTTP+SSE bridge serving both analysis and AI endpoints.

Combines the document-analysis pipeline from :mod:`analysis_server` with the
AI streaming handlers from :mod:`teea.ai.handlers` into a single HTTP server,
so the add-in talks to one port for everything.

SSE framing
-----------
The add-in's :class:`~addin.src.taskpane.services.IpcBridge.SseParser` reads
standard ``data: <payload>\\n\\n`` events.  Frame payloads (all JSON):

``{ "token": "…" }``
    One token of generated text.  Multiple token events form the output.
``{ "cancelled": true }``
    The generation was cancelled before it finished.
``{ "error": { "code": "…", "message": "…" } }``
    An error occurred; the generation is over.
``[DONE]`` (as a bare ``data:`` line, not JSON)
    The generation completed normally.

Endpoints
---------
===================== ======= ================================================
Path                  Method  Description
===================== ======= ================================================
``/health``           GET     Liveness check.
``/api/analysis/run`` POST    Run the full analysis pipeline (JSON response).
``/api/ai/rewrite``   POST    AI rewrite (SSE response).
``/api/ai/explain``   POST    AI grammar explanation (SSE response).
``/api/ai/summarize`` POST    AI summarisation (SSE response).
``/api/ai/cancel``    POST    Cancel a running generation (SSE response).
===================== ======= ================================================
"""

from __future__ import annotations

import contextlib
import ipaddress
import json
import sys
import threading
from collections.abc import Mapping
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Final

import structlog
from pydantic import ValidationError

from teea.ai.handlers import AI_ENDPOINT_METHODS, HandlerFn
from teea.core.errors import ConfigurationError, ErrorCode, TEEAError
from teea.fusion import PriorityRankedFusionEngine
from teea.ipc.models import PROTOCOL_VERSION, IpcFault, IpcRequest, IpcResponse
from teea.nlp.snapshot import LanguageServerSnapshotBuilder
from teea.plugins import SupervisedPluginRuntime

logger = structlog.get_logger(__name__)

DEFAULT_HOST: Final = "127.0.0.1"
DEFAULT_PORT: Final = 50505
LOOPBACK_HOSTS: Final = frozenset({"127.0.0.1", "localhost"})
DEFAULT_SESSION_ID: Final = "http-loopback"

ANALYSIS_METHOD: Final = "analysis.run"
ANALYSIS_PATH: Final = "/api/analysis/run"

AI_PATHS: Final = frozenset({
    "/api/ai/rewrite",
    "/api/ai/explain",
    "/api/ai/summarize",
    "/api/ai/cancel",
    "/api/ai/translate",
    "/api/ai/ocr",
    "/api/ai/stt",
})

_EXPECTED_DISCONNECT_ERRORS: Final = (
    ConnectionResetError,
    ConnectionAbortedError,
    BrokenPipeError,
    TimeoutError,
)
_MAX_BODY_SIZE: Final = 10 * 1024 * 1024
_DONE_PAYLOAD: Final = b"[DONE]"


class NotLoopbackError(ConfigurationError):
    """Raised when asked to bind anywhere but a loopback address."""
    default_code = ErrorCode.CONFIGURATION_INVALID


def _validate_loopback(host: str) -> None:
    """Raise unless ``host`` names an IPv4 loopback address."""
    if host in LOOPBACK_HOSTS:
        return
    try:
        parsed = ipaddress.ip_address(host)
    except ValueError as exc:
        raise NotLoopbackError(
            "Refusing to bind to a non-address host.",
            context={"host": host}, cause=exc,
        ) from exc
    if not (parsed.version == 4 and parsed.is_loopback):
        raise NotLoopbackError(
            "Refusing to bind to a non-IPv4-loopback address.",
            context={"host": host},
        )


def _fault_from(exc: Exception) -> IpcFault:
    """Build an ``IpcFault`` from a handler exception."""
    if isinstance(exc, TEEAError):
        return IpcFault(
            code=exc.code.value,
            error_type=type(exc).__name__,
            message=exc.message,
            context=exc.context,
        )
    return IpcFault(
        code=ErrorCode.UNKNOWN.value,
        error_type=type(exc).__name__,
        message=str(exc),
    )


def _send_sse_frame(wfile: Any, payload: bytes) -> None:
    """Write a single SSE frame: ``data: …\\n\\n``."""
    with contextlib.suppress(BrokenPipeError, ConnectionAbortedError, OSError):
        wfile.write(b"data: ")
        wfile.write(payload)
        wfile.write(b"\n\n")
        wfile.flush()


class _BridgeHTTPServer(ThreadingHTTPServer):
    """``ThreadingHTTPServer`` carrying the collaborators every request needs."""

    daemon_threads = True
    allow_reuse_address = True

    builder: LanguageServerSnapshotBuilder
    plugins: SupervisedPluginRuntime
    fusion: PriorityRankedFusionEngine

    def handle_error(self, request: object, client_address: tuple[str, int]) -> None:
        _exc_type, exc, _tb = sys.exc_info()
        if isinstance(exc, _EXPECTED_DISCONNECT_ERRORS):
            logger.debug("http_connection_reset", client=client_address[0], error=str(exc))
            return
        logger.error("http_request_failed", client=client_address[0], exc_info=True)


class _BridgeRequestHandler(BaseHTTPRequestHandler):
    """Serves one HTTP request — analysis or AI streaming."""

    server: _BridgeHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        logger.debug("http_access", client=self.client_address[0], line=format % args)

    # ── CORS ──────────────────────────────────────────────────────────────

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ── GET ───────────────────────────────────────────────────────────────

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(HTTPStatus.OK, {
                "status": "ok",
                "protocol_version": PROTOCOL_VERSION,
            })
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    # ── POST ──────────────────────────────────────────────────────────────

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or "0")
        if length > _MAX_BODY_SIZE:
            self._send_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {"error": {"code": "PAYLOAD_TOO_LARGE", "max_bytes": _MAX_BODY_SIZE}},
            )
            return
        raw = self.rfile.read(length) if length > 0 else b"{}"

        if self.path == ANALYSIS_PATH:
            self._handle_analysis(raw)
        elif self.path in AI_PATHS:
            self._handle_ai_stream(raw)
        else:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": {"code": ErrorCode.IPC_METHOD_NOT_FOUND.value, "path": self.path}},
            )

    # ── Analysis pipeline ─────────────────────────────────────────────────

    def _handle_analysis(self, raw: bytes) -> None:
        try:
            request = IpcRequest.model_validate_json(raw)
        except ValidationError as exc:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": {"code": ErrorCode.IPC_MALFORMED_MESSAGE.value,
                           "message": "invalid IpcRequest",
                           "detail": exc.errors(include_url=False)}},
            )
            return
        if request.method != ANALYSIS_METHOD:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": {"code": ErrorCode.IPC_MALFORMED_MESSAGE.value,
                           "message": "method mismatch"}},
            )
            return

        text = request.params.get("text", "")
        if not isinstance(text, str):
            self._send_ipc_response(
                IpcResponse.failure(
                    request.request_id,
                    IpcFault(code=ErrorCode.INPUT_INVALID.value,
                             error_type="InputValidationError",
                             message="text must be a string"),
                ),
                HTTPStatus.OK,
            )
            return

        try:
            snapshot = self.server.builder.analyze(text)
            plugin_results = self.server.plugins.dispatch(snapshot)
            unified = self.server.fusion.fuse(text, plugin_results.suggestions)
            result = unified.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001 - reported as a fault, not a 500 traceback.
            self._send_ipc_response(
                IpcResponse.failure(request.request_id, _fault_from(exc)),
                HTTPStatus.OK,
            )
            return
        self._send_ipc_response(
            IpcResponse.success(request.request_id, result), HTTPStatus.OK,
        )

    # ── AI streaming ──────────────────────────────────────────────────────

    def _handle_ai_stream(self, raw: bytes) -> None:
        """Route an AI method to its handler and stream the SSE response."""
        try:
            request = IpcRequest.model_validate_json(raw)
        except ValidationError as exc:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": {"code": ErrorCode.IPC_MALFORMED_MESSAGE.value,
                           "message": "invalid IpcRequest",
                           "detail": exc.errors(include_url=False)}},
            )
            return

        method = request.method
        handler: HandlerFn | None = AI_ENDPOINT_METHODS.get(method)
        if handler is None:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": {"code": ErrorCode.IPC_METHOD_NOT_FOUND.value,
                           "message": f"no handler for {method}"}},
            )
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self._send_cors_headers()
        self.end_headers()

        request_id = request.request_id
        params: dict[str, Any] = dict(request.params)

        try:
            frames = handler(params, request_id)
            for frame in frames:
                kind = frame.get("kind")
                if kind == "token":
                    payload = json.dumps({"token": frame["token"]}, ensure_ascii=False)
                    _send_sse_frame(self.wfile, payload.encode("utf-8"))
                elif kind == "cancelled":
                    _send_sse_frame(self.wfile, b'{"cancelled": true}')
                    _send_sse_frame(self.wfile, _DONE_PAYLOAD)
                    return
                elif kind == "error":
                    err = {"error": {"code": frame.get("code", "TEEA-0000"),
                                     "message": frame.get("message", "unknown error")}}
                    _send_sse_frame(self.wfile, json.dumps(err, ensure_ascii=False).encode("utf-8"))
                    _send_sse_frame(self.wfile, _DONE_PAYLOAD)
                    return
                elif kind == "done":
                    _send_sse_frame(self.wfile, _DONE_PAYLOAD)
                    return
        except Exception as exc:  # noqa: BLE001 - reported as a fault, not a 500 traceback.
            err = {"error": {"code": "TEEA-0500", "message": str(exc)}}
            _send_sse_frame(self.wfile, json.dumps(err, ensure_ascii=False).encode("utf-8"))
            _send_sse_frame(self.wfile, _DONE_PAYLOAD)

    # ── Output helpers ────────────────────────────────────────────────────

    def _send_ipc_response(self, response: IpcResponse, status: HTTPStatus) -> None:
        self._send_json(status, json.loads(response.model_dump_json()))

    def _send_json(self, status: HTTPStatus, payload: Mapping[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        with contextlib.suppress(BrokenPipeError, ConnectionAbortedError, OSError):
            self.wfile.write(body)

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")


class TEEAHttpServer:
    """A running loopback HTTP+SSE bridge for analysis *and* AI endpoints.

    Args:
        builder: The Language Server snapshot builder.
        plugins: The supervised plugin runtime.
        fusion: The suggestion fusion engine.
        host: Loopback bind address.
        port: Port to bind; ``0`` for an OS-assigned ephemeral port.
    """

    def __init__(
        self,
        builder: LanguageServerSnapshotBuilder,
        plugins: SupervisedPluginRuntime,
        fusion: PriorityRankedFusionEngine,
        *,
        host: str = DEFAULT_HOST,
        port: int = 0,
    ) -> None:
        _validate_loopback(host)
        httpd = _BridgeHTTPServer((host, port), _BridgeRequestHandler)
        httpd.builder = builder
        httpd.plugins = plugins
        httpd.fusion = fusion
        self._httpd = httpd
        self._thread: threading.Thread | None = None

    @property
    def host(self) -> str:
        """The address this server is bound to."""
        return str(self._httpd.server_address[0])

    @property
    def port(self) -> int:
        """The port this server is bound to."""
        return int(self._httpd.server_address[1])

    @property
    def base_url(self) -> str:
        """``http://host:port``, for building endpoint URLs."""
        return f"http://{self.host}:{self.port}"

    def start(self) -> None:
        """Start serving on a background thread. Idempotent."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="teea-http-bridge",
            daemon=True,
        )
        self._thread.start()

    def shutdown(self, *, timeout: float = 5.0) -> None:
        """Stop serving and release the socket. Idempotent."""
        if self._thread is not None:
            self._httpd.shutdown()
            self._thread.join(timeout=timeout)
            self._thread = None
        self._httpd.server_close()

    def __enter__(self) -> TEEAHttpServer:
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.shutdown()


def serve_http(
    builder: LanguageServerSnapshotBuilder,
    plugins: SupervisedPluginRuntime,
    fusion: PriorityRankedFusionEngine,
    *,
    host: str = DEFAULT_HOST,
    port: int = 0,
) -> TEEAHttpServer:
    """Build and start the combined HTTP bridge.

    Args:
        builder: The Language Server snapshot builder.
        plugins: The supervised plugin runtime.
        fusion: The suggestion fusion engine.
        host: Loopback bind address.
        port: Port to bind; ``0`` for an OS-assigned ephemeral port.

    Returns:
        The running server. Callers own its lifetime.
    """
    server = TEEAHttpServer(builder, plugins, fusion, host=host, port=port)
    server.start()
    return server


__all__ = [
    "AI_PATHS",
    "ANALYSIS_METHOD",
    "ANALYSIS_PATH",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "DEFAULT_SESSION_ID",
    "LOOPBACK_HOSTS",
    "NotLoopbackError",
    "TEEAHttpServer",
    "serve_http",
]