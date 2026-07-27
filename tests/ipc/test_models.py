"""Message-model invariants, protocol versioning, and serialization.

These models are the wire format. Their guarantees are what both ends rely on
without re-checking: a response is either a result or a fault and never both, a
request always names a method, and every message round-trips through JSON without
losing a Tibetan codepoint.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from teea.core.errors import ErrorCode
from teea.ipc import (
    PROTOCOL_VERSION,
    HealthStatus,
    IpcFault,
    IpcRequest,
    IpcResponse,
    JsonMessageCodec,
    MalformedMessageError,
    MethodDescriptor,
    MethodKind,
    Session,
    protocol_major,
)

TIBETAN = "བཀྲ་ཤིས་བདེ་ལེགས།"


# -- Error codes ---------------------------------------------------------------
def test_the_ipc_layer_has_its_own_error_code_domain() -> None:
    """Stable codes cross the boundary and must not be renumbered."""
    assert ErrorCode.IPC_PROTOCOL_MISMATCH.value == "TEEA-4000"
    assert ErrorCode.IPC_SESSION_INVALID.value == "TEEA-4008"


def test_every_error_code_is_unique() -> None:
    values = [code.value for code in ErrorCode]
    assert len(set(values)) == len(values)


# -- Protocol version ----------------------------------------------------------
def test_the_protocol_version_is_major_dot_minor() -> None:
    major, _, minor = PROTOCOL_VERSION.partition(".")
    assert major.isdigit() and minor.isdigit()


@pytest.mark.parametrize(
    ("version", "expected"), [("1.0", "1"), ("1.7", "1"), ("2.0", "2"), ("10.3", "10")]
)
def test_only_the_major_component_decides_compatibility(version: str, expected: str) -> None:
    """A minor bump is additive; a major bump is not."""
    assert protocol_major(version) == expected


def test_messages_carry_the_protocol_version_by_default() -> None:
    assert IpcRequest(request_id="r1", method="m").protocol_version == PROTOCOL_VERSION
    assert IpcResponse(request_id="r1", ok=True, result={}).protocol_version == PROTOCOL_VERSION


# -- IpcRequest ----------------------------------------------------------------
def test_a_request_carries_its_call() -> None:
    request = IpcRequest(
        request_id="r1", method="analyze", params={"text": TIBETAN}, session_id="s1"
    )
    assert request.method == "analyze"
    assert request.params["text"] == TIBETAN
    assert request.expects_response is True


def test_a_command_expects_no_response() -> None:
    """FR-8's non-blocking bus: a command is fire-and-forget."""
    assert (
        IpcRequest(request_id="r1", method="ping", expects_response=False).expects_response is False
    )


def test_a_request_must_carry_an_id() -> None:
    """Without an id a response could not be correlated to its call."""
    with pytest.raises(ValidationError, match="must carry a request id"):
        IpcRequest(request_id="", method="m")


def test_a_request_must_name_a_method() -> None:
    with pytest.raises(ValidationError, match="must name a method"):
        IpcRequest(request_id="r1", method="")


def test_params_default_to_empty() -> None:
    assert IpcRequest(request_id="r1", method="m").params == {}


def test_a_request_is_immutable() -> None:
    request = IpcRequest(request_id="r1", method="m")
    with pytest.raises(ValidationError):
        request.method = "other"  # type: ignore[misc]


def test_a_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        IpcRequest(request_id="r1", method="m", priority="high")  # type: ignore[call-arg]


# -- IpcFault ------------------------------------------------------------------
def test_a_fault_carries_the_handlers_code_and_type() -> None:
    fault = IpcFault(
        code="TEEA-0001", error_type="ConfigurationError", message="bad", context={"k": 1}
    )
    assert fault.code == "TEEA-0001"
    assert fault.context["k"] == 1


def test_a_fault_must_carry_a_code() -> None:
    with pytest.raises(ValidationError, match="must carry an error code"):
        IpcFault(code="", error_type="X", message="m")


def test_a_fault_must_name_the_error_type() -> None:
    with pytest.raises(ValidationError, match="must name the error type"):
        IpcFault(code="TEEA-0000", error_type="", message="m")


def test_a_fault_may_carry_an_empty_message() -> None:
    """Plenty of exceptions are raised with no message."""
    assert IpcFault(code="TEEA-0000", error_type="RuntimeError", message="").message == ""


# -- IpcResponse ---------------------------------------------------------------
def test_a_successful_response_carries_a_result() -> None:
    response = IpcResponse.success("r1", {"value": 1})
    assert response.ok is True
    assert response.result == {"value": 1}
    assert response.error is None


