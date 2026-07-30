"""Unit tests for the Dictionary Repository (:mod:`teea.persistence`).

Figure 2 puts a **Dictionary Repository** in the Storage Platform and has the
Language Server perform a Dictionary Lookup against it at step 6 of the UML
Sequence Diagram. :mod:`teea.persistence.interfaces` states that boundary and
:mod:`teea.persistence.dictionary` ships the only implementation that exists
today. Three properties of that arrangement are what these tests defend.

*The abstraction is real.* ``InMemoryDictionaryRepository`` is checked against
the ``runtime_checkable`` protocol rather than merely being assumed to fit, so
the SQLite- or LMDB-backed store Figure 2 anticipates has an executable
definition of "substitutable" to satisfy.

*The contract is counts, not probabilities.* The interface docstring makes
smoothing the consumer's decision. A float leaking into any exposed mapping
would silently move that decision into storage, so every count reachable through
the public API is asserted to be a non-negative ``int``.

*Failure is loud.* A daemon that starts with no grammatical knowledge produces
confidently worthless analyses, so every corrupt-payload path is required to
raise :class:`~teea.core.errors.ConfigurationError` -- a ``TEEAError`` carrying
a stable ``ErrorCode`` the add-in can act on -- rather than a bare Python
exception or, worse, an empty repository.

Surfaces used below were probed against the shipped payload first; none are
guessed. Thresholds are set with margin under measured values, because the
fixtures are excerpts of a larger corpus and must not be over-fitted.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from teea.core.errors import ConfigurationError, ErrorCode, TEEAError
from teea.persistence import (
    DEFAULT_DATA_PATH,
    SENTENCE_START,
    DictionaryRepository,
    InMemoryDictionaryRepository,
    default_dictionary,
)

# Real syllables, each confirmed present in the shipped payload. The repository
# is keyed on syllables *without* a trailing tsheg, which TSHEG_SUFFIXED probes.
LAS = "ལས"  # ablative particle / noun "work" -- the ambiguity case
OI = "འི"  # fused genitive
SA = "ས"  # agentive
LA = "ལ"  # allative
NAS = "ནས"  # elative
DANG = "དང"  # associative
MI = "མི"  # "person" / negation particle
SHAD = "།"  # sentence-final punctuation

KNOWN_SURFACES = (LAS, OI, SA, LA, NAS, DANG, MI, SHAD)

#: Surfaces confirmed absent. ``LAS + tsheg`` is the important one: it pins that
#: the lexicon is keyed on bare syllables, so a caller that forgets to strip the
#: delimiter gets a clean miss instead of an accidental hit.
TSHEG_SUFFIXED = LAS + "་"
UNKNOWN_SURFACES = ("", "xyzzy", TSHEG_SUFFIXED, LAS * 3, "ཧྰུྃ", "न")

REQUIRED_SECTIONS = ("tags", "tag_counts", "emissions", "transitions")


# -- Helpers ------------------------------------------------------------------
def valid_payload() -> dict[str, Any]:
    """A complete, hand-written payload -- deliberately unlike the shipped one."""
    return {
        "tags": ["n.count", "case.abl", "punc"],
        "tag_counts": {"n.count": 3, "case.abl": 1, "punc": 2},
        "emissions": {LAS: {"n.count": 3, "case.abl": 1}, SHAD: {"punc": 2}},
        "transitions": {
            SENTENCE_START: {"n.count": 2},
            "n.count": {"case.abl": 1, "punc": 1},
            "case.abl": {"punc": 1},
        },
        "provenance": {"source": "hand-written test fixture", "training_tokens": 6},
    }


def write_payload(directory: Path, payload: object, name: str = "model.json") -> Path:
    """Serialize ``payload`` as UTF-8 JSON and return its path."""
    path = directory / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def base_tag(tag: str) -> str:
    """Strip the corpus's ``~span-role`` suffix, e.g. ``cl.quot~quote.E``.

    The annotation composes a POS tag with a named-entity/quotation span role.
    The repository stores the POS half only, so comparisons must decompose.
    """
    return tag.split("~", 1)[0]


def distinct_surfaces(corpus: list[list[tuple[str, str]]]) -> list[str]:
    """Every distinct gold surface in ``corpus``, in first-appearance order."""
    seen: dict[str, None] = {}
    for line in corpus:
        for surface, _ in line:
            seen.setdefault(surface, None)
    return list(seen)


def assert_counts(mapping: Mapping[str, int], label: str) -> None:
    """Assert every value is a non-negative ``int`` -- a count, not a probability."""
    for key, value in mapping.items():
        assert isinstance(value, int) and not isinstance(value, bool), (
            f"{label}[{key!r}] is {type(value).__name__}, not an integer count"
        )
        assert value >= 0, f"{label}[{key!r}] == {value} is negative"


class PartialRepository:
    """Everything the protocol requires except :meth:`transitions`."""

    def __init__(self) -> None:
        self.tags: frozenset[str] = frozenset()
        self.tag_counts: Mapping[str, int] = {}

    def lookup(self, surface: str) -> Mapping[str, int] | None:
        """Never finds anything."""
        return None

    def __contains__(self, surface: str) -> bool:
        return False


# -- Protocol conformance -----------------------------------------------------
def test_the_shipped_implementation_satisfies_the_protocol(
    dictionary: InMemoryDictionaryRepository,
) -> None:
    """The substitution point of Figure 2, checked rather than assumed."""
    assert isinstance(dictionary, DictionaryRepository)


def test_a_repository_missing_a_member_does_not_satisfy_the_protocol() -> None:
    """Guards the check above against passing for everything."""
    assert not isinstance(PartialRepository(), DictionaryRepository)
    assert not isinstance(object(), DictionaryRepository)


@pytest.mark.parametrize("member", ["tags", "tag_counts", "lookup", "transitions"])
def test_every_protocol_member_is_present_on_the_implementation(
    dictionary: InMemoryDictionaryRepository, member: str
) -> None:
    assert hasattr(dictionary, member)


# -- The process-wide cache ---------------------------------------------------
def test_default_dictionary_returns_the_same_object_every_time() -> None:
    """Parsing the payload costs real time; every request needs the same data."""
    assert default_dictionary() is default_dictionary()


def test_the_dictionary_fixture_is_the_shared_instance(
    dictionary: InMemoryDictionaryRepository,
) -> None:
    assert dictionary is default_dictionary()


def test_constructing_directly_bypasses_the_cache(
    dictionary: InMemoryDictionaryRepository,
) -> None:
    """The cache shares one instance; it does not make the class a singleton."""
    fresh = InMemoryDictionaryRepository()
    assert fresh is not dictionary
    assert fresh.tags == dictionary.tags
    assert len(fresh) == len(dictionary)


def test_the_default_path_is_the_shipped_payload(
    dictionary: InMemoryDictionaryRepository,
) -> None:
    assert DEFAULT_DATA_PATH.is_file()
    explicit = InMemoryDictionaryRepository(DEFAULT_DATA_PATH)
    assert explicit.tags == dictionary.tags
    assert explicit.vocabulary_size == dictionary.vocabulary_size


# -- Loaded shape -------------------------------------------------------------
def test_the_tag_inventory_is_the_77_corpus_tags(
    dictionary: InMemoryDictionaryRepository,
) -> None:
    """The reference corpus distinguishes 77 tags; none may be dropped on load."""
    assert isinstance(dictionary.tags, frozenset)
    assert len(dictionary.tags) == 77
    assert all(tag and not tag.isspace() for tag in dictionary.tags)


def test_tag_counts_covers_exactly_the_tag_inventory(
    dictionary: InMemoryDictionaryRepository,
) -> None:
    """A tag with no count, or a count with no tag, means a truncated load."""
    assert set(dictionary.tag_counts) == set(dictionary.tags)


def test_vocabulary_size_agrees_with_len_and_is_substantial(
    dictionary: InMemoryDictionaryRepository,
) -> None:
    assert dictionary.vocabulary_size == len(dictionary.vocabulary)
    assert dictionary.vocabulary_size > 2000


def test_the_sentence_start_marker_is_a_position_not_a_tag(
    dictionary: InMemoryDictionaryRepository,
) -> None:
    """``<s>`` keys the transition table but must never be assignable as a tag."""
    assert SENTENCE_START not in dictionary.tags
    assert SENTENCE_START not in dictionary.tag_counts


# -- lookup(): the lexicon ----------------------------------------------------
@pytest.mark.parametrize("surface", KNOWN_SURFACES)
def test_lookup_returns_a_tag_distribution_for_a_known_surface(
    dictionary: InMemoryDictionaryRepository, surface: str
) -> None:
    entry = dictionary.lookup(surface)
    assert entry is not None, f"{surface!r} should be in the lexicon"
    assert isinstance(entry, Mapping)
    assert entry, "a present surface must carry at least one reading"
    assert set(entry) <= set(dictionary.tags), "emitted a tag outside the inventory"


@pytest.mark.parametrize("surface", UNKNOWN_SURFACES)
def test_lookup_returns_none_for_an_unknown_surface(
    dictionary: InMemoryDictionaryRepository, surface: str
) -> None:
    """Out-of-vocabulary is ``None``, never an empty mapping -- the tagger
    distinguishes "unseen" from "seen with no readings"."""
    assert dictionary.lookup(surface) is None


def test_a_tsheg_suffixed_surface_misses(
    dictionary: InMemoryDictionaryRepository,
) -> None:
    """The documented key format: a surface form *without* a trailing tsheg."""
    assert dictionary.lookup(LAS) is not None
    assert dictionary.lookup(TSHEG_SUFFIXED) is None


def test_lookup_reflects_genuine_lexical_ambiguity(
    dictionary: InMemoryDictionaryRepository,
) -> None:
    """``ལས`` is the ablative particle and the noun "work".

    This is the reason the repository stores a distribution rather than a single
    tag: resolving it is Stage 7's job, and storage must not pre-empt it.
    """
    entry = dictionary.lookup(LAS)
    assert entry is not None
    assert len(entry) > 1
    assert entry["case.abl"] > 0
    assert entry["n.count"] > 0


def test_a_syncretic_particle_is_not_collapsed_to_one_reading(
    dictionary: InMemoryDictionaryRepository,
) -> None:
    """``ལ`` is allative case, allative converb and more; all readings survive."""
    entry = dictionary.lookup(LA)
    assert entry is not None
    assert {"case.all", "cv.all"} <= set(entry)


def test_repeated_lookups_agree(dictionary: InMemoryDictionaryRepository) -> None:
    """Reads must be side-effect free: the store is shared across threads."""
    first = dictionary.lookup(LAS)
    second = dictionary.lookup(LAS)
    assert first == second
    assert dictionary.vocabulary_size == len(dictionary.vocabulary)


# -- transitions(): the morphological rules catalog ---------------------------
@pytest.mark.parametrize("tag", ["n.count", "case.gen", "punc", SENTENCE_START])
def test_transitions_returns_a_distribution_for_a_known_key(
    dictionary: InMemoryDictionaryRepository, tag: str
) -> None:
    following = dictionary.transitions(tag)
    assert isinstance(following, Mapping)
    assert following, f"{tag!r} should have observed successors"
    assert set(following) <= set(dictionary.tags)


def test_every_known_tag_has_successors(
    dictionary: InMemoryDictionaryRepository,
) -> None:
    """A tag with an empty row would make the tagger's Viterbi path dead-end."""
    empty = sorted(tag for tag in dictionary.tags if not dictionary.transitions(tag))
    assert empty == []


