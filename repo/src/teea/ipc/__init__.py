"""TEEA Local IPC layer.

Figure 3 places this component at P3, between the Office.js add-in and the
Desktop Daemon, and gives it two jobs: **Message Transport** and **Request
Routing**. Figure 9 names the wire "Named Pipe / Local IPC · Secure Local Comms",
and SRS 2.1 describes the whole product as "split across a local network loopback
boundary".

It ships the protocol and the routing, and **no socket**. The byte transport sits
behind the :class:`Transport` protocol -- a named-pipe or gRPC adapter implements
it later -- and the in-memory :class:`LoopbackTransport` is the reference
implementation the protocol is defined and tested against (ADR-020). This mirrors
the AI Runtime shipping no inference engine (ADR-019), the Plugin Runtime
shipping no plugin (ADR-018) and persistence shipping no SQLite (ADR-006).

Public API:

* :class:`IpcServer` -- the daemon side: routing, dispatch, sessions, lifecycle.
* :class:`IpcClient`, :class:`PendingCall` -- the add-in side: calls, commands,
  timeouts, cancellation, capability discovery.
* :class:`Transport`, :class:`MessageCodec`, :class:`RequestHandler` -- the three
  replaceable seams.
* :class:`LoopbackTransport`, :class:`JsonMessageCodec` -- the shipped defaults.
* Message models: :class:`IpcRequest`, :class:`IpcResponse`, :class:`IpcFault`,
  :class:`Session`, :class:`MethodDescriptor`, :class:`MethodKind`,
  :class:`HealthStatus`, and :data:`PROTOCOL_VERSION`.
* Errors: :class:`IPCError` and its subclasses.

The package depends on :mod:`teea.core` alone. It knows nothing of the Language
Server, the Plugin Runtime, the Fusion Engine or the AI Runtime: the daemon
registers handlers that call those, so the dependency runs from the handler to
them, never from the IPC layer. The constraint is enforced by
``tests/test_architecture.py``.

Typical usage, wiring a daemon method and calling it across the boundary::

    from teea.ipc import IpcClient, IpcServer, LoopbackTransport

    server = IpcServer()
    server.register("analyze", AnalyzeHandler())     # the daemon's own handler
    client_end, server_end = LoopbackTransport.pair()
    server.serve(server_end)

    client = IpcClient()
    client.connect(client_end)        # handshake: version check + session
    client.methods                    # capability discovery
    client.call("analyze", {"text": document})
    client.notify("document_changed", {"revision": 7})   # command, non-blocking
    client.close()

A handler that raises keeps its error code across the boundary: a
:class:`~teea.core.errors.TEEAError` raised in the daemon surfaces on the client
as a :class:`RemoteError` carrying that same code.
"""

from __future__ import annotations

from teea.ipc.client import IpcClient, PendingCall
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
from teea.ipc.interfaces import MessageCodec, RequestHandler, Transport
from teea.ipc.models import (
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
from teea.ipc.server import IpcServer
from teea.ipc.transport import LoopbackTransport

__all__ = [
    "PROTOCOL_VERSION",
    "HealthStatus",
    "IPCError",
    "IpcClient",
    "IpcFault",
    "IpcRequest",
    "IpcResponse",
    "IpcServer",
    "JsonMessageCodec",
    "LoopbackTransport",
    "MalformedMessageError",
    "MessageCodec",
    "MethodDescriptor",
    "MethodKind",
    "MethodNotFoundError",
    "NotConnectedError",
    "PendingCall",
    "ProtocolVersionError",
    "RemoteError",
    "RequestCancelledError",
    "RequestHandler",
    "RequestTimeoutError",
    "Session",
    "SessionError",
    "Transport",
    "TransportClosedError",
    "protocol_major",
]
