"""Shared helpers for the Suggestion Fusion Engine suite.

The document is real Tibetan so that character and byte offsets genuinely
diverge -- every Tibetan code point is three UTF-8 bytes, and a fusion engine
that confused the two would still pass against ASCII.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from teea.core.types import TextSpan, utf8_byte_offsets
from teea.fusion import PriorityRankedFusionEngine, Suggestion, SuggestionPriority

#: "bkra shis bde legs" -- 17 characters, 49 UTF-8 bytes.
DOCUMENT = "བཀྲ་ཤིས་བདེ་ལེགས།"

_OFFSETS = utf8_byte_offsets(DOCUMENT)


def span(char_start: int, char_end: int) -> TextSpan:
    """Return a span over :data:`DOCUMENT`, with true byte offsets.

    Offsets beyond the document fall back to a plausible three-bytes-per-
    character estimate, which is what a plugin working from stale coordinates
    would produce -- exactly the input the validator has to reject.
    """
    return TextSpan(
        char_start=char_start,
        char_end=char_end,
        byte_start=_OFFSETS[char_start] if char_start < len(_OFFSETS) else char_start * 3,
        byte_end=_OFFSETS[char_end] if char_end < len(_OFFSETS) else char_end * 3,
    )


def make_suggestion(
    source: str = "spell",
    char_start: int = 0,
    char_end: int = 3,
    replacement: str | None = "ཀཀཀ",
    score: float = 0.9,
    priority: SuggestionPriority = SuggestionPriority.MEDIUM,
    message: str = "",
) -> Suggestion:
    """Build a suggestion over :data:`DOCUMENT` with sensible defaults."""
    return Suggestion(
        source=source,
        span=span(char_start, char_end),
        replacement=replacement,
        score=score,
        priority=priority,
        message=message,
    )


@pytest.fixture
def document() -> str:
    """The document every fusion test works against."""
    return DOCUMENT


@pytest.fixture
def engine() -> PriorityRankedFusionEngine:
    """An engine with default weighting and adjacent-edit consolidation."""
    return PriorityRankedFusionEngine()


@pytest.fixture
def suggestion() -> Callable[..., Suggestion]:
    """Factory for suggestions over the shared document."""
    return make_suggestion