def test_the_sentence_start_marker_keys_the_transition_table(
    dictionary: InMemoryDictionaryRepository,
) -> None:
    """Stage 7 needs an initial distribution, not a uniform guess."""
    assert dictionary.transitions(SENTENCE_START)


@pytest.mark.parametrize("tag", ["", "no-such-tag", "N.COUNT", SENTENCE_START * 2])
def test_transitions_returns_an_empty_mapping_for_an_unknown_tag(
    dictionary: InMemoryDictionaryRepository, tag: str
) -> None:
    """Empty, not ``None`` and not an exception: callers iterate unconditionally."""
    following = dictionary.transitions(tag)
    assert following is not None
    assert isinstance(following, Mapping)
    assert len(following) == 0


# -- __contains__ -------------------------------------------------------------
@pytest.mark.parametrize("surface", KNOWN_SURFACES)
def test_contains_is_true_for_known_surfaces(
    dictionary: InMemoryDictionaryRepository, surface: str
) -> None:
    assert surface in dictionary


@pytest.mark.parametrize("surface", UNKNOWN_SURFACES)
def test_contains_is_false_for_unknown_surfaces(
    dictionary: InMemoryDictionaryRepository, surface: str
) -> None:
    assert surface not in dictionary


def test_contains_agrees_with_lookup_across_the_corpus(
    dictionary: InMemoryDictionaryRepository,
    tagged_corpus: list[list[tuple[str, str]]],
) -> None:
    """Checked over every distinct gold surface, not a hand-picked handful.

    Gold tokens may span several syllables while the lexicon is syllable-keyed,
    so this sample is mostly misses -- which is exactly what makes it a real
    test of the two accessors agreeing.
    """
    surfaces = distinct_surfaces(tagged_corpus)
    disagreements = [s for s in surfaces if (s in dictionary) != (dictionary.lookup(s) is not None)]
    assert disagreements == []

    present = [s for s in surfaces if s in dictionary]
    assert len(present) >= 50, "sample must contain hits"
    assert len(surfaces) - len(present) >= 500, "sample must contain misses"


