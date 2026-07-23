"""The IPC client: the add-in side of the Local IPC boundary (Figure 3, P3).

The client establishes a session, sends queries and commands, and correlates each
response to the call that is waiting for it. It is the mirror of
:class:`~teea.ipc.server.IpcServer`, and like it depends on ``teea.core`` alone.

Blocking calls over an async channel
------------------------------------
A query is request/response, but the response may arrive on another thread (the
transport delivers it whenever the peer sends). So each call registers a
:class:`PendingCall` keyed by a unique request id, sends the request, and waits on
the pending call's event until the response arrives or a deadline passes. The
receiver, running on the delivery thread, resolves the matching pending call. All
of this is guarded by a lock, because the sending and receiving threads touch the
same table of pending calls.

Timeouts and cancellation
-------------------------
A query carries a deadline. If it lapses, the pending call is abandoned, a
``$cancel`` command tells the server to skip the work if it has not started, and
:class:`~teea.ipc.errors.RequestTimeoutError` is raised. Cancellation is the same
without the deadline: :meth:`PendingCall.cancel` abandons the call, notifies the
server, and a late response is discarded because nothing is waiting for its id.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Mapping
from typing import Any

from teea.core.errors import ErrorCode
from teea.ipc.codec import JsonMessageCodec
from teea.ipc.errors import (
    IPCError,
    MalformedMessageError,
    MethodNotFoundError,
    NotConnectedError,
    ProtocolVersionError,
    RemoteError,
    RequestCancelledError,
    RequestTimeoutError,
    SessionError,
    TransportClosedError,
)
from teea.ipc.interfaces import MessageCodec, Transport
from teea.ipc.models import (
    FAULT_ORIGIN_KEY,
    FAULT_ORIGIN_PROTOCOL,
    PROTOCOL_VERSION,
    IpcFault,
    IpcRequest,
    IpcResponse,
    MethodDescriptor,
    protocol_major,
)

#: The protocol-layer error codes that map back to a specific client-side
#: exception -- but only for faults the *server's routing* raised, not faults a
#: handler raised. A handler failure always becomes a :class:`RemoteError`
#: carrying the handler's own code, which is the propagation contract.
_SPECIFIC_ERRORS: dict[ErrorCode, type[IPCError]] = {
    ErrorCode.IPC_METHOD_NOT_FOUND: MethodNotFoundError,
    ErrorCode.IPC_PROTOCOL_MISMATCH: ProtocolVersionError,
    ErrorCode.IPC_SESSION_INVALID: SessionError,
}


class PendingCall:
    """A query awaiting its response.

    Returned by :meth:`IpcClient.call_async`. A caller waits on :meth:`result`,
    or abandons the call with :meth:`cancel`.
    """

    def __init__(self, request_id: str, client: IpcClient) -> None:
        self._request_id = request_id
        self._client = client
        self._event = threading.Event()
        self._response: IpcResponse | None = None
        self._cancelled = False
        self._lock = threading.Lock()

    @property
    def request_id(self) -> str:
        """The id correlating this call to its response."""
        return self._request_id

    @property
    def done(self) -> bool:
        """Whether a response has actually arrived.

        Distinct from cancellation: a timed-out or cancelled call is *settled*
        but not ``done``, because no answer was delivered. Reading the response
        rather than the wait event keeps ``done`` and :attr:`cancelled` mutually
        exclusive.
        """
        with self._lock:
            return self._response is not None

    @property
    def cancelled(self) -> bool:
        """Whether the call was cancelled or timed out."""
        with self._lock:
            return self._cancelled

    def _resolve(self, response: IpcResponse) -> None:
        """Deliver the response. Called by the client's receiver."""
        with self._lock:
            if self._cancelled or self._response is not None:
                return
            self._response = response
        self._event.set()

    def result(self, timeout: float | None = None) -> Mapping[str, Any]:
        """Wait for and return the call's result.

        Args:
            timeout: Seconds to wait, or ``None`` to wait indefinitely.

        Returns:
            The handler's result mapping.

        Raises:
            RequestTimeoutError: If the deadline lapses first.
            RequestCancelledError: If the call was cancelled.
            RemoteError: If the handler failed. The error keeps the handler's own
                code across the boundary.
        """
        if self._event.wait(timeout):
            with self._lock:
                response = self._response
            if response is not None:
                return _unwrap(response)
            raise RequestCancelledError(
                "The call was cancelled.",
                context={"request_id": self._request_id},
            )

        # The deadline lapsed. The response may have arrived in the race window
        # between the wait timing out and this lock -- take it if so, and only
        # commit to cancelling when there really is nothing to return.
        with self._lock:
            if self._response is not None:
                response = self._response
            else:
                self._cancelled = True
                response = None
            # Settle the event either way, so a second result() returns at once
            # rather than re-waiting the whole deadline.
            self._event.set()
        if response is not None:
            return _unwrap(response)
        self._client._abandon(self._request_id)
        self._client._notify_cancel(self._request_id)
        raise RequestTimeoutError(
            "The call did not complete within the deadline.",
            context={"request_id": self._request_id, "timeout": timeout},
        )

    def cancel(self) -> None:
        """Abandon the call and tell the server to skip it. Idempotent.

        A no-op once a response has arrived: cancelling then would throw away an
        answer already in hand and leave the call reporting both ``done`` and
        ``cancelled``. This mirrors :meth:`concurrent.futures.Future.cancel`,
        which refuses once the future is done.
        """
        with self._lock:
            if self._cancelled or self._response is not None:
                return
            self._cancelled = True
        self._client._abandon(self._request_id)
        self._client._notify_cancel(self._request_id)
        self._event.set()