def test_a_failed_response_carries_a_fault() -> None:
    fault = IpcFault(code="TEEA-0000", error_type="X", message="m")
    response = IpcResponse.failure("r1", fault)
    assert response.ok is False
    assert response.error is fault
    assert response.result is None


def test_a_successful_response_cannot_carry_a_fault() -> None:
    """Exactly one of result and fault, never both."""
    fault = IpcFault(code="TEEA-0000", error_type="X", message="m")
    with pytest.raises(ValidationError, match="cannot carry a fault"):
        IpcResponse(request_id="r1", ok=True, error=fault)


def test_a_failed_response_must_carry_a_fault() -> None:
    """...and never neither: a failure with no reason tells the caller nothing."""
    with pytest.raises(ValidationError, match="must carry a fault"):
        IpcResponse(request_id="r1", ok=False)


def test_a_response_must_carry_a_request_id() -> None:
    with pytest.raises(ValidationError, match="must carry a request id"):
        IpcResponse(request_id="", ok=True, result={})


# -- Descriptors and status ----------------------------------------------------
def test_a_method_descriptor_names_its_bus() -> None:
    """Figure 9's Command Bus and Query Bus, as metadata."""
    assert MethodDescriptor(name="m", kind=MethodKind.COMMAND).kind is MethodKind.COMMAND


def test_a_session_carries_its_agreed_version() -> None:
    session = Session(session_id="s1", protocol_version=PROTOCOL_VERSION)
    assert session.session_id == "s1"


def test_a_health_status_reports_the_server() -> None:
    status = HealthStatus(
        status="ok",
        protocol_version=PROTOCOL_VERSION,
        serving=True,
        active_sessions=2,
        methods=6,
    )
    assert status.serving is True
    assert status.active_sessions == 2


def test_negative_counters_are_rejected() -> None:
    with pytest.raises(ValidationError):
        HealthStatus(
            status="ok",
            protocol_version=PROTOCOL_VERSION,
            serving=True,
            active_sessions=-1,
            methods=0,
        )


# -- Serialization -------------------------------------------------------------
def test_a_request_round_trips_through_the_codec() -> None:
    codec = JsonMessageCodec()
    request = IpcRequest(
        request_id="r1",
        method="analyze",
        params={"text": TIBETAN, "nested": {"n": [1, 2, 3]}},
        session_id="s1",
    )
    assert codec.decode_request(codec.encode(request)) == request


def test_a_response_round_trips_through_the_codec() -> None:
    codec = JsonMessageCodec()
    response = IpcResponse.failure(
        "r1", IpcFault(code="TEEA-0001", error_type="X", message=TIBETAN)
    )
    restored = codec.decode_response(codec.encode(response))
    assert restored == response
    assert restored.error is not None
    assert restored.error.message == TIBETAN


def test_tibetan_survives_encoding_byte_for_byte() -> None:
    """Every Tibetan codepoint is three UTF-8 bytes; none may be mangled."""
    codec = JsonMessageCodec()
    request = IpcRequest(request_id="r1", method="m", params={"t": TIBETAN})
    assert codec.decode_request(codec.encode(request)).params["t"] == TIBETAN


def test_an_empty_result_round_trips() -> None:
    codec = JsonMessageCodec()
    assert codec.decode_response(codec.encode(IpcResponse.success("r1", {}))).result == {}


@pytest.mark.parametrize("payload", [b"", b"not json", b"[]", b"{}", b'{"a":1}', b"\xff"])
def test_a_malformed_payload_is_rejected_as_a_typed_failure(payload: bytes) -> None:
    """Garbage from a peer must not escape as an untyped ValidationError."""
    codec = JsonMessageCodec()
    with pytest.raises(MalformedMessageError, match="not a valid IPC request"):
        codec.decode_request(payload)
    with pytest.raises(MalformedMessageError, match="not a valid IPC response"):
        codec.decode_response(payload)


def test_a_response_is_not_accepted_as_a_request() -> None:
    """The two message types are distinct on the wire, not interchangeable."""
    codec = JsonMessageCodec()
    encoded = codec.encode(IpcResponse.success("r1", {}))
    with pytest.raises(MalformedMessageError):
        codec.decode_request(encoded)


def test_a_request_is_not_accepted_as_a_response() -> None:
    codec = JsonMessageCodec()
    encoded = codec.encode(IpcRequest(request_id="r1", method="m"))
    with pytest.raises(MalformedMessageError):
        codec.decode_response(encoded)


def test_the_codec_is_stateless_and_reusable() -> None:
    codec = JsonMessageCodec()
    request = IpcRequest(request_id="r1", method="m")
    assert codec.encode(request) == codec.encode(request)
