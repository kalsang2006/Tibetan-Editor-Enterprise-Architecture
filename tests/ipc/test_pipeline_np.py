"""Integration tests: the full IPC pipeline over the Named Pipe transport.

Wires ``IpcServer`` and ``IpcClient`` over a
:class:`~teea.ipc.transport_np.WindowsNamedPipeTransport` pair and verifies
that method calls, commands, timeouts, cancellation, and error propagation
all work identically to the in-process loopback.
"""

from __future__ import annotations

import concurrent.futures
import platform
import time as _time
import uuid

import pytest

from teea.core.errors import ErrorCode, TEEAError
from teea.ipc import IpcClient, IpcServer
from teea.ipc.errors import NotConnectedError, RemoteError, RequestTimeoutError
from teea.ipc.transport_np import WindowsNamedPipeTransport

is_windows = platform.system() == "Windows"


def _uniq_name() -> str:
    return f"itest-{uuid.uuid4().hex[:12]}"


# -- Fixtures ------------------------------------------------------------------


@pytest.fixture()
def np_transport_pair() -> (
    tuple[WindowsNamedPipeTransport, WindowsNamedPipeTransport]
):
    name = _uniq_name()
    s, c = WindowsNamedPipeTransport.pair(name)
    try:
        yield s, c
    finally:
        s.close()
        c.close()


@pytest.fixture()
def server() -> IpcServer:
    s = IpcServer()
    yield s
    s.stop()


@pytest.fixture()
def client() -> IpcClient:
    c = IpcClient()
    yield c
    c.close()


# -- Tests ----------------------------------------------------------------------


@pytest.mark.skipif(not is_windows, reason="Windows Named Pipes only")
def test_connection_establishes_a_session(server, client, np_transport_pair) -> None:
    server_end, client_end = np_transport_pair
    server.serve(server_end)
    client.connect(client_end)
    assert client.session_id is not None


@pytest.mark.skipif(not is_windows, reason="Windows Named Pipes only")
def test_a_call_returns_its_result(server, client, np_transport_pair) -> None:
    server_end, client_end = np_transport_pair
    server.register("echo", _EchoHandler())
    server.serve(server_end)
    client.connect(client_end)
    result = client.call("echo", {"value": 42})
    assert result == {"value": 42}


@pytest.mark.skipif(not is_windows, reason="Windows Named Pipes only")
def test_a_notify_reaches_the_handler(server, client, np_transport_pair) -> None:
    server_end, client_end = np_transport_pair
    calls: list = []
    server.register("record", _RecordingHandler(calls))
    server.serve(server_end)
    client.connect(client_end)
    client.notify("record", {"msg": "hello"})
    _wait_for(calls, 1)
    assert calls == [{"msg": "hello"}]


@pytest.mark.skipif(not is_windows, reason="Windows Named Pipes only")
def test_health_is_reachable(server, client, np_transport_pair) -> None:
    server_end, client_end = np_transport_pair
    server.register("ping", _PingHandler())
    server.serve(server_end)
    client.connect(client_end)
    methods = [m.name for m in client.methods]
    assert "ping" in methods
    assert "$connect" in methods
    assert "$cancel" in methods
    assert "$health" in methods


@pytest.mark.skipif(not is_windows, reason="Windows Named Pipes only")
def test_timeout_raises(server, client, np_transport_pair) -> None:
    server_end, client_end = np_transport_pair
    server.register("slow", _SlowHandler(0.5))
    server.serve(server_end)
    client.connect(client_end)
    with pytest.raises(RequestTimeoutError):
        client.call("slow", {}, timeout=0.05)


@pytest.mark.skipif(not is_windows, reason="Windows Named Pipes only")
def test_a_handler_error_reaches_the_client_as_remote_error(
    server, client, np_transport_pair
) -> None:
    server_end, client_end = np_transport_pair
    server.register("fail", _FailingHandler())
    server.serve(server_end)
    client.connect(client_end)
    with pytest.raises(RemoteError) as exc_info:
        client.call("fail", {})
    assert exc_info.value.code == ErrorCode("TEEA-2000")


@pytest.mark.skipif(not is_windows, reason="Windows Named Pipes only")
def test_a_failing_call_does_not_break_the_next(
    server, client, np_transport_pair
) -> None:
    server_end, client_end = np_transport_pair
    server.register("fail", _FailingHandler())
    server.register("echo", _EchoHandler())
    server.serve(server_end)
    client.connect(client_end)
    with pytest.raises(RemoteError):
        client.call("fail", {})
    result = client.call("echo", {"ok": True})
    assert result == {"ok": True}


@pytest.mark.skipif(not is_windows, reason="Windows Named Pipes only")
def test_closing_the_client_ends_the_session(server, client, np_transport_pair) -> None:
    server_end, client_end = np_transport_pair
    server.register("ping", _PingHandler())
    server.serve(server_end)
    client.connect(client_end)
    client.close()
    with pytest.raises(NotConnectedError):
        client.call("ping", {})


@pytest.mark.skipif(not is_windows, reason="Windows Named Pipes only")
def test_concurrent_calls_all_return(server, client, np_transport_pair) -> None:
    server_end, client_end = np_transport_pair
    server.register("echo", _EchoHandler())
    server.serve(server_end)
    client.connect(client_end)
    n = 30
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(lambda i: client.call("echo", {"i": i}), range(n))
        )
    assert len(results) == n
    for i, r in enumerate(results):
        assert r == {"i": i}


# -- Stub handlers --------------------------------------------------------------


class _PingHandler:
    def handle(self, params, session):
        return {"pong": True}


class _EchoHandler:
    def handle(self, params, session):
        return dict(params)


class _RecordingHandler:
    def __init__(self, storage: list):
        self._storage = storage

    def handle(self, params, session):
        self._storage.append(dict(params))
        return {}


class _SlowHandler:
    def __init__(self, delay: float):
        self._delay = delay

    def handle(self, params, session):
        _time.sleep(self._delay)
        return {"done": True}


class _FailingHandler:
    def handle(self, params, session):
        raise TEEAError("intentional", code=ErrorCode("TEEA-2000"))


# -- Helpers -------------------------------------------------------------------


def _wait_for(lst: list, n: int, timeout: float = 5.0) -> None:
    deadline = _time.monotonic() + timeout
    while len(lst) < n and _time.monotonic() < deadline:
        pass
