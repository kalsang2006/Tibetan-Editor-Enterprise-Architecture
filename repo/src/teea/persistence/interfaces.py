"""Persistence layer abstractions for TEEA.

Figure 2 places a **Dictionary Repository** in the Persistence Layer, holding a
"Tibetan lexicon & lemma store" and a "Morphological rules catalog", and the UML
Sequence Diagram has the Language Server perform a Dictionary Lookup against the
Storage Platform at step 6. This module defines that boundary.

Only the abstraction lives here. The Language Server depends on this protocol,
never on a concrete store, so the in-memory implementation shipped today can be
replaced by the SQLite- or LMDB-backed repository Figure 2 anticipates without
any consumer changing. That substitution is the whole point of stating the
interface before the storage engine exists.

Scope note
----------
This is the *minimum* required by Stage 7. The other repositories Figure 2 lists
-- the fingerprint index, the LMDB cache, the SQLite document store -- are
deliberately absent: they belong to features that have not been built, and
speculatively defining their interfaces would be inventing requirements.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable


@runtime_checkable
class DictionaryRepository(Protocol):
    """Read-only access to the Tibetan lexicon and grammatical statistics.

    Implementations must be safe to share across threads for read-only use: the
    daemon analyses many documents concurrently against one repository.

    Counts rather than probabilities are exposed on purpose. Smoothing is a
    modelling decision that belongs to the consumer -- a tagger and a spell
    checker will want different treatments of the same underlying evidence, and
    baking one choice into storage would force it on both.
    """

    @property
    def tags(self) -> frozenset[str]:
        """Every part-of-speech tag known to the repository."""
        ...

    @property
    def tag_counts(self) -> Mapping[str, int]:
        """How often each tag occurs in the reference corpus."""
        ...

    def lookup(self, surface: str) -> Mapping[str, int] | None:
        """Return the tag distribution for a surface form.

        This is the "Tibetan lexicon & lemma store" of Figure 2.

        Args:
            surface: A surface form, without a trailing tsheg.

        Returns:
            A mapping of tag to observed count, or ``None`` when the surface is
            not in the lexicon (an out-of-vocabulary form).
        """
        ...

    def transitions(self, tag: str) -> Mapping[str, int]:
        """Return the distribution of tags observed after ``tag``.

        This is the "Morphological rules catalog" of Figure 2, expressed as
        observed sequence statistics rather than hand-written rules.

        Args:
            tag: The preceding tag, or the sentence-start marker.

        Returns:
            A mapping of following tag to observed count; empty when ``tag`` was
            never seen.
        """
        ...

    def __contains__(self, surface: str) -> bool:
        """Whether ``surface`` is present in the lexicon."""
        ...


__all__ = ["DictionaryRepository"]
