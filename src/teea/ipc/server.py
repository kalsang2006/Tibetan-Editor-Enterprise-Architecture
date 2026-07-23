"""The IPC server: routing, dispatch, sessions and lifecycle (Figure 3, P3).

This is the daemon side of the Local IPC boundary. It routes an incoming
:class:`~teea.ipc.models.IpcRequest` to a registered handler, dispatches it,
and sends back an :class:`~teea.ipc.models.IpcResponse` -- Figure 3's "Message
Transport" and "Request Routing" in one component. It knows nothing of the
Language Server, the AI Runtime or any feature: those are the handlers the daemon
registers, so ``teea.ipc`` depends on ``teea.core`` alone.

Built-in methods
----------------
Four methods are always routed, under a ``$`` prefix that user methods cannot
take, so the connection can be managed without a feature having to provide it:

* ``$connect`` -- the handshake: checks the protocol version, opens a session,
  and returns the session id and the routable methods (capability discovery).
* ``$disconnect`` -- closes a session.
* ``$health`` -- returns a :class:`~teea.ipc.models.HealthStatus`.
* ``$cancel`` -- marks a request cancelled so a not-yet-started dispatch is
  skipped.

Concurrency
-----------
FR-8 asks for non-blocking, asynchronous buses. Dispatch of a user method runs on
an injected :class:`~concurrent.futures.Executor` when one is supplied, so a slow
handler does not block the transport or other requests; with no executor,
dispatch is synchronous. Either way the server holds no request ordering, so the
choice cannot change results. Mutable state -- the open sessions and the set of
cancelled requests -- is guarded by a lock, following the AI Runtime's precedent
for a stateful, concurrently-called component.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Mapping
from concurrent.futures import Executor
from typing import Any

from teea.core.errors import ErrorCode, TEEAError
from teea.ipc.codec import JsonMessageCodec
from teea.ipc.errors import MalformedMessageError, TransportClosedError
from teea.ipc.interfaces import MessageCodec, RequestHandler, Transport
from teea.ipc.models import (
    FAULT_ORIGIN_KEY,
    FAULT_ORIGIN_PROTOCOL,
    PROTOCOL_VERSION,
    HealthStatus,
    IpcFault,
    IpcRequest,
    IpcResponse,
    MethodDescriptor,
    MethodKind,
    Session,
    protocol_major,
)

#: Methods the server always provides. User methods may not start with ``$``.
_BUILTIN_PREFIX = "$"


class IpcServer:
    """Routes and dispatches IPC requests for the daemon.

    Satisfies the shape of an IPC server: register handlers, serve a transport,
    stop. Every collaborator is injected.

    Args:
        codec: How messages are (de)serialized. Defaults to JSON.
        executor: Where user-method dispatch runs. ``None`` dispatches
            synchronously on the receiving thread; an executor makes dispatch
            non-blocking (FR-8).
    """

    def __init__(
        self, *, codec: MessageCodec | None = None, executor: Executor | None = None
    ) -> None:
        # `is None`, not `or`: an injected collaborator must not be second-guessed.
        self._codec = JsonMessageCodec() if codec is None else codec
        self._executor = executor
        self._handlers: dict[str, tuple[RequestHandler, MethodKind]] = {}
        self._lock = threading.Lock()
        self._transport: Transport | None = None
        self._serving = False
        self._sessions: dict[str, Session] = {}
        # Cancellation is keyed by (session_id, request_id): a client's ids are
        # only unique per connection, so a global id-only set would let one
        # session cancel another's work. Both sets are bounded by the number of
        # in-flight requests.
        self._inflight: set[tuple[str, str]] = set()
        self._cancelled: set[tuple[str, str]] = set()
        self._session_counter = 0

    # -- Registration --------------------------------------------------------
    def register(
        self,
        method: str,
        handler: RequestHandler,
        *,
        kind: MethodKind = MethodKind.QUERY,
    ) -> None:
        """Route ``method`` to ``handler``.

        Args:
            method: The method name. Must not be empty or start with ``$``.
            handler: What serves the call.
            kind: Whether it is a query or a command.

        Raises:
            ValueError: If the name is invalid or already registered, or if the
                server is already serving. Handlers are registered before serving
                begins, so the routing table is fixed while requests are in
                flight and needs no lock on the read path.
        """
        if not method:
            raise ValueError("a method name must not be empty")
        if method.startswith(_BUILTIN_PREFIX):
            raise ValueError(f"method names must not start with {_BUILTIN_PREFIX!r}")
        with self._lock:
            if self._serving:
                raise ValueError("cannot register a method while the server is serving")
            if method in self._handlers:
                raise ValueError(f"method {method!r} is already registered")
            self._handlers[method] = (handler, kind)

    @property
    def methods(self) -> tuple[MethodDescriptor, ...]:
        """Every routable method, built-ins included, sorted by name."""
        user = [
            MethodDescriptor(name=name, kind=kind)
            for name, (_handler, kind) in self._handlers.items()
        ]
        builtin = [
            MethodDescriptor(name=name, kind=MethodKind.QUERY)
            for name in ("$connect", "$disconnect", "$health")
        ] + [MethodDescriptor(name="$cancel", kind=MethodKind.COMMAND)]
        return tuple(sorted(user + builtin, key=lambda d: d.name))

    @property
    def is_serving(self) -> bool:
        """Whether the server is bound to a transport and serving."""
        with self._lock:
            return self._serving

    @property
    def active_sessions(self) -> int:
        """How many sessions are open."""
        with self._lock:
            return len(self._sessions)

    # -- Lifecycle -----------------------------------------------------------
    def serve(self, transport: Transport) -> None:
        """Begin serving requests arriving on ``transport``.

        Args:
            transport: The channel to the client.

        Raises:
            ValueError: If the server is already serving.
        """
        with self._lock:
            if self._serving:
                raise ValueError("the server is already serving")
            self._transport = transport
            self._serving = True
        transport.set_receiver(self._on_message)

    def stop(self) -> None:
        """Stop serving, dropping every session. Idempotent.

        The transport is not closed here: the server does not own it, the caller
        that supplied it does, and closing it would decide the client's fate too.
        """
        with self._lock:
            self._serving = False
            self._transport = None
            self._sessions.clear()
            self._cancelled.clear()
            self._inflight.clear()

    def health(self) -> HealthStatus:
        """Return a snapshot of the server's state."""
        with self._lock:
            return HealthStatus(
                status="ok" if self._serving else "stopped",
                protocol_version=PROTOCOL_VERSION,
                serving=self._serving,
                active_sessions=len(self._sessions),
                methods=len(self._handlers) + 4,
            )

    # -- Message handling ----------------------------------------------------
    def _on_message(self, payload: bytes) -> None:
        """Decode, route and dispatch one incoming payload."""
        with self._lock:
            if not self._serving:
                # A stopped server has released its transport and its sessions;
                # a message arriving after stop() must not be decoded, routed,
                # dispatched, or allowed to mint a session.
                return
        try:
            request = self._codec.decode_request(payload)
        except MalformedMessageError:
            # A garbled payload has no request id to correlate a reply to, so
            # there is nothing to send back; dropping it is the only safe move.
            return
        self._route(request)

    def _route(self, request: IpcRequest) -> None:
        """Handle protocol checks and route ``request`` to its dispatcher."""
        if protocol_major(request.protocol_version) != protocol_major(PROTOCOL_VERSION):
            self._reply_error(
                request,
                _fault_from(
                    "IPC_PROTOCOL_MISMATCH",
                    "ProtocolVersionError",
                    "The client and server speak incompatible protocol versions.",
                    {"client": request.protocol_version, "server": PROTOCOL_VERSION},
                ),
            )
            return

        if request.method == "$connect":
            # A handshake with no reply channel would mint a session whose id is
            # told to no one, so a $connect must be a query.
            if request.expects_response:
                self._reply(request, self._handle_connect(request))
            return

        session = self._session_for(request)
        if session is None:
            self._reply_error(
                request,
                _fault_from(
                    "IPC_SESSION_INVALID",
                    "SessionError",
                    "The request carries no valid session.",
                    {"session_id": request.session_id},
                ),
            )
            return

        if request.method == "$cancel":
            # Cancellation is now scoped to the caller's own session, so it is
            # routed *after* the session check, not before. It is a command, but
            # a caller that sent it as a query still gets an acknowledgement
            # rather than hanging on a reply that never comes.
            self._handle_cancel(request, session)
            self._reply(request, {"cancelled": request.params.get("request_id")})
            return
        if request.method == "$disconnect":
            self._reply(request, self._handle_disconnect(session))
            return
        if request.method == "$health":
            self._reply(request, self.health().model_dump(mode="json"))
            return

        self._dispatch_user(request, session)

    # -- Built-in methods ----------------------------------------------------
    def _handle_connect(self, request: IpcRequest) -> Mapping[str, Any]:
        """Open a session and return it, with the routable methods."""
        with self._lock:
            self._session_counter += 1
            session = Session(
                session_id=f"sess-{self._session_counter}",
                protocol_version=PROTOCOL_VERSION,
            )
            self._sessions[session.session_id] = session
        return {
            "session_id": session.session_id,
            "protocol_version": PROTOCOL_VERSION,
            "methods": [d.model_dump(mode="json") for d in self.methods],
        }

    def _handle_disconnect(self, session: Session) -> Mapping[str, Any]:
        """Close a session."""
        with self._lock:
            self._sessions.pop(session.session_id, None)
        return {"closed": session.session_id}

    def _handle_cancel(self, request: IpcRequest, session: Session) -> None:
        """Mark one in-flight request cancelled, so its dispatch is skipped.

        Scoped to ``session`` and to requests actually in flight, which is what
        keeps the cancelled set bounded and stops one session cancelling
        another's work: a client's request ids are only unique per connection, so
        a global, id-only kill-list would let a stale cancel void an unrelated
        future request. A cancel for an id that is not in flight -- already
        served, or never sent -- is simply ignored.
        """
        target = request.params.get("request_id")
        if not isinstance(target, str) or not target:
            return
        key = (session.session_id, target)
        with self._lock:
            if key in self._inflight:
                self._cancelled.add(key)

    # -- User-method dispatch ------------------------------------------------
    def _dispatch_user(self, request: IpcRequest, session: Session) -> None:
        """Route a user method to its handler, on the executor if there is one."""
        entry = self._handlers.get(request.method)
        if entry is None:
            self._reply_error(
                request,
                _fault_from(
                    "IPC_METHOD_NOT_FOUND",
                    "MethodNotFoundError",
                    "No handler is registered for this method.",
                    {"method": request.method},
                ),
            )
            return
        handler, _kind = entry
        with self._lock:
            self._inflight.add((session.session_id, request.request_id))
        if self._executor is not None:
            self._executor.submit(self._run, request, session, handler)
        else:
            self._run(request, session, handler)

    def _run(
        self, request: IpcRequest, session: Session, handler: RequestHandler
    ) -> None:
        """Run one handler and reply, unless the request was cancelled first.

        The success response is built *and sent* inside the inner try, so a
        handler returning something that is not a JSON-serializable mapping --
        whether it fails at ``dict()``, at model validation, or only at encode
        time -- is caught and reported as a handler failure rather than escaping.
        On the synchronous transport it would otherwise unwind through the
        client's own send. (A closed transport is not a handler fault; ``_send``
        suppresses that itself, so only a genuine serialization error reaches the
        ``except``.)
        """
        key = (session.session_id, request.request_id)
        try:
            with self._lock:
                cancelled = key in self._cancelled
            if cancelled:
                self._reply_error(
                    request,
                    _fault_from(
                        "IPC_CANCELLED",
                        "RequestCancelledError",
                        "The request was cancelled before it was served.",
                        {"request_id": request.request_id},
                    ),
                )
                return
            try:
                result = handler.handle(request.params, session)
                if request.expects_response:
                    self._send(IpcResponse.success(request.request_id, dict(result)))
            except TEEAError as exc:
                self._reply_error(request, _fault_from_exception(exc, exc.code.value))
            except Exception as exc:  # noqa: BLE001 - a handler is untrusted
                self._reply_error(
                    request, _fault_from_exception(exc, "IPC_HANDLER_FAILED")
                )
        finally:
            with self._lock:
                self._inflight.discard(key)
                self._cancelled.discard(key)

    # -- Replying ------------------------------------------------------------
    def _reply(self, request: IpcRequest, result: Mapping[str, Any]) -> None:
        """Send a success response, unless the request is a command."""
        if not request.expects_response:
            return
        self._send(IpcResponse.success(request.request_id, dict(result)))

    def _reply_error(self, request: IpcRequest, fault: IpcFault) -> None:
        """Send a failure response, unless the request is a command."""
        if not request.expects_response:
            return
        self._send(IpcResponse.failure(request.request_id, fault))

    def _send(self, response: IpcResponse) -> None:
        """Encode and send a response over the transport.

        A transport that has closed under us -- the client hung up mid-dispatch --
        makes the send fail; there is nowhere to deliver a reply, so it is
        dropped rather than raised out of a worker thread.
        """
        with self._lock:
            transport = self._transport
        if transport is None:
            return
        with contextlib.suppress(TransportClosedError):
            transport.send(self._codec.encode(response))

    def _session_for(self, request: IpcRequest) -> Session | None:
        """Return the live session named by ``request``, or ``None``."""
        if request.session_id is None:
            return None
        with self._lock:
            return self._sessions.get(request.session_id)


def _fault_from(
    code: str, error_type: str, message: str, context: Mapping[str, Any]
) -> IpcFault:
    """Build a fault the server's own routing raised.

    Marked as protocol-originated, so the client raises the matching protocol
    exception (``MethodNotFoundError`` and the like) for it -- a distinction it
    must not draw for a handler that happens to raise an IPC-coded error.
    """
    marked = dict(context)
    marked[FAULT_ORIGIN_KEY] = FAULT_ORIGIN_PROTOCOL
    return IpcFault(
        code=ErrorCode[code].value,
        error_type=error_type,
        message=message,
        context=marked,
    )


def _fault_from_exception(exc: Exception, code: str) -> IpcFault:
    """Build a fault from a raised handler exception."""
    resolved = ErrorCode[code].value if code.startswith("IPC_") else code
    return IpcFault(
        code=resolved,
        error_type=type(exc).__name__,
        message=str(exc),
        context={},
    )


__all__ = ["IpcServer"]
