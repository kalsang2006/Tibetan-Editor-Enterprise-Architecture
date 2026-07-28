"""TEEA persistence layer.

Figure 1 and Figure 2 place a Storage Platform beneath the runtime layer, holding
the SQLite document store, the LMDB cache, the fingerprint index and the
**Dictionary Repository**. This subpackage provides both in-memory and
SQLite-backed implementations of every repository protocol.

This subpackage depends solely on :mod:`teea.core` and never on
:mod:`teea.nlp`: the language layer reads from storage, not the reverse. That
direction is enforced by ``tests/test_architecture.py``.

Public API:

* :class:`DictionaryRepository` -- surface/tag statistics, used by Stage 7.
* :class:`GazetteerRepository` -- attested proper nouns, used by Stage 9.
* :class:`TerminologyRepository` -- technical terms and the user dictionary,
  used by Stage 10.
* :class:`VerbLexiconRepository` -- verb lemmas and attested argument frames,
  used by Stage 11.
* :class:`FingerprintRepository` -- read/write fingerprint storage for
  plagiarism detection.
* :class:`DatabaseManager` -- SQLite connection, schema, and migration.
* :class:`InMemoryDictionaryRepository`, :class:`InMemoryGazetteer`,
  :class:`InMemoryTerminology`, :class:`InMemoryVerbLexicon` -- the shipped
  in-memory implementations.
* :class:`SqliteDictionaryRepository`, :class:`SqliteGazetteer`,
  :class:`SqliteTerminology`, :class:`SqliteVerbLexicon`,
  :class:`SqliteFingerprintRepository` -- SQLite-backed implementations.
* :func:`default_dictionary`, :func:`default_gazetteer`,
  :func:`default_terminology`, :func:`default_verb_lexicon` -- process-wide
  cached in-memory instances.
* :func:`create_sqlite_repositories` -- factory for all SQLite-backed repos.

All protocols are facets of the single Dictionary Repository Figure 2 places
in the Persistence Layer; they are stated separately so no consumer depends on
another's data (Interface Segregation).
"""

from __future__ import annotations

# ruff: noqa: I001 — the import order is intentional: local project imports
# before third-party, alphabetically by subpackage name.

from teea.persistence.dictionary import (
    DEFAULT_DATA_PATH,
    SENTENCE_START as DICT_SENTENCE_START,
    InMemoryDictionaryRepository,
    default_dictionary,
)
from teea.persistence.gazetteer import (
    DEFAULT_GAZETTEER_PATH,
    GazetteerRepository,
    InMemoryGazetteer,
    default_gazetteer,
)
from teea.persistence.interfaces import DictionaryRepository
from teea.persistence.sqlite import (
    DatabaseManager,
    SqliteDictionaryRepository,
    SqliteFingerprintRepository,
    SqliteGazetteer,
    SqliteTerminology,
    SqliteVerbLexicon,
    create_sqlite_repositories,
    populate_all,
    populate_dictionary,
    populate_gazetteer,
    populate_terminology,
    populate_verb_lexicon,
)
from teea.persistence.terminology import (
    DEFAULT_TERMINOLOGY_PATH,
    InMemoryTerminology,
    TerminologyRepository,
    TermSource,
    default_terminology,
)
from teea.persistence.verbs import (
    DEFAULT_VERB_LEXICON_PATH,
    ArgumentSlot,
    InMemoryVerbLexicon,
    Transitivity,
    VerbFrame,
    VerbLexiconRepository,
    Volition,
    default_verb_lexicon,
)
from teea.persistence.fingerprints import (
    FingerprintRepository,
    InMemoryFingerprintRepository,
)

# Re-export SENTENCE_START for backward compatibility (used by tagger).
SENTENCE_START = DICT_SENTENCE_START

__all__ = [
    "DEFAULT_DATA_PATH",
    "DEFAULT_GAZETTEER_PATH",
    "DEFAULT_TERMINOLOGY_PATH",
    "DEFAULT_VERB_LEXICON_PATH",
    "SENTENCE_START",
    "ArgumentSlot",
    "DatabaseManager",
    "DictionaryRepository",
    "FingerprintRepository",
    "GazetteerRepository",
    "InMemoryDictionaryRepository",
    "InMemoryFingerprintRepository",
    "InMemoryGazetteer",
    "InMemoryTerminology",
    "InMemoryVerbLexicon",
    "SqliteDictionaryRepository",
    "SqliteFingerprintRepository",
    "SqliteGazetteer",
    "SqliteTerminology",
    "SqliteVerbLexicon",
    "TermSource",
    "TerminologyRepository",
    "Transitivity",
    "VerbFrame",
    "VerbLexiconRepository",
    "Volition",
    "create_sqlite_repositories",
    "default_dictionary",
    "default_gazetteer",
    "default_terminology",
    "default_verb_lexicon",
    "populate_all",
    "populate_dictionary",
    "populate_gazetteer",
    "populate_terminology",
    "populate_verb_lexicon",
]