# -- Counts, not probabilities ------------------------------------------------
def test_tag_counts_are_non_negative_integers(
    dictionary: InMemoryDictionaryRepository,
) -> None:
    assert_counts(dictionary.tag_counts, "tag_counts")


def test_transition_counts_are_non_negative_integers(
    dictionary: InMemoryDictionaryRepository,
) -> None:
    for tag in [*sorted(dictionary.tags), SENTENCE_START]:
        assert_counts(dictionary.transitions(tag), f"transitions({tag!r})")


def test_emission_counts_are_non_negative_integers(
    dictionary: InMemoryDictionaryRepository,
    tagged_corpus: list[list[tuple[str, str]]],
) -> None:
    """Smoothing belongs to the consumer, so storage exposes raw evidence."""
    surfaces = [s for s in distinct_surfaces(tagged_corpus) if s in dictionary]
    assert len(surfaces) >= 50, "premise: the corpus sample reaches the lexicon"
    for surface in [*surfaces, *KNOWN_SURFACES]:
        entry = dictionary.lookup(surface)
        assert entry is not None
        assert_counts(entry, f"lookup({surface!r})")


# -- Provenance ---------------------------------------------------------------
def test_provenance_records_the_source_corpus(
    dictionary: InMemoryDictionaryRepository,
) -> None:
    """An offline daemon cannot re-fetch its data, so it must be able to say
    where the data came from."""
    provenance = dictionary.provenance
    assert isinstance(provenance, Mapping)
    assert provenance
    assert "mila" in str(provenance["source"]).lower()


