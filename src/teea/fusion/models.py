"""Immutable domain models of the Suggestion Fusion Engine.

Figure 7 is a dedicated diagram for this component, and these are the value
objects on its two boundaries: :class:`Suggestion` is what the Feature Plugins
Layer emits ("Outputs: Suggestions, Score, Priority"), and
:class:`UnifiedSuggestions` is the "Final Synchronized Output Package" the engine
hands back -- "Final Ranked Suggestions" together with a "Document Patch, Ready
for Office.js Rendering".

Why the suggestion format is defined here
-----------------------------------------
The format is a contract between the Plugin Runtime and this engine, and neither
component existed before now. Figure 7 settles the ownership question directly:
it assigns "Normalize suggestion format" to the **Suggestion Collector**, which
is a sub-component of the fusion engine. The format is therefore this component's
concern, and a plugin conforms to it rather than the reverse.

Edits and advisories
--------------------
Figure 7's output package mixes two kinds of thing: "Grammar Corrections" and
"Spelling Corrections" rewrite the document, while "Plagiarism Warnings" and
"Summary & Citations" do not. So :attr:`Suggestion.replacement` is optional. A
suggestion with a replacement is an *edit* and competes for its range; one
without is an *advisory* that annotates a range and competes with nothing. Only
edits reach the patch.

Nothing is discarded silently
-----------------------------
Figure 7 gives the Validator "Remove invalid entries · Filter duplicates" and the
Conflict Resolution Engine "Select best candidate". Both throw suggestions away.
Every discarded suggestion is returned in :attr:`UnifiedSuggestions.rejected`
with the reason, following the discipline Stage 08 set with its unattached
morphemes and Stage 11 with its unresolved roles: a rate that cannot be measured
is a rate nobody will notice rising.
"""

from __future__ import annotations

import enum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from teea.core.types import TextSpan


@enum.unique
class SuggestionPriority(enum.Enum):
    """How urgently a suggestion should reach the user.

    Exactly the four classes Figure 7's Priority Manager names, in the order it
    names them: *"Critical, High, Medium, Low priority ordering &
    classification"*.
    """

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @property
    def rank(self) -> int:
        """Sort position, ``0`` being the most urgent."""
        return _PRIORITY_RANK[self]


#: Figure 7's ordering, stated once so the enum and the ranking cannot drift.
_PRIORITY_RANK: Final[dict[SuggestionPriority, int]] = {
    SuggestionPriority.CRITICAL: 0,
    SuggestionPriority.HIGH: 1,
    SuggestionPriority.MEDIUM: 2,
    SuggestionPriority.LOW: 3,
}


@enum.unique
class RejectionReason(enum.Enum):
    """Why the engine discarded a suggestion.

    The first three come from Figure 7's Validator, the last from its Conflict
    Resolution Engine.
    """

    #: The span does not address the document that was fused.
    INVALID_RANGE = "invalid_range"
    #: The replacement is exactly the text already there, so applying it would
    #: change nothing while still asking the user to make a decision.
    NO_OP = "no_op"
    #: An identical suggestion was already accepted.
    DUPLICATE = "duplicate"
    #: It overlapped a better candidate and lost (FR-7).
    SUPERSEDED = "superseded"


class Suggestion(BaseModel):
    """One recommendation from one feature plugin.

    Attributes:
        source: The plugin that produced it. Free-form because the Plugin
            Runtime, which will own the plugin identifiers, does not exist yet;
            Figure 7 names eight plugins but nothing fixes their identifiers.
        span: The document range the suggestion addresses. An empty span is an
            insertion point.
        replacement: The text to put in that range, or ``None`` for an advisory
            that recommends no edit.
        score: The plugin's own confidence, in ``[0, 1]``. Figure 7 lists Score
            among the plugin outputs, so it is required rather than defaulted --
            a forgotten score would otherwise silently rank as certainty.
        priority: The urgency class. Also a listed plugin output, also required.
        message: Human-readable explanation for the task pane. Optional.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    span: TextSpan
    replacement: str | None = None
    score: float = Field(ge=0.0, le=1.0)
    priority: SuggestionPriority
    message: str = ""

    @model_validator(mode="after")
    def _validate_consistency(self) -> Suggestion:
        if not self.source:
            raise ValueError("a suggestion must name the plugin that produced it")
        if self.replacement == "" and self.span.is_empty:
            raise ValueError("an edit must either cover a range or insert text")
        return self

    @property
    def is_edit(self) -> bool:
        """Whether this suggestion rewrites the document."""
        return self.replacement is not None

    @property
    def is_advisory(self) -> bool:
        """Whether this suggestion only annotates, recommending no edit."""
        return self.replacement is None

    def conflicts_with(self, other: Suggestion) -> bool:
        """Whether both are edits competing for overlapping text.

        FR-7 requires overlapping range coordinates to be resolved before the
        canvas is updated, and overlap is what makes two edits irreconcilable:
        applying both would corrupt the range the second one addressed.

        Advisories never conflict. A plagiarism warning spanning a paragraph does
        not compete with a spelling correction inside it -- they are shown
        together, because neither changes what the other refers to.

        Args:
            other: The suggestion to test against.

        Returns:
            ``True`` when both are edits and their spans overlap. An insertion
            point counts as overlapping a range that strictly contains it, and
            two insertions at the same offset count as overlapping each other.
        """
        if self.is_advisory or other.is_advisory:
            return False
        first, second = self.span, other.span
        if first.is_empty and second.is_empty:
            return first.char_start == second.char_start
        if first.is_empty:
            return second.char_start <= first.char_start < second.char_end
        if second.is_empty:
            return first.char_start <= second.char_start < first.char_end
        return first.char_start < second.char_end and second.char_start < first.char_end


class RejectedSuggestion(BaseModel):
    """A suggestion the engine discarded, and why.

    Attributes:
        suggestion: The discarded suggestion, unchanged.
        reason: What discarded it.
        superseded_by: The winning suggestion, when the reason is
            :attr:`RejectionReason.SUPERSEDED` or
            :attr:`RejectionReason.DUPLICATE`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    suggestion: Suggestion
    reason: RejectionReason
    superseded_by: Suggestion | None = None

    @model_validator(mode="after")
    def _validate_consistency(self) -> RejectedSuggestion:
        needs_winner = {RejectionReason.SUPERSEDED, RejectionReason.DUPLICATE}
        if self.reason in needs_winner and self.superseded_by is None:
            raise ValueError(f"{self.reason.value} must name the suggestion that won")
        if self.reason not in needs_winner and self.superseded_by is not None:
            raise ValueError(f"{self.reason.value} cannot name a winner")
        return self


