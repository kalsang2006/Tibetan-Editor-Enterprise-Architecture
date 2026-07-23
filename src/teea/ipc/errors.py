"""Error taxonomy for the Local IPC layer.

Every failure the IPC layer raises is an :class:`IPCError`, which is a
:class:`~teea.core.errors.TEEAError` and so carries a stable
:class:`~teea.core.errors.ErrorCode`. That is what makes **error propagation
across the boundary** work: a handler on the server raises a ``TEEAError`` with
its own code -- an AI-runtime ``TEEA-3005``, say -- the server serialises the
code into the response, and the client re-raises an :class:`RemoteError` carrying
*that same code*. A caller on the add-in side therefore sees the original failure
category, not a generic "call failed".

The hierarchy mirrors :mod:`teea.ai.errors`: a package base class, and one
subclass per failure mode, each fixing its own default code.
"""

from __future__ import annotations

from typing import Any

from teea.core.errors import ErrorCode, TEEAError


class IPCError(TEEAError):
    """Base class for every Local IPC failure."""

    default_code = ErrorCode.UNKNOWN


class ProtocolVersionError(IPCError):
    """Raised when the two ends disagree on the protocol version."""

    default_code = ErrorCode.IPC_PROTOCOL_MISMATCH


class MethodNotFoundError(IPCError):
    """Raised when a request names a method the server does not route."""

    default_code = ErrorCode.IPC_METHOD_NOT_FOUND


class MalformedMessageError(IPCError):
    """Raised when a payload cannot be decoded into a valid message."""

    default_code = ErrorCode.IPC_MALFORMED_MESSAGE


class RequestTimeoutError(IPCError):
    """Raised when a call does not receive its response within the deadline."""

    default_code = ErrorCode.IPC_TIMEOUT


class RequestCancelledError(IPCError):
    """Raised when a call is cancelled before its response arrives."""

    default_code = ErrorCode.IPC_CANCELLED


class TransportClosedError(IPCError):
    """Raised when a message is sent over a closed transport."""

    default_code = ErrorCode.IPC_TRANSPORT_CLOSED


class NotConnectedError(IPCError):
    """Raised when a client operation needs a connection and there is none."""

    default_code = ErrorCode.IPC_NOT_CONNECTED


class SessionError(IPCError):
    """Raised when a request carries a session the server does not recognise."""

    default_code = ErrorCode.IPC_SESSION_INVALID


class RemoteError(IPCError):
    """Raised on the client when the server returned a fault.

    Its :attr:`~teea.core.errors.TEEAError.code` is the code the *handler* failed
    with, reconstructed from the wire, so a domain error keeps its identity
    across the boundary. The originating exception's type name is preserved in
    the context under ``remote_error_type``.
    """

    default_code = ErrorCode.IPC_HANDLER_FAILED

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode,
        remote_error_type: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        merged = dict(context or {})
        merged["remote_error_type"] = remote_error_type
        super().__init__(message, code=code, context=merged)
        self.remote_error_type = remote_error_type


__all__ = [
    "IPCError",
    "MalformedMessageError",
    "MethodNotFoundError",
    "NotConnectedError",
    "ProtocolVersionError",
    "RemoteError",
    "RequestCancelledError",
    "RequestTimeoutError",
    "SessionError",
    "TransportClosedError",
]
