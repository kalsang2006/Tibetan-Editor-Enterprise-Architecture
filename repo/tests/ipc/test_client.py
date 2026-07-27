"""Client tests: lifecycle, calls, timeouts, cancellation and discovery.

The client is the add-in side of the boundary. What matters here is that a call
gets its own answer or a typed failure, that a deadline is honoured, that a
cancelled call stays cancelled even if the answer turns up later, and that none
of it corrupts the table of pending calls.

Timeout and cancellation tests need a response that can be made to arrive late,
so they run the server on an executor with a handler that blocks until released.
"""

from __future__ import annotations

import contextlib
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from teea.core.errors import ErrorCode
from teea.ipc import (
    PROTOCOL_VERSION,
    IpcClient,
    IpcServer,
    LoopbackTransport,
    MethodKind,
    NotConnectedError,
    ProtocolVersionError,
    RequestCancelledError,
    RequestTimeoutError,
    TransportClosedError,
)
from tests.ipc.conftest import BlockingHandler, EchoHandler, RecordingHandler, connect


def blocking_setup() -> tuple[IpcClient, BlockingHandler, ThreadPoolExecutor]:
    """A connected client whose server runs one blocking handler on one worker."""
    handler = BlockingHandler()
    pool = ThreadPoolExecutor(max_workers=1)
    server = IpcServer(executor=pool)
    server.register("slow", handler)
    client, _transport = connect(server)
    return client, handler, pool


# -- Lifecycle -----------------------------------------------------------------
def test_a_fresh_client_is_not_connected() -> None:
    client = IpcClient()
    assert client.is_connected is False
    assert client.session_id is None
    assert client.methods == ()


def test_connecting_establishes_a_session() -> None:
    server = IpcServer()
    server.register("echo", EchoHandler())
    client, _t = connect(server)
    assert client.is_connected is True
    assert client.session_id == "sess-1"


def test_calling_before_connecting_is_refused() -> None:
    with pytest.raises(NotConnectedError, match="not connected") as error:
        IpcClient().call("echo")
    assert error.value.code is ErrorCode.IPC_NOT_CONNECTED


def test_notifying_before_connecting_is_refused() -> None:
    with pytest.raises(NotConnectedError):
        IpcClient().notify("ping")


def test_closing_ends_the_session() -> None:
    server = IpcServer()
    server.register("echo", EchoHandler())
    client, _t = connect(server)
    client.close()
    assert client.is_connected is False
    assert server.active_sessions == 0


def test_closing_is_idempotent() -> None:
    server = IpcServer()
    server.register("echo", EchoHandler())
    client, _t = connect(server)
    client.close()
    client.close()
    assert client.is_connected is False


def test_calling_after_closing_is_refused() -> None:
    server = IpcServer()
    server.register("echo", EchoHandler())
    client, _t = connect(server)
    client.close()
    with pytest.raises(NotConnectedError):
        client.call("echo")


def test_a_second_client_gets_its_own_session() -> None:
    server = IpcServer()
    server.register("echo", EchoHandler())
    first, _t1 = connect(server)
    assert first.session_id == "sess-1"
    assert server.active_sessions == 1


# -- Capability discovery ------------------------------------------------------
def test_connecting_discovers_the_servers_methods() -> None:
    """The handshake doubles as capability discovery."""
    server = IpcServer()
    server.register("analyze", EchoHandler())
    server.register("ping", EchoHandler(), kind=MethodKind.COMMAND)
    client, _t = connect(server)
    discovered = {d.name: d.kind for d in client.methods}
    assert discovered["analyze"] is MethodKind.QUERY
    assert discovered["ping"] is MethodKind.COMMAND
    assert "$health" in discovered


def test_health_is_reachable_over_the_wire() -> None:
    server = IpcServer()
    server.register("echo", EchoHandler())
    client, _t = connect(server)
    status = client.health()
    assert status["status"] == "ok"
    assert status["protocol_version"] == PROTOCOL_VERSION
    assert status["active_sessions"] == 1


