"""Tests for the proper-noun gazetteer (:mod:`teea.persistence.gazetteer`).

The gazetteer is the second facet of Figure 2's Dictionary Repository and the
main evidence source for Stage 9. Two things matter beyond it loading: the
**two-tier split** that keeps precision usable, and the error paths, since a
daemon that silently recognises nothing looks exactly like a clean document.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from teea.core.errors import ConfigurationError, TEEAError
from teea.persistence import GazetteerRepository, InMemoryGazetteer, default_gazetteer


def write_payload(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


# -- Loading ------------------------------------------------------------------
def test_satisfies_the_gazetteer_protocol(gazetteer: InMemoryGazetteer) -> None:
    assert isinstance(gazetteer, GazetteerRepository)


def test_default_gazetteer_is_cached() -> None:
    assert default_gazetteer() is default_gazetteer()


def test_shipped_gazetteer_is_populated(gazetteer: InMemoryGazetteer) -> None:
    assert len(gazetteer) > 2000
    assert gazetteer.num_confident > 2000
    assert gazetteer.num_ambiguous > 100
    assert len(gazetteer) == gazetteer.num_confident + gazetteer.num_ambiguous


def test_provenance_records_the_sources(gazetteer: InMemoryGazetteer) -> None:
    provenance = gazetteer.provenance
    assert provenance["sources"]
    assert "classical-lexicon" in " ".join(provenance["sources"])
    assert provenance["lexicon_entries"] > 0


# -- The two tiers ------------------------------------------------------------
def test_the_tiers_are_disjoint(gazetteer: InMemoryGazetteer) -> None:
    """A surface is either self-evidently a name or it is not; never both."""
    confident = gazetteer._entries
    ambiguous = gazetteer._ambiguous
    assert not (confident & ambiguous)


def test_confident_entries_are_all_multi_syllable(gazetteer: InMemoryGazetteer) -> None:
    """A single syllable is too short to be distinctive.

    Measured on held-out text, single-syllable entries fire 584 times but name
    something only 151 of those, so they are demoted to the tier that requires
    corroboration.
    """
    assert all(len(entry) > 1 for entry in gazetteer._entries)


def test_max_length_bounds_both_tiers(gazetteer: InMemoryGazetteer) -> None:
    """The matcher's lookahead must cover every entry it could match."""
    longest = max(len(e) for e in (gazetteer._entries | gazetteer._ambiguous))
    assert gazetteer.max_length == longest


def test_no_duplication_artifact_survives(gazetteer: InMemoryGazetteer) -> None:
    """One lexicon row repeats a three-syllable name twenty-two times.

    It is filtered because the longest entry bounds the recogniser's lookahead
    at every position; keeping it would quadruple that scan for nothing.
    """
    assert gazetteer.max_length <= 20
    for entry in gazetteer._entries | gazetteer._ambiguous:
        for period in range(1, len(entry) // 2 + 1):
            if len(entry) % period == 0 and len(entry) // period >= 3:
                assert entry != entry[:period] * (len(entry) // period), entry


# -- Lookup -------------------------------------------------------------------
def test_lookup_matches_a_known_multi_syllable_name(gazetteer: InMemoryGazetteer) -> None:
    """A name the corpus annotates across three tokens, including a genitive."""
    assert gazetteer.contains(("འཛམ", "བུ", "འི", "གླིང"))


def test_lookup_rejects_an_ordinary_word(gazetteer: InMemoryGazetteer) -> None:
    assert not gazetteer.contains(("ཁྱིམ",))
    assert not gazetteer.contains_ambiguous(("ཁྱིམ",))


def test_lookup_is_exact_not_prefix(gazetteer: InMemoryGazetteer) -> None:
    """A prefix of an entry is not itself an entry."""
    assert gazetteer.contains(("འཛམ", "བུ", "འི", "གླིང"))
    assert not gazetteer.contains(("འཛམ", "བུ", "འི"))


def test_lookup_accepts_any_sequence_type(gazetteer: InMemoryGazetteer) -> None:
    assert gazetteer.contains(["འཛམ", "བུ", "འི", "གླིང"])


def test_empty_lookup_is_not_a_match(gazetteer: InMemoryGazetteer) -> None:
    assert not gazetteer.contains(())
    assert not gazetteer.contains_ambiguous(())


# -- Error paths --------------------------------------------------------------
def test_a_missing_file_raises_configuration_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError) as excinfo:
        InMemoryGazetteer(tmp_path / "absent.json")
    assert "path" in excinfo.value.context
    assert isinstance(excinfo.value, TEEAError)


def test_invalid_json_raises_configuration_error(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="not valid JSON"):
        InMemoryGazetteer(path)


def test_a_non_utf8_payload_raises_configuration_error(tmp_path: Path) -> None:
    path = tmp_path / "utf16.json"
    path.write_bytes(b"\xff\xfe{\x00}\x00")
    with pytest.raises(ConfigurationError, match="could not be read"):
        InMemoryGazetteer(path)


@pytest.mark.parametrize("payload", [42, "text", [1, 2]])
def test_a_non_object_payload_raises_configuration_error(tmp_path: Path, payload: object) -> None:
    with pytest.raises(ConfigurationError, match="must be a JSON object"):
        InMemoryGazetteer(write_payload(tmp_path / "scalar.json", payload))


def test_a_payload_without_entries_raises_configuration_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="missing required sections"):
        InMemoryGazetteer(write_payload(tmp_path / "empty.json", {"provenance": {}}))


def test_entries_must_be_a_list(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="must be a list"):
        InMemoryGazetteer(write_payload(tmp_path / "bad.json", {"entries": "nope"}))


# -- Custom payloads ----------------------------------------------------------
def test_a_hand_written_payload_is_independent_of_the_shipped_one(
    tmp_path: Path, gazetteer: InMemoryGazetteer
) -> None:
    custom = InMemoryGazetteer(
        write_payload(
            tmp_path / "tiny.json",
            {"entries": [["ཀ", "ཁ"]], "ambiguous_entries": [["ག"]]},
        )
    )
    assert len(custom) == 2
    assert custom.contains(("ཀ", "ཁ"))
    assert custom.contains_ambiguous(("ག",))
    assert custom.max_length == 2
    assert not custom.contains(("འཛམ", "བུ", "འི", "གླིང"))
    assert gazetteer.contains(("འཛམ", "བུ", "འི", "གླིང"))


def test_a_payload_without_an_ambiguous_tier_still_loads(tmp_path: Path) -> None:
    """The section is optional, so an older payload keeps working."""
    custom = InMemoryGazetteer(write_payload(tmp_path / "legacy.json", {"entries": [["ཀ", "ཁ"]]}))
    assert custom.num_ambiguous == 0
    assert custom.contains(("ཀ", "ཁ"))


def test_an_entirely_empty_gazetteer_is_valid(tmp_path: Path) -> None:
    custom = InMemoryGazetteer(write_payload(tmp_path / "none.json", {"entries": []}))
    assert len(custom) == 0
    assert custom.max_length == 0
    assert not custom.contains(("ཀ",))
