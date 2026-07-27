"""Structured error taxonomy for TEEA.

Every failure raised inside TEEA is a subclass of :class:`TEEAError` and carries
a stable, machine-readable :class:`ErrorCode`. This is deliberate: the Language
Server, AI Runtime, Plugin Runtime and (eventually) the local IPC boundary must
serialize failures into a transport-neutral envelope so the Office.js add-in can
react programmatically (retry, surface a task-pane notice, degrade gracefully)
rather than parse human-readable strings.

Design decisions
----------------
* **Stable codes over message parsing.** ``ErrorCode`` values are part of the
  contract and must not be renumbered once shipped.
* **Context dictionary, not string interpolation.** Structured ``context`` keeps
  errors greppable and log-friendly and lets the IPC layer forward machine
  data.
* **No secrets in errors.** Callers must never place credentials or full
  document contents into ``context``; only identifiers, sizes and codes.
"""

from __future__ import annotations

import enum
from typing import Any


@enum.unique
class ErrorCode(enum.Enum):
    """Stable, serializable identifiers for TEEA failure modes.

    The string values form part of the public contract across the IPC boundary
    and MUST remain stable across releases. Add new members; never repurpose
    existing ones.
    """

    # Generic / foundational -------------------------------------------------
    UNKNOWN = "TEEA-0000"
    CONFIGURATION_INVALID = "TEEA-0001"
    INPUT_INVALID = "TEEA-0002"

    # Tokenization domain (TEEA-1xxx) ---------------------------------------
    TOKENIZER_LOAD_FAILED = "TEEA-1000"
    TOKENIZER_NOT_INITIALIZED = "TEEA-1001"
    TOKENIZATION_FAILED = "TEEA-1002"
    DETOKENIZATION_FAILED = "TEEA-1003"
    INPUT_NOT_STRING = "TEEA-1004"
    INPUT_EMPTY = "TEEA-1005"
    INPUT_TOO_LONG = "TEEA-1006"
    OFFSET_ALIGNMENT_FAILED = "TEEA-1007"
    NORMALIZATION_FAILED = "TEEA-1008"

    # Plugin runtime domain (TEEA-2xxx) --------------------------------------
    #: A feature plugin raised while examining a document snapshot. NFR 5.3
    #: requires the runtime to capture this rather than let it reach the host, so
    #: it is reported as a result rather than propagated as an exception.
    PLUGIN_EXECUTION_FAILED = "TEEA-2000"
    #: A plugin returned output that does not satisfy the runtime's contract --
    #: most importantly, suggestions attributed to a different plugin.
    PLUGIN_CONTRACT_VIOLATED = "TEEA-2001"

    # AI runtime domain (TEEA-3xxx) ------------------------------------------
    #: An operation needing a running AI Runtime was attempted before it was
    #: started, or after it was stopped.
    RUNTIME_NOT_STARTED = "TEEA-3000"
    #: A model was registered under a name and version already taken.
    MODEL_ALREADY_REGISTERED = "TEEA-3001"
    #: A model was referenced that the registry does not hold.
    MODEL_NOT_REGISTERED = "TEEA-3002"
    #: No registered model provides the requested capability.
    CAPABILITY_UNAVAILABLE = "TEEA-3003"
    #: The inference engine failed to load a model's weights.
    MODEL_LOAD_FAILED = "TEEA-3004"
    #: The inference engine failed while running a model.
    INFERENCE_FAILED = "TEEA-3005"
    #: A model cannot be made resident within the runtime's memory budget.
    RESOURCE_EXHAUSTED = "TEEA-3006"

    # Local IPC domain (TEEA-4xxx) ------------------------------------------
    #: The two ends of a connection disagree on the protocol version.
    IPC_PROTOCOL_MISMATCH = "TEEA-4000"
    #: A request named a method the server does not route.
    IPC_METHOD_NOT_FOUND = "TEEA-4001"
    #: A message could not be decoded into a valid request or response.
    IPC_MALFORMED_MESSAGE = "TEEA-4002"
    #: A request handler raised while serving a call.
    IPC_HANDLER_FAILED = "TEEA-4003"
    #: A call did not receive its response within the deadline.
    IPC_TIMEOUT = "TEEA-4004"
    #: A call was cancelled before its response arrived.
    IPC_CANCELLED = "TEEA-4005"
    #: The transport was closed, so no message can be sent.
    IPC_TRANSPORT_CLOSED = "TEEA-4006"
    #: A client operation needs an established connection and there is none.
    IPC_NOT_CONNECTED = "TEEA-4007"
    #: A request carried a session the server does not recognise.
    IPC_SESSION_INVALID = "TEEA-4008"


class TEEAError(Exception):
    """Base class for all TEEA errors.

    Args:
        message: Human-readable description (for logs and developers).
        code: Stable :class:`ErrorCode` identifying the failure category.
        context: Optional structured, non-sensitive key/value details. Values
            should be JSON-serializable so they can cross the IPC boundary.
        cause: Optional originating exception, preserved for traceback chaining.
    """

    #: Default code used when a subclass does not override it.
    default_code: ErrorCode = ErrorCode.UNKNOWN

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | None = None,
        context: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
        self.context: dict[str, Any] = dict(context) if context else {}
        if cause is not None:
            self.__cause__ = cause

    def to_dict(self) -> dict[str, Any]:
        """Return a transport-neutral representation for logging / IPC.

        Returns:
            A JSON-serializable dictionary with ``error``, ``code`` and
            ``context`` keys.
        """
        return {
            "error": type(self).__name__,
            "code": self.code.value,
            "message": self.message,
            "context": self.context,
        }

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"{type(self).__name__}(code={self.code.value!r}, "
            f"message={self.message!r}, context={self.context!r})"
        )


class ConfigurationError(TEEAError):
    """Raised when configuration is missing or invalid."""

    default_code = ErrorCode.CONFIGURATION_INVALID


class InputValidationError(TEEAError):
    """Raised when caller-supplied input fails validation."""

    default_code = ErrorCode.INPUT_INVALID


__all__ = [
    "ConfigurationError",
    "ErrorCode",
    "InputValidationError",
    "TEEAError",
]
