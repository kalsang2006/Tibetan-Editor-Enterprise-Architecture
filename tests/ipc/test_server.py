"""Server tests: registration, routing, dispatch, sessions and lifecycle.

Figure 3 gives the Local IPC Layer "Request Routing", and this is where that is
verified: the right handler is chosen, an unknown method is refused, a command
gets no reply, a forged session cannot reach a handler, and a handler's failure
comes back as a fault carrying its own code.

Most tests drive the server through a real client, because a route that works
only when poked directly is not a route.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from teea.core.errors import ErrorCode
from teea.ipc import (
    PROTOCOL_VERSION,
    IpcClient,
    IpcRequest,
    IpcServer,
    JsonMessageCodec,
    LoopbackTransport,
    MethodKind,
    MethodNotFoundError,
    RemoteError,
    Session,
    SessionError,
)
from tests.ipc.conftest import (
    EchoHandler,
    RecordingHandler,
    SilentFailureHandler,
    TypedFailureHandler,
    UntypedFailureHandler,
    connect,
)


# -- Registration --------------------------------------------------------------
def test_a_registered_method_is_routable() -> None:
    server = IpcServer()
    server.register("echo", EchoHandler())
    assert "echo" in {d.name for d in server.methods}


def test_the_builtin_methods_are_always_routable() -> None:
    """The connection can be managed without a feature providing anything."""
    names = {d.name for d in IpcServer().methods}
    assert {"$connect", "$disconnect", "$health", "$cancel"} <= names


def test_the_cancel_method_is_a_command() -> None:
    kinds = {d.name: d.kind for d in IpcServer().methods}
    assert kinds["$cancel"] is MethodKind.COMMAND
    assert kinds["$health"] is MethodKind.QUERY


def test_a_method_may_not_shadow_a_builtin() -> None:
    """The ``$`` prefix is reserved, so a feature cannot hijack the handshake."""
    with pytest.raises(ValueError, match="must not start with"):
        IpcServer().register("$connect", EchoHandler())


def test_a_method_name_must_not_be_empty() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        IpcServer().register("", EchoHandler())


def test_a_duplicate_registration_is_refused() -> None:
    server = IpcServer()
    server.register("echo", EchoHandler())
    with pytest.raises(ValueError, match="already registered"):
        server.register("echo", EchoHandler())


def test_registration_is_refused_while_serving() -> None:
    """The routing table is fixed while requests are in flight."""
    server = IpcServer()
    _client, _server_end = LoopbackTransport.pair()
    server.serve(_server_end)
    with pytest.raises(ValueError, match="while the server is serving"):
        server.register("late", EchoHandler())


def test_methods_are_listed_in_a_stable_order() -> None:
    server = IpcServer()
    for name in ("zeta", "alpha", "mid"):
        server.register(name, EchoHandler())
    names = [d.name for d in server.methods]
    assert names == sorted(names)


# -- Lifecycle -----------------------------------------------------------------
def test_a_fresh_server_is_not_serving() -> None:
    assert IpcServer().is_serving is False


def test_serving_binds_the_transport() -> None:
    server = IpcServer()
    _client_end, server_end = LoopbackTransport.pair()
    server.serve(server_end)
    assert server.is_serving is True


def test_a_server_cannot_serve_twice() -> None:
    server = IpcServer()
    _c1, s1 = LoopbackTransport.pair()
    _c2, s2 = LoopbackTransport.pair()
    server.serve(s1)
    with pytest.raises(ValueError, match="already serving"):
        server.serve(s2)


def test_stopping_drops_every_session() -> None:
    server = IpcServer()
    server.register("echo", EchoHandler())
    _client, _t = connect(server)
    assert server.active_sessions == 1
    server.stop()
    assert server.is_serving is False
    assert server.active_sessions == 0


def test_stopping_is_idempotent() -> None:
    server = IpcServer()
    _c, s = LoopbackTransport.pair()
    server.serve(s)
    server.stop()
    server.stop()
    assert server.is_serving is False


def test_a_server_can_serve_again_after_stopping() -> None:
    """Stop releases the transport rather than poisoning the server."""
    server = IpcServer()
    server.register("echo", EchoHandler())
    first_client, _t = connect(server)
    first_client.close()
    server.stop()

    second = IpcClient()
    client_end, server_end = LoopbackTransport.pair()
    server.serve(server_end)
    second.connect(client_end)
    assert second.call("echo", {"a": 1})["echo"] == {"a": 1}


def test_health_reports_the_servers_state() -> None:
    server = IpcServer()
    server.register("echo", EchoHandler())
    assert server.health().serving is False
    assert server.health().status == "stopped"
    _client, _t = connect(server)
    status = server.health()
    assert status.serving is True
    assert status.active_sessions == 1
    assert status.protocol_version == PROTOCOL_VERSION
    assert status.methods == 5  # one user method plus four built-ins


# -- Routing -------------------------------------------------------------------
def test_a_call_reaches_its_registered_handler() -> None:
    handler = RecordingHandler()
    server = IpcServer()
    server.register("record", handler)
    client, _t = connect(server)
    assert client.call("record", {"n": 1})["count"] == 1
    assert handler.calls == [{"n": 1}]


def test_each_method_reaches_its_own_handler() -> None:
    first, second = RecordingHandler(), RecordingHandler()
    server = IpcServer()
    server.register("first", first)
    server.register("second", second)
    client, _t = connect(server)
    client.call("first", {"a": 1})
    client.call("second", {"b": 2})
    assert first.calls == [{"a": 1}]
    assert second.calls == [{"b": 2}]


def test_an_unknown_method_is_refused() -> None:
    server = IpcServer()
    server.register("echo", EchoHandler())
    client, _t = connect(server)
    with pytest.raises(MethodNotFoundError, match="No handler is registered") as error:
        client.call("absent")
    assert error.value.code is ErrorCode.IPC_METHOD_NOT_FOUND


def test_the_handler_receives_its_session() -> None:
    server = IpcServer()
    server.register("echo", EchoHandler())
    client, _t = connect(server)
    assert client.call("echo", {})["session"] == client.session_id


def test_params_reach_the_handler_unchanged() -> None:
    server = IpcServer()
    server.register("echo", EchoHandler())
    client, _t = connect(server)
    params = {"text": "བཀྲ་ཤིས", "n": 3, "nested": {"deep": [1, 2]}}
    assert client.call("echo", params)["echo"] == params


# -- Commands (FR-8) -----------------------------------------------------------
def test_a_command_reaches_its_handler_without_a_reply() -> None:
    handler = RecordingHandler()
    server = IpcServer()
    server.register("ping", handler, kind=MethodKind.COMMAND)
    client, _t = connect(server)
    client.notify("ping", {"n": 1})
    assert handler.calls == [{"n": 1}]


def test_a_failing_command_does_not_take_the_server_down() -> None:
    """Fire-and-forget: there is no channel to report the failure on."""
    server = IpcServer()
    server.register("boom", UntypedFailureHandler(), kind=MethodKind.COMMAND)
    server.register("echo", EchoHandler())
    client, _t = connect(server)
    client.notify("boom", {})
    assert client.call("echo", {"still": "alive"})["echo"] == {"still": "alive"}


def test_a_command_for_an_unknown_method_sends_nothing_back() -> None:
    """An unsolicited error response would have no pending call to resolve."""
    server = IpcServer()
    server.register("echo", EchoHandler())
    client, _t = connect(server)
    client.notify("absent", {})
    assert client.call("echo", {"ok": 1})["echo"] == {"ok": 1}


# -- Sessions ------------------------------------------------------------------
def test_a_request_with_no_session_is_refused() -> None:
    """Only the handshake may arrive without one."""
    server = IpcServer()
    server.register("echo", EchoHandler())
    client_end, server_end = LoopbackTransport.pair()
    server.serve(server_end)
    codec = JsonMessageCodec()
    replies: list[bytes] = []
    client_end.set_receiver(replies.append)
    client_end.send(codec.encode(IpcRequest(request_id="r1", method="echo", session_id=None)))
    response = codec.decode_response(replies[0])
    assert response.ok is False
    assert response.error is not None
    assert response.error.code == ErrorCode.IPC_SESSION_INVALID.value


def test_a_forged_session_cannot_reach_a_handler() -> None:
    handler = RecordingHandler()
    server = IpcServer()
    server.register("record", handler)
    client_end, server_end = LoopbackTransport.pair()
    server.serve(server_end)
    codec = JsonMessageCodec()
    replies: list[bytes] = []
    client_end.set_receiver(replies.append)
    client_end.send(
        codec.encode(IpcRequest(request_id="r1", method="record", session_id="sess-999"))
    )
    assert handler.calls == []
    assert codec.decode_response(replies[0]).ok is False


def test_a_session_is_unusable_after_disconnect() -> None:
    server = IpcServer()
    server.register("echo", EchoHandler())
    client, transport = connect(server)
    session_id = client.session_id
    client.close()
    assert server.active_sessions == 0

    revived = IpcClient()
    revived._transport = transport
    revived._session_id = session_id
    transport.set_receiver(revived._on_message)
    with pytest.raises(SessionError):
        revived.call("echo", {})


def test_sessions_are_numbered_independently() -> None:
    server = IpcServer()
    server.register("echo", EchoHandler())
    first, _t1 = connect(server)
    assert first.session_id == "sess-1"
    assert server.active_sessions == 1


# -- Protocol versioning -------------------------------------------------------
def test_an_incompatible_client_version_is_refused() -> None:
    """The check runs on every request, not only the handshake."""
    server = IpcServer()
    server.register("echo", EchoHandler())
    client_end, server_end = LoopbackTransport.pair()
    server.serve(server_end)
    codec = JsonMessageCodec()
    replies: list[bytes] = []
    client_end.set_receiver(replies.append)
    client_end.send(
        codec.encode(IpcRequest(request_id="r1", method="$connect", protocol_version="99.0"))
    )
    response = codec.decode_response(replies[0])
    assert response.ok is False
    assert response.error is not None
    assert response.error.code == ErrorCode.IPC_PROTOCOL_MISMATCH.value


def test_a_compatible_minor_version_is_accepted() -> None:
    """A minor bump is additive, so it must not break an existing client."""
    server = IpcServer()
    server.register("echo", EchoHandler())
    client_end, server_end = LoopbackTransport.pair()
    server.serve(server_end)
    codec = JsonMessageCodec()
    replies: list[bytes] = []
    client_end.set_receiver(replies.append)
    major = PROTOCOL_VERSION.split(".", 1)[0]
    client_end.send(
        codec.encode(IpcRequest(request_id="r1", method="$connect", protocol_version=f"{major}.99"))
    )
    assert codec.decode_response(replies[0]).ok is True


# -- Error propagation ---------------------------------------------------------
def test_a_typed_handler_error_keeps_its_code_across_the_boundary() -> None:
    """The whole point of the fault envelope."""
    server = IpcServer()
    server.register("boom", TypedFailureHandler())
    client, _t = connect(server)
    with pytest.raises(RemoteError) as error:
        client.call("boom")
    assert error.value.code is ErrorCode.CONFIGURATION_INVALID
    assert error.value.remote_error_type == "ConfigurationError"
    assert "no dictionary available" in error.value.message


def test_an_untyped_handler_error_becomes_a_generic_failure() -> None:
    server = IpcServer()
    server.register("boom", UntypedFailureHandler())
    client, _t = connect(server)
    with pytest.raises(RemoteError) as error:
        client.call("boom")
    assert error.value.code is ErrorCode.IPC_HANDLER_FAILED
    assert error.value.remote_error_type == "ValueError"


def test_an_error_with_no_message_still_propagates() -> None:
    server = IpcServer()
    server.register("boom", SilentFailureHandler())
    client, _t = connect(server)
    with pytest.raises(RemoteError) as error:
        client.call("boom")
    assert error.value.remote_error_type == "RuntimeError"


def test_one_failing_call_does_not_break_the_next() -> None:
    server = IpcServer()
    server.register("boom", UntypedFailureHandler())
    server.register("echo", EchoHandler())
    client, _t = connect(server)
    with pytest.raises(RemoteError):
        client.call("boom")
    assert client.call("echo", {"ok": 1})["echo"] == {"ok": 1}


def test_a_garbled_payload_is_dropped_without_crashing() -> None:
    """There is no request id to correlate a reply to, so there is nothing to send."""
    server = IpcServer()
    server.register("echo", EchoHandler())
    client, transport = connect(server)
    transport.send(b"this is not a message")
    assert client.call("echo", {"ok": 1})["echo"] == {"ok": 1}


# -- Concurrency ---------------------------------------------------------------
def test_concurrent_calls_all_get_their_own_answer() -> None:
    """Responses must correlate to their own request, never cross over."""
    server = IpcServer()
    server.register("echo", EchoHandler())
    client, _t = connect(server)

    def call(index: int) -> int:
        result = client.call("echo", {"n": index})
        return int(result["echo"]["n"])

    with ThreadPoolExecutor(max_workers=8) as pool:
        answers = list(pool.map(call, range(200)))
    assert answers == list(range(200))


def test_an_executor_lets_a_slow_handler_run_off_the_transport_thread() -> None:
    """FR-8's non-blocking bus."""
    entered = threading.Event()

    class Slow:
        def handle(self, params: Mapping[str, Any], session: Session) -> Mapping[str, Any]:
            entered.set()
            return {"ok": True}

    with ThreadPoolExecutor(max_workers=2) as pool:
        server = IpcServer(executor=pool)
        server.register("slow", Slow())
        client, _t = connect(server)
        assert client.call("slow", timeout=2.0)["ok"] is True
        assert entered.is_set()


def test_the_server_is_deterministic_across_identical_calls() -> None:
    server = IpcServer()
    server.register("echo", EchoHandler())
    client, _t = connect(server)
    assert client.call("echo", {"n": 1}) == client.call("echo", {"n": 1})
