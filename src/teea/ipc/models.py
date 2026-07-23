"""Immutable message models of the Local IPC layer.

Figure 3 assigns the Local IPC Layer two jobs -- "Message Transport" and "Request
Routing" -- and these are the messages that flow across it. Every one is a frozen
Pydantic model, so a message is a value that cannot be altered after it leaves
its sender, and every one serializes to JSON, because that is what crosses the
boundary as bytes.

Protocol versioning
-------------------
Every message carries :data:`PROTOCOL_VERSION`. The version is checked when a
connection is established, so a client and a daemon built against incompatible
protocols fail loudly at connect time rather than misinterpreting each other's
fields mid-session. The check is on the **major** version: a minor bump is
additive and compatible, a major bump is not.

Command and query, one envelope
--------------------------------
FR-8 requires "non-blocking, asynchronous command and query buses". Both ride the
same :class:`IpcRequest`: a *query* sets :attr:`~IpcRequest.expects_response` and
the caller awaits an :class:`IpcResponse`; a *command* clears it and returns at
once, nothing to await. :class:`MethodKind` records which a method is, for
discovery.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: The protocol version this build speaks, ``"major.minor"``. The major component
#: is the compatibility boundary; see the module docstring.
PROTOCOL_VERSION = "1.0"


def protocol_major(version: str) -> str:
    """Return the major component of a ``"major.minor"`` version string."""
    return version.split(".", 1)[0]


@enum.unique
class MethodKind(enum.Enum):
    """Whether a routed method answers or merely acts.

    Figure 9 lists a Command Bus and a Query Bus among the daemon's application
    busses; this is which bus a method belongs to.
    """

    #: A request/response method: the caller awaits a result.
    QUERY = "query"
    #: A fire-and-forget method: the caller does not wait, and gets no result.
    COMMAND = "command"


class IpcRequest(BaseModel):
    """One call from a client to the server.

    Attributes:
        protocol_version: The version the sender speaks.
        request_id: Correlates a response to this request. Unique per client
            connection.
        method: The routed method name.
        params: The call's arguments, as an opaque JSON-serializable mapping.
        session_id: The session this call belongs to, or ``None`` for the
            handshake that establishes one.
        expects_response: Whether the caller awaits an :class:`IpcResponse`. A
            query does; a command does not.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    protocol_version: str = PROTOCOL_VERSION
    request_id: str
    method: str
    params: Mapping[str, Any] = Field(default_factory=dict)
    session_id: str | None = None
    expects_response: bool = True

    @model_validator(mode="after")
    def _validate_consistency(self) -> IpcRequest:
        if not self.request_id:
            raise ValueError("a request must carry a request id")
        if not self.method:
            raise ValueError("a request must name a method")
        return self


class IpcFault(BaseModel):
    """A failure, serialized to travel inside an :class:`IpcResponse`.

    Carries the handler's error code and type but never a traceback: a traceback
    would embed local variables, and a handler's locals hold document content,
    which :mod:`teea.core.errors` forbids from crossing the boundary.

    Attributes:
        code: The stable :class:`~teea.core.errors.ErrorCode` value the handler
            failed with.
        error_type: The exception class name, for diagnosis.
        message: The failure's human-readable message.
        context: Structured, non-sensitive detail.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    error_type: str
    message: str
    context: Mapping[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_consistency(self) -> IpcFault:
        if not self.code:
            raise ValueError("a fault must carry an error code")
        if not self.error_type:
            raise ValueError("a fault must name the error type")
        return self


class IpcResponse(BaseModel):
    """The server's reply to a query.

    Exactly one of :attr:`result` and :attr:`error` is present: a response either
    succeeded with a result or failed with a fault, never both and never neither.

    Attributes:
        protocol_version: The version the server speaks.
        request_id: The id of the request this answers.
        ok: Whether the call succeeded.
        result: The handler's return value, when ``ok``.
        error: The fault, when not ``ok``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    protocol_version: str = PROTOCOL_VERSION
    request_id: str
    ok: bool
    result: Mapping[str, Any] | None = None
    error: IpcFault | None = None

    @model_validator(mode="after")
    def _validate_consistency(self) -> IpcResponse:
        if not self.request_id:
            raise ValueError("a response must carry a request id")
        if self.ok and self.error is not None:
            raise ValueError("a successful response cannot carry a fault")
        if not self.ok and self.error is None:
            raise ValueError("a failed response must carry a fault")
        return self

    @classmethod
    def success(
        cls, request_id: str, result: Mapping[str, Any]
    ) -> IpcResponse:
        """Build a successful response."""
        return cls(request_id=request_id, ok=True, result=result)

    @classmethod
    def failure(cls, request_id: str, fault: IpcFault) -> IpcResponse:
        """Build a failed response."""
        return cls(request_id=request_id, ok=False, error=fault)


class MethodDescriptor(BaseModel):
    """One routable method, for capability discovery.

    Attributes:
        name: The method name.
        kind: Whether it is a query or a command.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    kind: MethodKind


class Session(BaseModel):
    """A logical connection between one client and the server.

    Attributes:
        session_id: The server-assigned identifier.
        protocol_version: The version agreed at connect time.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str
    protocol_version: str


class HealthStatus(BaseModel):
    """A snapshot of the server's state, returned by the health method.

    Attributes:
        status: ``"ok"`` while the server is serving.
        protocol_version: The version the server speaks.
        serving: Whether the server is currently serving a transport.
        active_sessions: How many sessions are open.
        methods: How many methods are routed, built-ins included.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    protocol_version: str
    serving: bool
    active_sessions: int = Field(ge=0)
    methods: int = Field(ge=0)


__all__ = [
    "PROTOCOL_VERSION",
    "HealthStatus",
    "IpcFault",
    "IpcRequest",
    "IpcResponse",
    "MethodDescriptor",
    "MethodKind",
    "Session",
    "protocol_major",
]
