"""Invariants of the Plugin Runtime's value objects.

Two of these are load-bearing rather than cosmetic. A plugin must not be able to
attribute its output to another, because the Fusion Engine weights suggestions by
that attribution (ADR-017). And a failed plugin must not also carry output,
because the add-in decides what to tell the user from exactly that distinction.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from teea.core.errors import ErrorCode
from teea.core.types import TextSpan
from teea.fusion import Suggestion, SuggestionPriority
from teea.plugins import PluginFailure, PluginOutcome, PluginResults

P = SuggestionPriority


def span(start: int = 0, end: int = 3) -> TextSpan:
    """A span with true three-bytes-per-character Tibetan offsets."""
    return TextSpan(char_start=start, char_end=end, byte_start=start * 3, byte_end=end * 3)


def suggestion(source: str = "spell", start: int = 0, end: int = 3) -> Suggestion:
    """A well-formed suggestion attributed to ``source``."""
    return Suggestion(
        source=source,
        span=span(start, end),
        replacement="ཀ",
        score=0.9,
        priority=P.HIGH,
    )


def failure(plugin: str = "crash") -> PluginFailure:
    """A recorded fault for ``plugin``."""
    return PluginFailure(
        plugin=plugin,
        code=ErrorCode.PLUGIN_EXECUTION_FAILED,
        error_type="RuntimeError",
        message="boom",
    )


# -- The new error codes -------------------------------------------------------
def test_the_plugin_domain_has_its_own_error_codes() -> None:
    """Stable codes are part of the IPC contract and must not be repurposed."""
    assert ErrorCode.PLUGIN_EXECUTION_FAILED.value == "TEEA-2000"
    assert ErrorCode.PLUGIN_CONTRACT_VIOLATED.value == "TEEA-2001"


def test_every_error_code_is_unique() -> None:
    values = [code.value for code in ErrorCode]
    assert len(set(values)) == len(values)


# -- PluginFailure -------------------------------------------------------------
def test_a_failure_records_what_happened() -> None:
    recorded = failure()
    assert recorded.plugin == "crash"
    assert recorded.code is ErrorCode.PLUGIN_EXECUTION_FAILED
    assert recorded.error_type == "RuntimeError"
    assert recorded.message == "boom"


def test_a_failure_must_name_its_plugin() -> None:
    """An unattributable fault tells the user nothing actionable."""
    with pytest.raises(ValidationError, match="must name the plugin"):
        PluginFailure(
            plugin="",
            code=ErrorCode.PLUGIN_EXECUTION_FAILED,
            error_type="RuntimeError",
            message="boom",
        )


def test_a_failure_must_name_the_error_type() -> None:
    with pytest.raises(ValidationError, match="must name the error type"):
        PluginFailure(
            plugin="crash",
            code=ErrorCode.PLUGIN_EXECUTION_FAILED,
            error_type="",
            message="boom",
        )


def test_a_failure_may_carry_an_empty_message() -> None:
    """Plenty of exceptions are raised with no message at all."""
    assert (
        PluginFailure(
            plugin="crash",
            code=ErrorCode.PLUGIN_EXECUTION_FAILED,
            error_type="RuntimeError",
            message="",
        ).message
        == ""
    )


def test_a_failure_is_immutable() -> None:
    with pytest.raises(ValidationError):
        failure().plugin = "other"  # type: ignore[misc]


# -- PluginOutcome -------------------------------------------------------------
def test_a_successful_outcome_carries_its_suggestions() -> None:
    outcome = PluginOutcome(plugin="spell", suggestions=(suggestion(),))
    assert outcome.succeeded is True
    assert outcome.num_suggestions == len(outcome) == 1


def test_an_outcome_with_nothing_found_still_succeeded() -> None:
    """The distinction the add-in needs: found nothing is not the same as crashed."""
    outcome = PluginOutcome(plugin="quiet")
    assert outcome.succeeded is True
    assert outcome.num_suggestions == 0


def test_a_failed_outcome_reports_the_fault() -> None:
    outcome = PluginOutcome(plugin="crash", failure=failure())
    assert outcome.succeeded is False
    assert outcome.num_suggestions == 0


def test_an_outcome_must_name_its_plugin() -> None:
    with pytest.raises(ValidationError, match="must name its plugin"):
        PluginOutcome(plugin="")


def test_a_failure_from_a_different_plugin_is_rejected() -> None:
    with pytest.raises(ValidationError, match="names a different plugin"):
        PluginOutcome(plugin="spell", failure=failure("crash"))


def test_a_failed_plugin_cannot_also_have_produced_output() -> None:
    """Partial output from a crash is not trustworthy and must not reach fusion."""
    with pytest.raises(ValidationError, match="cannot also have produced output"):
        PluginOutcome(plugin="crash", suggestions=(suggestion("crash"),), failure=failure("crash"))


def test_a_plugin_cannot_attribute_output_to_another_plugin() -> None:
    """Attribution decides trust, so borrowing a name would borrow trust.

    The Fusion Engine weights suggestions by their source (ADR-017); a plugin
    that claimed a trusted plugin's name would inherit its weighting.
    """
    with pytest.raises(ValidationError, match="attributed a suggestion to"):
        PluginOutcome(plugin="liar", suggestions=(suggestion("spell"),))


def test_every_suggestion_is_checked_not_just_the_first() -> None:
    with pytest.raises(ValidationError, match="attributed a suggestion to"):
        PluginOutcome(
            plugin="spell",
            suggestions=(suggestion("spell"), suggestion("other", 4, 6)),
        )


def test_an_outcome_is_immutable() -> None:
    with pytest.raises(ValidationError):
        PluginOutcome(plugin="quiet").plugin = "other"  # type: ignore[misc]


# -- PluginResults -------------------------------------------------------------
def results() -> PluginResults:
    """Two successes and one failure, in the required order."""
    return PluginResults(
        outcomes=(
            PluginOutcome(plugin="crash", failure=failure("crash")),
            PluginOutcome(plugin="quiet"),
            PluginOutcome(plugin="spell", suggestions=(suggestion(), suggestion("spell", 4, 6))),
        )
    )


def test_empty_results_are_healthy() -> None:
    """A runtime with no plugins registered has nothing that could have failed."""
    empty = PluginResults()
    assert empty.is_healthy is True
    assert len(empty) == empty.num_plugins == 0
    assert empty.suggestions == () == empty.failures
    assert empty.num_suggestions == empty.num_failed == empty.num_succeeded == 0
    assert empty.outcome_of("spell") is None


def test_results_summarise_every_plugin() -> None:
    collected = results()
    assert len(collected) == collected.num_plugins == 3
    assert collected.num_succeeded == 2
    assert collected.num_failed == 1
    assert collected.is_healthy is False
    assert collected.num_suggestions == 2


def test_results_flatten_the_suggestions_for_fusion() -> None:
    """This tuple is exactly what the Fusion Engine consumes."""
    collected = results()
    assert len(collected.suggestions) == 2
    assert {s.source for s in collected.suggestions} == {"spell"}


def test_results_expose_the_faults_that_were_captured() -> None:
    collected = results()
    assert [f.plugin for f in collected.failures] == ["crash"]


def test_one_plugins_outcome_can_be_looked_up() -> None:
    collected = results()
    found = collected.outcome_of("spell")
    assert found is not None
    assert found.num_suggestions == 2
    assert collected.outcome_of("absent") is None


def test_outcomes_must_be_ordered_by_plugin_name() -> None:
    """Ordering is what makes the result independent of finishing order."""
    with pytest.raises(ValidationError, match="ordered by plugin name"):
        PluginResults(outcomes=(PluginOutcome(plugin="spell"), PluginOutcome(plugin="crash")))


def test_a_plugin_must_not_appear_twice() -> None:
    with pytest.raises(ValidationError, match="must not appear twice"):
        PluginResults(outcomes=(PluginOutcome(plugin="spell"), PluginOutcome(plugin="spell")))


def test_results_are_immutable() -> None:
    with pytest.raises(ValidationError):
        results().outcomes = ()  # type: ignore[misc]


# -- Serialization -------------------------------------------------------------
def test_results_round_trip_through_json() -> None:
    """Plugin results cross the daemon's internal boundaries as data."""
    collected = results()
    restored = PluginResults.model_validate_json(collected.model_dump_json())
    assert restored == collected
    assert restored.failures[0].code is ErrorCode.PLUGIN_EXECUTION_FAILED


def test_results_dump_to_plain_data() -> None:
    dumped = results().model_dump(mode="json")
    assert dumped["outcomes"][0]["failure"]["code"] == "TEEA-2000"
    assert dumped["outcomes"][2]["suggestions"][0]["source"] == "spell"
    assert dumped["outcomes"][1]["failure"] is None
