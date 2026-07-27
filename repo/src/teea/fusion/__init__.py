"""TEEA Suggestion Fusion Engine.

Figure 1 places this component in the Runtime Layer beside the Language Server
and the Plugin Runtime; Figure 3 routes "Plugin Results" into it and "Merged
Suggestions" out of it; and Figure 7 is a dedicated diagram specifying it as
seven stages. SRS §7 puts "Fusion Stream" in the **Highest** MVP priority ring.

It takes what the feature plugins recommend -- possibly contradicting each other,
possibly overlapping, arriving in any order -- and produces one ranked package
plus a conflict-free document patch (FR-7).

Public API:

* :class:`SuggestionFusionEngine` -- the abstraction downstream code depends on.
* :class:`PriorityRankedFusionEngine` -- the shipped implementation.
* Domain models: :class:`Suggestion`, :class:`SuggestionPriority`,
  :class:`UnifiedSuggestions`, :class:`DocumentPatch`, :class:`EditOperation`,
  :class:`RejectedSuggestion`, :class:`RejectionReason`.

This package depends on :mod:`teea.core` alone. It never imports
:mod:`teea.nlp`: Figure 3 shows it receiving plugin results, not parsed text, and
fusion is arithmetic over ranges rather than linguistics. The constraint is
enforced by ``tests/test_architecture.py``.

Typical usage::

    from teea.core.types import TextSpan
    from teea.fusion import PriorityRankedFusionEngine, Suggestion, SuggestionPriority

    engine = PriorityRankedFusionEngine(plugin_weights={"spell": 1.0, "style": 0.6})
    unified = engine.fuse(document, plugin_outputs)

    unified.suggestions           # ranked, most urgent and most confident first
    unified.edits                 # those that rewrite the document
    unified.advisories            # those that only annotate
    unified.patch.apply()         # the rewritten document
    unified.rejected              # everything discarded, with the reason

Confidence adjustment by the AI Runtime, which Figure 7 also shows, is absent:
that component does not exist in this repository and ADR-006 established that
defining interfaces for absent features invents requirements. See ADR-017.
"""

from __future__ import annotations

from teea.fusion.engine import DEFAULT_PLUGIN_WEIGHT, PriorityRankedFusionEngine
from teea.fusion.interfaces import SuggestionFusionEngine
from teea.fusion.models import (
    DocumentPatch,
    EditOperation,
    RejectedSuggestion,
    RejectionReason,
    Suggestion,
    SuggestionPriority,
    UnifiedSuggestions,
)

__all__ = [
    "DEFAULT_PLUGIN_WEIGHT",
    "DocumentPatch",
    "EditOperation",
    "PriorityRankedFusionEngine",
    "RejectedSuggestion",
    "RejectionReason",
    "Suggestion",
    "SuggestionFusionEngine",
    "SuggestionPriority",
    "UnifiedSuggestions",
]
