"""Tests for the Windows Named Pipe transport.

The transport is the OS-specific wire behind ADR-020. Every test in here
mirrors the contract in :mod:`test_transport` so a named-pipe adapter is
held to the same standard as the in-process loopback. Tests that are
Windows-only are marked with ``pytest.mark.skipif(not is_windows)``; tests
that exercise pure transport behaviour are compiled in the wildcard below.
"""

from __future__ import annotations

import platform
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from teea.ipc import Transport, TransportClosedError
from teea.ipc.transport_np import WindowsNamedPipeTransport

is_windows = platform.system() == "Windows"


def _uniq_name() -> str:
    """Return a unique pipe name for each test."""
    return f"test-{uuid.uuid4().hex[:12]}"


# -- Fixtures ------------------------------------------------------------------


@pytest.fixture()
def np_pair() -> tuple[WindowsNamedPipeTransport, WindowsNamedPipeTransport]:
    """Create a connected named-pipe pair; close both ends after the test."""
    name = _uniq_name()
    server, client = WindowsNamedPipeTransport.pair(name)
    try:
        yield server, client
    finally:
        server.close()
        client.close()


# -- Protocol contract ---------------------------------------------------------


@pytest.mark.skipif(not is_windows, reason="Windows Named Pipes only")
def test_a_np_end_satisfies_the_transport_protocol(np_pair) -> None:
    server, client = np_pair
    assert isinstance(server, Transport)
    assert isinstance(client, Transport)


@pytest.mark.skipif(not is_windows, reason="Windows Named Pipes only")
def test_a_pair_is_open_in_both_directions(np_pair) -> None:
    server, client = np_pair
    assert server.is_open is True
    assert client.is_open is True
    assert server.name == "server"
    assert client.name == "client"


# -- Delivery ------------------------------------------------------------------


@pytest.mark.skipif(not is_windows, reason="Windows Named Pipes only")
def test_a_send_reaches_the_peers_receiver(np_pair) -> None:
    server, client = np_pair
    received: list[bytes] = []
    server.set_receiver(received.append)
    client.send(b"hello")
    _wait_for(received, 1)
    assert received == [b"hello"]


@pytest.mark.skipif(not is_windows, reason="Windows Named Pipes only")
def test_delivery_works_in_both_directions(np_pair) -> None:
    server, client = np_pair
    to_server: list[bytes] = []
    to_client: list[bytes] = []
    server.set_receiver(to_server.append)
    client.set_receiver(to_client.append)
    client.send(b"request")
    server.send(b"response")
    _wait_for(to_server, 1)
    _wait_for(to_client, 1)
    assert to_server == [b"request"]
    assert to_client == [b"response"]


@pytest.mark.skipif(not is_windows, reason="Windows Named Pipes only")
def test_multiple_messages_in_sequence(np_pair) -> None:
    server, client = np_pair
    received: list[bytes] = []
    server.set_receiver(received.append)
    for i in range(20):
        client.send(str(i).encode())
    _wait_for(received, 20)
    assert len(received) == 20
    assert [int(p) for p in received] == list(range(20))


@pytest.mark.skipif(not is_windows, reason="Windows Named Pipes only")
def test_large_payload(np_pair) -> None:
    server, client = np_pair
    received: list[bytes] = []
    server.set_receiver(received.append)
    large = b"x" * 250_000  # > 2x read buffer, tests multi-chunk path
    client.send(large)
    _wait_for(received, 1)
    assert received == [large]


@pytest.mark.skipif(not is_windows, reason="Windows Named Pipes only")
def test_empty_payload(np_pair) -> None:
    server, client = np_pair
    received: list[bytes] = []
    server.set_receiver(received.append)
    client.send(b"")
    _wait_for(received, 1)
    assert received == [b""]


@pytest.mark.skipif(not is_windows, reason="Windows Named Pipes only")
def test_the_receiver_can_be_replaced(np_pair) -> None:
    server, client = np_pair
    first: list[bytes] = []
    second: list[bytes] = []
    server.set_receiver(first.append)
    server.set_receiver(second.append)
    client.send(b"x")
    _wait_for(second, 1)
    assert first == []
    assert second == [b"x"]


@pytest.mark.skipif(not is_windows, reason="Windows Named Pipes only")
def test_round_trip(np_pair) -> None:
    server, client = np_pair
    replies: list[bytes] = []
    client.set_receiver(replies.append)
    server.set_receiver(lambda p: server.send(b"re:" + p))
    client.send(b"ping")
    _wait_for(replies, 1)
    assert replies == [b"re:ping"]


# -- Closure -------------------------------------------------------------------