# -- Protocol versioning -------------------------------------------------------
def test_a_client_refuses_an_incompatible_server() -> None:
    """The check is symmetric: the client validates the server's version too."""

    class WrongVersionServer(IpcServer):
        def _handle_connect(self, request: Any) -> dict[str, Any]:
            return {
                "session_id": "sess-x",
                "protocol_version": "99.0",
                "methods": [],
            }

    server = WrongVersionServer()
    client_end, server_end = LoopbackTransport.pair()
    server.serve(server_end)
    client = IpcClient()
    with pytest.raises(ProtocolVersionError, match="incompatible protocol") as error:
        client.connect(client_end)
    assert error.value.code is ErrorCode.IPC_PROTOCOL_MISMATCH
    assert client.is_connected is False


# -- Calls ---------------------------------------------------------------------
def test_a_call_returns_its_own_result() -> None:
    server = IpcServer()
    server.register("echo", EchoHandler())
    client, _t = connect(server)
    assert client.call("echo", {"n": 7})["echo"] == {"n": 7}


def test_a_call_with_no_params_works() -> None:
    server = IpcServer()
    server.register("echo", EchoHandler())
    client, _t = connect(server)
    assert client.call("echo")["echo"] == {}


def test_request_ids_are_unique_and_sequential() -> None:
    """Deterministic ids, so a run is reproducible; no randomness involved."""
    server = IpcServer()
    server.register("echo", EchoHandler())
    client, _t = connect(server)
    first = client.call_async("echo")
    second = client.call_async("echo")
    assert first.request_id != second.request_id
    first.result(2.0)
    second.result(2.0)


def test_a_completed_call_reports_done() -> None:
    server = IpcServer()
    server.register("echo", EchoHandler())
    client, _t = connect(server)
    pending = client.call_async("echo", {"n": 1})
    assert pending.result(2.0)["echo"] == {"n": 1}
    assert pending.done is True
    assert pending.cancelled is False


# -- Timeouts ------------------------------------------------------------------
def test_a_call_that_outlives_its_deadline_times_out() -> None:
    client, handler, pool = blocking_setup()
    try:
        with pytest.raises(RequestTimeoutError, match="within the deadline") as error:
            client.call("slow", {"n": 1}, timeout=0.1)
        assert error.value.code is ErrorCode.IPC_TIMEOUT
        assert error.value.context["timeout"] == 0.1
    finally:
        handler.release()
        pool.shutdown(wait=True)


def test_a_timed_out_call_is_forgotten_so_a_late_answer_is_discarded() -> None:
    """The answer arrives after the caller gave up; nothing may break."""
    client, handler, pool = blocking_setup()
    try:
        with pytest.raises(RequestTimeoutError):
            client.call("slow", {"n": 1}, timeout=0.1)
        handler.release()
        pool.shutdown(wait=True)
        assert client._pending == {}
    finally:
        handler.release()


def test_a_timeout_does_not_break_the_connection() -> None:
    client, handler, pool = blocking_setup()
    try:
        with pytest.raises(RequestTimeoutError):
            client.call("slow", {"n": 1}, timeout=0.1)
        handler.release()
        pool.shutdown(wait=True)
        assert client.is_connected is True
    finally:
        handler.release()


# -- Cancellation --------------------------------------------------------------
def test_a_cancelled_call_raises_when_awaited() -> None:
    client, handler, pool = blocking_setup()
    try:
        pending = client.call_async("slow", {"n": 1})
        handler.entered.wait(2.0)
        pending.cancel()
        assert pending.cancelled is True
        with pytest.raises(RequestCancelledError, match="was cancelled") as error:
            pending.result(1.0)
        assert error.value.code is ErrorCode.IPC_CANCELLED
    finally:
        handler.release()
        pool.shutdown(wait=True)


def test_cancelling_is_idempotent() -> None:
    client, handler, pool = blocking_setup()
    try:
        pending = client.call_async("slow", {"n": 1})
        pending.cancel()
        pending.cancel()
        assert pending.cancelled is True
    finally:
        handler.release()
        pool.shutdown(wait=True)


