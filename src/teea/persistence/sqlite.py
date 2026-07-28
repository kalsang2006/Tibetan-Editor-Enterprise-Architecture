"""SQLite-backed persistence for TEEA.

Provides SQLite implementations of every repository protocol defined in
:mod:`teea.persistence.interfaces`, :mod:`teea.persistence.gazetteer`,
:mod:`teea.persistence.terminology`, :mod:`teea.persistence.verbs`, and
:mod:`teea.persistence.fingerprints`.

Architecture
------------
* :class:`DatabaseManager` -- owns the connection, schema creation and
  migration, and thread safety. Every SQLite-backed repository takes a
  shared manager, so one database serves all facets.
* :class:`SqliteDictionaryRepository` -- :class:`DictionaryRepository` over
  SQLite. Populated from the shipped JSON payload on first launch.
* :class:`SqliteGazetteer` -- :class:`GazetteerRepository` over SQLite.
* :class:`SqliteTerminology` -- :class:`TerminologyRepository` over SQLite,
  with user-dictionary persistence.
* :class:`SqliteVerbLexicon` -- :class:`VerbLexiconRepository` over SQLite.
* :class:`SqliteFingerprintRepository` -- :class:`FingerprintRepository`
  over SQLite, for durable fingerprint storage.

Thread safety
-------------
The ``DatabaseManager`` uses WAL journal mode and a reentrant lock so that
multiple threads can read concurrently while writes are serialised.  Every
repository is safe to share across threads for read-only use; writes are
serialised through the manager's lock.

Lifecycle
---------
1. Create a ``DatabaseManager(path)``.  The manager creates or opens the
   database, applies any pending migrations, and returns.
2. Create repositories by passing the manager to their constructors.
3. For the shipped-data repositories, call the factory function once to
   populate the database from JSON (e.g. ``populate_dictionary()``).
4. Use the repositories as you would the in-memory versions.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from teea.core.errors import ConfigurationError

#: Current schema version.  Bump this when you add a migration.
_SCHEMA_VERSION: Final = 1

#: Default database directory (platform-aware).
if os.name == "nt":
    _DEFAULT_DB_DIR = Path(os.environ.get("APPDATA", "~/.teea")) / "teea"
else:
    _DEFAULT_DB_DIR = Path.home() / ".teea"

_DEFAULT_DB_PATH: Final = _DEFAULT_DB_DIR / "teea.db"

#: The marker used for the position before the first token of a sentence.
SENTENCE_START: Final = "<s>"


# ══════════════════════════════════════════════════════════════════════════
#  Database manager  —  connection, schema, migration, thread safety
# ══════════════════════════════════════════════════════════════════════════


class DatabaseManager:
    """Manages the SQLite connection, schema, and migration lifecycle.

    Args:
        path: Path to the SQLite database file.  Created if it does not
            exist.  Defaults to ``~/.teea/teea.db`` (or ``%APPDATA%/teea/``
            on Windows).

    Raises:
        ConfigurationError: If the database cannot be opened or the schema
            version is newer than what this code knows about.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _DEFAULT_DB_PATH
        self._lock = threading.RLock()

        # Ensure the directory exists
        self._path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # check_same_thread=False lets us share the connection across
            # threads; the lock serialises writes.
            self._conn = sqlite3.connect(
                str(self._path),
                check_same_thread=False,
                timeout=5.0,
            )
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.execute("PRAGMA busy_timeout=5000")
        except sqlite3.Error as exc:
            raise ConfigurationError(
                "Could not open the TEEA database.",
                context={"path": str(self._path), "error": str(exc)},
                cause=exc,
            ) from exc

        self._create_schema()
        self._migrate()

    @property
    def path(self) -> Path:
        """The path to the database file."""
        return self._path

    @property
    def connection(self) -> sqlite3.Connection:
        """The underlying SQLite connection."""
        return self._conn

    # -- Schema -----------------------------------------------------------

    def _create_schema(self) -> None:
        """Create all tables if they do not exist.

        Always runs ``CREATE TABLE IF NOT EXISTS`` so that a database with
        an existing schema version but missing tables (e.g. from a crash
        during initial creation) is fully recovered.
        """
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS dictionary_tags (
                    tag TEXT NOT NULL PRIMARY KEY
                );

                CREATE TABLE IF NOT EXISTS dictionary_tag_counts (
                    tag TEXT NOT NULL PRIMARY KEY,
                    count INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS dictionary_entries (
                    surface TEXT NOT NULL PRIMARY KEY,
                    tag_distribution TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS dictionary_transitions (
                    from_tag TEXT NOT NULL,
                    to_tag TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (from_tag, to_tag)
                );

                CREATE INDEX IF NOT EXISTS idx_dict_trans_from
                    ON dictionary_transitions(from_tag);

                CREATE TABLE IF NOT EXISTS gazetteer_entries (
                    syllables TEXT NOT NULL PRIMARY KEY
                );

                CREATE TABLE IF NOT EXISTS gazetteer_ambiguous (
                    syllables TEXT NOT NULL PRIMARY KEY
                );

                CREATE TABLE IF NOT EXISTS terminology_glossary (
                    syllables TEXT NOT NULL PRIMARY KEY
                );

                CREATE TABLE IF NOT EXISTS terminology_user (
                    syllables TEXT NOT NULL PRIMARY KEY
                );

                CREATE TABLE IF NOT EXISTS verb_frames (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lemma TEXT NOT NULL,
                    frame TEXT NOT NULL DEFAULT '',
                    slots TEXT NOT NULL DEFAULT '[]',
                    transitivity TEXT NOT NULL DEFAULT 'unknown',
                    volition TEXT NOT NULL DEFAULT 'unknown'
                );

                CREATE TABLE IF NOT EXISTS verb_surfaces (
                    syllables TEXT NOT NULL,
                    frame_id INTEGER NOT NULL,
                    PRIMARY KEY (syllables, frame_id),
                    FOREIGN KEY (frame_id) REFERENCES verb_frames(id)
                );

                CREATE INDEX IF NOT EXISTS idx_verb_surfaces_syllables
                    ON verb_surfaces(syllables);

                CREATE TABLE IF NOT EXISTS fingerprint_documents (
                    document_id TEXT NOT NULL PRIMARY KEY,
                    source TEXT NOT NULL,
                    fingerprint_count INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS fingerprint_hashes (
                    hash_value INTEGER NOT NULL,
                    document_id TEXT NOT NULL,
                    PRIMARY KEY (hash_value, document_id),
                    FOREIGN KEY (document_id)
                        REFERENCES fingerprint_documents(document_id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_fp_hashes_hash
                    ON fingerprint_hashes(hash_value);

                CREATE INDEX IF NOT EXISTS idx_fp_hashes_doc
                    ON fingerprint_hashes(document_id);
            """)

            cur = self._conn.execute("PRAGMA user_version")
            (current_version,) = cur.fetchone()
            if current_version < _SCHEMA_VERSION:
                self._conn.execute(
                    f"PRAGMA user_version = {_SCHEMA_VERSION}"
                )

    # -- Migration ---------------------------------------------------------

    def _migrate(self) -> None:
        """Apply any pending database migrations.

        Each migration is a function that takes ``(conn, lock)`` and advances
        the schema from version N to N+1.  The function must be safe to call
        multiple times (it should check whether its change was already applied).
        """
        cur = self._conn.execute("PRAGMA user_version")
        (current_version,) = cur.fetchone()

        migrations: list[Any] = [
            # Version 0 → 1 is handled by _create_schema above.
        ]

        for version, migrate_fn in enumerate(migrations, start=1):
            if current_version < version:
                with self._lock:
                    migrate_fn(self._conn)
                    self._conn.execute(f"PRAGMA user_version = {version}")

    # -- Utilities ---------------------------------------------------------

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            self._conn.commit()
            self._conn.close()

    def vacuum(self) -> None:
        """Reclaim unused space.  Call during maintenance windows."""
        with self._lock:
            self._conn.execute("VACUUM")


# ══════════════════════════════════════════════════════════════════════════
#  Populate helpers  —  load shipped JSON payloads into SQLite
# ══════════════════════════════════════════════════════════════════════════


def populate_dictionary(db: DatabaseManager) -> None:
    """Load the shipped dictionary JSON payload into SQLite.

    Idempotent: only inserts rows that are not yet present.
    """
    # Local imports to avoid circular dependencies at module level.
    from teea.persistence.dictionary import (  # noqa: PLC0415, I001
        SENTENCE_START as SS,
        InMemoryDictionaryRepository,
    )

    with db._lock:
        cur = db._conn.execute("SELECT COUNT(*) FROM dictionary_tags")
        (count,) = cur.fetchone()
        if count > 0:
            return

        repo = InMemoryDictionaryRepository()

        db._conn.execute("BEGIN")
        try:
            for tag in repo.tags:
                db._conn.execute(
                    "INSERT OR IGNORE INTO dictionary_tags (tag) VALUES (?)",
                    (tag,),
                )
            for tag, tcount in repo.tag_counts.items():
                db._conn.execute(
                    "INSERT OR REPLACE INTO dictionary_tag_counts "
                    "(tag, count) VALUES (?, ?)",
                    (tag, tcount),
                )

            for surface, distro in repo._emissions.items():
                distro_json = json.dumps(distro, ensure_ascii=False)
                db._conn.execute(
                    "INSERT OR IGNORE INTO dictionary_entries "
                    "(surface, tag_distribution) VALUES (?, ?)",
                    (surface, distro_json),
                )

            # Transitions for both tags and SENTENCE_START
            all_tags = [*list(repo.tags), SS]
            for from_tag in all_tags:
                following = repo.transitions(from_tag)
                for to_tag, tcount in following.items():
                    db._conn.execute(
                        "INSERT OR IGNORE INTO dictionary_transitions "
                        "(from_tag, to_tag, count) VALUES (?, ?, ?)",
                        (from_tag, to_tag, tcount),
                    )

            db._conn.execute("COMMIT")
        except BaseException:
            db._conn.execute("ROLLBACK")
            raise


def populate_gazetteer(db: DatabaseManager) -> None:
    """Load the shipped gazetteer JSON payload into SQLite.

    Idempotent: only inserts rows that are not yet present.
    """
    from teea.persistence.gazetteer import InMemoryGazetteer  # noqa: PLC0415

    with db._lock:
        cur = db._conn.execute("SELECT COUNT(*) FROM gazetteer_entries")
        (count,) = cur.fetchone()
        if count > 0:
            return

        repo = InMemoryGazetteer()
        db._conn.execute("BEGIN")
        try:
            for entry in repo._entries:
                db._conn.execute(
                    "INSERT OR IGNORE INTO gazetteer_entries (syllables) VALUES (?)",
                    (json.dumps(list(entry), ensure_ascii=False),),
                )
            for entry in repo._ambiguous:
                db._conn.execute(
                    "INSERT OR IGNORE INTO gazetteer_ambiguous (syllables) VALUES (?)",
                    (json.dumps(list(entry), ensure_ascii=False),),
                )
            db._conn.execute("COMMIT")
        except BaseException:
            db._conn.execute("ROLLBACK")
            raise


def populate_terminology(db: DatabaseManager) -> None:
    """Load the shipped terminology glossary into SQLite.

    Idempotent: only inserts rows that are not yet present.
    """
    from teea.persistence.terminology import InMemoryTerminology  # noqa: PLC0415

    with db._lock:
        cur = db._conn.execute("SELECT COUNT(*) FROM terminology_glossary")
        (count,) = cur.fetchone()
        if count > 0:
            return

        repo = InMemoryTerminology()
        db._conn.execute("BEGIN")
        try:
            for entry in repo._glossary:
                db._conn.execute(
                    "INSERT OR IGNORE INTO terminology_glossary (syllables) VALUES (?)",
                    (json.dumps(list(entry), ensure_ascii=False),),
                )
            db._conn.execute("COMMIT")
        except BaseException:
            db._conn.execute("ROLLBACK")
            raise


def populate_verb_lexicon(db: DatabaseManager) -> None:
    """Load the shipped verb lexicon JSON payload into SQLite.

    Idempotent: only inserts rows that are not yet present.
    """
    from teea.persistence.verbs import InMemoryVerbLexicon  # noqa: PLC0415

    with db._lock:
        cur = db._conn.execute("SELECT COUNT(*) FROM verb_frames")
        (count,) = cur.fetchone()
        if count > 0:
            return

        repo = InMemoryVerbLexicon()

        # Build a unique index of frames by content identity.
        # Each VerbFrame from the in-memory store is assigned a SQLite row id.
        # We use a dict keyed by (lemma, frame, slots, transitivity, volition)
        # to deduplicate frames that happen to be identical.
        seen_frames: dict[tuple[Any, ...], int] = {}
        surface_links: list[tuple[tuple[str, ...], int]] = []

        for syllables, frames in repo._surfaces.items():
            for vf in frames:
                key = (
                    vf.lemma,
                    vf.frame,
                    tuple(sorted(s.value for s in vf.slots)),
                    vf.transitivity.value,
                    vf.volition.value,
                )
                if key not in seen_frames:
                    fid = len(seen_frames) + 1
                    seen_frames[key] = fid
                else:
                    fid = seen_frames[key]
                surface_links.append((syllables, fid))

        db._conn.execute("BEGIN")
        try:
            for (lemma, frame, slots_tuple, trans, vol), fid in seen_frames.items():
                slots_json = json.dumps(list(slots_tuple), ensure_ascii=False)
                db._conn.execute(
                    "INSERT OR IGNORE INTO verb_frames "
                    "(id, lemma, frame, slots, transitivity, volition) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (fid, lemma, frame, slots_json, trans, vol),
                )

            for syllables, fid in surface_links:
                syllables_json = json.dumps(list(syllables), ensure_ascii=False)
                db._conn.execute(
                    "INSERT OR IGNORE INTO verb_surfaces "
                    "(syllables, frame_id) VALUES (?, ?)",
                    (syllables_json, fid),
                )

            db._conn.execute("COMMIT")
        except BaseException:
            db._conn.execute("ROLLBACK")
            raise


def populate_all(db: DatabaseManager) -> None:
    """Populate all shipped-data tables from the JSON payloads."""
    populate_dictionary(db)
    populate_gazetteer(db)
    populate_terminology(db)
    populate_verb_lexicon(db)


# ══════════════════════════════════════════════════════════════════════════
#  Helper: parse a VerbFrame from a SQLite row
# ══════════════════════════════════════════════════════════════════════════


def _row_to_verb_frame(
    lemma: str,
    frame: str,
    slots_json: str,
    trans: str,
    vol: str,
) -> Any:
    """Convert SQLite row columns to a VerbFrame instance."""
    from teea.persistence.verbs import (  # noqa: PLC0415
        ArgumentSlot,
        Transitivity,
        VerbFrame,
        Volition,
    )

    try:
        slot_list = json.loads(slots_json) if slots_json else []
        slots = frozenset(ArgumentSlot(s) for s in slot_list)
    except (ValueError, TypeError):
        slots = frozenset()

    try:
        transitivity = Transitivity(trans) if trans else Transitivity.UNKNOWN
    except ValueError:
        transitivity = Transitivity.UNKNOWN

    try:
        volition = Volition(vol) if vol else Volition.UNKNOWN
    except ValueError:
        volition = Volition.UNKNOWN

    return VerbFrame(
        lemma=lemma,
        frame=frame,
        slots=slots,
        transitivity=transitivity,
        volition=volition,
    )


# ══════════════════════════════════════════════════════════════════════════
#  SqliteDictionaryRepository
# ══════════════════════════════════════════════════════════════════════════


class SqliteDictionaryRepository:
    """A :class:`~teea.persistence.interfaces.DictionaryRepository` over SQLite.

    Args:
        db: The database manager.
        auto_populate: Whether to load the shipped JSON data into the database
            if the tables are empty.  Defaults to ``True``.

    Raises:
        ConfigurationError: If the database is corrupt or the schema is
            incompatible.
    """

    def __init__(self, db: DatabaseManager, *, auto_populate: bool = True) -> None:
        self._db = db

        if auto_populate:
            populate_dictionary(db)

        self._validate()

    def _validate(self) -> None:
        """Check that the dictionary tables are present and readable.

        Skips validation when auto_populate=False (caller may be testing
        with an empty database).
        """
        try:
            with self._db._lock:
                cur = self._db._conn.execute(
                    "SELECT COUNT(*) FROM dictionary_tags"
                )
                (tag_count,) = cur.fetchone()
                if tag_count == 0:
                    return  # Empty database, not an error
        except sqlite3.Error as exc:
            raise ConfigurationError(
                "Dictionary database is corrupt or unreadable.",
                context={"error": str(exc), "path": str(self._db.path)},
                cause=exc,
            ) from exc

    @property
    def tags(self) -> frozenset[str]:
        """Every part-of-speech tag known to the repository."""
        with self._db._lock:
            cur = self._db._conn.execute(
                "SELECT tag FROM dictionary_tags ORDER BY tag"
            )
            return frozenset(row[0] for row in cur.fetchall())

    @property
    def tag_counts(self) -> Mapping[str, int]:
        """How often each tag occurs in the reference corpus."""
        with self._db._lock:
            cur = self._db._conn.execute(
                "SELECT tag, count FROM dictionary_tag_counts ORDER BY tag"
            )
            return dict(cur.fetchall())

    def lookup(self, surface: str) -> Mapping[str, int] | None:
        """Return the tag distribution for a surface form, or ``None``."""
        with self._db._lock:
            cur = self._db._conn.execute(
                "SELECT tag_distribution FROM dictionary_entries "
                "WHERE surface = ?",
                (surface,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            try:
                return dict(json.loads(row[0]))
            except (ValueError, TypeError):
                return None

    def transitions(self, tag: str) -> Mapping[str, int]:
        """Return the distribution of tags observed after ``tag``."""
        with self._db._lock:
            cur = self._db._conn.execute(
                "SELECT to_tag, count FROM dictionary_transitions "
                "WHERE from_tag = ? ORDER BY to_tag",
                (tag,),
            )
            return dict(cur.fetchall())

    def __contains__(self, surface: str) -> bool:
        """Whether ``surface`` is present in the lexicon."""
        with self._db._lock:
            cur = self._db._conn.execute(
                "SELECT 1 FROM dictionary_entries WHERE surface = ?",
                (surface,),
            )
            return cur.fetchone() is not None

    def __len__(self) -> int:
        """Number of distinct surface forms in the lexicon."""
        with self._db._lock:
            cur = self._db._conn.execute(
                "SELECT COUNT(*) FROM dictionary_entries"
            )
            (count,) = cur.fetchone()
            return int(count)

    @property
    def vocabulary_size(self) -> int:
        """Number of distinct surface forms in the lexicon."""
        return len(self)


# ══════════════════════════════════════════════════════════════════════════
#  SqliteGazetteer
# ══════════════════════════════════════════════════════════════════════════


class SqliteGazetteer:
    """A :class:`~teea.persistence.gazetteer.GazetteerRepository` over SQLite.

    Args:
        db: The database manager.
        auto_populate: Whether to load the shipped JSON data if the tables
            are empty.  Defaults to ``True``.
    """

    def __init__(self, db: DatabaseManager, *, auto_populate: bool = True) -> None:
        self._db = db
        if auto_populate:
            populate_gazetteer(db)

    @property
    def max_length(self) -> int:
        """Longest entry, in syllables."""
        with self._db._lock:
            cur = self._db._conn.execute(
                "SELECT COALESCE(MAX(json_array_length(syllables)), 0) "
                "FROM ("
                "  SELECT syllables FROM gazetteer_entries "
                "  UNION ALL "
                "  SELECT syllables FROM gazetteer_ambiguous"
                ")"
            )
            (length,) = cur.fetchone()
            return int(length) if length is not None else 0

    def contains(self, syllables: Sequence[str]) -> bool:
        """Whether this run is an attested proper noun."""
        key = json.dumps(list(syllables), ensure_ascii=False)
        with self._db._lock:
            cur = self._db._conn.execute(
                "SELECT 1 FROM gazetteer_entries WHERE syllables = ?",
                (key,),
            )
            return cur.fetchone() is not None

    def contains_ambiguous(self, syllables: Sequence[str]) -> bool:
        """Whether this run is attested but also occurs as an ordinary word."""
        key = json.dumps(list(syllables), ensure_ascii=False)
        with self._db._lock:
            cur = self._db._conn.execute(
                "SELECT 1 FROM gazetteer_ambiguous WHERE syllables = ?",
                (key,),
            )
            return cur.fetchone() is not None

    @property
    def num_confident(self) -> int:
        """Entries that need no corroboration."""
        with self._db._lock:
            cur = self._db._conn.execute(
                "SELECT COUNT(*) FROM gazetteer_entries"
            )
            (count,) = cur.fetchone()
            return int(count)

    @property
    def num_ambiguous(self) -> int:
        """Entries that require independent evidence."""
        with self._db._lock:
            cur = self._db._conn.execute(
                "SELECT COUNT(*) FROM gazetteer_ambiguous"
            )
            (count,) = cur.fetchone()
            return int(count)

    def __len__(self) -> int:
        """Number of entries in both tiers."""
        with self._db._lock:
            cur = self._db._conn.execute(
                "SELECT (SELECT COUNT(*) FROM gazetteer_entries) + "
                "(SELECT COUNT(*) FROM gazetteer_ambiguous)"
            )
            (count,) = cur.fetchone()
            return int(count)


# ══════════════════════════════════════════════════════════════════════════
#  SqliteTerminology
# ══════════════════════════════════════════════════════════════════════════


class SqliteTerminology:
    """A :class:`~teea.persistence.terminology.TerminologyRepository` over SQLite.

    Supports user dictionary persistence: user terms survive restarts.

    Args:
        db: The database manager.
        auto_populate: Whether to load the shipped glossary if the table
            is empty.  Defaults to ``True``.
    """

    def __init__(self, db: DatabaseManager, *, auto_populate: bool = True) -> None:
        self._db = db
        if auto_populate:
            populate_terminology(db)

    @property
    def max_length(self) -> int:
        """Longest term, in syllables."""
        with self._db._lock:
            cur = self._db._conn.execute(
                "SELECT COALESCE(MAX(json_array_length(syllables)), 0) "
                "FROM ("
                "  SELECT syllables FROM terminology_glossary "
                "  UNION ALL "
                "  SELECT syllables FROM terminology_user"
                ")"
            )
            (length,) = cur.fetchone()
            return int(length) if length is not None else 0

    @property
    def num_glossary(self) -> int:
        """Terms in the shipped glossary."""
        with self._db._lock:
            cur = self._db._conn.execute(
                "SELECT COUNT(*) FROM terminology_glossary"
            )
            (count,) = cur.fetchone()
            return int(count)

    @property
    def num_user(self) -> int:
        """Terms in the user dictionary."""
        with self._db._lock:
            cur = self._db._conn.execute(
                "SELECT COUNT(*) FROM terminology_user"
            )
            (count,) = cur.fetchone()
            return int(count)

    def lookup(self, syllables: Sequence[str]) -> Any | None:
        """Return where this run of syllables is attested, or ``None``.

        The user dictionary takes precedence over the shipped glossary.
        """
        from teea.persistence.terminology import TermSource  # noqa: PLC0415

        key = json.dumps(list(syllables), ensure_ascii=False)
        with self._db._lock:
            cur = self._db._conn.execute(
                "SELECT 1 FROM terminology_user WHERE syllables = ?",
                (key,),
            )
            if cur.fetchone() is not None:
                return TermSource.USER_DICTIONARY

            cur = self._db._conn.execute(
                "SELECT 1 FROM terminology_glossary WHERE syllables = ?",
                (key,),
            )
            if cur.fetchone() is not None:
                return TermSource.GLOSSARY

            return None

    def add_user_term(self, syllables: Sequence[str]) -> None:
        """Add a term to the user dictionary.  Idempotent."""
        key = json.dumps(list(syllables), ensure_ascii=False)
        with self._db._lock:
            self._db._conn.execute(
                "INSERT OR IGNORE INTO terminology_user (syllables) VALUES (?)",
                (key,),
            )
            self._db._conn.commit()

    def remove_user_term(self, syllables: Sequence[str]) -> bool:
        """Remove a term from the user dictionary.

        Returns:
            ``True`` if the term was present and was removed.
        """
        key = json.dumps(list(syllables), ensure_ascii=False)
        with self._db._lock:
            cur = self._db._conn.execute(
                "DELETE FROM terminology_user WHERE syllables = ?",
                (key,),
            )
            self._db._conn.commit()
            return cur.rowcount > 0

    def clear_user_terms(self) -> None:
        """Remove every term from the user dictionary."""
        with self._db._lock:
            self._db._conn.execute("DELETE FROM terminology_user")
            self._db._conn.commit()

    def __len__(self) -> int:
        """Number of terms across both sources."""
        with self._db._lock:
            cur = self._db._conn.execute(
                "SELECT (SELECT COUNT(*) FROM terminology_glossary) + "
                "(SELECT COUNT(*) FROM terminology_user)"
            )
            (count,) = cur.fetchone()
            return int(count)


# ══════════════════════════════════════════════════════════════════════════
#  SqliteVerbLexicon
# ══════════════════════════════════════════════════════════════════════════


class SqliteVerbLexicon:
    """A :class:`~teea.persistence.verbs.VerbLexiconRepository` over SQLite.

    Args:
        db: The database manager.
        auto_populate: Whether to load the shipped JSON data if the tables
            are empty.  Defaults to ``True``.
    """

    def __init__(self, db: DatabaseManager, *, auto_populate: bool = True) -> None:
        self._db = db
        if auto_populate:
            populate_verb_lexicon(db)

    @property
    def max_length(self) -> int:
        """Longest surface form, in syllables."""
        with self._db._lock:
            cur = self._db._conn.execute(
                "SELECT COALESCE(MAX(json_array_length(syllables)), 0) "
                "FROM verb_surfaces"
            )
            (length,) = cur.fetchone()
            return int(length) if length is not None else 0

    @property
    def num_lemmas(self) -> int:
        """Number of distinct dictionary entries."""
        with self._db._lock:
            cur = self._db._conn.execute(
                "SELECT COUNT(*) FROM verb_frames"
            )
            (count,) = cur.fetchone()
            return int(count)

    def lookup(self, syllables: Sequence[str]) -> tuple[Any, ...]:
        """Return every lemma this run of syllables can be a stem of."""
        key = json.dumps(list(syllables), ensure_ascii=False)
        with self._db._lock:
            cur = self._db._conn.execute(
                "SELECT vf.lemma, vf.frame, vf.slots, "
                "vf.transitivity, vf.volition "
                "FROM verb_frames vf "
                "JOIN verb_surfaces vs ON vf.id = vs.frame_id "
                "WHERE vs.syllables = ? "
                "ORDER BY vf.id",
                (key,),
            )
            return tuple(
                _row_to_verb_frame(lemma, frame, slots_json, trans, vol)
                for lemma, frame, slots_json, trans, vol in cur.fetchall()
            )

    def __len__(self) -> int:
        """Number of distinct surface forms known to the lexicon."""
        with self._db._lock:
            cur = self._db._conn.execute(
                "SELECT COUNT(DISTINCT syllables) FROM verb_surfaces"
            )
            (count,) = cur.fetchone()
            return int(count)


# ══════════════════════════════════════════════════════════════════════════
#  SqliteFingerprintRepository
# ══════════════════════════════════════════════════════════════════════════


class SqliteFingerprintRepository:
    """A :class:`~teea.persistence.fingerprints.FingerprintRepository` over SQLite.

    Persists fingerprint data durably.  Supports concurrent reads; writes
    are serialised through the database manager's lock.

    Args:
        db: The database manager.
    """

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def save(self, document: Any) -> None:
        """Persist a document and its fingerprints.

        Idempotent: saving the same document twice is a no-op.
        """
        with self._db._lock:
            cur = self._db._conn.execute(
                "SELECT 1 FROM fingerprint_documents WHERE document_id = ?",
                (document.document_id,),
            )
            if cur.fetchone() is not None:
                return

            self._db._conn.execute(
                "INSERT INTO fingerprint_documents "
                "(document_id, source, fingerprint_count) VALUES (?, ?, ?)",
                (
                    document.document_id,
                    document.source,
                    len(document.fingerprints),
                ),
            )

            for h in document.fingerprints:
                self._db._conn.execute(
                    "INSERT OR IGNORE INTO fingerprint_hashes "
                    "(hash_value, document_id) VALUES (?, ?)",
                    (int(h), document.document_id),
                )

            self._db._conn.commit()

    def load(self, document_id: str) -> Any | None:
        """Retrieve a document by id, or ``None`` if not found."""
        from teea.plagiarism.models import SourceDocument  # noqa: PLC0415

        with self._db._lock:
            cur = self._db._conn.execute(
                "SELECT source, fingerprint_count FROM fingerprint_documents "
                "WHERE document_id = ?",
                (document_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None

            source = row[0]

            cur = self._db._conn.execute(
                "SELECT hash_value FROM fingerprint_hashes "
                "WHERE document_id = ? ORDER BY hash_value",
                (document_id,),
            )
            fingerprints = frozenset(int(row[0]) for row in cur.fetchall())

            return SourceDocument(
                document_id=document_id,
                source=source,
                fingerprints=fingerprints,
            )

    def delete(self, document_id: str) -> bool:
        """Remove a document.  Returns ``True`` if it existed.

        Uses CASCADE to remove associated fingerprint hashes.
        """
        with self._db._lock:
            cur = self._db._conn.execute(
                "SELECT 1 FROM fingerprint_documents WHERE document_id = ?",
                (document_id,),
            )
            if cur.fetchone() is None:
                return False

            self._db._conn.execute(
                "DELETE FROM fingerprint_hashes WHERE document_id = ?",
                (document_id,),
            )
            self._db._conn.execute(
                "DELETE FROM fingerprint_documents WHERE document_id = ?",
                (document_id,),
            )
            self._db._conn.commit()
            return True

    def all_ids(self) -> Iterable[str]:
        """Return the ids of every stored document."""
        with self._db._lock:
            cur = self._db._conn.execute(
                "SELECT document_id FROM fingerprint_documents "
                "ORDER BY document_id"
            )
            return tuple(row[0] for row in cur.fetchall())

    def count(self) -> int:
        """Return the number of stored documents."""
        with self._db._lock:
            cur = self._db._conn.execute(
                "SELECT COUNT(*) FROM fingerprint_documents"
            )
            (count,) = cur.fetchone()
            return int(count)

    def all(self) -> Sequence[Any]:
        """Return every stored document."""
        docs: list[Any] = []
        for doc_id in self.all_ids():
            doc = self.load(doc_id)
            if doc is not None:
                docs.append(doc)
        return tuple(docs)

    def clear(self) -> None:
        """Remove all documents from the repository."""
        with self._db._lock:
            self._db._conn.execute("DELETE FROM fingerprint_hashes")
            self._db._conn.execute("DELETE FROM fingerprint_documents")
            self._db._conn.commit()


# ══════════════════════════════════════════════════════════════════════════
#  Convenience factory
# ══════════════════════════════════════════════════════════════════════════


def create_sqlite_repositories(
    db: DatabaseManager | None = None,
    *,
    auto_populate: bool = True,
) -> dict[str, Any]:
    """Create a SQLite-backed database manager and all repositories.

    Args:
        db: An existing database manager, or ``None`` to create a default one.
        auto_populate: Whether to populate shipped data from JSON payloads.

    Returns:
        A dict with keys ``manager``, ``dictionary``, ``gazetteer``,
        ``terminology``, ``verb_lexicon``, ``fingerprint``.
    """
    if db is None:
        db = DatabaseManager()

    if auto_populate:
        populate_all(db)

    return {
        "manager": db,
        "dictionary": SqliteDictionaryRepository(db, auto_populate=False),
        "gazetteer": SqliteGazetteer(db, auto_populate=False),
        "terminology": SqliteTerminology(db, auto_populate=False),
        "verb_lexicon": SqliteVerbLexicon(db, auto_populate=False),
        "fingerprint": SqliteFingerprintRepository(db),
    }


__all__ = [
    "SENTENCE_START",
    "DatabaseManager",
    "SqliteDictionaryRepository",
    "SqliteFingerprintRepository",
    "SqliteGazetteer",
    "SqliteTerminology",
    "SqliteVerbLexicon",
    "create_sqlite_repositories",
    "populate_all",
    "populate_dictionary",
    "populate_gazetteer",
    "populate_terminology",
    "populate_verb_lexicon",
]
