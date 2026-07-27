"""Immutable domain models of the Plugin Runtime.

Figure 3 places the Plugin Runtime between the Language Server and the Suggestion
Fusion Engine: it receives "Parsed Tokens / Graph" and emits "Plugin Results".
These are the value objects on the second of those edges.

Why an outcome rather than a list of suggestions
------------------------------------------------
NFR 5.3 requires that "a system fault or unhandled error inside a particular
feature plugin must be captured by its manager without causing the host Word
interface or other running tools to crash". Captured means *recorded*: the
runtime cannot return only what succeeded, because the add-in has to be able to
tell "the style checker found nothing" from "the style checker crashed". So
dispatch returns one :class:`PluginOutcome` per registered plugin, whether it
succeeded or not, and a failure is data rather than an exception.

This is the same discipline the analysis pipeline applies to its own uncertainty
-- Stage 08 records the morphemes it could not attach, Stage 11 the roles it
could not type, and the Fusion Engine the suggestions it discarded. A rate that
cannot be measured is a rate nobody will notice rising.

Attribution is enforced, not trusted
------------------------------------
Every suggestion carries the name of the plugin that produced it, and the Fusion
Engine weights suggestions by that name (ADR-017). A plugin that attributed its
output to another would therefore borrow that plugin's trust. Sandboxing an
extension means not taking its word for who it is, so
:class:`PluginOutcome` rejects any suggestion whose source is not the plugin the
runtime dispatched.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

from teea.core.errors import ErrorCode
from teea.fusion import Suggestion


class PluginFailure(BaseModel):
    """What a plugin did instead of producing suggestions.

    Carries the exception's type and message rather than a traceback: a
    traceback would embed local variables, and a plugin's locals hold the
    document. :mod:`teea.core.errors` requires that error context never contain
    document contents.

    Attributes:
        plugin: The plugin that failed.
        code: Machine-readable classification. A plugin raising a
            :class:`~teea.core.errors.TEEAError` keeps its own code, so a
            configuration fault stays distinguishable from a crash.
        error_type: The exception class name, for diagnosis.
        message: The exception's message, verbatim. A plugin that writes document
            text into its own exception message publishes it here; that is the
            plugin's choice, and the runtime does not paraphrase it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    plugin: str
    code: ErrorCode
    error_type: str
    message: str

    @model_validator(mode="after")
    def _validate_consistency(self) -> PluginFailure:
        if not self.plugin:
            raise ValueError("a failure must name the plugin it came from")
        if not self.error_type:
            raise ValueError("a failure must name the error type")
        return self


class PluginOutcome(BaseModel):
    """What one plugin produced for one document.

    Attributes:
        plugin: The registered name of the plugin.
        suggestions: What it recommended, in the order it produced them. Empty
            when it recommended nothing, and always empty when it failed.
        failure: The fault that stopped it, or ``None`` when it completed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    plugin: str
    suggestions: tuple[Suggestion, ...] = ()
    failure: PluginFailure | None = None

    @model_validator(mode="after")
    def _validate_consistency(self) -> PluginOutcome:
        if not self.plugin:
            raise ValueError("an outcome must name its plugin")
        if self.failure is not None:
            if self.failure.plugin != self.plugin:
                raise ValueError("the failure names a different plugin")
            if self.suggestions:
                raise ValueError("a failed plugin cannot also have produced output")
        for suggestion in self.suggestions:
            if suggestion.source != self.plugin:
                raise ValueError(
                    f"{self.plugin!r} attributed a suggestion to {suggestion.source!r}"
                )
        return self

    def __len__(self) -> int:
        """Number of suggestions produced."""
        return len(self.suggestions)

    @property
    def succeeded(self) -> bool:
        """Whether the plugin ran to completion."""
        return self.failure is None

    @property
    def num_suggestions(self) -> int:
        """Number of suggestions produced."""
        return len(self.suggestions)


class PluginResults(BaseModel):
    """Everything the registered plugins produced for one document.

    This is Figure 3's "Plugin Results" edge, and :attr:`suggestions` is what the
    Suggestion Fusion Engine consumes.

    Attributes:
        outcomes: One entry per registered plugin, ordered by plugin name so the
            result does not depend on the order they happened to finish in.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    outcomes: tuple[PluginOutcome, ...] = ()

    @model_validator(mode="after")
    def _validate_consistency(self) -> PluginResults:
        names = [outcome.plugin for outcome in self.outcomes]
        if names != sorted(names):
            raise ValueError("outcomes must be ordered by plugin name")
        if len(set(names)) != len(names):
            raise ValueError("a plugin must not appear twice")
        return self

    def __len__(self) -> int:
        """Number of plugins that were dispatched."""
        return len(self.outcomes)

    @property
    def num_plugins(self) -> int:
        """Number of plugins that were dispatched."""
        return len(self.outcomes)

    @property
    def suggestions(self) -> tuple[Suggestion, ...]:
        """Every suggestion produced, ready for the Fusion Engine.

        Flattened in plugin-name order. The Fusion Engine is order-independent by
        contract, so this ordering is for reproducibility rather than for it.
        """
        return tuple(suggestion for outcome in self.outcomes for suggestion in outcome.suggestions)

    @property
    def failures(self) -> tuple[PluginFailure, ...]:
        """Every fault that was captured, in plugin-name order."""
        return tuple(outcome.failure for outcome in self.outcomes if outcome.failure is not None)

    @property
    def num_suggestions(self) -> int:
        """Total suggestions across every plugin."""
        return sum(outcome.num_suggestions for outcome in self.outcomes)

    @property
    def num_failed(self) -> int:
        """How many plugins failed."""
        return len(self.failures)

    @property
    def num_succeeded(self) -> int:
        """How many plugins ran to completion."""
        return len(self.outcomes) - self.num_failed

    @property
    def is_healthy(self) -> bool:
        """Whether every dispatched plugin completed.

        The signal a task pane needs to decide whether to tell the user that part
        of the analysis is missing.
        """
        return not self.failures

    def outcome_of(self, plugin: str) -> PluginOutcome | None:
        """Return one plugin's outcome, or ``None`` if it was not dispatched."""
        for outcome in self.outcomes:
            if outcome.plugin == plugin:
                return outcome
        return None


__all__ = ["PluginFailure", "PluginOutcome", "PluginResults"]
