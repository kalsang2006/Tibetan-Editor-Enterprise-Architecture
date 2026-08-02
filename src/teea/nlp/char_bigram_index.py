"""Character-bigram inverted index over a vocabulary.

Candidate generation for spelling correction must not scan the whole
dictionary for every unknown word -- the corpus vocabulary has ~178k
syllables, and a full scan per query is the difference between interactive
latency and a frozen task pane.  This index inverts the vocabulary by its
character bigrams so that candidate retrieval is proportional to the number
of shared bigrams rather than the size of the vocabulary.

The index is *recall-first*: :meth:`CharBigramIndex.query` returns any word
that shares at least one bigram with the query, ranked by how many bigrams
it shares, and the caller is expected to filter and score with a real edit
distance (see :mod:`teea.nlp.edit_distance`).  That makes the index a cheap
pre-filter that widens the candidate net (distance-3 is affordable because
the scan is over a handful of postings lists, not 178k entries), leaving the
exact-distance computation to the caller.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable

_WORD_END = "\u0002"


def _char_bigrams(word: str) -> list[str]:
    """Return the character-bigram keys for ``word``.

    The word-end sentinel is appended before slicing so that a short word
    still yields a distinguishing key (``"ab"`` vs ``"ba"`` share no
    bigrams at all without it, and even ``"ab"`` vs ``"abc"`` would share
    ``"ab"``; the sentinel keeps them distinct).
    """
    padded = word + _WORD_END
    if len(padded) < 2:
        return [padded]
    return [padded[i : i + 2] for i in range(len(padded) - 1)]


class CharBigramIndex:
    """Inverted index from character bigrams to vocabulary words.

    The index is immutable once built and safe to share across threads
    (it holds no mutable state after :meth:`build`).
    """

    def __init__(self, words: Iterable[str] = ()) -> None:
        """Build the index over ``words``.

        Args:
            words: The vocabulary to index.  Words are deduplicated; empty
                and whitespace-only entries are skipped.
        """
        self._postings: dict[str, set[str]] = defaultdict(set)
        self._words: set[str] = set()
        for word in words:
            self.add(word)

    @property
    def size(self) -> int:
        """Number of distinct words indexed."""
        return len(self._words)

    def add(self, word: str) -> None:
        """Add one word to the index (no-op if already present or blank).

        Args:
            word: The vocabulary entry to index.
        """
        word = word.strip()
        if not word or word in self._words:
            return
        for bigram in _char_bigrams(word):
            self._postings[bigram].add(word)
        self._words.add(word)

    def query(self, word: str, max_results: int = 100) -> list[str]:
        """Return candidate words sharing character bigrams with ``word``.

        Candidates are ranked by the number of shared bigrams, descending;
        ties are broken deterministically by surface form.  The query word
        itself is excluded from the results.  Only the top ``max_results``
        candidates are returned.

        Args:
            word: The query surface form (e.g. a misspelled word).
            max_results: Upper bound on the number of candidates returned.

        Returns:
            Vocabulary words that share at least one bigram with ``word``,
            most similar first.
        """
        word = word.strip()
        if not word:
            return []
        counts: Counter[str] = Counter()
        for bigram in _char_bigrams(word):
            for candidate in self._postings.get(bigram, ()):
                if candidate != word:
                    counts[candidate] += 1
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return [candidate for candidate, _count in ordered[:max_results]]

    def __len__(self) -> int:
        """Number of distinct words indexed."""
        return len(self._words)


__all__ = ["CharBigramIndex"]
