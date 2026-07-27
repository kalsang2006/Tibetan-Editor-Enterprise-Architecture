"""In-memory loopback transport: the reference :class:`Transport`.

SRS 2.1 calls the boundary a "loopback", and this is a loopback in its purest
form -- two ends in one process, each :meth:`send` delivering straight to the
other's receiver. It is not a stand-in for a named pipe; it is the transport the
whole protocol is defined and tested against, and the one the daemon and add-in
use when they run in-process. A named-pipe or gRPC transport is the OS-specific
adapter that implements the same protocol later (ADR-020).

Delivery model
--------------
By default delivery is **synchronous**: :meth:`send` calls the peer's receiver
inline and returns when it has run. That makes a request/response round trip
deterministic and, for a synchronous server, complete before :meth:`send`
returns. Passing an executor makes delivery **asynchronous** -- the receiver runs
on the executor -- which is how the timeout and cancellation behaviour is
exercised, since a response can then arrive late or not at all.

Closing either end closes the channel in both directions: a half-open loopback
would let one side believe it could still send.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Executor

from teea.ipc.errors import TransportClosedError


class LoopbackTransport:
    """One end of an in-process duplex channel.

    Satisfies the :class:`~teea.ipc.interfaces.Transport` protocol. Construct a
    connected pair with :meth:`pair`; constructing one directly yields an end
    with no peer, which cannot send.

    Args:
        name: A label for diagnostics ("client" / "server").
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._peer: LoopbackTransport | None = None
        self._receiver: Callable[[bytes], None] | None = None
        self._executor: Executor | None = None
        self._open = True
        self._lock = threading.Lock()

    @classmethod
    def pair(
        cls, *, executor: Executor | None = None
    ) -> tuple[LoopbackTransport, LoopbackTransport]:
        """Return a connected ``(client, server)`` pair.

        Args:
            executor: If given, each end delivers to the other on this executor,
                making delivery asynchronous. Otherwise delivery is synchronous.

        Returns:
            Two transports whose sends reach each other.
        """
        client = cls("client")
        server = cls("server")
        client._peer = server
        server._peer = client
        client._executor = executor
        server._executor = executor
        return client, server

    @property
    def name(self) -> str:
        """The diagnostic label of this end."""
        return self._name

    @property
    def is_open(self) -> bool:
        """Whether the channel is open in both directions."""
        with self._lock:
            if not self._open or self._peer is None:
                return False
            peer = self._peer
        return peer._is_open_locked()

    def _is_open_locked(self) -> bool:
        with self._lock:
            return self._open

    def set_receiver(self, receiver: Callable[[bytes], None]) -> None:
        """Register the callback the peer's sends are delivered to."""
        with self._lock:
            self._receiver = receiver

    def send(self, payload: bytes) -> None:
        """Deliver ``payload`` to the peer's receiver.

        Raises:
            TransportClosedError: If either end is closed, or the peer has no
                receiver registered yet.
        """
        with self._lock:
            if not self._open:
                raise TransportClosedError("The transport is closed.", context={"end": self._name})
            peer = self._peer
        if peer is None or not peer._is_open_locked():
            raise TransportClosedError("The peer end is closed.", context={"end": self._name})
        receiver = peer._receiver_locked()
        if receiver is None:
            raise TransportClosedError(
                "The peer is not ready to receive.", context={"end": self._name}
            )
        if self._executor is not None:
            self._executor.submit(receiver, payload)
        else:
            receiver(payload)

    def _receiver_locked(self) -> Callable[[bytes], None] | None:
        with self._lock:
            return self._receiver

    def close(self) -> None:
        """Close this end. Idempotent."""
        with self._lock:
            self._open = False


__all__ = ["LoopbackTransport"]