def test_provenance_records_the_training_volume(
    dictionary: InMemoryDictionaryRepository,
) -> None:
    tokens = dictionary.provenance["training_tokens"]
    assert isinstance(tokens, int) and not isinstance(tokens, bool)
    assert tokens > 10_000


def test_the_stored_counts_are_consistent_with_the_declared_volume(
    dictionary: InMemoryDictionaryRepository,
) -> None:
    """Tags are projected from gold tokens onto syllables, so the number of
    tagged units cannot be *fewer* than the number of training tokens."""
    assert sum(dictionary.tag_counts.values()) >= dictionary.provenance["training_tokens"]


# -- Error paths --------------------------------------------------------------
def test_a_missing_file_raises_configuration_error(tmp_path: Path) -> None:
    """Starting with no grammatical knowledge must fail loudly, not silently."""
    missing = tmp_path / "absent" / "model.json"
    with pytest.raises(ConfigurationError) as excinfo:
        InMemoryDictionaryRepository(missing)
    assert excinfo.value.context["path"] == str(missing)


def test_invalid_json_raises_configuration_error(tmp_path: Path) -> None:
    path = tmp_path / "model.json"
    path.write_text('{"tags": [', encoding="utf-8")
    with pytest.raises(ConfigurationError) as excinfo:
        InMemoryDictionaryRepository(path)
    assert excinfo.value.context["path"] == str(path)
    assert isinstance(excinfo.value.__cause__, ValueError), "the parse failure is preserved"


@pytest.mark.parametrize("section", REQUIRED_SECTIONS)
def test_a_missing_section_is_named_in_the_error(tmp_path: Path, section: str) -> None:
    """The operator must learn *which* section is absent, not merely that one is."""
    payload = valid_payload()
    del payload[section]
    path = write_payload(tmp_path, payload)

    with pytest.raises(ConfigurationError) as excinfo:
        InMemoryDictionaryRepository(path)
    assert excinfo.value.context["missing"] == [section]


def test_every_missing_section_is_reported_at_once(tmp_path: Path) -> None:
    """Reporting one at a time would make recovery an N-round guessing game."""
    path = write_payload(tmp_path, {"provenance": {}})
    with pytest.raises(ConfigurationError) as excinfo:
        InMemoryDictionaryRepository(path)
    assert excinfo.value.context["missing"] == sorted(REQUIRED_SECTIONS)


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("truncated", '{"tags": ['),
        ("empty_file", ""),
        ("json_array", "[1, 2, 3]"),
        ("json_string", '"tags"'),
    ],
)
def test_corrupt_payloads_are_teea_errors_with_a_stable_code(
    tmp_path: Path, name: str, content: str
) -> None:
    """The add-in reacts to codes, never to message text, so the code is contract."""
    path = tmp_path / f"{name}.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ConfigurationError) as excinfo:
        InMemoryDictionaryRepository(path)
    error = excinfo.value
    assert isinstance(error, TEEAError)
    assert error.code is ErrorCode.CONFIGURATION_INVALID
    assert error.to_dict()["code"] == "TEEA-0001"
    assert error.to_dict()["context"]["path"] == str(path)