class IpcClient:
    """Sends requests to an :class:`~teea.ipc.server.IpcServer`.

    Args:
        codec: How messages are (de)serialized. Defaults to JSON, and must match
            the server's codec.
    """

    def __init__(self, *, codec: MessageCodec | None = None) -> None:
        self._codec = JsonMessageCodec() if codec is None else codec
        self._transport: Transport | None = None
        self._lock = threading.Lock()
        self._pending: dict[str, PendingCall] = {}
        self._request_counter = 0
        self._session_id: str | None = None
        self._methods: tuple[MethodDescriptor, ...] = ()

    # -- Introspection -------------------------------------------------------
    @property
    def is_connected(self) -> bool:
        """Whether a session is established."""
        with self._lock:
            return self._session_id is not None

    @property
    def session_id(self) -> str | None:
        """The current session id, or ``None`` before connecting."""
        with self._lock:
            return self._session_id

    @property
    def methods(self) -> tuple[MethodDescriptor, ...]:
        """The methods the server advertised at connect: capability discovery."""
        return self._methods

    # -- Lifecycle -----------------------------------------------------------
    def connect(self, transport: Transport, *, timeout: float | None = 5.0) -> None:
        """Establish a session over ``transport``.

        Sends the handshake, checks the protocol version, and records the session
        id and the server's methods.

        Args:
            transport: The channel to the server.
            timeout: How long to wait for the handshake.

        Raises:
            NotConnectedError: If a session is already established. Reconnecting
                without closing first would orphan the previous server session,
                which only ``$disconnect`` on the old id could ever reclaim.
            ProtocolVersionError: If the server speaks an incompatible protocol.
            RequestTimeoutError: If the handshake is not answered in time.
        """
        with self._lock:
            if self._session_id is not None:
                raise NotConnectedError(
                    "The client is already connected; close it before reconnecting.",
                    context={"session_id": self._session_id},
                )
            self._transport = transport
        transport.set_receiver(self._on_message)
        result = self._call_raw("$connect", {}, session_id=None, timeout=timeout)
        server_version = str(result["protocol_version"])
        if protocol_major(server_version) != protocol_major(PROTOCOL_VERSION):
            raise ProtocolVersionError(
                "The server speaks an incompatible protocol version.",
                context={"server": server_version, "client": PROTOCOL_VERSION},
            )
        with self._lock:
            self._session_id = str(result["session_id"])
            self._methods = tuple(
                MethodDescriptor.model_validate(d) for d in result["methods"]
            )

    def close(self, *, timeout: float | None = 5.0) -> None:
        """Close the session. Idempotent.

        The transport is left open: the client does not own it. Any calls still
        pending are cancelled, since no response can now arrive for them.
        """
        with self._lock:
            session_id = self._session_id
            self._session_id = None
            pending = list(self._pending.values())
        if session_id is not None:
            # A close that cannot reach the server is still a close; there is
            # nothing useful to do with the failure.
            with contextlib.suppress(IPCError):
                self._call_raw(
                    "$disconnect", {}, session_id=session_id, timeout=timeout
                )
        for call in pending:
            call.cancel()

    # -- Calls ---------------------------------------------------------------
    def call(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        timeout: float | None = 5.0,
    ) -> Mapping[str, Any]:
        """Send a query and wait for its result.

        Args:
            method: The method to call.
            params: The call's arguments.
            timeout: Seconds to wait for the response.

        Returns:
            The handler's result.

        Raises:
            NotConnectedError: If no session is established.
            RequestTimeoutError, RequestCancelledError, RemoteError: As
                :meth:`PendingCall.result` documents.
        """
        return self.call_async(method, params).result(timeout)

    def call_async(
        self, method: str, params: Mapping[str, Any] | None = None
    ) -> PendingCall:
        """Send a query and return a handle to await or cancel.

        Args:
            method: The method to call.
            params: The call's arguments.

        Returns:
            A :class:`PendingCall`.

        Raises:
            NotConnectedError: If no session is established.
        """
        session_id = self._require_session()
        return self._send(method, params or {}, session_id, expects_response=True)

    def notify(
        self, method: str, params: Mapping[str, Any] | None = None
    ) -> None:
        """Send a command: fire-and-forget, no response awaited (FR-8).

        Args:
            method: The command to send.
            params: The command's arguments.

        Raises:
            NotConnectedError: If no session is established.
        """
        session_id = self._require_session()
        self._send(method, params or {}, session_id, expects_response=False)

    def health(self, *, timeout: float | None = 5.0) -> Mapping[str, Any]:
        """Return the server's health snapshot."""
        return self.call("$health", timeout=timeout)

    # -- Internals -----------------------------------------------------------
    def _require_session(self) -> str:
        with self._lock:
            if self._session_id is None:
                raise NotConnectedError("The client is not connected.")
            return self._session_id

    def _call_raw(
        self,
        method: str,
        params: Mapping[str, Any],
        *,
        session_id: str | None,
        timeout: float | None,
    ) -> Mapping[str, Any]:
        """Send a query without requiring an established session (for handshakes)."""
        return self._send(method, params, session_id, expects_response=True).result(
            timeout
        )

    def _send(
        self,
        method: str,
        params: Mapping[str, Any],
        session_id: str | None,
        *,
        expects_response: bool,
    ) -> PendingCall:
        """Build, register and send one request.

        The pending entry is registered *before* the send, not after, because the
        synchronous loopback transport delivers the response inline -- the reply
        can be resolved before :meth:`send` returns, so the entry has to exist
        first. To keep that from leaking a pending entry when the send fails, the
        registration is rolled back on any error.
        """
        with self._lock:
            self._request_counter += 1
            request_id = f"req-{self._request_counter}"
            call = PendingCall(request_id, self)
            if expects_response:
                self._pending[request_id] = call
            transport = self._transport
        try:
            if transport is None:
                raise NotConnectedError("The client has no transport.")
            request = IpcRequest(
                request_id=request_id,
                method=method,
                params=dict(params),
                session_id=session_id,
                expects_response=expects_response,
            )
            transport.send(self._codec.encode(request))
        except BaseException:
            with self._lock:
                self._pending.pop(request_id, None)
            raise
        return call

    def _on_message(self, payload: bytes) -> None:
        """Resolve the pending call a response belongs to."""
        try:
            response = self._codec.decode_response(payload)
        except MalformedMessageError:
            return
        with self._lock:
            call = self._pending.pop(response.request_id, None)
        if call is not None:
            call._resolve(response)

    def _abandon(self, request_id: str) -> None:
        """Forget a pending call, so a late response for it is discarded."""
        with self._lock:
            self._pending.pop(request_id, None)

    def _notify_cancel(self, request_id: str) -> None:
        """Tell the server a request was cancelled, best-effort."""
        with self._lock:
            session_id = self._session_id
            transport = self._transport
        if transport is None:
            return
        request = IpcRequest(
            request_id=f"cancel-{request_id}",
            method="$cancel",
            params={"request_id": request_id},
            session_id=session_id,
            expects_response=False,
        )
        # Cancellation is best-effort: if the channel has gone, the server has
        # nothing left to cancel.
        with contextlib.suppress(TransportClosedError):
            transport.send(self._codec.encode(request))


