"""The Suggestion Fusion Engine (Figure 7).

Figure 7 lays the component out as seven stages in a fixed order, and this module
implements them in that order:

============================  =============================================
Figure 7 stage                Implementation
============================  =============================================
Suggestion Collector          :meth:`~PriorityRankedFusionEngine._collect`
Suggestion Validator          :meth:`~PriorityRankedFusionEngine._validate`
Conflict Resolution Engine    :meth:`~PriorityRankedFusionEngine._resolve`
Merge Engine                  :meth:`~PriorityRankedFusionEngine._merge`
Confidence Ranking            :meth:`~PriorityRankedFusionEngine._rank`
Priority Manager              folded into the ranking sort key
Patch Generator               :meth:`~PriorityRankedFusionEngine._patch`
============================  =============================================

Two readings the diagram forces
-------------------------------
**Confidence is an input before it is an output.** Conflict Resolution comes
*before* Confidence Ranking, yet it has to "select best candidate", which needs a
notion of better. There is no contradiction: Figure 7 lists **Score** among the
things plugins emit, so a score exists from the moment a suggestion is collected.
Conflict resolution ranks candidates by that score; the Confidence Ranking stage
then orders the survivors for presentation. The score is the input, the ranking
is the output.

**Priority outranks confidence.** The Priority Manager sits between Confidence
Ranking and the Patch Generator, so its classification is applied last and
therefore dominates. A Critical suggestion precedes a High one however confident
the latter is -- which is the only reading under which a priority class means
anything at all.

What is deliberately absent
---------------------------
Figure 7 shows the **AI Runtime** attached to the Merge Engine and Confidence
Ranking for "Semantic validation · Confidence adjustment · Context verification ·
Ranking assistance". The AI Runtime is a separate component that this repository
does not implement, and ADR-006 established that defining an interface for a
feature that does not exist is inventing requirements. No hook is provided;
confidence here is the plugin's own score under a per-plugin weight. See ADR-017.

Order independence
------------------
Plugins report concurrently, so the engine sorts what it collects into a
canonical order before doing anything else. Every later stage is a fold over that
order, which makes the whole pipeline a pure function of the *set* of suggestions
rather than the sequence they arrived in. A test fuses shuffled permutations and
asserts identical results.
"""

from __future__ import annotations

import bisect
from collections.abc import Iterable, Mapping, Sequence

from teea.core.types import TextSpan
from teea.fusion.models import (
    DocumentPatch,
    EditOperation,
    RejectedSuggestion,
    RejectionReason,
    Suggestion,
    UnifiedSuggestions,
)

#: Weight applied to a plugin the caller did not weight explicitly.
DEFAULT_PLUGIN_WEIGHT = 1.0


