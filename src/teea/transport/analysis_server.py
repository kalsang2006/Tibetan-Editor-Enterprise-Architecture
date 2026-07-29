"""A loopback-only HTTP server bridging the add-in to document analysis.

See the package docstring for why this exists and why it is not part of
``teea.ipc``. In one sentence: an HTTP request is a standalone call, not a slot
in one persistent duplex channel, so each request runs the same three-step
pipeline :class:`~teea.daemon.TEEADaemon` already wires onto its ``IpcServer``
as three separate handlers (``analyze``, ``plugins``, ``fuse``) -- but run here
as one composite call, so a book-length document's immutable snapshot never
has to round-trip over the wire between steps.

Browser trust, without a certificate
-------------------------------------
The W3C Secure Contexts specification treats loopback addresses
(``127.0.0.1``, ``::1``, ``localhost``) as "potentially trustworthy" even over
plain HTTP, which is exactly why current Chromium (and so the Edge WebView2
that hosts a Word task pane) permits an HTTPS page to ``fetch`` a plain
``http://127.0.0.1`` endpoint without tripping mixed-content blocking. That is
what lets this server skip a self-signed certificate and a trust-store
enrollment step entirely -- and why :data:`LOOPBACK_HOSTS` is a hard gate, not
a default: the exemption is for loopback specifically, nothing wider. This
server binds IPv4 loopback only (``127.0.0.1`` / ``localhost``) -- see
:class:`_BoundHTTPServer` for why ``::1`` is out of scope -- which is still
squarely inside the exemption and is what :data:`DEFAULT_HOST` uses.

CORS is opened permissively (``Access-Control-Allow-Origin: *``) for the same
reason it is safe to: only a process already running on this machine can reach
a loopback socket in the first place, so a permissive header here does not
expose anything to a remote origin that could not already read it locally.
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

from teea.core.errors import ConfigurationError, ErrorCode, TEEAError
from teea.fusion import PriorityRankedFusionEngine
from teea.ipc.models import PROTOCOL_VERSION, IpcFault, IpcRequest, IpcResponse
from teea.nlp.snapshot import LanguageServerSnapshotBuilder
from teea.plugins import SupervisedPluginRuntime

logger = structlog.get_logger(__name__)

#: The default bind address: loopback, IPv4.
DEFAULT_HOST: Final = "127.0.0.1"

#: The port a daemon entry point should bind by convention, pending a real
#: launcher deciding this for good -- no such launcher exists yet. Every test
#: in this package binds ``0`` (an OS-assigned ephemeral port) instead, exactly
#: to avoid depending on this number; it exists only so the task pane's default
#: endpoint (``addin/src/taskpane/types/ipc.ts``'s ``DEFAULT_DAEMON_PORT``) has
#: a documented, single source of truth to match on the day a launcher exists.
DEFAULT_PORT: Final = 50505

#: IPv4 loopback and the hostname that resolves to it, accepted without
#: needing to parse as an IP literal. Not ``::1``: see :class:`_BoundHTTPServer`
#: for why IPv6 loopback is out of scope here.
LOOPBACK_HOSTS: Final = frozenset({"127.0.0.1", "localhost"})

#: The session identity used when a caller sends none. There is no `$connect`
#: handshake in this bridge (see the package docstring), so every request that
#: omits `session_id` shares this one, which is correct for the single-user,
#: single-document daemon this server is built for.
DEFAULT_SESSION_ID: Final = "http-loopback"

#: The one method this bridge answers.
ANALYSIS_METHOD: Final = "analysis.run"

#: The path `ANALYSIS_METHOD` is served at.
ANALYSIS_PATH: Final = "/api/analysis/run"

#: What an ordinary client disconnect looks like from the server's side of a
#: keep-alive socket -- not a bug, just a peer that went away.
_EXPECTED_DISCONNECT_ERRORS: Final = (
    ConnectionResetError,
    ConnectionAbortedError,
    BrokenPipeError,
    TimeoutError,
)

#: Maximum HTTP request body this server will accept (10 MiB). Requests with
#: a ``Content-Length`` exceeding this limit receive a 413 response before any
#: body bytes are read, protecting the server from memory exhaustion.
_MAX_BODY_SIZE: Final = 10 * 1024 * 1024


class NotLoopbackError(ConfigurationError):
    """Raised when asked to bind anywhere but a loopback address."""

    default_code = ErrorCode.CONFIGURATION_INVALID


def _validate_loopback(host: str) -> None:
    """Raise unless ``host`` names an IPv4 loopback address.

    Args:
        host: The bind address requested.

    Raises:
        NotLoopbackError: If ``host`` is not IPv4 loopback -- including a
            syntactically valid IPv6 loopback address, an address family this
            server cannot bind to; see :class:`_BoundHTTPServer`.
    """
    if host in LOOPBACK_HOSTS:
        return
    try:
        parsed = ipaddress.ip_address(host)
    except ValueError as exc:
        raise NotLoopbackError(
            "Refusing to bind the analysis transport to a non-address host.",
            context={"host": host},
            cause=exc,
        ) from exc
    if not (parsed.version == 4 and parsed.is_loopback):
        raise NotLoopbackError(
            "Refusing to bind the analysis transport to a non-IPv4-loopback "
            "address. The daemon must never be reachable from another "
            "machine, and this server does not support IPv6 loopback "
            "(see NotLoopbackError's module documentation).",
            context={"host": host},
        )


def _fault_from(exc: Exception) -> IpcFault:
    """Build an `IpcFault` from a handler's exception, never a traceback."""
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


