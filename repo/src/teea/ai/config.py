"""Configuration for the AI Runtime.

Mirrors :class:`~teea.core.config.TokenizationSettings`: a
:mod:`pydantic_settings` model whose every value is overridable by a
``TEEA_AI__`` environment variable and validated at construction.

It stands alone rather than nesting inside ``TEEASettings``. That root model
lives in :mod:`teea.core`, and ``core`` must never import a layer above it, so a
``core`` settings object cannot hold an AI type. The daemon composes the two at
its own layer instead.
"""

from __future__ import annotations

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from teea.ai.models import Device
from teea.core.errors import ConfigurationError


class AIRuntimeSettings(BaseSettings):
    """Settings governing the AI Runtime.

    Attributes:
        memory_budget_bytes: The most resident model memory the runtime keeps
            loaded at once. ``None``, the default, is unlimited -- the honest
            default when no model has declared a footprint, since a budget over
            unknown sizes would evict arbitrarily. A finite budget turns on the
            Memory Manager's eviction.
        default_device: The device inference runs on unless a context overrides
            it.
        eager_load: Whether registering a model while the runtime is running
            loads it immediately. ``False``, the default, is Figure 6's "Lazy
            loading": a model loads on first use.
    """

    model_config = SettingsConfigDict(
        env_prefix="TEEA_AI__",
        env_file=None,
        extra="forbid",
        frozen=True,
    )

    memory_budget_bytes: int | None = Field(default=None, ge=0)
    default_device: Device = Device.AUTO
    eager_load: bool = False


def load_ai_settings(**overrides: object) -> AIRuntimeSettings:
    """Construct and validate AI Runtime settings.

    Args:
        **overrides: Explicit values that take precedence over environment
            variables and defaults.

    Returns:
        A validated, immutable :class:`AIRuntimeSettings`.

    Raises:
        ConfigurationError: If the resulting configuration is invalid.
    """
    try:
        return AIRuntimeSettings(**overrides)  # type: ignore[arg-type]
    except ValidationError as exc:
        raise ConfigurationError(
            "Invalid AI Runtime configuration.",
            context={"errors": exc.errors(include_url=False)},
            cause=exc,
        ) from exc


__all__ = ["AIRuntimeSettings", "load_ai_settings"]
