from __future__ import annotations

from teea.core.logging import (
    bind_correlation_id,
    clear_context,
    configure_logging,
    get_logger,
)


def test_configure_logging_is_idempotent() -> None:
    configure_logging(level="DEBUG", json_output=False)
    configure_logging(level="INFO", json_output=True)


def test_get_logger_returns_a_bound_logger() -> None:
    logger = get_logger(__name__)
    assert logger is not None
    logger.info("test_message")


def test_get_logger_with_initial_values() -> None:
    logger = get_logger(__name__, component="test")
    assert logger is not None
    logger.info("test_with_initial")


def test_bind_and_clear_correlation_id() -> None:
    bind_correlation_id("test-req-1")
    clear_context()


def test_bind_correlation_does_not_raise() -> None:
    bind_correlation_id("req-42")
    clear_context()