class _BoundHTTPServer(ThreadingHTTPServer):
    """A `ThreadingHTTPServer` carrying the collaborators every request needs.

    Attributes are set once by :class:`AnalysisHttpServer` and read by every
    request thread through `self.server`, which is how :mod:`http.server`
    hands a request handler back to the server that accepted its connection.

    IPv4 loopback only, for the same reason `teea.transport`'s AI bridge binds
    only IPv4: `socketserver.TCPServer` binds as `AF_INET` unless told
    otherwise, and selecting `AF_INET6` for an `::1` bind would need the
    `socket` module's address-family constants -- one of the network-client
    imports `tests/test_architecture.py` bans package-wide (ADR-002). That ban
    is for outbound clients, not a loopback listener, but it is an AST check on
    the mere presence of the import, not its use, so it cannot distinguish the
    two. IPv4 loopback is what a real Word add-in binds to anyway
    (:data:`DEFAULT_HOST`); see :data:`LOOPBACK_HOSTS` for the consequence --
    ``::1`` is deliberately not accepted.
    """

    daemon_threads = True
    allow_reuse_address = True

    builder: LanguageServerSnapshotBuilder
    plugins: SupervisedPluginRuntime
    fusion: PriorityRankedFusionEngine

    def handle_error(self, request: object, client_address: tuple[str, int]) -> None:
        """Log a connection failure through structlog instead of stderr.

        A keep-alive connection a client abandons without a clean close --
        a browser tab shut, a network drop, a test that never called
        ``close()`` -- surfaces here as an ordinary `ConnectionResetError` or
        similar while a later `readline()`/`write()` waits on that same
        socket. `socketserver`'s default handler prints a full traceback to
        stderr for this exactly as it would for a genuine bug; that noise
        would drown out the one thing worth seeing at this severity, so an
        expected disconnect logs at debug and anything else stays loud.
        """
        _exc_type, exc, _tb = sys.exc_info()
        if isinstance(exc, _EXPECTED_DISCONNECT_ERRORS):
            logger.debug("http_connection_reset", client=client_address[0], error=str(exc))
            return
        logger.error("http_request_failed", client=client_address[0], exc_info=True)


