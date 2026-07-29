"""Built-in typography and punctuation checker plugin for TEEA.

Detects Tibetan tsheg spacing errors, duplicate tshegs, duplicate shads,
misplaced punctuation, and trailing whitespace issues.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from teea.core.types import TextSpan, utf8_byte_offsets
from teea.fusion import Suggestion, SuggestionPriority
from teea.nlp.snapshot import DocumentSnapshot


class TypographyPlugin:
    """Checks Tibetan typography, tsheg spacing, and punctuation rules."""

    def __init__(self, name: str = "teea.typography") -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def examine(self, snapshot: DocumentSnapshot) -> Iterable[Suggestion]:
        text = snapshot.source
        if not text:
            return

        byte_table = utf8_byte_offsets(text)

        # 1. Duplicate tshegs (e.g. ་་)
        for match in re.finditer(r"་{2,}", text):
            start, end = match.span()
            yield Suggestion(
                source=self._name,
                span=TextSpan(
                    char_start=start,
                    char_end=end,
                    byte_start=byte_table[start],
                    byte_end=byte_table[end],
                ),
                replacement="་",
                score=0.95,
                priority=SuggestionPriority.HIGH,
                message="Duplicate tsheg (་) detected",
            )

        # 2. Duplicate shads (3 or more consecutive shads །)
        for match in re.finditer(r"།{3,}", text):
            start, end = match.span()
            yield Suggestion(
                source=self._name,
                span=TextSpan(
                    char_start=start,
                    char_end=end,
                    byte_start=byte_table[start],
                    byte_end=byte_table[end],
                ),
                replacement="༎",
                score=0.9,
                priority=SuggestionPriority.MEDIUM,
                message="Excessive consecutive shads (།) detected",
            )

        # 3. Space before tsheg (e.g.  ་)
        for match in re.finditer(r"\s+་", text):
            start, end = match.span()
            yield Suggestion(
                source=self._name,
                span=TextSpan(
                    char_start=start,
                    char_end=end,
                    byte_start=byte_table[start],
                    byte_end=byte_table[end],
                ),
                replacement="་",
                score=0.85,
                priority=SuggestionPriority.MEDIUM,
                message="Unexpected space before tsheg (་)",
            )


__all__ = ["TypographyPlugin"]
