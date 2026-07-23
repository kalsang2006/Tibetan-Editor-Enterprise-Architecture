"""Defensive paths of the IPC layer, exercised deliberately.

Each of these guards a race or a hostile input that the ordinary tests cannot
reach: a response arriving for a call that was already cancelled, a peer sending
a ``$cancel`` with junk in it, a reply that has nowhere to go because the server
stopped mid-dispatch. They are cheap to write and they are exactly the paths that
rot unnoticed, because nothing in a happy-path suite touches them.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from teea.core.errors import ErrorCode
from teea.ipc import (
    IpcClient,
    IpcFault,
    IpcRequest,
    IpcResponse,
    IpcServer,
    JsonMessageCodec,
    LoopbackTransport,
    MethodKind,
    MethodNotFoundError,
    RemoteError,
    RequestCancelledError,
    Session,
)
from teea.ipc.client import PendingCall, _raise_fault
from tests.ipc.conftest import BlockingHandler, EchoHandler, RecordingHandler, connect


# -- A response that arrives too late -----------------------------------------
def test_a_response_for_an_already_cancelled_call_is_ignored() -> None:
    """The race the pending table exists to survive.

    The receiver thread can be delivering a response at the very moment the
    caller gives up. Whichever wins, the call must not end up holding a result it
    already reported as cancelled.
    """
    client = IpcClient()
    pending = PendingCall("req-1", client)
    pending.cancel()

    # The receiver thread delivers the answer a moment too late.
    pending._resolve(IpcResponse.success("req-1", {"late": True}))

    assert pending.cancelled is True
    with pytest.raises(RequestCancelledError, match="was cancelled"):
        pending.result(0.01)


def test_a_second_response_for_one_call_is_ignored() -> None:
    """A duplicate reply must not overwrite the answer already delivered."""
    client = IpcClient()
    pending = PendingCall("req-1", client)
    pending._resolve(IpcResponse.success("req-1", {"n": 1}))
    pending._resolve(IpcResponse.success("req-1", {"n": 2}))
    assert pending.result(0.01) == {"n": 1}


def test_cancelling_with_no_transport_is_survivable() -> None:
    """A client whose transport went away must still cancel cleanly."""
    client = IpcClient()
    pending = PendingCall("req-1", client)
    pending.cancel()
    assert pending.cancelled is True


# -- Hostile and malformed protocol traffic -----------------------------------
def test_a_cancel_carrying_junk_is_ignored() -> None:
    """``$cancel`` is a command from an untrusted peer; its params are not typed."""
    server = IpcServer()
    server.register("echo", EchoHandler())
    client, transport = connect(server)
    codec = JsonMessageCodec()

    for junk in ({}, {"request_id": None}, {"request_id": 42}, {"request_id": ""}):
        transport.send(
            codec.encode(
                IpcRequest(
                    request_id="c1",
                    method="$cancel",
                    params=junk,
                    session_id=client.session_id,
                    expects_response=False,
                )
            )
        )

    assert server._cancelled == set()
    assert client.call("echo", {"ok": 1})["echo"] == {"ok": 1}


def test_a_cancel_for_an_unknown_request_is_harmless() -> None:
    server = IpcServer()
    server.register("echo", EchoHandler())
    client, _t = connect(server)
    client._notify_cancel("req-never-sent")
    assert client.call("echo", {"ok": 1})["echo"] == {"ok": 1}


def test_an_unknown_fault_code_degrades_to_unknown() -> None:
    """A peer built against a newer taxonomy must not crash this one."""
    with pytest.raises(RemoteError) as error:
        _raise_fault(
            IpcFault(code="TEEA-9999", error_type="FutureError", message="from tomorrow")
        )
    assert error.value.code is ErrorCode.UNKNOWN
    assert error.value.remote_error_type == "FutureError"


def test_a_known_ipc_fault_maps_to_its_own_exception() -> None:
    with pytest.raises(MethodNotFoundError):
        _raise_fault(
            IpcFault(
                code=ErrorCode.IPC_METHOD_NOT_FOUND.value,
                error_type="MethodNotFoundError",
                message="nope",
            )
        )


# -- Replies with nowhere to go ------------------------------------------------
def test_a_reply_after_the_server_stopped_is_dropped() -> None:
    """The server was stopped while a handler was still running on a worker.

    There is no transport left to answer on, and raising out of a worker thread
    would take the executor's thread down with it.
    """
    handler = BlockingHandler()
    with ThreadPoolExecutor(max_workers=1) as pool:
        server = IpcServer(executor=pool)
        server.register("slow", handler)
        client, _t = connect(server)
        pending = client.call_async("slow", {"n": 1})
        handler.entered.wait(2.0)
        server.stop()          # transport dropped while the handler runs
        handler.release()
        pool.shutdown(wait=True)
    assert handler.completed == [1]   # the handler finished
    assert pending.done is False      # and its answer went nowhere


def test_a_reply_over_a_closed_transport_is_dropped() -> None:
    """The client hung up mid-dispatch; the send fails and is swallowed."""
    handler = BlockingHandler()
    with ThreadPoolExecutor(max_workers=1) as pool:
        server = IpcServer(executor=pool)
        server.register("slow", handler)
        client, transport = connect(server)
        client.call_async("slow", {"n": 1})
        handler.entered.wait(2.0)
        transport.close()
        handler.release()
        pool.shutdown(wait=True)
    assert handler.completed == [1]
    assert server.is_serving is True   # the server survived the failed send


def test_a_client_receiving_a_response_it_never_asked_for_ignores_it() -> None:
    """An unsolicited reply has no pending call, so it must be discarded."""
    server = IpcServer()
    server.register("echo", EchoHandler())
    client, _transport = connect(server)
    codec = JsonMessageCodec()
    client._on_message(codec.encode(IpcResponse.success("req-999", {"x": 1})))
    assert client.call("echo", {"ok": 1})["echo"] == {"ok": 1}


# -- Stop and restart under load ----------------------------------------------
def test_stopping_mid_flight_leaves_the_server_reusable() -> None:
    server = IpcServer()
    server.register("record", RecordingHandler())
    client, _t = connect(server)
    client.call("record", {"n": 1})
    server.stop()

    client_end, server_end = LoopbackTransport.pair()
    server.serve(server_end)
    fresh = IpcClient()
    fresh.connect(client_end)
    assert fresh.call("record", {"n": 2})["count"] == 2


def test_a_handler_returning_an_empty_result_is_fine() -> None:
    class Empty:
        def handle(
            self, params: Mapping[str, Any], session: Session
        ) -> Mapping[str, Any]:
            return {}

    server = IpcServer()
    server.register("empty", Empty())
    client, _t = connect(server)
    assert client.call("empty") == {}


def test_a_command_handler_returning_a_value_has_it_discarded() -> None:
    """Nothing is waiting for it, so returning one is harmless but pointless."""
    handler = RecordingHandler()
    server = IpcServer()
    server.register("ping", handler, kind=MethodKind.COMMAND)
    client, _t = connect(server)
    client.notify("ping", {"n": 1})
    assert handler.calls == [{"n": 1}]
    assert client._pending == {}


def test_concurrent_cancels_of_one_call_are_safe() -> None:
    """Several threads racing to cancel the same call must agree on the outcome."""
    client = IpcClient()
    pending = PendingCall("req-1", client)
    barrier = threading.Barrier(8)

    def cancel(_index: int) -> None:
        barrier.wait()
        pending.cancel()

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(cancel, range(8)))
    assert pending.cancelled is True
