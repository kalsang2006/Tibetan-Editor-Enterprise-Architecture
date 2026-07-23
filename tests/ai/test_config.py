"""Tests for AI Runtime configuration.

Mirrors the tokenization-settings tests: defaults, environment overrides, and
the validation that turns a bad value into a ``ConfigurationError`` at startup
rather than a failure deep inside the runtime.
"""

from __future__ import annotations

import pytest

from teea.ai import AIRuntimeSettings, LocalAIRuntime, load_ai_settings
from teea.ai.models import Device
from teea.core.errors import ConfigurationError, ErrorCode
from tests.ai.conftest import RecordingEngine


def test_the_defaults_are_lazy_unlimited_and_auto() -> None:
    settings = AIRuntimeSettings()
    assert settings.memory_budget_bytes is None
    assert settings.default_device is Device.AUTO
    assert settings.eager_load is False


def test_settings_are_overridable_by_keyword() -> None:
    settings = load_ai_settings(
        memory_budget_bytes=1_024, default_device="gpu", eager_load=True
    )
    assert settings.memory_budget_bytes == 1_024
    assert settings.default_device is Device.GPU
    assert settings.eager_load is True


def test_settings_are_immutable() -> None:
    settings = AIRuntimeSettings()
    with pytest.raises(ValueError, match="frozen"):
        settings.eager_load = True  # type: ignore[misc]


def test_a_negative_budget_is_rejected_at_construction() -> None:
    """Eager validation: a bad budget fails now, not mid-inference."""
    with pytest.raises(ConfigurationError, match="Invalid AI Runtime") as error:
        load_ai_settings(memory_budget_bytes=-1)
    assert error.value.code is ErrorCode.CONFIGURATION_INVALID
    assert "errors" in error.value.context


def test_an_unknown_setting_is_rejected() -> None:
    with pytest.raises(ConfigurationError):
        load_ai_settings(gpu_count=4)


def test_settings_are_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEEA_AI__MEMORY_BUDGET_BYTES", "512")
    monkeypatch.setenv("TEEA_AI__EAGER_LOAD", "true")
    settings = AIRuntimeSettings()
    assert settings.memory_budget_bytes == 512
    assert settings.eager_load is True


def test_the_runtime_exposes_its_settings(engine: RecordingEngine) -> None:
    settings = AIRuntimeSettings(memory_budget_bytes=100)
    runtime = LocalAIRuntime(engine, settings=settings)
    assert runtime.settings is settings