# Regression guard: valid JSON need not be an object. A bare scalar once reached
# the membership check inside _load and leaked a raw TypeError, which no caller is
# told to catch. The loader now rejects any non-object payload up front.
def test_a_scalar_payload_raises_configuration_error(tmp_path: Path) -> None:
    path = tmp_path / "scalar.json"
    path.write_text("5", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        InMemoryDictionaryRepository(path)


# Regression guard: UnicodeDecodeError is a ValueError, not an OSError, so a
# corrupt or truncated payload once escaped the loader untyped. This is the
# realistic on-disk failure for a shipped data file.
def test_a_non_utf8_payload_raises_configuration_error(tmp_path: Path) -> None:
    path = tmp_path / "utf16.json"
    path.write_bytes(b"\xff\xfe{\x00}\x00")
    with pytest.raises(ConfigurationError):
        InMemoryDictionaryRepository(path)


# -- The path argument is honoured --------------------------------------------
def test_a_hand_written_payload_loads_and_is_independent(
    tmp_path: Path, dictionary: InMemoryDictionaryRepository
) -> None:
    """Proves the constructor reads ``path`` rather than always the shipped file.

    Without this, every other test here could be passing against the same global
    data no matter what was asked for.
    """
    repo = InMemoryDictionaryRepository(write_payload(tmp_path, valid_payload()))

    assert isinstance(repo, DictionaryRepository)
    assert repo.tags == frozenset({"n.count", "case.abl", "punc"})
    assert repo.vocabulary_size == len(repo) == 2
    assert repo.lookup(LAS) == {"n.count": 3, "case.abl": 1}
    assert repo.transitions("n.count") == {"case.abl": 1, "punc": 1}
    assert repo.transitions(SENTENCE_START) == {"n.count": 2}
    assert LAS in repo and SHAD in repo

    # Same surface, different evidence; and a surface the shipped store knows is
    # absent here. The two repositories share no state.
    assert repo.lookup(LAS) != dictionary.lookup(LAS)
    assert OI in dictionary
    assert OI not in repo
    assert len(repo) < len(dictionary)


def test_tibetan_survives_the_round_trip_through_the_payload(tmp_path: Path) -> None:
    """The payload is read as UTF-8; a mojibake key would silently miss forever."""
    repo = InMemoryDictionaryRepository(write_payload(tmp_path, valid_payload()))
    assert repo.lookup(LAS) is not None
    assert repo.lookup(LAS.encode("utf-8").decode("latin-1")) is None


def test_provenance_is_empty_when_the_payload_omits_it(tmp_path: Path) -> None:
    """Provenance is optional; its absence must not stop the daemon starting."""
    payload = valid_payload()
    del payload["provenance"]
    repo = InMemoryDictionaryRepository(write_payload(tmp_path, payload))
    assert repo.provenance == {}


# -- Data integrity against the reference corpus ------------------------------
def test_every_corpus_tag_is_known_to_the_repository(
    dictionary: InMemoryDictionaryRepository,
    tagged_corpus: list[list[tuple[str, str]]],
) -> None:
    """A gold tag the repository cannot represent is unreachable by any tagger."""
    corpus_tags = {base_tag(tag) for line in tagged_corpus for _, tag in line}
    assert corpus_tags, "premise: the corpus fixture is annotated"
    assert corpus_tags - set(dictionary.tags) == set()


def test_frequent_corpus_tags_all_appear_in_the_repository(
    dictionary: InMemoryDictionaryRepository,
    tagged_corpus: list[list[tuple[str, str]]],
) -> None:
    counts: dict[str, int] = {}
    for line in tagged_corpus:
        for _, tag in line:
            counts[base_tag(tag)] = counts.get(base_tag(tag), 0) + 1
    frequent = {tag for tag, count in counts.items() if count >= 20}
    assert len(frequent) >= 30, "premise: the excerpt exercises many tags"
    assert frequent <= set(dictionary.tags)


def test_the_repository_tags_are_almost_all_witnessed_by_the_corpus(
    dictionary: InMemoryDictionaryRepository,
    tagged_corpus: list[list[tuple[str, str]]],
) -> None:
    """The fixture is an excerpt, so a few genuinely rare tags may not occur.

    Any tag that does not occur must be rare in the full corpus as well --
    otherwise the repository is carrying an inventory the corpus never supports.
    """
    corpus_tags = {base_tag(tag) for line in tagged_corpus for _, tag in line}
    unwitnessed = dictionary.tags - corpus_tags
    assert len(unwitnessed) <= 3

    total = sum(dictionary.tag_counts.values())
    for tag in unwitnessed:
        assert dictionary.tag_counts[tag] / total < 0.01, f"{tag!r} is not rare"