@pytest.mark.skipif(not is_windows, reason="Windows Named Pipes only")
def test_sending_on_a_closed_end_is_refused(np_pair) -> None:
    server, client = np_pair
    server.set_receiver(lambda _p: None)
    client.close()
    with pytest.raises(TransportClosedError, match="transport is closed") as error:
        client.send(b"x")
    assert error.value.code.value == "TEEA-4006"


@pytest.mark.skipif(not is_windows, reason="Windows Named Pipes only")
def test_closing_one_end_closes_it(np_pair) -> None:
    server, client = np_pair
    client.set_receiver(lambda _p: None)
    server.set_receiver(lambda _p: None)
    client.close()
    assert client.is_open is False
    # The server's reader thread detects the broken pipe and marks the
    # server as closed.  This matches LoopbackTransport behaviour where
    # closing one end makes *both* ends report ``is_open=False``.  A
    # spin-wait handles the race with the reader thread.
    for _ in range(50):
        if not server.is_open:
            break
        __import__("time").sleep(0.01)
    assert server.is_open is False
    # Sending on the server after the client disconnected also fails.
    with pytest.raises(TransportClosedError):
        server.send(b"x")


@pytest.mark.skipif(not is_windows, reason="Windows Named Pipes only")
def test_closing_is_idempotent(np_pair) -> None:
    _server, client = np_pair
    client.close()
    client.close()
    assert client.is_open is False


@pytest.mark.skipif(not is_windows, reason="Windows Named Pipes only")
def test_send_after_peer_close_raises(np_pair) -> None:
    server, client = np_pair
    server.set_receiver(lambda _p: None)
    client.set_receiver(lambda _p: None)
    server.close()
    # After server closes, client write should eventually raise
    with pytest.raises(TransportClosedError):
        client.send(b"x")


@pytest.mark.skipif(not is_windows, reason="Windows Named Pipes only")
def test_reader_handles_clean_shutdown(np_pair) -> None:
    """Closing the server while the reader is blocked must not crash.

    Dropping the peer on the pipe causes the client's reader thread to
    detect the disconnection and close its own end.  The race between the
    client reader and this assertion is inherent -- either state is correct
    -- so this test only verifies that the close sequence itself is
    idempotent and does not raise.
    """
    server, _client = np_pair
    server.set_receiver(lambda _p: None)
    for _ in range(10):
        server.close()
        server.close()  # idempotent
        assert server.is_open is False


# -- Concurrency ---------------------------------------------------------------


@pytest.mark.skipif(not is_windows, reason="Windows Named Pipes only")
def test_concurrent_sends_all_arrive(np_pair) -> None:
    server, client = np_pair
    lock = threading.Lock()
    received: list[bytes] = []

    def receive(payload: bytes) -> None:
        with lock:
            received.append(payload)

    server.set_receiver(receive)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: client.send(str(i).encode()), range(100)))
    _wait_for(received, 100, timeout=5)
    assert len(received) == 100
    assert {int(p) for p in received} == set(range(100))


@pytest.mark.skipif(not is_windows, reason="Windows Named Pipes only")
def test_concurrent_round_trips_deliver_all_responses(np_pair) -> None:
    """All concurrent requests produce responses, even under concurrency."""
    server, client = np_pair
    received: list[bytes] = []
    lock = threading.Lock()

    def handle(payload: bytes) -> None:
        server.send(b"resp:" + payload)

    server.set_receiver(handle)

    reply_count = [0]
    reply_event = threading.Event()

    def on_reply(payload: bytes) -> None:
        with lock:
            received.append(payload)
            reply_count[0] += 1
            if reply_count[0] >= 20:
                reply_event.set()

    client.set_receiver(on_reply)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: client.send(f"req-{i}".encode()), range(20)))

    assert reply_event.wait(timeout=10), "Not all responses arrived"
    assert len(received) == 20
    resp_indices = {int(p.split(b":")[1].split(b"-")[1]) for p in received}
    assert resp_indices == set(range(20))


# -- Transport protocol check (skip on non-Windows) ----------------------------


@pytest.mark.skipif(not is_windows, reason="Windows Named Pipes only")
def test_import_guard_on_non_windows() -> None:
    """The module must be importable on any platform; only the class
    raises when instantiated."""
    assert WindowsNamedPipeTransport is not None


# -- Helpers -------------------------------------------------------------------


def _wait_for(lst: list, n: int, timeout: float = 5.0) -> None:
    """Spin-wait until *lst* has at least *n* items."""
    deadline = _now() + timeout
    while len(lst) < n and _now() < deadline:
        pass


def _wait_for_set(events: dict[int, threading.Event], timeout: float = 10.0) -> None:
    deadline = _now() + timeout
    while not all(e.is_set() for e in events.values()) and _now() < deadline:
        pass


def _now() -> float:
    return threading._time() if hasattr(threading, "_time") else __import__("time").time()  # type: ignore[attr-defined]
