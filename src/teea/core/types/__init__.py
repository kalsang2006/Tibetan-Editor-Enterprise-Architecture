"""Shared, immutable domain primitives used across TEEA modules.

The most important type here is :class:`TextSpan`. Every layer that needs to
point at a slice of a document — the tokenizer (subword spans), the plugins
(error ranges), the suggestion fusion engine (edit ranges) and, ultimately, the
Office.js add-in (mapping suggestions back to Word ranges) — speaks in spans.

A span carries **both** character offsets and UTF-8 byte offsets:

* Character offsets are what Python string slicing and most editors use.
* Byte offsets are what wire protocols and some native APIs use.

Carrying both from the start avoids lossy, error-prone recomputation later at
the IPC boundary.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

#: Inclusive lower / exclusive upper bounds of the Tibetan Unicode block.
TIBETAN_BLOCK_START = 0x0F00
TIBETAN_BLOCK_END = 0x0FFF

#: The Tibetan tsheg (syllable delimiter) ``་`` (U+0F0B).
TSHEG = "\u0f0b"

#: The Tibetan shad (phrase terminator) ``།`` (U+0F0D).
SHAD = "\u0f0d"

#: Every character that delimits a syllable: the tsheg and its non-breaking
#: variant (U+0F0C).
TSHEG_CHARS = frozenset({"\u0f0b", "\u0f0c"})

#: Every character that terminates a phrase or sentence. This is the canonical
#: home for the shad family, shared by syllable segmentation (Stage 5) and
#: sentence segmentation (Stage 4) so the two stages cannot silently drift
#: apart:
#:
#: * U+0F0D shad -- the ordinary phrase terminator
#: * U+0F0E nyis shad -- double shad, a stronger break
#: * U+0F0F tsheg shad
#: * U+0F10 nyis tsheg shad
#: * U+0F11 rin chen spungs shad
#: * U+0F12 rgya gram shad
#: * U+0F14 gter tsheg
#:
#: U+0F13 is deliberately excluded: it is an annotation mark, not a terminator.
#: This is exactly the set syllable segmentation has always used; it is lifted
#: here verbatim rather than redefined, so behaviour is unchanged.
SHAD_CHARS = frozenset(
    {"\u0f0d", "\u0f0e", "\u0f0f", "\u0f10", "\u0f11", "\u0f12", "\u0f14"}
)

#: Every character that ends a line or a paragraph.
#:
#: Shared by Unicode normalization (Stage 2) and sentence segmentation
#: (Stage 4) so the two cannot disagree about document structure. The breadth is
#: host-driven: the Office.js bridge supplies Word's own text model, in which a
#: paragraph mark is CR (U+000D) and a manual line break (Shift+Enter) is VT
#: (U+000B). If Stage 2 stripped those as control characters, Stage 4 would see
#: one runaway sentence per document.
#:
#: The legacy information separators (U+001C-U+001E) are deliberately excluded:
#: they carry no meaning in a Word document, so Stage 2 is right to remove them
#: as invalid characters.
LINE_BREAK_CHARS = frozenset(
    {"\n", "\r", "\v", "\f", "\x85", "\u2028", "\u2029"}
)


class TextSpan(BaseModel):
    """An immutable half-open span ``[start, end)`` over a text.

    Attributes:
        char_start: Inclusive character index of the span start.
        char_end: Exclusive character index of the span end.
        byte_start: Inclusive UTF-8 byte index of the span start.
        byte_end: Exclusive UTF-8 byte index of the span end.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    char_start: int
    char_end: int
    byte_start: int
    byte_end: int

    @model_validator(mode="after")
    def _validate_bounds(self) -> TextSpan:
        if self.char_start < 0 or self.byte_start < 0:
            raise ValueError("span offsets must be non-negative")
        if self.char_end < self.char_start:
            raise ValueError("char_end must be >= char_start")
        if self.byte_end < self.byte_start:
            raise ValueError("byte_end must be >= byte_start")
        return self

    @property
    def char_length(self) -> int:
        """Number of characters covered by the span."""
        return self.char_end - self.char_start

    @property
    def byte_length(self) -> int:
        """Number of UTF-8 bytes covered by the span."""
        return self.byte_end - self.byte_start

    @property
    def is_empty(self) -> bool:
        """Whether the span covers zero characters."""
        return self.char_end == self.char_start


def is_tibetan_char(char: str) -> bool:
    """Return whether a single character lies in the Tibetan Unicode block.

    Args:
        char: A single-character string.

    Returns:
        ``True`` if the character's code point is within
        ``[TIBETAN_BLOCK_START, TIBETAN_BLOCK_END]``.

    Raises:
        ValueError: If ``char`` is not exactly one character.
    """
    if len(char) != 1:
        raise ValueError("is_tibetan_char expects a single character")
    return TIBETAN_BLOCK_START <= ord(char) <= TIBETAN_BLOCK_END


def tibetan_ratio(text: str) -> float:
    """Return the fraction of characters in ``text`` in the Tibetan block.

    Whitespace-only or empty input returns ``0.0``.

    Args:
        text: The text to measure.

    Returns:
        A ratio in ``[0.0, 1.0]``.
    """
    if not text:
        return 0.0
    tibetan = sum(1 for ch in text if TIBETAN_BLOCK_START <= ord(ch) <= TIBETAN_BLOCK_END)
    return tibetan / len(text)


def utf8_byte_offsets(text: str) -> list[int]:
    """Return cumulative UTF-8 byte offsets for every character boundary.

    ``result[i]`` is the byte offset at which character ``i`` begins, and
    ``result[len(text)]`` is the total byte length. Precomputing the whole table
    once turns span construction into O(1) lookups instead of repeatedly
    re-encoding prefixes.

    This lives in ``core`` because every stage that emits a
    :class:`TextSpan` needs it, and Tibetan makes the need acute: Tibetan code
    points occupy three UTF-8 bytes each, so character and byte offsets diverge
    from the very first character and cannot be used interchangeably.

    Args:
        text: The text to measure.

    Returns:
        A list of ``len(text) + 1`` cumulative byte offsets.
    """
    offsets = [0] * (len(text) + 1)
    for index, char in enumerate(text):
        offsets[index + 1] = offsets[index] + len(char.encode("utf-8"))
    return offsets


__all__ = [
    "LINE_BREAK_CHARS",
    "SHAD",
    "SHAD_CHARS",
    "TIBETAN_BLOCK_END",
    "TIBETAN_BLOCK_START",
    "TSHEG",
    "TSHEG_CHARS",
    "TextSpan",
    "is_tibetan_char",
    "tibetan_ratio",
    "utf8_byte_offsets",
]