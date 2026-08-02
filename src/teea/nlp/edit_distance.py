"""Grapheme-aware edit distance for Tibetan text.

Plain codepoint-level edit distance mis-scores Tibetan errors.  Tibetan
orthography stacks a base letter with combining marks -- vowel signs
(``U+0F71..U+0F7E``), subjoined consonants (``U+0F90..U+0FBC``) and assorted
marks -- and moving or substituting one of those marks is a *single* spelling
error, not a multi-codepoint rewrite.  Comparing at the codepoint level counts
a vowel-sign move (e.g. ``བདོ`` -> ``བོད``) as two or more edits, which pushes
real errors past an edit-distance cap and out of candidate reach.

This module groups each base letter with the combining marks attached to it
into one *grapheme unit* before computing distance, and computes Damerau-
Levenshtein over those units so adjacent transpositions also cost one edit.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence

#: Combining marks that attach to a Tibetan base letter.  Vowel signs and
#: the subjoined-consonant block are listed explicitly because several of
#: them have canonical combining class 0 (so ``unicodedata.combining``
#: would not identify them); everything else falls back to the Unicode
#: combining-class test.
_TIBETAN_COMBINING_RANGES: tuple[tuple[int, int], ...] = (
    (0x0F71, 0x0F7E),  # vowel signs
    (0x0F80, 0x0F84),  # vocalic vowel signs / marks
    (0x0F86, 0x0F87),  # marks
    (0x0F90, 0x0FBC),  # subjoined consonants
)
_TIBETAN_COMBINING_POINTS: frozenset[int] = frozenset({0x0F35, 0x0F37, 0x0F39})


def _is_combining(char: str) -> bool:
    """Return whether ``char`` is a combining mark that attaches to a base.

    Uses the explicit Tibetan ranges first (several subjoined consonants and
    vowel signs have Unicode combining class 0, so the generic test alone is
    not reliable), then falls back to ``unicodedata.combining`` for anything
    else (Latin diacritics, etc.).
    """
    code = ord(char)
    if code in _TIBETAN_COMBINING_POINTS:
        return True
    for start, end in _TIBETAN_COMBINING_RANGES:
        if start <= code <= end:
            return True
    return unicodedata.combining(char) != 0


def tibetan_graphemes(word: str) -> list[str]:
    """Split ``word`` into grapheme units: a base letter plus its marks.

    Args:
        word: Any Unicode string (usually Tibetan, but ASCII passes through
            unchanged -- each base character forms its own unit).

    Returns:
        The list of grapheme units in surface order.  Each unit is a base
        character with every combining mark that follows it.
    """
    normalized = unicodedata.normalize("NFC", word)
    if not normalized:
        return []
    units: list[str] = []
    current: list[str] = [normalized[0]]
    for char in normalized[1:]:
        if _is_combining(char):
            current.append(char)
        else:
            units.append("".join(current))
            current = [char]
    units.append("".join(current))
    return units


def damerau_levenshtein(seq_a: Sequence[str], seq_b: Sequence[str]) -> int:
    """Damerau-Levenshtein distance between two sequences (OSA variant).

    Optimal-string-alignment distance: substitution, insertion, deletion and
    adjacent transposition each cost one edit.  Operates on arbitrary
    sequences of units (codepoints or graphemes); the Tibetan-aware caller
    feeds it :func:`tibetan_graphemes` output.

    Args:
        seq_a: First sequence of units.
        seq_b: Second sequence of units.

    Returns:
        The minimum edit distance, ``0`` for equal sequences.
    """
    len_a, len_b = len(seq_a), len(seq_b)
    if seq_a == seq_b:
        return 0
    if not len_a:
        return len_b
    if not len_b:
        return len_a

    # Two-row rolling implementation with a transposition check against the
    # row two steps back.
    previous = list(range(len_b + 1))  # distance from empty prefix of a
    current: list[int] = [0] * (len_b + 1)
    two_back: list[int] = [0] * (len_b + 1)

    for i, ca in enumerate(seq_a, start=1):
        current[0] = i
        for j, cb in enumerate(seq_b, start=1):
            cost = 0 if ca == cb else 1
            current[j] = min(
                current[j - 1] + 1,  # insertion
                previous[j] + 1,  # deletion
                previous[j - 1] + cost,  # substitution
            )
            if (
                i > 1
                and j > 1
                and ca == seq_b[j - 2]
                and seq_a[i - 2] == cb
            ):
                current[j] = min(current[j], two_back[j - 2] + cost)
        two_back, previous, current = previous, current, two_back
    return previous[len_b]


def tibetan_damerau(a: str, b: str) -> int:
    """Grapheme-aware Damerau-Levenshtein distance between two strings.

    Both inputs are NFC-normalized and grouped into Tibetan grapheme units
    before the distance is computed, so a vowel-sign move or subjoined
    consonant substitution counts as one edit rather than several.

    Args:
        a: First string.
        b: Second string.

    Returns:
        The distance in grapheme units.
    """
    return damerau_levenshtein(tibetan_graphemes(a), tibetan_graphemes(b))


__all__ = [
    "damerau_levenshtein",
    "tibetan_damerau",
    "tibetan_graphemes",
]
