"""Handler doubles and fixtures for the Local IPC suite.

The IPC layer routes to handlers it knows nothing about, so the handlers here are
deliberately minimal and mostly badly behaved: they raise typed errors, raise
untyped ones, block until released, or record what they were given. What is under
test is the *layer*, not any feature.

Every fixture wires a real server to a real client over a real
:class:`~teea.ipc.LoopbackTransport`, because the protocol is only meaningful end
to end.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator, Mapping
from typing import Any

import pytest

from teea.core.errors import ConfigurationError
from teea.ipc import (
    IpcClient,
    IpcServer,
    LoopbackTransport,
    MethodKind,
    Session,
)


class EchoHandler:
    """Returns its params, plus the session it was called under."""

    def handle(self, params: Mapping[str, Any], session: Session) -> Mapping[str, Any]:
        return {"echo": dict(params), "session": session.session_id}


class RecordingHandler:
    """Records every call, thread-safely, and returns a running count."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.calls: list[Mapping[str, Any]] = []

    def handle(self, params: Mapping[str, Any], session: Session) -> Mapping[str, Any]:
        with self._lock:
            self.calls.append(dict(params))
            return {"count": len(self.calls)}


class TypedFailureHandler:
    """Raises a TEEAError, whose code must survive the crossing."""

    def handle(self, params: Mapping[str, Any], session: Session) -> Mapping[str, Any]:
        raise ConfigurationError("no dictionary available", context={"path": "x.json"})


class UntypedFailureHandler:
    """Raises a plain exception, which becomes a generic handler failure."""

    def handle(self, params: Mapping[str, Any], session: Session) -> Mapping[str, Any]:
        raise ValueError("something went wrong")


class SilentFailureHandler:
    """Raises an exception with no message at all."""

    def handle(self, params: Mapping[str, Any], session: Session) -> Mapping[str, Any]:
        raise RuntimeError


class BlockingHandler:
    """Blocks until released, so timeouts and cancellation can be exercised."""

    def __init__(self) -> None:
        self.gate = threading.Event()
        self.entered = threading.Event()
        self.completed: list[Any] = []

    def handle(self, params: Mapping[str, Any], session: Session) -> Mapping[str, Any]:
        self.entered.set()
        self.gate.wait(5.0)
        self.completed.append(params.get("n"))
        return {"n": params.get("n")}

    def release(self) -> None:
        self.gate.set()


def build_server(**handlers: object) -> IpcServer:
    """A server routing ``name=handler`` pairs as queries."""
    server = IpcServer()
    for name, handler in handlers.items():
        server.register(name, handler)  # type: ignore[arg-type]
    return server


def connect(server: IpcServer) -> tuple[IpcClient, LoopbackTransport]:
    """Serve ``server`` on a fresh loopback pair and return a connected client."""
    client_end, server_end = LoopbackTransport.pair()
    server.serve(server_end)
    client = IpcClient()
    client.connect(client_end)
    return client, client_end


@pytest.fixture
def echo_server() -> IpcServer:
    """A server routing ``echo`` (query) and ``ping`` (command)."""
    server = IpcServer()
    server.register("echo", EchoHandler())
    server.register("ping", EchoHandler(), kind=MethodKind.COMMAND)
    return server


@pytest.fixture
def connected(echo_server: IpcServer) -> Iterator[tuple[IpcClient, IpcServer]]:
    """A connected ``(client, server)`` pair over loopback."""
    client, _transport = connect(echo_server)
    yield client, echo_server
    client.close()
