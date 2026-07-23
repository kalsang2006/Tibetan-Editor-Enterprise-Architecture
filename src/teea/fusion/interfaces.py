"""The suggestion fusion abstraction (interface) for TEEA.

The daemon drives Figure 7's engine through this protocol rather than a concrete
class, consistent with every other component in the project. Figure 3 routes
"Plugin Results" into the Fusion Engine and "Merged Suggestions" back out to the
Office.js add-in; this single method is that call.

One call, not a stream
----------------------
SRS 1.2 and 3.2 describe the fusion as *streaming* and *asynchronous*. That is a
statement about scheduling, not about the algorithm: the engine itself is a pure
function of the document and the suggestions it is handed, and the *daemon*
decides when to call it and with how much. Making fusion cheap and total means a
caller can run it again each time another plugin reports, and show the result
immediately -- which is what SRS 3.2 asks for when it requires deterministic
feedback to paint at once while slower work continues behind it.

This is the same division ADR-016 drew for incremental re-analysis: the Language
Server decides *what* needs re-analysis, the daemon decides *when* to ask. Here
the engine decides *what wins*, and the daemon decides *when to fuse*.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from teea.fusion.models import Suggestion, UnifiedSuggestions


@runtime_checkable
class SuggestionFusionEngine(Protocol):
    """A suggestion fusion contract.

    Implementations must be safe to share across threads for read-only use: the
    daemon fuses for many documents at once against one engine.
    """

    def fuse(
        self, source: str, suggestions: Iterable[Suggestion]
    ) -> UnifiedSuggestions:
        """Merge plugin recommendations into one ranked, conflict-free package.

        Implementations must be **total**: no suggestion, however malformed its
        range, may raise. Figure 7 gives the Validator "Remove invalid entries",
        which is a filtering instruction, not an error-handling one -- and NFR
        5.3 requires that one misbehaving plugin cannot take down the others.
        Everything discarded must be reported rather than dropped in silence.

        Implementations must be **deterministic and order-independent**: the same
        suggestions in a different arrival order must fuse to the same result.
        Plugins report concurrently, so any dependence on arrival order would make
        the user's task pane vary between identical documents.

        The returned patch must contain no overlapping operations (FR-7).

        Args:
            source: The document the suggestions address.
            suggestions: Plugin output, in any order. Each names its own plugin,
                so they may arrive interleaved.

        Returns:
            The unified package: ranked survivors, the patch, and every
            rejection with its reason.
        """
        ...


__all__ = ["SuggestionFusionEngine"]
