"""Structured logging for TEEA, built on :mod:`structlog`.

Rationale
---------
A production Tibetan NLP daemon needs machine-parseable logs (for local
diagnostics bundles and per-stage latency accounting) rather than free-form
prints. ``structlog`` gives us key/value events, a JSON renderer for
production, and a readable console renderer for development, all behind one
call: :func:`configure_logging`.

The module also provides :func:`bind_correlation_id`, which stamps a request or
document-analysis identifier onto every subsequent log line via context-local
variables. Once the local IPC boundary exists, the add-in's request id flows
straight through here, making cross-process traces possible.

This module never configures logging as an import side effect; the application
entrypoint (or tests) calls :func:`configure_logging` explicitly.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars
from structlog.typing import Processor

_CORRELATION_KEY = "correlation_id"


def configure_logging(*, level: str = "INFO", json_output: bool = True) -> None:
    """Configure process-wide structured logging.

    Idempotent: safe to call multiple times (tests rely on this).

    Args:
        level: Minimum level name (e.g. ``"INFO"``, ``"DEBUG"``).
        json_output: When ``True`` emit newline-delimited JSON; otherwise emit a
            colorized, human-readable console format.
    """
    numeric_level = logging.getLevelName(level.upper())
    if not isinstance(numeric_level, int):  # pragma: no cover - defensive
        numeric_level = logging.INFO

    # Route stdlib logging (used by third-party libs such as transformers)
    # through a single stderr handler at the requested level.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=numeric_level,
        force=True,
    )

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None, **initial_values: Any) -> structlog.stdlib.BoundLogger:
    """Return a bound logger, optionally namespaced and pre-bound with values.

    Args:
        name: Logical logger name, conventionally the module ``__name__``.
        **initial_values: Key/value pairs bound onto every event from this
            logger.

    Returns:
        A structlog bound logger.
    """
    logger = structlog.get_logger(name) if name else structlog.get_logger()
    if initial_values:
        logger = logger.bind(**initial_values)
    return logger  # type: ignore[no-any-return]


def bind_correlation_id(correlation_id: str) -> None:
    """Bind a correlation id onto all subsequent log lines in this context.

    Args:
        correlation_id: Identifier for the current request / document analysis.
    """
    bind_contextvars(**{_CORRELATION_KEY: correlation_id})


def clear_context() -> None:
    """Clear all context-local bound values (e.g. at the end of a request)."""
    clear_contextvars()


__all__ = [
    "bind_correlation_id",
    "clear_context",
    "configure_logging",
    "get_logger",
]