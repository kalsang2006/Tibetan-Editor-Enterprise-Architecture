"""Tibetan syllable segmentation based on the tsheg delimiter.

Tibetan orthography groups letters into syllables delimited by the *tsheg*
``་`` (U+0F0B; the non-breaking variant U+0F0C is also handled). Phrases are
terminated by the *shad* ``།`` and its variants. This module turns a normalized
string into a sequence of :class:`~teea.nlp.tokenization.models.Syllable`
objects, each carrying a precise character/byte span.

Why this is separate from the SentencePiece tokenizer
-----------------------------------------------------
TiBERT's SentencePiece pieces are statistical subwords; they do **not** align
with orthographic syllables. Yet several downstream features are defined at the
syllable level:

* spell checking (candidate generation over syllables),
* dadrag / affixed-particle handling,
* rule-based diagnostics.

So the platform needs syllable structure as first-class metadata computed
deterministically from the text, independent of and complementary to the
subword tokenization. This module provides exactly that and nothing more.

Scope
-----
This is an orthographic segmenter, not a word tokenizer. Runs of non-Tibetan
characters between delimiters are returned verbatim as their own chunks;
callers that need Tibetan-only syllables can filter using
:func:`~teea.core.types.tibetan_ratio`.
"""

from __future__ import annotations

from teea.core.types import SHAD_CHARS, TSHEG_CHARS, TextSpan
from teea.nlp.tokenization.models import Syllable


def _byte_prefix(text: str) -> list[int]:
    """Return cumulative UTF-8 byte offsets for each character boundary.

    ``result[i]`` is the byte offset of character ``i``; ``result[len(text)]``
    is the total byte length.
    """
    prefix = [0] * (len(text) + 1)
    for index, char in enumerate(text):
        prefix[index + 1] = prefix[index] + len(char.encode("utf-8"))
    return prefix


class SyllableSegmenter:
    """Segments Tibetan text into tsheg-delimited syllables.

    The segmenter is stateless and thread-safe.
    """

    def segment(self, text: str) -> list[Syllable]:
        """Segment ``text`` into syllables.

        Args:
            text: Normalized Tibetan text.

        Returns:
            An ordered list of :class:`Syllable` objects. Punctuation and
            whitespace act as delimiters and are not themselves returned as
            syllables, but the spans of returned syllables remain absolute with
            respect to ``text`` (gaps correspond to delimiters).
        """
        if not text:
            return []

        byte_prefix = _byte_prefix(text)
        syllables: list[Syllable] = []
        start: int | None = None

        def close(end: int, *, trailing_tsheg: bool) -> None:
            nonlocal start
            if start is None:
                return
            syllables.append(
                Syllable(
                    text=text[start:end],
                    span=TextSpan(
                        char_start=start,
                        char_end=end,
                        byte_start=byte_prefix[start],
                        byte_end=byte_prefix[end],
                    ),
                    has_trailing_tsheg=trailing_tsheg,
                )
            )
            start = None

        for index, char in enumerate(text):
            if char in TSHEG_CHARS:
                close(index, trailing_tsheg=True)
            elif char in SHAD_CHARS or char.isspace():
                close(index, trailing_tsheg=False)
            else:
                if start is None:
                    start = index

        # Close any final syllable that runs to the end of the string.
        close(len(text), trailing_tsheg=False)
        return syllables


__all__ = ["SyllableSegmenter"]