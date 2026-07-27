"""Terminology repository, the third facet of Figure 2's Dictionary Repository.

The Deployment Diagram lists the Dictionary Repo artifact as holding "Tibetan
Dictionary" and "Grammar & **Terminology**", and step 6 of the UML Sequence
Diagram has the Language Server perform a "Terminology Lookup" against the
Storage Platform. This module is that lookup.

Two sources, as Figure 5 specifies
----------------------------------
Stage 10 is *"Technical Terms · Buddhist Vocabulary · User Dictionary"*, so the
repository distinguishes two provenances:

* the **shipped glossary**, derived from the authoritative data repository, and
* a **user dictionary** supplied at construction, which a scholar populates with
  their own technical vocabulary.

They are kept apart rather than merged because a consumer needs to know which is
which: a spell checker should never flag a user's own term, and a translator
should render it exactly as the user specified.

Following :mod:`teea.persistence.gazetteer`, entries are stored pre-segmented
into syllables, because Stage 6 emits syllable-level morphemes and the recogniser
matches runs of them.
"""

from __future__ import annotations

import enum
import json
from collections.abc import Iterable, Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, Protocol, runtime_checkable

from teea.core.errors import ConfigurationError

#: Location of the shipped glossary, relative to this module.
DEFAULT_TERMINOLOGY_PATH: Final = Path(__file__).parent / "data" / "terminology.json"


@enum.unique
class TermSource(enum.Enum):
    """Where a recognised term came from."""

    #: The glossary shipped with the package.
    GLOSSARY = "glossary"
    #: A term supplied by the user at construction.
    USER_DICTIONARY = "user_dictionary"


@runtime_checkable
class TerminologyRepository(Protocol):
    """Read-only lookup of known technical terms.

    Implementations must be safe to share across threads for read-only use.
    """

    @property
    def max_length(self) -> int:
        """Longest term, in syllables, bounding a matcher's lookahead."""
        ...

    def lookup(self, syllables: Sequence[str]) -> TermSource | None:
        """Return where this run of syllables is attested, or ``None``.

        The user dictionary takes precedence: a scholar who has defined a term
        has stated the reading they want, and that intent outranks the shipped
        glossary.
        """
        ...

    def __len__(self) -> int:
        """Number of terms across both sources."""
        ...


class InMemoryTerminology:
    """A read-only terminology repository held entirely in memory.

    Satisfies the :class:`TerminologyRepository` protocol. Immutable after
    construction and safe to share across threads.

    Args:
        path: Location of the glossary payload. Defaults to the one shipped with
            the package.
        user_terms: The user dictionary, as surfaces already split into
            syllables. Empty by default, which is the correct out-of-the-box
            state: the user has not defined anything yet.

    Raises:
        ConfigurationError: If the payload is missing, unreadable, or malformed.
    """

    def __init__(
        self,
        path: Path | None = None,
        *,
        user_terms: Iterable[Sequence[str]] = (),
    ) -> None:
        source = path or DEFAULT_TERMINOLOGY_PATH
        payload = self._load(source)

        self._provenance: Mapping[str, Any] = dict(payload.get("provenance", {}))
        self._glossary: frozenset[tuple[str, ...]] = frozenset(
            tuple(entry) for entry in payload["entries"]
        )
        self._user: frozenset[tuple[str, ...]] = frozenset(
            tuple(term) for term in user_terms if tuple(term)
        )
        self._max_length = max((len(term) for term in (self._glossary | self._user)), default=0)

    @staticmethod
    def _load(source: Path) -> dict[str, Any]:
        """Read and structurally validate the payload."""
        try:
            raw = source.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ConfigurationError(
                "Terminology data could not be read.",
                context={"path": str(source)},
                cause=exc,
            ) from exc

        try:
            payload: Any = json.loads(raw)
        except ValueError as exc:
            raise ConfigurationError(
                "Terminology data is not valid JSON.",
                context={"path": str(source)},
                cause=exc,
            ) from exc

        if not isinstance(payload, dict):
            raise ConfigurationError(
                "Terminology data must be a JSON object.",
                context={"path": str(source), "actual_type": type(payload).__name__},
            )
        if "entries" not in payload:
            raise ConfigurationError(
                "Terminology data is missing required sections.",
                context={"path": str(source), "missing": ["entries"]},
            )
        if not isinstance(payload["entries"], list):
            raise ConfigurationError(
                "Terminology entries must be a list.",
                context={"path": str(source)},
            )
        return payload

    @property
    def provenance(self) -> Mapping[str, Any]:
        """Where the glossary came from, and on what criteria."""
        return self._provenance

    @property
    def max_length(self) -> int:
        """Longest term, in syllables."""
        return self._max_length

    @property
    def num_glossary(self) -> int:
        """Terms in the shipped glossary."""
        return len(self._glossary)

    @property
    def num_user(self) -> int:
        """Terms in the user dictionary."""
        return len(self._user)

    def lookup(self, syllables: Sequence[str]) -> TermSource | None:
        """Return where this run is attested, or ``None`` if it is not a term."""
        key = tuple(syllables)
        if key in self._user:
            return TermSource.USER_DICTIONARY
        if key in self._glossary:
            return TermSource.GLOSSARY
        return None

    def __len__(self) -> int:
        """Number of terms across both sources."""
        return len(self._glossary | self._user)


@lru_cache(maxsize=1)
def default_terminology() -> InMemoryTerminology:
    """Return the process-wide shared glossary, loading it once.

    Carries no user dictionary: user terms are per-deployment, so a caller that
    has them constructs its own instance.
    """
    return InMemoryTerminology()


__all__ = [
    "DEFAULT_TERMINOLOGY_PATH",
    "InMemoryTerminology",
    "TermSource",
    "TerminologyRepository",
    "default_terminology",
]
