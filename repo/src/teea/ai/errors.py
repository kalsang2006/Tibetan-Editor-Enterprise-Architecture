"""Error taxonomy for the AI Runtime.

Every failure the runtime raises is a :class:`AIRuntimeError`, which is a
:class:`~teea.core.errors.TEEAError` and so carries a stable
:class:`~teea.core.errors.ErrorCode`. That matters for composition: the AI
Runtime is invoked *by* feature plugins, and the Plugin Runtime captures a
plugin's exception into a :class:`~teea.plugins.PluginFailure` that preserves a
``TEEAError``'s own code (ADR-018). So an inference failure inside a plugin
surfaces to the add-in as an AI-runtime code (``TEEA-3xxx``) rather than a
generic crash, without either component knowing about the other.

The hierarchy mirrors :mod:`teea.nlp.tokenization.exceptions`: a package base
class, and one subclass per failure mode, each fixing its own default code.
"""

from __future__ import annotations

from teea.core.errors import ErrorCode, TEEAError


class AIRuntimeError(TEEAError):
    """Base class for every AI Runtime failure."""

    default_code = ErrorCode.UNKNOWN


class RuntimeStateError(AIRuntimeError):
    """Raised when an operation needs a running runtime and it is not."""

    default_code = ErrorCode.RUNTIME_NOT_STARTED


class ModelRegistrationError(AIRuntimeError):
    """Raised when a model is registered under a name/version already taken."""

    default_code = ErrorCode.MODEL_ALREADY_REGISTERED


class ModelNotFoundError(AIRuntimeError):
    """Raised when a referenced model is not in the registry."""

    default_code = ErrorCode.MODEL_NOT_REGISTERED


class CapabilityUnavailableError(AIRuntimeError):
    """Raised when no registered model provides a requested capability."""

    default_code = ErrorCode.CAPABILITY_UNAVAILABLE


class ModelLoadError(AIRuntimeError):
    """Raised when the inference engine fails to load a model."""

    default_code = ErrorCode.MODEL_LOAD_FAILED


class InferenceError(AIRuntimeError):
    """Raised when the inference engine fails while running a model."""

    default_code = ErrorCode.INFERENCE_FAILED


class ResourceExhaustedError(AIRuntimeError):
    """Raised when a model cannot fit within the runtime's memory budget."""

    default_code = ErrorCode.RESOURCE_EXHAUSTED


__all__ = [
    "AIRuntimeError",
    "CapabilityUnavailableError",
    "InferenceError",
    "ModelLoadError",
    "ModelNotFoundError",
    "ModelRegistrationError",
    "ResourceExhaustedError",
    "RuntimeStateError",
]
