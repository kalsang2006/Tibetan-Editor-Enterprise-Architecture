"""Exceptions specific to the tokenization module.

Each maps to a stable :class:`~teea.core.errors.ErrorCode` so the failure can be
serialized across the IPC boundary. All inherit from
:class:`~teea.core.errors.TEEAError`, so callers can catch the whole family or a
specific member.
"""

from __future__ import annotations

from typing import Any

from teea.core.errors import ErrorCode, TEEAError


class TokenizationError(TEEAError):
    """Base class for tokenization failures."""

    default_code = ErrorCode.TOKENIZATION_FAILED


class TokenizerLoadError(TokenizationError):
    """Raised when the underlying tokenizer/model cannot be loaded."""

    default_code = ErrorCode.TOKENIZER_LOAD_FAILED


class TokenizerNotInitializedError(TokenizationError):
    """Raised when tokenization is attempted before the backend is loaded."""

    default_code = ErrorCode.TOKENIZER_NOT_INITIALIZED


class DetokenizationError(TokenizationError):
    """Raised when token ids cannot be decoded back to text."""

    default_code = ErrorCode.DETOKENIZATION_FAILED


class InputNotStringError(TokenizationError):
    """Raised when the input is not a ``str``."""

    default_code = ErrorCode.INPUT_NOT_STRING

    def __init__(self, received_type: str, **kwargs: Any) -> None:
        super().__init__(
            f"Expected str input, received {received_type!r}.",
            context={"received_type": received_type},
            **kwargs,
        )


class EmptyInputError(TokenizationError):
    """Raised when the input is empty or whitespace-only and this is disallowed."""

    default_code = ErrorCode.INPUT_EMPTY

    def __init__(self, **kwargs: Any) -> None:
        super().__init__("Input text is empty or whitespace-only.", **kwargs)


class InputTooLongError(TokenizationError):
    """Raised when tokenization would exceed the configured maximum length."""

    default_code = ErrorCode.INPUT_TOO_LONG

    def __init__(self, produced: int, maximum: int, **kwargs: Any) -> None:
        super().__init__(
            f"Tokenized length {produced} exceeds maximum {maximum}.",
            context={"produced": produced, "maximum": maximum},
            **kwargs,
        )


class OffsetAlignmentError(TokenizationError):
    """Raised when subword pieces cannot be aligned to source character offsets."""

    default_code = ErrorCode.OFFSET_ALIGNMENT_FAILED


class NormalizationError(TokenizationError):
    """Raised when Unicode normalization fails."""

    default_code = ErrorCode.NORMALIZATION_FAILED


__all__ = [
    "DetokenizationError",
    "EmptyInputError",
    "InputNotStringError",
    "InputTooLongError",
    "NormalizationError",
    "OffsetAlignmentError",
    "TokenizationError",
    "TokenizerLoadError",
    "TokenizerNotInitializedError",
]
