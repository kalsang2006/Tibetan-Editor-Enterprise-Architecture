"""Tests for the reference loopback transport.

The transport is the seam ADR-020 put the OS-specific wire behind, so what has to
hold here is the *contract* a named-pipe adapter will also have to honour:
delivery to the peer's receiver, both-directions closure, and safety under
concurrent sends.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from teea.ipc import LoopbackTransport, Transport, TransportClosedError


def collector() -> tuple[list[bytes], threading.Lock]:
    return [], threading.Lock()


# -- Contract ------------------------------------------------------------------
def test_a_loopback_end_satisfies_the_transport_protocol() -> None:
    client, server = LoopbackTransport.pair()
    assert isinstance(client, Transport)
    assert isinstance(server, Transport)


def test_a_pair_is_open_in_both_directions() -> None:
    client, server = LoopbackTransport.pair()
    assert client.is_open is True
    assert server.is_open is True
    assert client.name == "client"
    assert server.name == "server"


# -- Delivery ------------------------------------------------------------------
def test_a_send_reaches_the_peers_receiver() -> None:
    client, server = LoopbackTransport.pair()
    received: list[bytes] = []
    server.set_receiver(received.append)
    client.send(b"hello")
    assert received == [b"hello"]


def test_delivery_works_in_both_directions() -> None:
    client, server = LoopbackTransport.pair()
    to_server: list[bytes] = []
    to_client: list[bytes] = []
    server.set_receiver(to_server.append)
    client.set_receiver(to_client.append)
    client.send(b"request")
    server.send(b"response")
    assert to_server == [b"request"]
    assert to_client == [b"response"]


def test_synchronous_delivery_completes_before_send_returns() -> None:
    """The default: a round trip is deterministic and needs no waiting."""
    client, server = LoopbackTransport.pair()
    order: list[str] = []
    server.set_receiver(lambda _p: order.append("received"))
    client.send(b"x")
    order.append("returned")
    assert order == ["received", "returned"]


def test_an_executor_makes_delivery_asynchronous() -> None:
    """Which is how a late or never-arriving response can be exercised."""
    done = threading.Event()
    with ThreadPoolExecutor(max_workers=1) as pool:
        client, server = LoopbackTransport.pair(executor=pool)
        server.set_receiver(lambda _p: done.set())
        client.send(b"x")
        assert done.wait(2.0)


def test_the_receiver_can_be_replaced() -> None:
    client, server = LoopbackTransport.pair()
    first: list[bytes] = []
    second: list[bytes] = []
    server.set_receiver(first.append)
    server.set_receiver(second.append)
    client.send(b"x")
    assert first == [] and second == [b"x"]


# -- Closure -------------------------------------------------------------------
def test_sending_on_a_closed_end_is_refused() -> None:
    client, server = LoopbackTransport.pair()
    server.set_receiver(lambda _p: None)
    client.close()
    with pytest.raises(TransportClosedError, match="transport is closed") as error:
        client.send(b"x")
    assert error.value.code.value == "TEEA-4006"


def test_closing_one_end_closes_the_channel_for_the_other() -> None:
    """A half-open loopback would let one side believe it could still send."""
    client, server = LoopbackTransport.pair()
    client.set_receiver(lambda _p: None)
    server.set_receiver(lambda _p: None)
    client.close()
    assert server.is_open is False
    with pytest.raises(TransportClosedError, match="peer end is closed"):
        server.send(b"x")


def test_closing_is_idempotent() -> None:
    client, _server = LoopbackTransport.pair()
    client.close()
    client.close()
    assert client.is_open is False


def test_sending_before_the_peer_is_ready_is_refused() -> None:
    """A peer with no receiver cannot take delivery, and silence would hide it."""
    client, _server = LoopbackTransport.pair()
    with pytest.raises(TransportClosedError, match="not ready to receive"):
        client.send(b"x")


def test_an_end_with_no_peer_cannot_send() -> None:
    """Constructing one directly, rather than via pair(), leaves it unconnected."""
    lone = LoopbackTransport("lone")
    assert lone.is_open is False
    with pytest.raises(TransportClosedError, match="peer end is closed"):
        lone.send(b"x")


# -- Concurrency ---------------------------------------------------------------
def test_concurrent_sends_all_arrive() -> None:
    """The server answers many requests over one transport, from many threads."""
    client, server = LoopbackTransport.pair()
    received, lock = collector()

    def receive(payload: bytes) -> None:
        with lock:
            received.append(payload)

    server.set_receiver(receive)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: client.send(str(i).encode()), range(400)))
    assert len(received) == 400
    assert {int(p) for p in received} == set(range(400))


def test_a_receiver_may_send_back_without_deadlocking() -> None:
    """Request/response is exactly this: the receiver replies while being called.

    No lock may be held across the receiver call, or a synchronous round trip
    would deadlock against itself.
    """
    client, server = LoopbackTransport.pair()
    replies: list[bytes] = []
    client.set_receiver(replies.append)
    server.set_receiver(lambda payload: server.send(b"re:" + payload))
    client.send(b"ping")
    assert replies == [b"re:ping"]


def test_closing_during_concurrent_sends_does_not_corrupt() -> None:
    """Some sends land, the rest are refused; none may raise anything else."""
    client, server = LoopbackTransport.pair()
    received, lock = collector()

    def receive(payload: bytes) -> None:
        with lock:
            received.append(payload)

    server.set_receiver(receive)
    refused = 0

    def attempt(index: int) -> None:
        nonlocal refused
        try:
            client.send(b"x")
        except TransportClosedError:
            refused += 1

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(attempt, i) for i in range(200)]
        client.close()
        for future in futures:
            future.result()
    assert len(received) + refused == 200
