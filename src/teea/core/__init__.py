"""TEEA core foundation: configuration, logging, errors and shared types.

This subpackage has no dependency on any NLP model and is safe to import from
every other layer. It defines the cross-cutting concerns that the rest of the
platform builds on.
"""

from __future__ import annotations

from teea.core.config import (
    DEFAULT_MAX_SEQUENCE_LENGTH,
    DEFAULT_TIBERT_MODEL_ID,
    TEEASettings,
    TokenizationSettings,
    load_settings,
)
from teea.core.errors import (
    ConfigurationError,
    ErrorCode,
    InputValidationError,
    TEEAError,
)
from teea.core.logging import (
    bind_correlation_id,
    clear_context,
    configure_logging,
    get_logger,
)
from teea.core.types import (
    SHAD,
    SHAD_CHARS,
    TIBETAN_BLOCK_END,
    TIBETAN_BLOCK_START,
    TSHEG,
    TSHEG_CHARS,
    TextSpan,
    is_tibetan_char,
    tibetan_ratio,
)

__all__ = [
    "DEFAULT_MAX_SEQUENCE_LENGTH",
    "DEFAULT_TIBERT_MODEL_ID",
    "SHAD",
    "SHAD_CHARS",
    "TIBETAN_BLOCK_END",
    "TIBETAN_BLOCK_START",
    "TSHEG",
    "TSHEG_CHARS",
    "ConfigurationError",
    "ErrorCode",
    "InputValidationError",
    "TEEAError",
    "TEEASettings",
    "TextSpan",
    "TokenizationSettings",
    "bind_correlation_id",
    "clear_context",
    "configure_logging",
    "get_logger",
    "is_tibetan_char",
    "load_settings",
    "tibetan_ratio",
]