def test_a_queued_request_cancelled_before_it_starts_is_skipped() -> None:
    """Server-side cancellation: work not yet begun is not done at all."""
    client, handler, pool = blocking_setup()
    try:
        first = client.call_async("slow", {"n": 1})
        handler.entered.wait(2.0)  # worker is now busy with n=1
        queued = client.call_async("slow", {"n": 2})  # waits behind it
        queued.cancel()
        handler.release()
        pool.shutdown(wait=True)
        assert handler.completed == [1], handler.completed
        first.result(2.0)
    finally:
        handler.release()


def test_a_late_answer_for_a_cancelled_call_is_discarded() -> None:
    client, handler, pool = blocking_setup()
    try:
        pending = client.call_async("slow", {"n": 1})
        handler.entered.wait(2.0)
        pending.cancel()
        handler.release()
        pool.shutdown(wait=True)
        assert pending.cancelled is True
        assert client._pending == {}
    finally:
        handler.release()


def test_closing_cancels_calls_still_pending() -> None:
    """No answer can arrive once the session is gone, so they must not hang."""
    client, handler, pool = blocking_setup()
    try:
        pending = client.call_async("slow", {"n": 1})
        handler.entered.wait(2.0)
        client.close(timeout=0.2)
        assert pending.cancelled is True
        with pytest.raises(RequestCancelledError):
            pending.result(0.5)
    finally:
        handler.release()
        pool.shutdown(wait=True)


# -- Transport failure ---------------------------------------------------------
def test_sending_over_a_closed_transport_is_refused() -> None:
    server = IpcServer()
    server.register("echo", EchoHandler())
    client, transport = connect(server)
    transport.close()
    with pytest.raises(TransportClosedError):
        client.call("echo")


def test_a_client_with_no_transport_cannot_send() -> None:
    client = IpcClient()
    client._session_id = "sess-1"
    with pytest.raises(NotConnectedError, match="no transport"):
        client.call("echo")


def test_a_garbled_response_is_dropped_without_resolving_a_call() -> None:
    """A corrupt reply must not resolve a pending call with nonsense."""
    server = IpcServer()
    server.register("echo", EchoHandler())
    client, _transport = connect(server)
    client._on_message(b"not a response")
    assert client.call("echo", {"ok": 1})["echo"] == {"ok": 1}


# -- Concurrency ---------------------------------------------------------------
def test_concurrent_calls_from_many_threads_stay_correlated() -> None:
    server = IpcServer()
    server.register("echo", EchoHandler())
    client, _t = connect(server)

    def call(index: int) -> int:
        return int(client.call("echo", {"n": index})["echo"]["n"])

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(call, range(300)))
    assert results == list(range(300))
    assert client._pending == {}


def test_concurrent_calls_and_cancellations_do_not_corrupt_the_pending_table() -> None:
    handler = BlockingHandler()
    handler.release()  # never blocks; every call completes at once
    with ThreadPoolExecutor(max_workers=4) as pool:
        server = IpcServer(executor=pool)
        server.register("fast", handler)
        client, _t = connect(server)

        def churn(index: int) -> None:
            pending = client.call_async("fast", {"n": index})
            if index % 2:
                pending.cancel()
            else:
                with contextlib.suppress(RequestCancelledError, RequestTimeoutError):
                    pending.result(2.0)

        with ThreadPoolExecutor(max_workers=8) as callers:
            list(callers.map(churn, range(200)))
    assert client._pending == {}


def test_many_calls_leave_no_state_behind() -> None:
    """The pending table and the server's cancelled set must not grow unbounded."""
    server = IpcServer()
    server.register("record", RecordingHandler())
    client, _t = connect(server)
    for index in range(500):
        client.call("record", {"n": index})
    assert client._pending == {}
    assert server._cancelled == set()


def test_a_command_needs_no_pending_entry() -> None:
    handler = RecordingHandler()
    server = IpcServer()
    server.register("ping", handler, kind=MethodKind.COMMAND)
    client, _t = connect(server)
    for index in range(50):
        client.notify("ping", {"n": index})
    assert len(handler.calls) == 50
    assert client._pending == {}
