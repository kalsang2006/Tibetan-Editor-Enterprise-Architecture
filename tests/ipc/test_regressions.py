"""Regression tests for the defects the adversarial review surfaced.

Each was independently reproduced against the shipped code before it was fixed
(`scratchpad/verify_defects.py`), and each test here was confirmed to fail
without its fix. They are grouped by the fix, and named for the failure mode, so
a reintroduction points straight at what broke.

The identifiers (G1, G2, …) match the handoff and the completion report.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from teea.core.errors import ConfigurationError, ErrorCode
from teea.ipc import (
    IpcClient,
    IpcRequest,
    IpcResponse,
    IpcServer,
    JsonMessageCodec,
    LoopbackTransport,
    NotConnectedError,
    RemoteError,
    RequestCancelledError,
    RequestTimeoutError,
    Session,
    SessionError,
    TransportClosedError,
)
from teea.ipc.client import PendingCall
from teea.ipc.errors import SessionError as HandlerRaisableSessionError
from tests.ipc.conftest import BlockingHandler, EchoHandler, RecordingHandler, connect


def blocking() -> tuple[IpcClient, BlockingHandler, ThreadPoolExecutor]:
    handler = BlockingHandler()
    pool = ThreadPoolExecutor(max_workers=1)
    server = IpcServer(executor=pool)
    server.register("slow", handler)
    client, _t = connect(server)
    return client, handler, pool


# -- G1: _pending must not leak on a failed send ------------------------------
def test_g1_a_failed_send_does_not_leak_a_pending_entry() -> None:
    server = IpcServer()
    server.register("work", RecordingHandler())
    client, transport = connect(server)
    transport.close()
    for _ in range(20):
        with pytest.raises(TransportClosedError):
            client.call("work", {"n": 1}, timeout=0.05)
    assert client._pending == {}


def test_g1_a_send_with_no_transport_leaves_no_pending_entry() -> None:
    client = IpcClient()
    client._session_id = "sess-1"
    with pytest.raises(NotConnectedError):
        client.call("work")
    assert client._pending == {}


# -- G2: cancellation is session-scoped, bounded, and never voids another call -
def test_g2_a_stale_cancel_does_not_void_a_future_request() -> None:
    """A cancel for an id not in flight is ignored, so a reused id still serves.

    Before the fix, the global id-keyed set retained the id and silently dropped
    the next request that happened to reuse it, with no reply.
    """
    server = IpcServer()
    handler = RecordingHandler()
    server.register("work", handler)
    client, _t = connect(server)
    # A cancel for a request that was never in flight (any format) must not stick.
    client._notify_cancel("req-2")
    assert client.call("work", {"n": 1}, timeout=2.0)["count"] == 1


def test_g2_one_session_cannot_cancel_another_sessions_request() -> None:
    """Cancellation is keyed by session, so a forged id from elsewhere is inert."""
    server = IpcServer()
    handler = RecordingHandler()
    server.register("work", handler)
    a_end, a_server = LoopbackTransport.pair()
    server.serve(a_server)
    client_a = IpcClient()
    client_a.connect(a_end)

    codec = JsonMessageCodec()
    # A second session forging a $cancel for client A's request-id space.
    a_end.send(
        codec.encode(
            IpcRequest(
                request_id="c1",
                method="$cancel",
                params={"request_id": "req-2"},
                session_id="sess-999",  # not a live session
                expects_response=False,
            )
        )
    )
    # A's next call (which will be req-2) is served, not silently dropped.
    assert client_a.call("work", {"n": 1}, timeout=2.0)["count"] == 1


def test_g2_an_unauthenticated_cancel_is_rejected_before_it_records() -> None:
    """$cancel is routed after session validation, so a session-less one is inert."""
    server = IpcServer()
    server.register("echo", EchoHandler())
    client, transport = connect(server)
    codec = JsonMessageCodec()
    for i in range(50):
        transport.send(
            codec.encode(
                IpcRequest(
                    request_id=f"c{i}",
                    method="$cancel",
                    params={"request_id": f"x{i}"},
                    session_id=None,
                    expects_response=False,
                )
            )
        )
    assert server._cancelled == set()
    assert client.call("echo", {"ok": 1})["echo"] == {"ok": 1}


def test_g2_the_cancelled_set_stays_bounded_by_inflight() -> None:
    """Completed requests leave nothing behind in either tracking set."""
    server = IpcServer()
    server.register("echo", EchoHandler())
    client, _t = connect(server)
    for index in range(200):
        client.call("echo", {"n": index})
        client._notify_cancel(f"req-{index}")
    assert server._cancelled == set()
    assert server._inflight == set()


def test_g2_a_genuinely_queued_request_is_still_cancellable() -> None:
    """The feature still works: a request cancelled before it starts is skipped."""
    client, handler, pool = blocking()
    try:
        first = client.call_async("slow", {"n": 1})
        handler.entered.wait(2.0)          # the worker is busy with n=1
        queued = client.call_async("slow", {"n": 2})  # waits behind it
        queued.cancel()
        handler.release()
        pool.shutdown(wait=True)
        assert handler.completed == [1]    # n=2 never ran
        first.result(2.0)
    finally:
        handler.release()


# -- G3: a response arriving in the timeout window is not thrown away ----------
def test_g3_a_response_in_the_timeout_window_is_returned_not_discarded() -> None:
    """Directly exercise the race: the response is present when the wait lapses."""
    client = IpcClient()
    pending = PendingCall("req-1", client)
    # Simulate the receiver having just resolved it, with the event not yet
    # observed by a waiter -- the state result() sees on a timeout.
    pending._resolve(IpcResponse.success("req-1", {"answer": 42}))
    pending._event.clear()
    assert pending.result(0.01) == {"answer": 42}
    assert pending.cancelled is False


# -- G4: cancel() must not discard an already-delivered response ---------------
def test_g4_cancelling_after_a_response_arrived_is_a_no_op() -> None:
    client = IpcClient()
    pending = PendingCall("req-1", client)
    pending._resolve(IpcResponse.success("req-1", {"v": 1}))
    pending.cancel()
    assert pending.done is True
    assert pending.cancelled is False
    assert pending.result(0.01) == {"v": 1}


def test_g4_done_and_cancelled_are_mutually_exclusive_under_a_race() -> None:
    """The inconsistent 'done and cancelled' state must never occur."""
    for _ in range(400):
        client = IpcClient()
        pending = PendingCall("req-x", client)

        def deliver_to(call: PendingCall) -> None:
            call._resolve(IpcResponse.success("req-x", {"v": 1}))

        deliver = threading.Thread(target=deliver_to, args=(pending,))
        deliver.start()
        pending.cancel()
        deliver.join()
        assert not (pending.done and pending.cancelled)


# -- G5: a second result() after a timeout returns at once --------------------
def test_g5_a_second_result_after_timeout_does_not_re_wait() -> None:
    client, handler, pool = blocking()
    try:
        pending = client.call_async("slow", {"n": 1})
        handler.entered.wait(2.0)
        with pytest.raises(RequestTimeoutError):
            pending.result(0.1)
        started = time.perf_counter()
        with pytest.raises((RequestTimeoutError, RequestCancelledError)):
            pending.result(0.5)
        assert time.perf_counter() - started < 0.2  # did not re-wait the deadline
    finally:
        handler.release()
        pool.shutdown(wait=True)


# -- G6: a stopped server routes nothing and mints nothing --------------------
def test_g6_a_stopped_server_mints_no_session() -> None:
    server = IpcServer()
    server.register("work", RecordingHandler())
    _client, transport = connect(server)
    server.stop()
    codec = JsonMessageCodec()
    transport.set_receiver(lambda _p: None)
    transport.send(codec.encode(IpcRequest(request_id="x1", method="$connect")))
    assert server.active_sessions == 0


def test_g6_a_stopped_server_dispatches_no_handler() -> None:
    handler = RecordingHandler()
    server = IpcServer()
    server.register("work", handler)
    client, transport = connect(server)
    session_id = client.session_id
    server.stop()
    codec = JsonMessageCodec()
    transport.set_receiver(lambda _p: None)
    transport.send(
        codec.encode(
            IpcRequest(request_id="x1", method="work", session_id=session_id)
        )
    )
    assert handler.calls == []


# -- G7: a handler's bad return becomes a fault, not a raw exception -----------
class ReturnsNone:
    def handle(self, params: Mapping[str, Any], session: Session) -> Mapping[str, Any]:
        return None  # type: ignore[return-value]


class ReturnsNonMapping:
    def handle(self, params: Mapping[str, Any], session: Session) -> Mapping[str, Any]:
        return [1, 2, 3]  # type: ignore[return-value]


class ReturnsNonJson:
    def handle(self, params: Mapping[str, Any], session: Session) -> Mapping[str, Any]:
        return {"obj": object()}


@pytest.mark.parametrize("handler", [ReturnsNone(), ReturnsNonMapping(), ReturnsNonJson()])
def test_g7_a_bad_handler_return_is_reported_as_a_handler_failure(
    handler: object,
) -> None:
    server = IpcServer()
    server.register("bad", handler)  # type: ignore[arg-type]
    client, _t = connect(server)
    with pytest.raises(RemoteError) as error:
        client.call("bad")
    assert error.value.code is ErrorCode.IPC_HANDLER_FAILED


def test_g7_a_bad_return_on_the_executor_path_also_faults() -> None:
    with ThreadPoolExecutor(max_workers=1) as pool:
        server = IpcServer(executor=pool)
        server.register("bad", ReturnsNone())
        client, _t = connect(server)
        with pytest.raises(RemoteError) as error:
            client.call("bad", timeout=2.0)
        assert error.value.code is ErrorCode.IPC_HANDLER_FAILED


# -- G9: connect() refuses to orphan a session --------------------------------
def test_g9_connecting_twice_is_refused() -> None:
    server = IpcServer()
    server.register("echo", EchoHandler())
    client_end, server_end = LoopbackTransport.pair()
    server.serve(server_end)
    reconnecting = IpcClient()
    reconnecting.connect(client_end)
    with pytest.raises(NotConnectedError, match="already connected"):
        reconnecting.connect(client_end)
    assert server.active_sessions == 1


# -- F6: a handler raising an IPC-coded error is a RemoteError, not protocol ---
class RaisesIpcCodedError:
    def handle(self, params: Mapping[str, Any], session: Session) -> Mapping[str, Any]:
        raise HandlerRaisableSessionError("the handler chose this")


def test_f6_a_handler_ipc_coded_error_surfaces_as_a_remote_error() -> None:
    server = IpcServer()
    server.register("weird", RaisesIpcCodedError())
    client, _t = connect(server)
    with pytest.raises(RemoteError) as error:
        client.call("weird")
    assert error.value.code is ErrorCode.IPC_SESSION_INVALID
    assert error.value.remote_error_type == "SessionError"


def test_f6_a_real_protocol_fault_still_raises_its_specific_exception() -> None:
    """The distinction must not break genuine protocol signalling."""
    server = IpcServer()
    server.register("echo", EchoHandler())
    client, _t = connect(server)
    with pytest.raises(SessionError):
        # Forge a request under a dead session to trigger the server's own fault.
        client._session_id = "sess-dead"
        client.call("echo")


def test_f6_a_domain_error_keeps_its_code(  # the control that was always correct
) -> None:
    server = IpcServer()

    class Boom:
        def handle(
            self, params: Mapping[str, Any], session: Session
        ) -> Mapping[str, Any]:
            raise ConfigurationError("no dictionary")

    server.register("boom", Boom())
    client, _t = connect(server)
    with pytest.raises(RemoteError) as error:
        client.call("boom")
    assert error.value.code is ErrorCode.CONFIGURATION_INVALID


# -- Minor: $connect as a command mints nothing; $cancel as a query is answered -
def test_a_connect_sent_as_a_command_mints_no_session() -> None:
    server = IpcServer()
    server.register("echo", EchoHandler())
    client_end, server_end = LoopbackTransport.pair()
    server.serve(server_end)
    codec = JsonMessageCodec()
    client_end.set_receiver(lambda _p: None)
    client_end.send(
        codec.encode(
            IpcRequest(request_id="x1", method="$connect", expects_response=False)
        )
    )
    assert server.active_sessions == 0


def test_a_cancel_sent_as_a_query_is_acknowledged() -> None:
    """A misused command must not hang the caller waiting for a reply."""
    server = IpcServer()
    server.register("echo", EchoHandler())
    client, _t = connect(server)
    ack = client.call("$cancel", {"request_id": "req-99"}, timeout=2.0)
    assert ack == {"cancelled": "req-99"}
