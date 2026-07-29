"""In-memory Dictionary Repository backed by corpus-derived data.

This is the minimal concrete implementation of
:class:`~teea.persistence.interfaces.DictionaryRepository` required by Stage 7.
It loads a single JSON payload derived from the part-of-speech annotated corpus
in the project's authoritative data repository.

Why in-memory rather than SQLite or LMDB
----------------------------------------
Figure 2 anticipates both engines, but neither is warranted yet. The payload is
roughly 220 KiB and entirely read-only, so an on-disk index would add operational
surface and a startup dependency while removing nothing: every lookup is already
a dictionary hit. When the document store and fingerprint index arrive and the
storage engines exist for other reasons, a repository backed by them satisfies
the same protocol and substitutes without touching the Language Server.

Provenance is carried in the payload and exposed through :attr:`provenance`, so a
deployed daemon can report which corpus its grammatical statistics came from.
That matters for an offline product where the data cannot simply be re-fetched
and inspected.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

from teea.core.errors import ConfigurationError

#: Location of the shipped model, relative to this module.
DEFAULT_DATA_PATH: Final = Path(__file__).parent / "data" / "pos_model.json"

#: Marker used for the position before the first token of a sentence.
SENTENCE_START: Final = "<s>"


class InMemoryDictionaryRepository:
    """A read-only Dictionary Repository held entirely in memory.

    Satisfies the :class:`~teea.persistence.interfaces.DictionaryRepository`
    protocol. Instances are immutable after construction and safe to share
    across threads.

    Args:
        path: Location of the JSON payload. Defaults to the model shipped with
            the package.

    Raises:
        ConfigurationError: If the payload is missing, unreadable, or does not
            contain the expected sections. Failing here is deliberate: a daemon
            that starts with no grammatical knowledge would produce silently
            worthless analyses.
    """

    def __init__(self, path: Path | None = None) -> None:
        source = path or DEFAULT_DATA_PATH
        payload = self._load(source)

        self._provenance: Mapping[str, Any] = dict(payload.get("provenance", {}))
        self._tag_counts: Mapping[str, int] = dict(payload["tag_counts"])
        self._emissions: Mapping[str, Mapping[str, int]] = {
            surface: dict(counts) for surface, counts in payload["emissions"].items()
        }
        self._transitions: Mapping[str, Mapping[str, int]] = {
            tag: dict(counts) for tag, counts in payload["transitions"].items()
        }
        self._tags = frozenset(payload["tags"])

    @staticmethod
    def _load(source: Path) -> dict[str, Any]:
        """Read and structurally validate the payload."""
        # UnicodeDecodeError is a ValueError, not an OSError, so a corrupt or
        # truncated payload would otherwise escape as an untyped failure that no
        # caller is told to catch.
        try:
            raw = source.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ConfigurationError(
                "Dictionary Repository data could not be read.",
                context={"path": str(source)},
                cause=exc,
            ) from exc

        try:
            payload: Any = json.loads(raw)
        except ValueError as exc:
            raise ConfigurationError(
                "Dictionary Repository data is not valid JSON.",
                context={"path": str(source)},
                cause=exc,
            ) from exc

        # Valid JSON need not be an object. A bare scalar reaches the membership
        # check below and raises TypeError from deep inside the loader instead of
        # the documented ConfigurationError.
        if not isinstance(payload, dict):
            raise ConfigurationError(
                "Dictionary Repository data must be a JSON object.",
                context={"path": str(source), "actual_type": type(payload).__name__},
            )

        missing = {"tags", "tag_counts", "emissions", "transitions"} - set(payload)
        if missing:
            raise ConfigurationError(
                "Dictionary Repository data is missing required sections.",
                context={"path": str(source), "missing": sorted(missing)},
            )
        return payload

    # -- Introspection ------------------------------------------------------
    @property
    def provenance(self) -> Mapping[str, Any]:
        """Where the grammatical statistics came from."""
        return self._provenance

    @property
    def tags(self) -> frozenset[str]:
        """Every part-of-speech tag known to the repository."""
        return self._tags

    @property
    def tag_counts(self) -> Mapping[str, int]:
        """How often each tag occurs in the reference corpus."""
        return self._tag_counts

    @property
    def vocabulary(self) -> frozenset[str]:
        """Every distinct surface form known to the lexicon."""
        return frozenset(self._emissions.keys())

    @property
    def vocabulary_size(self) -> int:
        """Number of distinct surface forms in the lexicon."""
        return len(self._emissions)

    # -- Lookups -------------------------------------------------------------
    def lookup(self, surface: str) -> Mapping[str, int] | None:
        """Return the tag distribution for ``surface``, or ``None`` if unknown."""
        return self._emissions.get(surface)

    def transitions(self, tag: str) -> Mapping[str, int]:
        """Return the distribution of tags observed after ``tag``."""
        return self._transitions.get(tag, {})

    def __contains__(self, surface: str) -> bool:
        """Whether ``surface`` is present in the lexicon."""
        return surface in self._emissions

    def __len__(self) -> int:
        """Number of distinct surface forms in the lexicon."""
        return len(self._emissions)


@lru_cache(maxsize=1)
def default_dictionary() -> InMemoryDictionaryRepository:
    """Return the process-wide shared repository, loading it once.

    Parsing the payload costs real time, and every Language Server request needs
    the same read-only data, so it is loaded lazily and cached rather than
    rebuilt per request or eagerly at import.
    """
    return InMemoryDictionaryRepository()


__all__ = [
    "DEFAULT_DATA_PATH",
    "SENTENCE_START",
    "InMemoryDictionaryRepository",
    "default_dictionary",
]
