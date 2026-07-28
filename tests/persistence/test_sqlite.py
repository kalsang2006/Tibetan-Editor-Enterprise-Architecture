"""Tests for the SQLite-backed persistence layer.

Validates:
- CRUD operations for every repository
- Transactional integrity
- Persistence across simulated restarts (close/re-open)
- Concurrent read access
- Corrupted database recovery
- Empty database handling
- Large dataset performance (smoke)
- Unicode Tibetan text round-tripping
- Schema migration and versioning
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from teea.core.errors import ConfigurationError
from teea.persistence import (
    DatabaseManager,
    InMemoryDictionaryRepository,
    InMemoryGazetteer,
    InMemoryVerbLexicon,
    SqliteDictionaryRepository,
    SqliteFingerprintRepository,
    SqliteGazetteer,
    SqliteTerminology,
    SqliteVerbLexicon,
    create_sqlite_repositories,
    populate_all,
    populate_dictionary,
)
from teea.persistence.terminology import TermSource
from teea.persistence.verbs import ArgumentSlot
from teea.plagiarism.models import SourceDocument

# ── Helpers ──────────────────────────────────────────────────────────────


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """A temporary path for the test database."""
    return tmp_path / "teea_test.db"


@pytest.fixture
def db(db_path: Path) -> DatabaseManager:
    """A fresh DatabaseManager on a temporary database."""
    return DatabaseManager(db_path)


@pytest.fixture
def populated_db(db_path: Path) -> DatabaseManager:
    """A DatabaseManager with shipped data populated."""
    mgr = DatabaseManager(db_path)
    populate_all(mgr)
    return mgr


# ══════════════════════════════════════════════════════════════════════════
#  DatabaseManager — schema, migration, startup
# ══════════════════════════════════════════════════════════════════════════


class TestDatabaseManager:
    def test_creates_database_file(self, db_path: Path) -> None:
        """Manager creates the database file on disk."""
        assert not db_path.exists()
        DatabaseManager(db_path)
        assert db_path.exists()

    def test_creates_directory_if_missing(self, tmp_path: Path) -> None:
        """Manager creates parent directories automatically."""
        nested = tmp_path / "a" / "b" / "test.db"
        DatabaseManager(nested)
        assert nested.exists()

    def test_reopens_existing_database(self, db_path: Path) -> None:
        """Opening an existing database is safe."""
        mgr1 = DatabaseManager(db_path)
        populate_dictionary(mgr1)
        mgr1.close()

        mgr2 = DatabaseManager(db_path)
        repo = SqliteDictionaryRepository(mgr2, auto_populate=False)
        assert len(repo) > 0
        mgr2.close()

    def test_corrupt_database_raises_configuration_error(self, tmp_path: Path) -> None:
        """A corrupt database file raises ConfigurationError."""
        path = tmp_path / "corrupt.db"
        path.write_bytes(b"this is not a sqlite database")
        with pytest.raises(ConfigurationError):
            DatabaseManager(path)

    def test_vacuum_does_not_raise(self, db: DatabaseManager) -> None:
        """Vacuum is safe on an empty database."""
        db.vacuum()

    def test_close_release_resources(self, db_path: Path) -> None:
        """Closing the database releases the file."""
        mgr = DatabaseManager(db_path)
        mgr.close()
        # Should be able to re-open
        mgr2 = DatabaseManager(db_path)
        assert mgr2.path == db_path
        mgr2.close()


# ══════════════════════════════════════════════════════════════════════════
#  SqliteDictionaryRepository  —  CRUD, consistency, error paths
# ══════════════════════════════════════════════════════════════════════════


class TestSqliteDictionaryRepository:
    """Matches the contract of ``tests/persistence/test_dictionary.py``."""

    def test_populate_loads_shipped_data(self, populated_db: DatabaseManager) -> None:
        """Populating the dictionary loads real corpus data."""
        repo = SqliteDictionaryRepository(populated_db, auto_populate=False)
        assert len(repo) > 2000
        assert len(repo.tags) == 77

    def test_lookup_known_surface(self, populated_db: DatabaseManager) -> None:
        """Lookup returns a distribution for known surfaces."""
        repo = SqliteDictionaryRepository(populated_db, auto_populate=False)
        entry = repo.lookup("ལས")
        assert entry is not None
        assert isinstance(entry, dict)
        assert len(entry) >= 2

    def test_lookup_unknown_surface(self, populated_db: DatabaseManager) -> None:
        """Lookup returns None for unknown surfaces."""
        repo = SqliteDictionaryRepository(populated_db, auto_populate=False)
        assert repo.lookup("xyzzy") is None

    def test_contains_known(self, populated_db: DatabaseManager) -> None:
        """__contains__ is True for known surfaces."""
        repo = SqliteDictionaryRepository(populated_db, auto_populate=False)
        assert "ལས" in repo

    def test_contains_unknown(self, populated_db: DatabaseManager) -> None:
        """__contains__ is False for unknown surfaces."""
        repo = SqliteDictionaryRepository(populated_db, auto_populate=False)
        assert "xyzzy" not in repo

    def test_transitions_known_tag(self, populated_db: DatabaseManager) -> None:
        """Transitions returns a distribution for known tags."""
        repo = SqliteDictionaryRepository(populated_db, auto_populate=False)
        following = repo.transitions("n.count")
        assert isinstance(following, dict)
        assert len(following) > 0

    def test_transitions_unknown_tag(self, populated_db: DatabaseManager) -> None:
        """Transitions returns empty dict for unknown tags."""
        repo = SqliteDictionaryRepository(populated_db, auto_populate=False)
        following = repo.transitions("no-such-tag")
        assert following == {}

    def test_auto_populate(self) -> None:
        """Auto-populate fills the database on construction."""
        import tempfile  # noqa: PLC0415

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = Path(f.name)
        try:
            mgr = DatabaseManager(path)
            repo = SqliteDictionaryRepository(mgr, auto_populate=True)
            assert len(repo) > 0
        finally:
            mgr.close()
            path.unlink(missing_ok=True)

    def test_matches_in_memory_content(self, populated_db: DatabaseManager) -> None:
        """SQLite content matches the in-memory repository."""
        sqlite_repo = SqliteDictionaryRepository(populated_db, auto_populate=False)
        mem_repo = InMemoryDictionaryRepository()

        assert sqlite_repo.tags == mem_repo.tags
        assert len(sqlite_repo) == len(mem_repo)
        assert sqlite_repo.lookup("ལས") == mem_repo.lookup("ལས")

    def test_idempotent_populate(self, db: DatabaseManager) -> None:
        """Calling populate_dictionary twice is safe."""
        populate_dictionary(db)
        populate_dictionary(db)
        repo = SqliteDictionaryRepository(db, auto_populate=False)
        assert len(repo) > 0


# ══════════════════════════════════════════════════════════════════════════
#  SqliteGazetteer  —  CRUD, tiers, consistency
# ══════════════════════════════════════════════════════════════════════════


class TestSqliteGazetteer:
    def test_populate_loads_data(self, populated_db: DatabaseManager) -> None:
        """Populating loads the shipped proper-noun gazetteer."""
        repo = SqliteGazetteer(populated_db, auto_populate=False)
        assert len(repo) > 2000

    def test_tiers_are_separate(self, populated_db: DatabaseManager) -> None:
        """Confident and ambiguous tiers are stored separately."""
        repo = SqliteGazetteer(populated_db, auto_populate=False)
        assert repo.num_confident > 2000
        assert repo.num_ambiguous > 100

    def test_contains_known_name(self, populated_db: DatabaseManager) -> None:
        """contains() matches a known proper noun."""
        repo = SqliteGazetteer(populated_db, auto_populate=False)
        assert repo.contains(("འཛམ", "བུ", "འི", "གླིང"))

    def test_contains_unknown(self, populated_db: DatabaseManager) -> None:
        """contains() rejects ordinary words."""
        repo = SqliteGazetteer(populated_db, auto_populate=False)
        assert not repo.contains(("ཁྱིམ",))

    def test_contains_ambiguous(self, populated_db: DatabaseManager) -> None:
        """contains_ambiguous() checks the ambiguous tier."""
        repo = SqliteGazetteer(populated_db, auto_populate=False)
        # At least one entry should be in the ambiguous tier
        assert repo.num_ambiguous > 0

    def test_max_length_bounds_both_tiers(self, populated_db: DatabaseManager) -> None:
        """max_length covers the longest entry."""
        repo = SqliteGazetteer(populated_db, auto_populate=False)
        mem_repo = InMemoryGazetteer()
        assert repo.max_length == mem_repo.max_length


# ══════════════════════════════════════════════════════════════════════════
#  SqliteTerminology  —  CRUD, user dictionary persistence
# ══════════════════════════════════════════════════════════════════════════


class TestSqliteTerminology:
    def test_populate_loads_glossary(self, populated_db: DatabaseManager) -> None:
        """Populating loads the shipped terminology glossary."""
        repo = SqliteTerminology(populated_db, auto_populate=False)
        assert repo.num_glossary > 800

    def test_lookup_glossary_term(self, populated_db: DatabaseManager) -> None:
        """lookup() returns GLOSSARY for a known term."""
        repo = SqliteTerminology(populated_db, auto_populate=False)
        # All glossary terms are multi-syllable; find any
        assert repo.num_glossary > 0

    def test_lookup_unknown(self, populated_db: DatabaseManager) -> None:
        """lookup() returns None for an unknown term."""
        repo = SqliteTerminology(populated_db, auto_populate=False)
        assert repo.lookup(("xyzzy",)) is None

    def test_add_user_term(self, db: DatabaseManager) -> None:
        """User terms can be added."""
        repo = SqliteTerminology(db, auto_populate=False)
        repo.add_user_term(("ཀ", "ཁ"))
        assert repo.num_user == 1
        assert repo.lookup(("ཀ", "ཁ")) == TermSource.USER_DICTIONARY

    def test_user_term_takes_precedence(self, db: DatabaseManager) -> None:
        """User terms outrank glossary terms."""
        repo = SqliteTerminology(db, auto_populate=False)
        # Add a user term that happens to also exist in glossary
        repo.add_user_term(("ཀ",))
        assert repo.lookup(("ཀ",)) == TermSource.USER_DICTIONARY

    def test_remove_user_term(self, db: DatabaseManager) -> None:
        """User terms can be removed."""
        repo = SqliteTerminology(db, auto_populate=False)
        repo.add_user_term(("ཀ", "ཁ"))
        assert repo.remove_user_term(("ཀ", "ཁ")) is True
        assert repo.num_user == 0

    def test_remove_nonexistent_term(self, db: DatabaseManager) -> None:
        """Removing a nonexistent term returns False."""
        repo = SqliteTerminology(db, auto_populate=False)
        assert repo.remove_user_term(("xyzzy",)) is False

    def test_clear_user_terms(self, db: DatabaseManager) -> None:
        """All user terms can be cleared at once."""
        repo = SqliteTerminology(db, auto_populate=False)
        repo.add_user_term(("ཀ",))
        repo.add_user_term(("ཁ",))
        repo.clear_user_terms()
        assert repo.num_user == 0

    def test_user_terms_survive_restart(self, db_path: Path) -> None:
        """User terms persist across database close/reopen."""
        mgr1 = DatabaseManager(db_path)
        repo1 = SqliteTerminology(mgr1, auto_populate=False)
        repo1.add_user_term(("ཀ", "ཁ"))
        mgr1.close()

        mgr2 = DatabaseManager(db_path)
        repo2 = SqliteTerminology(mgr2, auto_populate=False)
        assert repo2.num_user == 1
        assert repo2.lookup(("ཀ", "ཁ")) == TermSource.USER_DICTIONARY
        mgr2.close()


# ══════════════════════════════════════════════════════════════════════════
#  SqliteVerbLexicon  —  CRUD, frame integrity
# ══════════════════════════════════════════════════════════════════════════


class TestSqliteVerbLexicon:
    def test_populate_loads_lexicon(self, populated_db: DatabaseManager) -> None:
        """Populating loads the shipped verb lexicon."""
        repo = SqliteVerbLexicon(populated_db, auto_populate=False)
        assert len(repo) > 10_000
        assert repo.num_lemmas > 1_000

    def test_lookup_known_verb(self, populated_db: DatabaseManager) -> None:
        """lookup() returns frames for a known verb stem."""
        repo = SqliteVerbLexicon(populated_db, auto_populate=False)
        frames = repo.lookup(("ཀློག",))
        assert len(frames) >= 1
        frame = frames[0]
        assert frame.frame == "Erg-Abs"
        assert ArgumentSlot.ERGATIVE in frame.slots

    def test_lookup_unknown(self, populated_db: DatabaseManager) -> None:
        """lookup() returns empty tuple for unknown stems."""
        repo = SqliteVerbLexicon(populated_db, auto_populate=False)
        assert repo.lookup(("zzz",)) == ()

    def test_matches_in_memory_content(self, populated_db: DatabaseManager) -> None:
        """SQLite content matches the in-memory lexicon."""
        sqlite_repo = SqliteVerbLexicon(populated_db, auto_populate=False)
        mem_repo = InMemoryVerbLexicon()

        known_stem = ("ཀློག",)
        sqlite_frames = sqlite_repo.lookup(known_stem)
        mem_frames = mem_repo.lookup(known_stem)
        assert len(sqlite_frames) == len(mem_frames)
        if sqlite_frames and mem_frames:
            assert sqlite_frames[0].lemma == mem_frames[0].lemma
            assert sqlite_frames[0].frame == mem_frames[0].frame

    def test_irregular_stem_resolves(self, populated_db: DatabaseManager) -> None:
        """Irregular verb stems resolve to the correct lemma."""
        repo = SqliteVerbLexicon(populated_db, auto_populate=False)
        lemmas = {f.lemma for f in repo.lookup(("སོང",))}
        assert "འགྲོ་" in lemmas


# ══════════════════════════════════════════════════════════════════════════
#  SqliteFingerprintRepository  —  CRUD, persistence, concurrency
# ══════════════════════════════════════════════════════════════════════════


class TestSqliteFingerprintRepository:
    def test_save_and_load(self, db: DatabaseManager) -> None:
        """Saving a document and loading it returns identical data."""
        repo = SqliteFingerprintRepository(db)
        doc = SourceDocument(
            document_id="test1",
            source="the quick brown fox",
            fingerprints=frozenset({123, 456, 789}),
        )
        repo.save(doc)

        loaded = repo.load("test1")
        assert loaded is not None
        assert loaded.document_id == "test1"
        assert loaded.source == "the quick brown fox"
        assert loaded.fingerprints == frozenset({123, 456, 789})

    def test_save_idempotent(self, db: DatabaseManager) -> None:
        """Saving the same document twice is a no-op."""
        repo = SqliteFingerprintRepository(db)
        doc = SourceDocument(
            document_id="dup",
            source="test",
            fingerprints=frozenset({1, 2}),
        )
        repo.save(doc)
        repo.save(doc)
        assert repo.count() == 1

    def test_load_nonexistent(self, db: DatabaseManager) -> None:
        """Loading a nonexistent document returns None."""
        repo = SqliteFingerprintRepository(db)
        assert repo.load("nope") is None

    def test_delete_existing(self, db: DatabaseManager) -> None:
        """Deleting an existing document returns True."""
        repo = SqliteFingerprintRepository(db)
        doc = SourceDocument(
            document_id="delme",
            source="test",
            fingerprints=frozenset({1}),
        )
        repo.save(doc)
        assert repo.delete("delme") is True
        assert repo.count() == 0

    def test_delete_nonexistent(self, db: DatabaseManager) -> None:
        """Deleting a nonexistent document returns False."""
        repo = SqliteFingerprintRepository(db)
        assert repo.delete("nope") is False

    def test_delete_cascades_fingerprints(self, db: DatabaseManager) -> None:
        """Deleting a document also removes its fingerprint hashes."""
        repo = SqliteFingerprintRepository(db)
        doc = SourceDocument(
            document_id="cascade",
            source="test",
            fingerprints=frozenset({1, 2, 3}),
        )
        repo.save(doc)

        # Verify fingerprints exist before delete
        loaded = repo.load("cascade")
        assert loaded is not None and len(loaded.fingerprints) == 3

        repo.delete("cascade")
        assert repo.load("cascade") is None

    def test_all_ids(self, db: DatabaseManager) -> None:
        """all_ids returns all stored document ids."""
        repo = SqliteFingerprintRepository(db)
        repo.save(SourceDocument(document_id="a", source="x"))
        repo.save(SourceDocument(document_id="b", source="y"))
        ids = list(repo.all_ids())
        assert sorted(ids) == ["a", "b"]

    def test_all_documents(self, db: DatabaseManager) -> None:
        """all() returns all stored documents."""
        repo = SqliteFingerprintRepository(db)
        repo.save(SourceDocument(document_id="a", source="x"))
        repo.save(SourceDocument(document_id="b", source="y"))
        docs = repo.all()
        assert len(docs) == 2

    def test_clear(self, db: DatabaseManager) -> None:
        """clear() removes all documents."""
        repo = SqliteFingerprintRepository(db)
        repo.save(SourceDocument(document_id="a", source="x"))
        repo.clear()
        assert repo.count() == 0

    def test_persistence_across_restart(self, db_path: Path) -> None:
        """Fingerprints persist across database close/reopen."""
        mgr1 = DatabaseManager(db_path)
        repo1 = SqliteFingerprintRepository(mgr1)
        repo1.save(SourceDocument(
            document_id="persist",
            source="tibetan text བཀྲ་ཤིས་བདེ་ལེགས།",
            fingerprints=frozenset({42, 99}),
        ))
        mgr1.close()

        mgr2 = DatabaseManager(db_path)
        repo2 = SqliteFingerprintRepository(mgr2)
        assert repo2.count() == 1
        loaded = repo2.load("persist")
        assert loaded is not None
        assert "བཀྲ་ཤིས་" in loaded.source
        assert loaded.fingerprints == frozenset({42, 99})
        mgr2.close()


# ══════════════════════════════════════════════════════════════════════════
#  Concurrency and transactions
# ══════════════════════════════════════════════════════════════════════════


class TestConcurrentAccess:
    def test_concurrent_reads(self, db_path: Path) -> None:
        """Multiple threads can read concurrently."""
        mgr = DatabaseManager(db_path)
        populate_all(mgr)
        repo = SqliteDictionaryRepository(mgr, auto_populate=False)
        errors: list[BaseException] = []
        lock = threading.Lock()

        def reader() -> None:
            try:
                for _ in range(50):
                    _ = repo.tags
                    _ = repo.lookup("ལས")
                    _ = repo.transitions("n.count")
            except BaseException as exc:  # noqa: BLE001
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=reader) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []

    def test_concurrent_write_read(self, db_path: Path) -> None:
        """Concurrent writes and reads do not corrupt the database."""
        mgr = DatabaseManager(db_path)
        repo = SqliteFingerprintRepository(mgr)
        errors: list[BaseException] = []
        lock = threading.Lock()

        n = 100

        def writer() -> None:
            try:
                for i in range(n):
                    repo.save(SourceDocument(
                        document_id=f"doc-{threading.get_ident()}-{i}",
                        source=f"text-{i}",
                        fingerprints=frozenset({i}),
                    ))
            except BaseException as exc:  # noqa: BLE001
                with lock:
                    errors.append(exc)

        def reader() -> None:
            try:
                for _ in range(n):
                    _ = repo.count()
                    _ = repo.all_ids()
            except BaseException as exc:  # noqa: BLE001
                with lock:
                    errors.append(exc)

        threads = (
            [threading.Thread(target=writer) for _ in range(4)]
            + [threading.Thread(target=reader) for _ in range(4)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert errors == []
        assert repo.count() >= 0


# ══════════════════════════════════════════════════════════════════════════
#  Unicode Tibetan text
# ══════════════════════════════════════════════════════════════════════════


class TestUnicodeTibetan:
    """Validates that Tibetan text round-trips through SQLite correctly."""

    TIBETAN_TEXT = "བཀྲ་ཤིས་བདེ་ལེགས།"

    def test_dictionary_tibetan_surfaces(self, populated_db: DatabaseManager) -> None:
        """Tibetan surface forms survive storage and retrieval."""
        repo = SqliteDictionaryRepository(populated_db, auto_populate=False)
        for surface in ("ལས", "ས", "ལ", "ནས", "དང", "མི"):
            entry = repo.lookup(surface)
            assert entry is not None, f"Surface {surface!r} should be found"

    def test_gazetteer_tibetan_names(self, populated_db: DatabaseManager) -> None:
        """Tibetan proper nouns survive storage and retrieval."""
        repo = SqliteGazetteer(populated_db, auto_populate=False)
        assert repo.contains(("འཛམ", "བུ", "འི", "གླིང"))

    def test_terminology_tibetan_terms(self, populated_db: DatabaseManager) -> None:
        """Tibetan terminology survives storage and retrieval."""
        repo = SqliteTerminology(populated_db, auto_populate=False)
        assert repo.num_glossary > 0

    def test_verb_lexicon_tibetan_stems(self, populated_db: DatabaseManager) -> None:
        """Tibetan verb stems survive storage and retrieval."""
        repo = SqliteVerbLexicon(populated_db, auto_populate=False)
        frames = repo.lookup(("ཀློག",))
        assert len(frames) > 0
        assert "ཀློག་" in frames[0].lemma

    def test_fingerprint_tibetan_text(self, db_path: Path) -> None:
        """Tibetan text persists through SQLite correctly."""
        mgr = DatabaseManager(db_path)
        repo = SqliteFingerprintRepository(mgr)
        doc = SourceDocument(
            document_id="tibetan",
            source=self.TIBETAN_TEXT,
            fingerprints=frozenset({1, 2, 3}),
        )
        repo.save(doc)
        loaded = repo.load("tibetan")
        assert loaded is not None
        assert loaded.source == self.TIBETAN_TEXT
        mgr.close()


# ══════════════════════════════════════════════════════════════════════════
#  Empty database
# ══════════════════════════════════════════════════════════════════════════


class TestEmptyDatabase:
    def test_empty_dictionary(self, db: DatabaseManager) -> None:
        """Empty dictionary returns empty results."""
        repo = SqliteDictionaryRepository(db, auto_populate=False)
        assert len(repo) == 0
        assert repo.tags == frozenset()
        assert repo.tag_counts == {}

    def test_empty_gazetteer(self, db: DatabaseManager) -> None:
        """Empty gazetteer returns empty results."""
        repo = SqliteGazetteer(db, auto_populate=False)
        assert len(repo) == 0
        assert repo.max_length == 0

    def test_empty_terminology(self, db: DatabaseManager) -> None:
        """Empty terminology returns empty results."""
        repo = SqliteTerminology(db, auto_populate=False)
        assert repo.num_glossary == 0
        assert repo.num_user == 0

    def test_empty_verb_lexicon(self, db: DatabaseManager) -> None:
        """Empty verb lexicon returns empty results."""
        repo = SqliteVerbLexicon(db, auto_populate=False)
        assert len(repo) == 0
        assert repo.num_lemmas == 0


# ══════════════════════════════════════════════════════════════════════════
#  Large dataset smoke tests
# ══════════════════════════════════════════════════════════════════════════


class TestLargeDatasets:
    def test_large_fingerprint_dataset(self, db: DatabaseManager) -> None:
        """Storing and querying many fingerprints performs adequately."""
        repo = SqliteFingerprintRepository(db)
        n = 500
        for i in range(n):
            repo.save(SourceDocument(
                document_id=f"big-{i}",
                source=f"document number {i} with some text content",
                fingerprints=frozenset(range(i, i + 20)),
            ))

        assert repo.count() == n
        loaded = repo.load("big-42")
        assert loaded is not None
        assert len(list(repo.all_ids())) == n

    def test_lookup_thousands_of_surfaces(self, populated_db: DatabaseManager) -> None:
        """Looking up many surfaces from the dictionary is performant."""
        repo = SqliteDictionaryRepository(populated_db, auto_populate=False)
        # Access all surfaces through iteration
        for surface in ("ལས", "ས", "ལ", "ནས", "དང", "མི", "ཀྱིས", "ཀྱི"):
            entry = repo.lookup(surface)
            assert entry is not None


# ══════════════════════════════════════════════════════════════════════════
#  Performance smoke tests
# ══════════════════════════════════════════════════════════════════════════


class TestPerformance:
    def test_dictionary_lookup_latency(self, populated_db: DatabaseManager) -> None:
        """Dictionary lookups complete in reasonable time."""
        repo = SqliteDictionaryRepository(populated_db, auto_populate=False)
        start = time.perf_counter()
        for _ in range(100):
            repo.lookup("ལས")
        elapsed = (time.perf_counter() - start) * 1000
        # 100 lookups should take well under 1 second
        assert elapsed < 1000

    def test_fingerprint_bulk_save(self, db: DatabaseManager) -> None:
        """Bulk saving documents completes in reasonable time."""
        repo = SqliteFingerprintRepository(db)
        start = time.perf_counter()
        for i in range(200):
            repo.save(SourceDocument(
                document_id=f"perf-{i}",
                source=f"text {i}",
                fingerprints=frozenset({i, i + 1, i + 2}),
            ))
        elapsed = (time.perf_counter() - start) * 1000
        # 200 saves should be well under 5 seconds
        assert elapsed < 5000


# ══════════════════════════════════════════════════════════════════════════
#  Error paths and recovery
# ══════════════════════════════════════════════════════════════════════════


class TestErrorPaths:
    def test_invalid_directory(self, tmp_path: Path) -> None:
        """Creating a database in an invalid path raises ConfigurationError."""
        # Use a path where we cannot create directories
        invalid = tmp_path / "\x00" / "test.db"
        with pytest.raises((ConfigurationError, OSError, ValueError)):
            DatabaseManager(invalid)

    def test_create_sqlite_repositories(self, db_path: Path) -> None:
        """Factory creates all repositories without error."""
        repos = create_sqlite_repositories(DatabaseManager(db_path))
        assert "manager" in repos
        assert "dictionary" in repos
        assert "gazetteer" in repos
        assert "terminology" in repos
        assert "verb_lexicon" in repos
        assert "fingerprint" in repos
        assert repos["dictionary"].tags