class PriorityRankedFusionEngine:
    """Fuses plugin suggestions by priority, then by weighted confidence.

    Satisfies the :class:`~teea.fusion.interfaces.SuggestionFusionEngine`
    protocol. Holds no mutable state and is safe to share across threads.

    Args:
        plugin_weights: Per-plugin multipliers applied to each suggestion's own
            score, which is Figure 7's "Apply plugin weighting". A plugin the
            caller does not name keeps :data:`DEFAULT_PLUGIN_WEIGHT`. Weights are
            the operator's judgement about how far to trust a plugin, so there is
            no defensible default beyond "trust them equally".
        merge_adjacent: Whether to consolidate edits that touch end to start into
            one operation, which is Figure 7's "Combine adjacent edits". Defaults
            to ``True``. Set it to ``False`` to keep every suggestion separately
            acceptable in the task pane.
    """

    def __init__(
        self,
        *,
        plugin_weights: Mapping[str, float] | None = None,
        merge_adjacent: bool = True,
    ) -> None:
        # `is None`, not `or`: an empty mapping is falsy, and a caller who
        # deliberately weights nothing must not silently get something else.
        # The same defect was found and fixed in Stages 07, 09 and 10.
        self._weights: Mapping[str, float] = (
            {} if plugin_weights is None else dict(plugin_weights)
        )
        self._merge_adjacent = merge_adjacent

    @property
    def merge_adjacent(self) -> bool:
        """Whether adjacent edits are consolidated."""
        return self._merge_adjacent

    def weight_of(self, source: str) -> float:
        """Return the multiplier applied to one plugin's scores."""
        return self._weights.get(source, DEFAULT_PLUGIN_WEIGHT)

    def confidence_of(self, suggestion: Suggestion) -> float:
        """Return a suggestion's weighted confidence, clamped to ``[0, 1]``.

        Figure 7's Confidence Ranking is "Calculate confidence score · Apply
        plugin weighting". The plugin supplies the score and the operator
        supplies the weight, so the combination is their product; clamping keeps
        the result a confidence rather than an unbounded ranking number.
        """
        return min(1.0, max(0.0, suggestion.score * self.weight_of(suggestion.source)))

    def fuse(
        self, source: str, suggestions: Iterable[Suggestion]
    ) -> UnifiedSuggestions:
        """Merge plugin recommendations into one ranked, conflict-free package.

        Total: no input can raise. Everything discarded is reported.

        Args:
            source: The document the suggestions address.
            suggestions: Plugin output, in any order.

        Returns:
            The unified package.
        """
        rejected: list[RejectedSuggestion] = []

        collected = self._collect(suggestions)
        accepted = self._validate(source, collected, rejected)
        survivors = self._resolve(accepted, rejected)

        return UnifiedSuggestions(
            suggestions=self._rank(survivors),
            patch=self._patch(source, survivors),
            rejected=tuple(rejected),
        )

    # -- 1. Suggestion Collector ---------------------------------------------
    @staticmethod
    def _collect(suggestions: Iterable[Suggestion]) -> tuple[Suggestion, ...]:
        """Gather plugin output into one canonically ordered sequence.

        Sorting here is what makes the rest of the engine independent of the
        order plugins happened to report in. The key is total: two suggestions
        that sort equal are equal in every field that the later stages read.
        """
        return tuple(sorted(suggestions, key=_canonical_key))

    # -- 2. Suggestion Validator ---------------------------------------------
    def _validate(
        self,
        source: str,
        collected: Sequence[Suggestion],
        rejected: list[RejectedSuggestion],
    ) -> tuple[Suggestion, ...]:
        """Drop entries that cannot be acted on, and duplicates.

        Structural validity is already guaranteed -- :class:`Suggestion` is a
        validated model -- so what is checked here is validity *against this
        document*: a range that runs off the end addresses something else, and a
        replacement identical to the text it replaces asks the user to approve a
        change that is not one.
        """
        accepted: list[Suggestion] = []
        seen: dict[tuple[object, ...], Suggestion] = {}

        for suggestion in collected:
            span = suggestion.span
            if span.char_end > len(source):
                rejected.append(
                    RejectedSuggestion(
                        suggestion=suggestion, reason=RejectionReason.INVALID_RANGE
                    )
                )
                continue
            if suggestion.replacement is not None and (
                source[span.char_start : span.char_end] == suggestion.replacement
            ):
                rejected.append(
                    RejectedSuggestion(
                        suggestion=suggestion, reason=RejectionReason.NO_OP
                    )
                )
                continue

            key = _identity_key(suggestion)
            winner = seen.get(key)
            if winner is not None:
                rejected.append(
                    RejectedSuggestion(
                        suggestion=suggestion,
                        reason=RejectionReason.DUPLICATE,
                        superseded_by=winner,
                    )
                )
                continue

            seen[key] = suggestion
            accepted.append(suggestion)

        return tuple(accepted)

    # -- 3. Conflict Resolution Engine ----------------------------------------
    def _resolve(
        self, accepted: Sequence[Suggestion], rejected: list[RejectedSuggestion]
    ) -> tuple[Suggestion, ...]:
        """Keep the best candidate wherever edits compete for the same text.

        FR-7: overlapping range coordinates must be resolved before the canvas is
        updated. Candidates are considered in ranked order, so the first to claim
        a range keeps it and later overlapping edits lose to it -- a greedy pass
        that is deterministic because the order is.

        Advisories never compete, so they all survive.

        Why the claimed ranges are kept sorted
        --------------------------------------
        Comparing each candidate against every range claimed so far is quadratic
        in the number of *survivors*, and survivors are the common case: a spell
        checker flags scattered words that do not overlap at all. Measured on a
        realistic batch, 6,400 suggestions took **11.3 seconds** that way, which
        is not a slow interactive response but a frozen one.

        Claimed ranges never conflict with each other -- that is the invariant
        this loop maintains -- so no two of them share a start offset. Keeping
        them in start order means the only claims that can overlap a candidate
        are the one starting at or before it, which is the only claim that can
        *contain* its start, and those starting within its extent, which a binary
        search locates directly. Everything else is skipped rather than compared.

        The rightward walk stops at the candidate's own end, so for the scattered
        short suggestions a spell checker actually produces it examines one or two
        claims. It is proportional to how much the candidate really overlaps,
        which is the work needed to answer *which* of the overlapping claims is
        the best -- and that has to be the highest-ranked one, not merely the
        leftmost, or the attribution reported to the user would be wrong.
        """
        survivors: list[Suggestion] = []
        starts: list[int] = []
        claimed: list[tuple[Suggestion, int]] = []

        for order, suggestion in enumerate(sorted(accepted, key=self._rank_key)):
            if suggestion.is_advisory:
                survivors.append(suggestion)
                continue

            start = suggestion.span.char_start
            position = bisect.bisect_left(starts, start)

            neighbours: list[tuple[Suggestion, int]] = []
            if position > 0:
                neighbours.append(claimed[position - 1])
            index = position
            while index < len(starts) and starts[index] <= suggestion.span.char_end:
                neighbours.append(claimed[index])
                index += 1

            conflicting = [
                (claim_order, held)
                for held, claim_order in neighbours
                if held.conflicts_with(suggestion)
            ]
            if conflicting:
                # The earliest claim is the highest-ranked one, because claims
                # are made in rank order. Naming it keeps the attribution the
                # scan produced.
                _, winner = min(conflicting, key=lambda pair: pair[0])
                rejected.append(
                    RejectedSuggestion(
                        suggestion=suggestion,
                        reason=RejectionReason.SUPERSEDED,
                        superseded_by=winner,
                    )
                )
                continue

            starts.insert(position, start)
            claimed.insert(position, (suggestion, order))
            survivors.append(suggestion)

        return tuple(sorted(survivors, key=_canonical_key))

    # -- 4. Merge Engine -------------------------------------------------------
    def _merge(self, survivors: Sequence[Suggestion]) -> tuple[EditOperation, ...]:
        """Turn surviving edits into operations, consolidating adjacent ones.

        The edits are non-overlapping by now, so walking them in document order
        and joining each to its predecessor when they touch end to start is
        sufficient. Two insertions at the same offset would both be adjacent to
        that offset, but conflict resolution has already reduced them to one.
        """
        # Bind the replacement while filtering, so the type narrows without an
        # assertion and without a branch no input can reach.
        edits = sorted(
            (
                (suggestion, suggestion.replacement)
                for suggestion in survivors
                if suggestion.replacement is not None
            ),
            key=lambda pair: _span_key(pair[0].span),
        )
        operations: list[EditOperation] = []

        for suggestion, replacement in edits:
            previous = operations[-1] if operations else None
            if (
                self._merge_adjacent
                and previous is not None
                and previous.span.char_end == suggestion.span.char_start
                and not suggestion.span.is_empty
                and not previous.span.is_empty
            ):
                operations[-1] = EditOperation(
                    span=TextSpan(
                        char_start=previous.span.char_start,
                        char_end=suggestion.span.char_end,
                        byte_start=previous.span.byte_start,
                        byte_end=suggestion.span.byte_end,
                    ),
                    replacement=previous.replacement + replacement,
                    sources=(*previous.sources, suggestion.source),
                )
                continue
            operations.append(
                EditOperation(
                    span=suggestion.span,
                    replacement=replacement,
                    sources=(suggestion.source,),
                )
            )

        return tuple(operations)

    # -- 5 + 6. Confidence Ranking and Priority Manager ------------------------
    def _rank(self, survivors: Sequence[Suggestion]) -> tuple[Suggestion, ...]:
        """Order the survivors for presentation, most urgent first."""
        return tuple(sorted(survivors, key=self._rank_key))

    def _rank_key(self, suggestion: Suggestion) -> tuple[object, ...]:
        """Return the total order Figure 7's last two stages imply.

        Priority first, because the Priority Manager is applied after Confidence
        Ranking and therefore dominates it. Then weighted confidence, descending.
        The remaining components break ties deterministically; without them two
        equally urgent, equally confident suggestions would order arbitrarily and
        the task pane would differ between identical runs.
        """
        return (
            suggestion.priority.rank,
            -self.confidence_of(suggestion),
            *_canonical_key(suggestion),
        )

    # -- 7. Patch Generator ----------------------------------------------------
    def _patch(self, source: str, survivors: Sequence[Suggestion]) -> DocumentPatch:
        """Produce the document edits, ready for Office.js rendering.

        Each operation names only the range it rewrites, so every character
        outside it keeps whatever formatting it had. That is as far as "preserve
        formatting" can be taken here: Word's formatting model lives behind the
        Office.js bridge, and nothing in this repository represents it.
        """
        return DocumentPatch(source=source, operations=self._merge(survivors))


def _span_key(span: TextSpan) -> tuple[int, int]:
    """Return a span's sort position."""
    return (span.char_start, span.char_end)


def _canonical_key(suggestion: Suggestion) -> tuple[object, ...]:
    """Return the arrival-order-independent ordering of a suggestion."""
    return (
        *_span_key(suggestion.span),
        suggestion.source,
        suggestion.replacement is None,
        suggestion.replacement or "",
        suggestion.message,
    )


def _identity_key(suggestion: Suggestion) -> tuple[object, ...]:
    """Return what makes two suggestions the same recommendation.

    Score and priority are excluded: two plugins proposing the same edit with
    different confidence are still proposing one edit, and keeping both would put
    the same change in front of the user twice. The first in canonical order
    wins, which is deterministic.
    """
    return (
        *_span_key(suggestion.span),
        suggestion.source,
        suggestion.replacement,
    )


__all__ = ["DEFAULT_PLUGIN_WEIGHT", "PriorityRankedFusionEngine"]