class EditOperation(BaseModel):
    """One replacement to apply to the document.

    Figure 7's Patch Generator produces these: *"Generate final document edits ·
    Preserve formatting · Produce edit operations"*. An operation names only the
    range it rewrites, so every character outside it -- and therefore all of the
    formatting attached to it -- is left alone.

    Attributes:
        span: The range to replace. An empty span is an insertion.
        replacement: The text to put there.
        sources: The plugins whose suggestions produced this operation, in
            surface order. More than one when adjacent edits were consolidated.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    span: TextSpan
    replacement: str
    sources: tuple[str, ...]

    @model_validator(mode="after")
    def _validate_consistency(self) -> EditOperation:
        if not self.sources:
            raise ValueError("an edit operation must name its source")
        if self.replacement == "" and self.span.is_empty:
            raise ValueError("an edit operation must change something")
        return self


class DocumentPatch(BaseModel):
    """The edits to apply, ready for Office.js rendering.

    Attributes:
        source: The document the operations address, exactly as fused.
        operations: The edits, in document order and never overlapping.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    operations: tuple[EditOperation, ...] = ()

    @model_validator(mode="after")
    def _validate_consistency(self) -> DocumentPatch:
        previous_end = 0
        for position, operation in enumerate(self.operations):
            span = operation.span
            if span.char_start < previous_end:
                raise ValueError(f"operation {position} overlaps the one before it")
            if span.char_end > len(self.source):
                raise ValueError(f"operation {position} extends past the document")
            previous_end = span.char_end
        return self

    def __len__(self) -> int:
        """Number of edit operations."""
        return len(self.operations)

    @property
    def num_operations(self) -> int:
        """Number of edit operations."""
        return len(self.operations)

    @property
    def is_empty(self) -> bool:
        """Whether the patch changes nothing."""
        return not self.operations

    def apply(self) -> str:
        """Return the document with every operation applied.

        Applied against :attr:`source` rather than an argument, so a patch cannot
        be applied to a document it was not built for. The operations are ordered
        and non-overlapping by construction, so a single forward pass suffices.

        Returns:
            The rewritten document.
        """
        pieces: list[str] = []
        cursor = 0
        for operation in self.operations:
            pieces.append(self.source[cursor : operation.span.char_start])
            pieces.append(operation.replacement)
            cursor = operation.span.char_end
        pieces.append(self.source[cursor:])
        return "".join(pieces)


class UnifiedSuggestions(BaseModel):
    """Figure 7's "Unified Suggestions -- Final Synchronized Output Package".

    Attributes:
        suggestions: Everything that survived, ranked -- most urgent and most
            confident first. Includes advisories, which carry no edit.
        patch: The edits, ready for Office.js.
        rejected: Everything discarded, with the reason. Never silently dropped.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    suggestions: tuple[Suggestion, ...] = ()
    patch: DocumentPatch
    rejected: tuple[RejectedSuggestion, ...] = ()

    def __len__(self) -> int:
        """Number of surviving suggestions."""
        return len(self.suggestions)

    @property
    def num_suggestions(self) -> int:
        """Number of surviving suggestions."""
        return len(self.suggestions)

    @property
    def num_rejected(self) -> int:
        """Number of discarded suggestions."""
        return len(self.rejected)

    @property
    def is_empty(self) -> bool:
        """Whether nothing survived."""
        return not self.suggestions

    @property
    def edits(self) -> tuple[Suggestion, ...]:
        """The surviving suggestions that rewrite the document."""
        return tuple(s for s in self.suggestions if s.is_edit)

    @property
    def advisories(self) -> tuple[Suggestion, ...]:
        """The surviving suggestions that only annotate."""
        return tuple(s for s in self.suggestions if s.is_advisory)

    def of_priority(self, priority: SuggestionPriority) -> tuple[Suggestion, ...]:
        """Return the surviving suggestions of one urgency class, in rank order."""
        return tuple(s for s in self.suggestions if s.priority is priority)

    def of_source(self, source: str) -> tuple[Suggestion, ...]:
        """Return the surviving suggestions from one plugin, in rank order."""
        return tuple(s for s in self.suggestions if s.source == source)

    def rejected_for(self, reason: RejectionReason) -> tuple[RejectedSuggestion, ...]:
        """Return everything discarded for one reason."""
        return tuple(r for r in self.rejected if r.reason is reason)


__all__ = [
    "DocumentPatch",
    "EditOperation",
    "RejectedSuggestion",
    "RejectionReason",
    "Suggestion",
    "SuggestionPriority",
    "UnifiedSuggestions",
]
