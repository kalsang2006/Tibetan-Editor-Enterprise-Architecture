"""The Local IPC abstractions (interfaces) for TEEA.

Figure 3 draws the Local IPC Layer as one box, but it has three replaceable
seams, stated here so each can change without the others: the **transport** that
moves bytes, the **codec** that turns messages into bytes, and the **handler**
that answers a routed call.

The load-bearing one is :class:`Transport`. SRS 2.1 names the wire as
"gRPC/Named Pipes" over a loopback boundary -- a native, OS-specific mechanism.
That mechanism is this protocol: the server and client speak through it and never
touch a socket, so a named-pipe or gRPC transport drops in behind the same
interface. No such transport ships here, because it is OS-specific I/O outside
the offline pure-Python core (ADR-002); the in-memory
:class:`~teea.ipc.transport.LoopbackTransport` is the reference implementation
the protocol is validated against. See ADR-020.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol, runtime_checkable

from teea.ipc.models import IpcRequest, IpcResponse, Session


@runtime_checkable
class Transport(Protocol):
    """A duplex byte channel between one client and one server.

    Message-oriented: each :meth:`send` delivers one whole framed payload to the
    peer, and the peer's registered receiver is called with it. Implementations
    must be safe to call :meth:`send` from several threads at once, since the
    server may answer many concurrent requests over one transport.
    """

    def send(self, payload: bytes) -> None:
        """Deliver one payload to the peer.

        Args:
            payload: The framed bytes to send.

        Raises:
            TransportClosedError: If this end or the peer is closed.
        """
        ...

    def set_receiver(self, receiver: Callable[[bytes], None]) -> None:
        """Register the callback invoked with each payload the peer sends.

        Called once, before traffic flows. The receiver runs on whatever thread
        the peer's :meth:`send` runs on, so it must be thread-safe.
        """
        ...

    def close(self) -> None:
        """Close the channel. Idempotent. After this, :meth:`send` raises."""
        ...

    @property
    def is_open(self) -> bool:
        """Whether the channel is open in both directions."""
        ...


@runtime_checkable
class MessageCodec(Protocol):
    """Turns messages into bytes and back: Figure 3's serialization concern.

    Stated as a seam so a future gRPC transport can pair a protobuf codec with
    the same server and client. The shipped default is JSON.
    """

    def encode(self, message: IpcRequest | IpcResponse) -> bytes:
        """Serialize a request or response to bytes."""
        ...

    def decode_request(self, payload: bytes) -> IpcRequest:
        """Deserialize a request, or raise ``MalformedMessageError``."""
        ...

    def decode_response(self, payload: bytes) -> IpcResponse:
        """Deserialize a response, or raise ``MalformedMessageError``."""
        ...


@runtime_checkable
class RequestHandler(Protocol):
    """Answers one routed method: the extension point for daemon features.

    The daemon registers a handler per method -- one that calls the Language
    Server, another the AI Runtime, and so on. The IPC layer knows none of them;
    it routes to whatever is registered, which is what keeps ``teea.ipc``
    dependent on ``teea.core`` alone.

    A handler for a query returns a result mapping. A handler for a command may
    return one too, but it is discarded, because the caller did not wait.
    Implementations must be safe to call concurrently: the server may dispatch
    several requests at once through an executor.
    """

    def handle(self, params: Mapping[str, Any], session: Session) -> Mapping[str, Any]:
        """Serve one call.

        Args:
            params: The call's arguments.
            session: The session the call belongs to.

        Returns:
            The result, as a JSON-serializable mapping.

        Raises:
            Exception: Any failure. A :class:`~teea.core.errors.TEEAError` keeps
                its code across the boundary; anything else is reported as a
                generic handler failure.
        """
        ...


__all__ = ["MessageCodec", "RequestHandler", "Transport"]
