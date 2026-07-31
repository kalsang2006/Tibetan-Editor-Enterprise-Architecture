"""Application configuration for TEEA.

Configuration is provided through :mod:`pydantic_settings` so that every value
can be overridden by environment variables (Windows-friendly, deployment-
friendly) while remaining strongly typed and validated at construction time.

Precedence (highest first):
    1. Explicit keyword arguments to :class:`TEEASettings`.
    2. Environment variables (prefixed ``TEEA_``; nested via ``__``).
    3. Declared defaults.

Examples:
    Override the model cache directory and normalization form from Windows
    PowerShell::

        $env:TEEA_TOKENIZATION__MODEL_CACHE_DIR = "D:\\teea\\models"
        $env:TEEA_TOKENIZATION__NORMALIZATION_FORM = "NFKC"

Design decisions
----------------
* **Nested settings model** (``tokenization``) keeps the namespace clean and
  mirrors the module boundaries; new modules add their own nested section.
* **Paths default under the user profile** (``~/.teea``) rather than the repo,
  honoring the rule that model weights are never committed to source control.
* **Validation is eager**: an invalid configuration raises
  :class:`~teea.core.errors.ConfigurationError` immediately instead of failing
  deep inside model loading.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from teea.core.errors import ConfigurationError
from teea.plagiarism.config import PlagiarismSettings

NormalizationForm = Literal["NFC", "NFKC", "NFD", "NFKD"]

#: Default Hugging Face model identifier for TiBERT. This is the authoritative
#: Tibetan encoder for the project and must not be silently substituted.
DEFAULT_TIBERT_MODEL_ID = "./TiBERT"

#: BERT-base positional limit. TiBERT is a BERT-base encoder (12 layers).
DEFAULT_MAX_SEQUENCE_LENGTH = 512


def _default_cache_dir() -> Path:
    """Return the default on-disk cache directory for downloaded models."""
    return Path.home() / ".teea" / "models"


class TokenizationSettings(BaseSettings):
    """Settings governing the TiBERT-backed tokenizer.

    Attributes:
        model_id: Hugging Face repo id for TiBERT. Overriding this to a
            different model is a deliberate, logged act; the default is the
            authoritative TiBERT.
        model_revision: Specific commit hash to pin the model download to.
            When set, ``from_pretrained`` fetches exactly this revision,
            protecting against silent upstream model changes. ``None``
            (default) uses the repository's default branch HEAD.
        model_local_path: Optional path to a pre-provisioned model directory.
            When set, the loader uses it instead of downloading. Useful for
            air-gapped Windows deployments.
        model_cache_dir: Directory into which Hugging Face caches downloads.
        max_sequence_length: Maximum number of tokens the tokenizer will emit
            before raising :class:`InputTooLongError` (unless truncation is
            explicitly requested by the caller).
        normalization_form: Unicode normalization form applied by the
            normalization utility (pipeline Stage 2) prior to tokenization.
        do_lower_case: Whether to lowercase input. Tibetan script is caseless;
            this defaults to ``False`` and should almost never be enabled.
        add_special_tokens: Whether encoding adds ``[CLS]``/``[SEP]`` by
            default. Callers may override per call.
    """

    model_config = SettingsConfigDict(
        env_prefix="TEEA_TOKENIZATION__",
        env_file=None,
        extra="forbid",
        frozen=True,
    )

    model_id: str = DEFAULT_TIBERT_MODEL_ID
    model_revision: str | None = None
    model_local_path: Path | None = None
    model_cache_dir: Path = Field(default_factory=_default_cache_dir)
    max_sequence_length: int = Field(default=DEFAULT_MAX_SEQUENCE_LENGTH, gt=0, le=4096)
    normalization_form: NormalizationForm = "NFC"
    do_lower_case: bool = False
    add_special_tokens: bool = True

    @field_validator("model_id")
    @classmethod
    def _model_id_not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("model_id must be a non-empty string")
        return value.strip()


class TEEASettings(BaseSettings):
    """Root application settings.

    Attributes:
        log_level: Root logging level (e.g. ``"INFO"``, ``"DEBUG"``).
        log_json: Emit logs as JSON (recommended for production) when ``True``;
            human-readable console rendering otherwise.
        tokenization: Nested tokenization settings.
    """

    model_config = SettingsConfigDict(
        env_prefix="TEEA_",
        env_nested_delimiter="__",
        env_file=None,
        extra="ignore",
        frozen=True,
    )

    log_level: str = "INFO"
    log_json: bool = True
    tokenization: TokenizationSettings = Field(default_factory=TokenizationSettings)
    plagiarism: PlagiarismSettings = Field(default_factory=PlagiarismSettings)

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
        upper = value.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return upper


def load_settings(**overrides: object) -> TEEASettings:
    """Construct and validate application settings.

    Args:
        **overrides: Explicit values that take precedence over environment
            variables and defaults.

    Returns:
        A validated, immutable :class:`TEEASettings` instance.

    Raises:
        ConfigurationError: If the resulting configuration is invalid.
    """
    try:
        return TEEASettings(**overrides)  # type: ignore[arg-type]
    except ValidationError as exc:
        raise ConfigurationError(
            "Invalid TEEA configuration.",
            context={"errors": exc.errors(include_url=False)},
            cause=exc,
        ) from exc


__all__ = [
    "DEFAULT_MAX_SEQUENCE_LENGTH",
    "DEFAULT_TIBERT_MODEL_ID",
    "NormalizationForm",
    "TEEASettings",
    "TokenizationSettings",
    "load_settings",
]