def _unwrap(response: IpcResponse) -> Mapping[str, Any]:
    """Return a response's result, or raise the fault it carries.

    Reading the fault first rather than branching on ``ok`` lets the type narrow
    without an assertion: :class:`IpcResponse` already guarantees that exactly
    one of the two is present.
    """
    fault = response.error
    if fault is not None:
        return _raise_fault(fault)
    return response.result or {}


def _raise_fault(fault: IpcFault) -> Mapping[str, Any]:
    """Raise the client-side exception for a server fault.

    A fault the *server's routing* produced (method not found, bad session,
    version mismatch) becomes its specific protocol exception, which the client
    reacts to. A fault a *handler* raised becomes a :class:`RemoteError` carrying
    the handler's own code, whatever that code is -- so a handler that raises an
    IPC-coded ``TEEAError`` is still reported as a handler failure, not mistaken
    for a protocol event.
    """
    context = dict(fault.context)
    from_protocol = context.pop(FAULT_ORIGIN_KEY, None) == FAULT_ORIGIN_PROTOCOL
    try:
        code = ErrorCode(fault.code)
    except ValueError:
        # A code from a newer peer this build does not know. Keep the wire value
        # so the caller can still see what the server actually said.
        context.setdefault("remote_code", fault.code)
        code = ErrorCode.UNKNOWN
    specific = _SPECIFIC_ERRORS.get(code) if from_protocol else None
    if specific is not None:
        raise specific(fault.message, context=context)
    raise RemoteError(
        fault.message,
        code=code,
        remote_error_type=fault.error_type,
        context=context,
    )


__all__ = ["IpcClient", "PendingCall"]
