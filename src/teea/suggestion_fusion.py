"""Suggestion Fusion Helper Module for TEEA.

Integrates suggestion collection, priority ranking, and payload formatting across
Structural, Spelling, Tense, and Contextual/Semantic plugins.
"""

from __future__ import annotations

from typing import Any

from teea.engine import TEEAEngine
from teea.fusion import (
    PriorityRankedFusionEngine,
    Suggestion,
    SuggestionPriority,
    UnifiedSuggestions,
)


class SuggestionFusionEngine:
    """Helper facade for fusing suggestions across structural, spelling, and contextual plugins."""

    def __init__(self, engine: TEEAEngine | None = None) -> None:
        self._engine = engine or TEEAEngine()
        self._fusion = PriorityRankedFusionEngine()

    def process_text(self, text: str) -> UnifiedSuggestions:
        """Run analysis engine and fuse suggestions into a single ranked result."""
        return self._engine.analyze(text)

    def format_ui_payload(self, text: str, unified: UnifiedSuggestions) -> dict[str, Any]:
        """Format UnifiedSuggestions into the Office.js MS Word Add-in payload."""
        suggestions_list = []
        for s in unified.suggestions:
            suggestions_list.append(
                {
                    "id": f"{s.source}:{s.span.char_start}:{s.span.char_end}",
                    "source": s.source,
                    "range": {
                        "char_start": s.span.char_start,
                        "char_end": s.span.char_end,
                        "byte_start": s.span.byte_start,
                        "byte_end": s.span.byte_end,
                    },
                    "replacement": s.replacement,
                    "suggestions": [s.replacement] if s.replacement else [],
                    "score": s.score,
                    "priority": (
                        s.priority.value if isinstance(s.priority, SuggestionPriority) else str(s.priority)
                    ),
                    "error_type": s.error_type,
                    "message": s.message,
                }
            )

        return {
            "ok": True,
            "char_count": len(text),
            "suggestions": suggestions_list,
        }


__all__ = ["SuggestionFusionEngine"]
