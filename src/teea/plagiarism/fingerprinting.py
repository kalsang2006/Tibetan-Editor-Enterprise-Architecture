"""Document fingerprint generation via Robust Winnowing (Figure 8).

Algorithm summary
------------------
1. **Normalise and clean** the document text (Unicode NFC + light cleaning).
2. **Generate k-grams**: every contiguous substring of *k* characters.
3. **Hash each k-gram** with a 64-bit rolling hash (Rabin-Karp variant).
4. **Winnow** the hash sequence: in every sliding window of *w* hashes,
   select the minimum hash.  This produces a sparse, position-independent
   fingerprint set.

The combination of *k*-gram hashing and winnowing guarantees that:

* Any matching substring of at least ``k + w - 1`` characters produces at
  least one shared fingerprint (the Robust Winnowing guarantee).
* The fingerprint density is controlled: at most ``1 / w`` of all k-gram
  hashes survive, keeping the index compact.
* The hash of a k-gram is deterministic and platform-independent.

Constants
---------
BASE:
    The base for the rolling hash polynomial.  A large prime (2⁶¹ - 1 =
    2305843009213693951, a Mersenne prime) is used so that multiplications
    fit in 64-bit unsigned arithmetic with negligible collision probability.
    The actual value is 2⁶⁴ to make the hash a pure 64-bit integer.
MOD:
    The 64-bit modulo (2⁶⁴).  The hash naturally wraps on overflow, which
    is fine for plagiarism detection — cryptographic strength is not needed.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from typing import Literal

from teea.plagiarism.models import Fingerprint

#: Rolling hash base (a large odd number with good bit mixing).
_BASE: int = 131

#: 64-bit mask — overflow is intentional for a non-cryptographic hash.
_MOD: int = 2**64


def _kgrams(text: str, k: int) -> list[int]:
    """Return the list of rolling hash values for every k-gram in ``text``.

    Uses a Rabin-Karp rolling hash so that adjacent k-grams share most of
    their computation.  This is O(n) for an n-character document.

    Args:
        text: The text to hash.
        k: Number of characters per k-gram.

    Returns:
        A list of ``max(0, len(text) - k + 1)`` hash values.
    """
    n = len(text)
    if n < k:
        return []

    # Precompute base^(k-1) mod 2^64
    power = 1
    for _ in range(k - 1):
        power = (power * _BASE) % _MOD

    # First k-gram
    h = 0
    for i in range(k):
        h = (h * _BASE + ord(text[i])) % _MOD

    hashes = [h]

    # Rolling window
    for i in range(k, n):
        h = (h - (ord(text[i - k]) * power) % _MOD + _MOD) % _MOD
        h = (h * _BASE + ord(text[i])) % _MOD
        hashes.append(h)

    return hashes


def _winnow(hashes: Sequence[int], window_size: int) -> list[tuple[int, int]]:
    """Robust Winnowing: select minimum hash in each sliding window.

    For every window of ``window_size`` consecutive hashes, the *minimum*
    hash is selected as a fingerprint.  When the minimum appears at the same
    position in two adjacent windows, the duplicate is suppressed — this is
    what keeps the fingerprint density at ``1 / window_size``.

    The implementation follows the "Robust Winnowing" algorithm described
    by Schleimer, Wilkerson, and Aiken (2003).

    Args:
        hashes: The full sequence of k-gram rolling hash values.
        window_size: Number of hashes per winnowing window.

    Returns:
        A list of ``(hash_value, kgram_start)`` pairs, preserving the
        original k-gram position for each selected fingerprint.
    """
    if not hashes or window_size < 2:
        # Without a meaningful window, every hash is a fingerprint.
        return [(h, i) for i, h in enumerate(hashes)]

    n = len(hashes)
    if n < window_size:
        min_h = min(hashes)
        min_idx = hashes.index(min_h)
        return [(min_h, min_idx)]

    fingerprints: list[tuple[int, int]] = []
    min_pos: int = -1  # position of the current window's minimum

    for i in range(n - window_size + 1):
        window = hashes[i : i + window_size]
        minimum = min(window)
        pos = i + window.index(minimum)

        if pos != min_pos:
            fingerprints.append((minimum, pos))
            min_pos = pos

    return fingerprints


def normalize_and_fingerprint(
    text: str,
    *,
    kgram_size: int = 6,
    winnow_window: int = 4,
    normalization_form: Literal["NFC", "NFD", "NFKC", "NFKD"] = "NFC",
) -> tuple[str, frozenset[Fingerprint]]:
    """Normalize text and produce a winnowed fingerprint set.

    This is the top-level entry point for Figure 8's Preprocessing Layer
    and Fingerprint Generation.

    Args:
        text: The document text.
        kgram_size: Characters per k-gram.
        winnow_window: Winnowing window size.
        normalization_form: Unicode normalization form.

    Returns:
        A ``(normalized_text, fingerprint_set)`` pair.  The normalized
        text is what should be stored/compared; the fingerprints are the
        winnowed hash set with position metadata.
    """
    # 1. Normalize
    normalized = unicodedata.normalize(normalization_form, text.strip())
    if not normalized or len(normalized) < kgram_size:
        return normalized, frozenset()

    effective_k = min(kgram_size, max(1, len(normalized)))
    effective_w = min(winnow_window, max(1, len(normalized) - effective_k + 1))

    # 2. K-gram rolling hashes
    hashes = _kgrams(normalized, effective_k)

    if not hashes:
        return normalized, frozenset()

    # 3. Winnow
    winnowed = _winnow(hashes, effective_w)

    # 4. Build fingerprint objects
    fingerprints = frozenset(
        Fingerprint(hash_value=hv, char_start=pos, char_end=pos + effective_k)
        for hv, pos in winnowed
    )

    return normalized, fingerprints


def hash_set(fingerprints: frozenset[Fingerprint]) -> frozenset[int]:
    """Extract just the hash values from a fingerprint set.

    This is a convenience function for index lookups and similarity
    computation, where only the hash values (not the positions) matter.
    """
    return frozenset(fp.hash_value for fp in fingerprints)


__all__ = ["hash_set", "normalize_and_fingerprint"]
