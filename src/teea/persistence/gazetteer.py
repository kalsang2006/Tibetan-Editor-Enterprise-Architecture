"""Proper-noun gazetteer, a second facet of Figure 2's Dictionary Repository.

Figure 2 describes the Dictionary Repository as a "Tibetan lexicon & lemma
store". Stage 7 uses one facet of it -- surface/tag statistics -- through
:class:`~teea.persistence.interfaces.DictionaryRepository`. Stage 9 needs a
different one: the set of surfaces attested as proper nouns.

Why a separate protocol rather than more methods on the existing one
-------------------------------------------------------------------
Interface Segregation. The tagger has no use for a gazetteer and the entity
recogniser has no use for transition statistics, so widening the existing
protocol would force every implementation of it to grow a method half its
consumers ignore -- and would silently break the stub repositories that
currently satisfy it. Two narrow protocols, satisfiable by one store when that
becomes worthwhile, keeps both consumers honest.

The entries are stored pre-segmented into syllables because Stage 6 emits
syllable-level morphemes and the recogniser matches runs of them. Doing the
segmentation once, when the payload is built, keeps it out of the request path.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, Protocol, runtime_checkable

from teea.core.errors import ConfigurationError

#: Location of the shipped gazetteer, relative to this module.
DEFAULT_GAZETTEER_PATH: Final = Path(__file__).parent / "data" / "proper_nouns.json"


@runtime_checkable
class GazetteerRepository(Protocol):
    """Read-only lookup of surfaces attested as proper nouns.

    Implementations must be safe to share across threads for read-only use.
    """

    @property
    def max_length(self) -> int:
        """Longest entry, in syllables.

        A matcher scanning for the longest entry at each position needs this to
        bound its lookahead; without it the bound would be the sentence length.
        """
        ...

    def contains(self, syllables: Sequence[str]) -> bool:
        """Whether this run is an attested proper noun needing no corroboration."""
        ...

    def contains_ambiguous(self, syllables: Sequence[str]) -> bool:
        """Whether this run is attested but also occurs as an ordinary word.

        Separated from :meth:`contains` because firing on these unconditionally
        is the largest source of false positives: a surface may be both a
        personal name and a common noun. A consumer should require independent
        evidence before accepting one.
        """
        ...

    def __len__(self) -> int:
        """Number of entries in both tiers."""
        ...


class InMemoryGazetteer:
    """A read-only gazetteer held entirely in memory.

    Satisfies the :class:`GazetteerRepository` protocol. Immutable after
    construction and safe to share across threads.

    Args:
        path: Location of the JSON payload. Defaults to the gazetteer shipped
            with the package.

    Raises:
        ConfigurationError: If the payload is missing, unreadable, or malformed.
            Failing here is deliberate, matching
            :class:`~teea.persistence.dictionary.InMemoryDictionaryRepository`:
            silently recognising no entities would look like a clean document.
    """

    def __init__(self, path: Path | None = None) -> None:
        source = path or DEFAULT_GAZETTEER_PATH
        payload = self._load(source)

        self._provenance: Mapping[str, Any] = dict(payload.get("provenance", {}))
        self._entries: frozenset[tuple[str, ...]] = frozenset(
            tuple(entry) for entry in payload["entries"]
        )
        self._ambiguous: frozenset[tuple[str, ...]] = frozenset(
            tuple(entry) for entry in payload.get("ambiguous_entries", ())
        )
        self._max_length = max(
            (len(entry) for entry in (self._entries | self._ambiguous)), default=0
        )

    @staticmethod
    def _load(source: Path) -> dict[str, Any]:
        """Read and structurally validate the payload."""
        try:
            raw = source.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ConfigurationError(
                "Gazetteer data could not be read.",
                context={"path": str(source)},
                cause=exc,
            ) from exc

        try:
            payload: Any = json.loads(raw)
        except ValueError as exc:
            raise ConfigurationError(
                "Gazetteer data is not valid JSON.",
                context={"path": str(source)},
                cause=exc,
            ) from exc

        if not isinstance(payload, dict):
            raise ConfigurationError(
                "Gazetteer data must be a JSON object.",
                context={"path": str(source), "actual_type": type(payload).__name__},
            )
        if "entries" not in payload:
            raise ConfigurationError(
                "Gazetteer data is missing required sections.",
                context={"path": str(source), "missing": ["entries"]},
            )
        if not isinstance(payload["entries"], list):
            raise ConfigurationError(
                "Gazetteer entries must be a list.",
                context={"path": str(source)},
            )
        return payload

    @property
    def provenance(self) -> Mapping[str, Any]:
        """Where the entries came from."""
        return self._provenance

    @property
    def max_length(self) -> int:
        """Longest entry, in syllables."""
        return self._max_length

    def contains(self, syllables: Sequence[str]) -> bool:
        """Whether this run is an attested proper noun needing no corroboration."""
        return tuple(syllables) in self._entries

    def contains_ambiguous(self, syllables: Sequence[str]) -> bool:
        """Whether this run is attested but also occurs as an ordinary word."""
        return tuple(syllables) in self._ambiguous

    @property
    def num_confident(self) -> int:
        """Entries that need no corroboration."""
        return len(self._entries)

    @property
    def num_ambiguous(self) -> int:
        """Entries that require independent evidence."""
        return len(self._ambiguous)

    def __len__(self) -> int:
        """Number of entries in both tiers."""
        return len(self._entries) + len(self._ambiguous)


@lru_cache(maxsize=1)
def default_gazetteer() -> InMemoryGazetteer:
    """Return the process-wide shared gazetteer, loading it once."""
    return InMemoryGazetteer()


__all__ = [
    "DEFAULT_GAZETTEER_PATH",
    "GazetteerRepository",
    "InMemoryGazetteer",
    "default_gazetteer",
]
