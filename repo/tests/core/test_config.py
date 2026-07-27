from __future__ import annotations

import pytest
from pydantic import ValidationError

from teea.core.config import TEEASettings, TokenizationSettings, load_settings
from teea.core.errors import ConfigurationError


def test_tokenization_settings_rejects_empty_model_id() -> None:
    with pytest.raises(ValidationError, match="model_id"):
        TokenizationSettings(model_id="")


def test_tokenization_settings_rejects_blank_model_id() -> None:
    with pytest.raises(ValidationError, match="model_id"):
        TokenizationSettings(model_id="   ")


def test_teeasettings_rejects_invalid_log_level() -> None:
    with pytest.raises(ValidationError, match="log_level"):
        TEEASettings(log_level="TRACE")


def test_load_settings_wraps_validation_error() -> None:
    with pytest.raises(ConfigurationError, match="Invalid TEEA configuration"):
        load_settings(log_level="TRACE")


def test_load_settings_passes_valid_config() -> None:
    settings = load_settings(log_level="DEBUG")
    assert settings.log_level == "DEBUG"