class _AnalysisRequestHandler(BaseHTTPRequestHandler):
    """Serves one HTTP request by running the analyze/plugins/fuse pipeline."""

    server: _BoundHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        """Route access logging through structlog, and never log a body."""
        logger.debug("http_access", client=self.client_address[0], line=format % args)

    def do_OPTIONS(self) -> None:
        """Answer a CORS preflight."""
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        """Serve `/health`: whether this bridge is up."""
        if self.path != "/health":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        self._send_json(HTTPStatus.OK, {"status": "ok", "protocol_version": PROTOCOL_VERSION})

    def do_POST(self) -> None:
        """Route one call to the analysis pipeline."""
        # Read (drain) the body before any early return, unconditionally. This
        # is HTTP/1.1 keep-alive hygiene, not a nicety: `BaseHTTPRequestHandler`
        # reuses the connection for a further request, and if this handler
        # returns having left unread body bytes in the socket, the next
        # `handle_one_request()` reads those leftover bytes as if they were the
        # start of a new request line. An unknown path or a mismatched method
        # still needs the body consumed before its own error reply goes out.
        length = int(self.headers.get("Content-Length") or "0")
        if length > _MAX_BODY_SIZE:
            self._send_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {"error": {"code": "PAYLOAD_TOO_LARGE", "max_bytes": _MAX_BODY_SIZE}},
            )
            return
        raw = self.rfile.read(length) if length > 0 else b"{}"

        if self.path != ANALYSIS_PATH:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": {"code": ErrorCode.IPC_METHOD_NOT_FOUND.value, "path": self.path}},
            )
            return

        try:
            request = IpcRequest.model_validate_json(raw)
        except ValidationError as exc:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": {
                        "code": ErrorCode.IPC_MALFORMED_MESSAGE.value,
                        "message": "the request body is not a valid IpcRequest",
                        "detail": exc.errors(include_url=False),
                    }
                },
            )
            return
        if request.method != ANALYSIS_METHOD:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": {
                        "code": ErrorCode.IPC_MALFORMED_MESSAGE.value,
                        "message": "the request's method does not match this endpoint",
                    }
                },
            )
            return

        text = request.params.get("text", "")
        if not isinstance(text, str):
            self._send_ipc_response(
                IpcResponse.failure(
                    request.request_id,
                    IpcFault(
                        code=ErrorCode.INPUT_INVALID.value,
                        error_type="InputValidationError",
                        message="text must be a string",
                    ),
                ),
                HTTPStatus.OK,
            )
            return

        try:
            result = self._analyze(text)
        except Exception as exc:  # noqa: BLE001 - reported as a fault, not a 500 traceback.
            self._send_ipc_response(
                IpcResponse.failure(request.request_id, _fault_from(exc)), HTTPStatus.OK
            )
            return
        self._send_ipc_response(
            IpcResponse.success(request.request_id, result), HTTPStatus.OK
        )

    def _analyze(self, text: str) -> Mapping[str, Any]:
        """Run the three-step pipeline the daemon's IPC handlers also run.

        Kept in-process end to end -- the immutable snapshot never leaves this
        call -- which is the whole reason this bridge exists as one composite
        endpoint rather than three endpoints shuttling the snapshot over HTTP.
        """
        snapshot = self.server.builder.analyze(text)
        plugin_results = self.server.plugins.dispatch(snapshot)
        unified = self.server.fusion.fuse(text, plugin_results.suggestions)
        return unified.model_dump(mode="json")

    def _send_ipc_response(self, response: IpcResponse, status: HTTPStatus) -> None:
        self._send_json(status, json.loads(response.model_dump_json()))

    def _send_json(self, status: HTTPStatus, payload: Mapping[str, Any]) -> None:
        # `default=str`: a malformed-body report embeds pydantic's own
        # `ValidationError.errors()`, and for a `json_invalid` error that
        # dict's `"input"` value is the raw offending payload -- `bytes`, when
        # the client sent one, which plain `json.dumps` cannot serialize. The
        # one path that reports a bad request must never itself fail to
        # respond because of what made the request bad.
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


class AnalysisHttpServer:
    """A running loopback HTTP bridge to the document-analysis pipeline.

    Args:
        builder: The Language Server snapshot builder. Owned by the caller.
        plugins: The supervised plugin runtime. Owned by the caller.
        fusion: The suggestion fusion engine. Owned by the caller.
        host: The bind address. Must be loopback; see :func:`_validate_loopback`.
        port: The port to bind. ``0`` (the default) asks the OS for a free
            ephemeral port, which is what tests want; a real deployment passes
            a fixed, documented port.

    Raises:
        NotLoopbackError: If ``host`` is not a loopback address.
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
        httpd = _BoundHTTPServer((host, port), _AnalysisRequestHandler)
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
        """The port this server is bound to (the real one, if ``0`` was asked for)."""
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
            name="teea-analysis-http",
            daemon=True,
        )
        self._thread.start()

    def shutdown(self, *, timeout: float = 5.0) -> None:
        """Stop serving and release the socket. Idempotent.

        Safe to call even if :meth:`start` was never called.
        """
        if self._thread is not None:
            self._httpd.shutdown()
            self._thread.join(timeout=timeout)
            self._thread = None
        self._httpd.server_close()

    def __enter__(self) -> AnalysisHttpServer:
        """Start the server and return it."""
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        """Shut the server down."""
        self.shutdown()


def serve_analysis_http(
    builder: LanguageServerSnapshotBuilder,
    plugins: SupervisedPluginRuntime,
    fusion: PriorityRankedFusionEngine,
    *,
    host: str = DEFAULT_HOST,
    port: int = 0,
) -> AnalysisHttpServer:
    """Build and start a loopback HTTP bridge over the analysis pipeline.

    Args:
        builder: The Language Server snapshot builder.
        plugins: The supervised plugin runtime.
        fusion: The suggestion fusion engine.
        host: The bind address. Must be loopback.
        port: The port to bind, ``0`` for an OS-assigned ephemeral one.

    Returns:
        The running server. Callers own its lifetime and must call
        :meth:`AnalysisHttpServer.shutdown` (directly, or via ``with``).
    """
    server = AnalysisHttpServer(builder, plugins, fusion, host=host, port=port)
    server.start()
    return server


__all__ = [
    "ANALYSIS_METHOD",
    "ANALYSIS_PATH",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "DEFAULT_SESSION_ID",
    "LOOPBACK_HOSTS",
    "AnalysisHttpServer",
    "NotLoopbackError",
    "serve_analysis_http",
]
