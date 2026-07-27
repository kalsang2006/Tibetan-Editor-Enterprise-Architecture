"""Tests for the verb lexicon, the fourth facet of the Dictionary Repository.

The lexicon is the evidence base for Stage 11's argument roles, so what matters
here is that it loads exactly what the authoritative source says, fails loudly
when it cannot, and never quietly invents an argument frame.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from teea.core.errors import ConfigurationError, ErrorCode
from teea.persistence import (
    DEFAULT_VERB_LEXICON_PATH,
    ArgumentSlot,
    InMemoryVerbLexicon,
    Transitivity,
    VerbFrame,
    VerbLexiconRepository,
    Volition,
    default_verb_lexicon,
)

#: A verb the lexicon reports as transitive with an ``Erg-Abs`` frame.
READ = ("ཀློག",)

#: The past stem of "to go", whose lemma is the suppletive ``འགྲོ་``.
WENT = ("སོང",)


def write_payload(path: Path, payload: object) -> Path:
    """Write a JSON payload and return its path."""
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def minimal_payload() -> dict[str, object]:
    """The smallest structurally valid payload."""
    return {
        "lemmas": [{"lemma": "ཀློག་", "frame": "Erg-Abs", "slots": ["erg", "abs"]}],
        "surfaces": [[["ཀློག"], [0]]],
    }


# -- Protocol and shared instance ---------------------------------------------
def test_satisfies_the_verb_lexicon_repository_protocol(
    verb_lexicon: InMemoryVerbLexicon,
) -> None:
    assert isinstance(verb_lexicon, VerbLexiconRepository)


def test_the_default_lexicon_is_loaded_once(verb_lexicon: InMemoryVerbLexicon) -> None:
    assert default_verb_lexicon() is default_verb_lexicon()
    assert default_verb_lexicon() is verb_lexicon


def test_the_shipped_payload_is_where_the_module_says_it_is() -> None:
    assert DEFAULT_VERB_LEXICON_PATH.exists()


# -- Payload integrity ---------------------------------------------------------
def test_the_lexicon_is_not_empty(verb_lexicon: InMemoryVerbLexicon) -> None:
    assert len(verb_lexicon) > 10_000
    assert verb_lexicon.num_lemmas > 1_000


def test_most_entries_report_usable_argument_structure(
    verb_lexicon: InMemoryVerbLexicon,
) -> None:
    """The lexicon is only worth loading if it decides argument structure.

    Pinned as a ratio rather than a count so a payload rebuild that silently
    dropped the transitivity column fails here.
    """
    informative = verb_lexicon.num_with_argument_structure
    assert informative / verb_lexicon.num_lemmas >= 0.70, informative


def test_provenance_names_the_authoritative_source(
    verb_lexicon: InMemoryVerbLexicon,
) -> None:
    """An offline daemon must be able to report where its lexicon came from."""
    provenance = verb_lexicon.provenance
    assert "kalsang2006/Data" in provenance["repository"]
    assert "Hill" in provenance["publication"]
    assert provenance["lemma_entries"] == verb_lexicon.num_lemmas
    assert provenance["surface_forms"] == len(verb_lexicon)


def test_the_payload_cross_check_against_the_grammar_lexicon_passed(
    verb_lexicon: InMemoryVerbLexicon,
) -> None:
    """The builder validates its alignment against an independent file.

    ``lemmas.txt`` and ``dictionary.xml`` are joined positionally, which is only
    sound if the two agree row for row. ``cg3-lemmas.txt`` states the same
    entries independently, so the agreement rate is recorded in the payload.
    """
    agreed, _, total = verb_lexicon.provenance["cross_check"].partition("/")
    checked = total.split()[0]
    assert int(agreed) / int(checked) >= 0.99


def test_max_length_bounds_the_longest_surface(
    verb_lexicon: InMemoryVerbLexicon,
) -> None:
    assert verb_lexicon.max_length >= 1
    assert len(verb_lexicon.lookup(READ)) >= 1


# -- Lookup --------------------------------------------------------------------
def test_a_known_stem_resolves_to_its_frame(verb_lexicon: InMemoryVerbLexicon) -> None:
    frames = verb_lexicon.lookup(READ)
    assert len(frames) == 1
    frame = frames[0]
    assert frame.frame == "Erg-Abs"
    assert frame.slots == frozenset({ArgumentSlot.ERGATIVE, ArgumentSlot.ABSOLUTIVE})
    assert frame.transitivity is Transitivity.TRANSITIVE
    assert frame.is_transitive is True


def test_an_irregular_stem_resolves_to_its_own_lemma(
    verb_lexicon: InMemoryVerbLexicon,
) -> None:
    """Lemmatisation is the point: ``སོང`` is a stem of ``འགྲོ་`` "to go".

    A stage keying on the surface form would treat the present and past of one
    verb as two predicates.
    """
    lemmas = {frame.lemma for frame in verb_lexicon.lookup(WENT)}
    assert "འགྲོ་" in lemmas


def test_an_unknown_run_resolves_to_nothing(
    verb_lexicon: InMemoryVerbLexicon,
) -> None:
    assert verb_lexicon.lookup(("ཟzz",)) == ()
    assert verb_lexicon.lookup(()) == ()


def test_lookup_accepts_any_sequence(verb_lexicon: InMemoryVerbLexicon) -> None:
    """The protocol says Sequence, so a list must work as well as a tuple."""
    assert verb_lexicon.lookup(list(READ)) == verb_lexicon.lookup(READ)


def test_lookup_is_stable_across_calls(verb_lexicon: InMemoryVerbLexicon) -> None:
    assert verb_lexicon.lookup(READ) == verb_lexicon.lookup(READ)


# -- VerbFrame -----------------------------------------------------------------
def test_a_frame_naming_an_ergative_slot_is_transitive() -> None:
    frame = VerbFrame(lemma="ཀློག་", frame="Erg-Abs", slots=frozenset({ArgumentSlot.ERGATIVE}))
    assert frame.has_agentive_slot is True
    assert frame.is_transitive is True
    assert frame.is_informative is True


def test_a_frame_without_an_ergative_slot_is_intransitive() -> None:
    frame = VerbFrame(lemma="ཀེར་", frame="Abs-Obl", slots=frozenset({ArgumentSlot.ABSOLUTIVE}))
    assert frame.has_agentive_slot is False
    assert frame.is_transitive is False


def test_the_frame_outranks_the_transitivity_label() -> None:
    """The frame is the more specific statement, so it decides.

    Labels summarise; a frame naming an ergative slot settles the question.
    """
    frame = VerbFrame(
        lemma="x",
        frame="Erg-Abs",
        slots=frozenset({ArgumentSlot.ERGATIVE}),
        transitivity=Transitivity.INTRANSITIVE,
    )
    assert frame.is_transitive is True


@pytest.mark.parametrize(
    ("transitivity", "expected"),
    [
        (Transitivity.TRANSITIVE, True),
        (Transitivity.INTRANSITIVE, False),
        (Transitivity.BOTH, None),
        (Transitivity.UNKNOWN, None),
    ],
)
def test_transitivity_decides_when_no_frame_is_reported(
    transitivity: Transitivity, expected: bool | None
) -> None:
    frame = VerbFrame(lemma="x", transitivity=transitivity)
    assert frame.is_transitive is expected


def test_an_entry_reporting_nothing_is_not_informative() -> None:
    """Absence of evidence must be distinguishable from evidence of absence."""
    frame = VerbFrame(lemma="x")
    assert frame.is_informative is False
    assert frame.is_transitive is None
    assert frame.volition is Volition.UNKNOWN


def test_a_frame_is_immutable() -> None:
    frame = VerbFrame(lemma="x")
    with pytest.raises(ValidationError):
        frame.lemma = "y"  # type: ignore[misc]


def test_a_frame_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        VerbFrame(lemma="x", gloss="to read")  # type: ignore[call-arg]


# -- Loading and error paths ---------------------------------------------------
def test_a_missing_payload_raises_configuration_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError) as error:
        InMemoryVerbLexicon(tmp_path / "absent.json")
    assert error.value.code is ErrorCode.CONFIGURATION_INVALID
    assert "path" in error.value.context


def test_a_non_utf8_payload_raises_configuration_error(tmp_path: Path) -> None:
    """UnicodeDecodeError is a ValueError, not an OSError, so it needs catching."""
    path = tmp_path / "verbs.json"
    path.write_bytes(b"\xff\xfe\x00garbage")
    with pytest.raises(ConfigurationError, match="could not be read"):
        InMemoryVerbLexicon(path)


def test_invalid_json_raises_configuration_error(tmp_path: Path) -> None:
    path = tmp_path / "verbs.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="not valid JSON"):
        InMemoryVerbLexicon(path)


def test_a_scalar_payload_raises_configuration_error(tmp_path: Path) -> None:
    """Valid JSON need not be an object; a bare scalar must not reach the loader."""
    path = write_payload(tmp_path / "verbs.json", 42)
    with pytest.raises(ConfigurationError, match="must be a JSON object"):
        InMemoryVerbLexicon(path)


@pytest.mark.parametrize("missing", ["lemmas", "surfaces"])
def test_a_payload_missing_a_section_raises_configuration_error(
    tmp_path: Path, missing: str
) -> None:
    payload = minimal_payload()
    del payload[missing]
    path = write_payload(tmp_path / "verbs.json", payload)
    with pytest.raises(ConfigurationError, match="missing required sections") as error:
        InMemoryVerbLexicon(path)
    assert error.value.context["missing"] == [missing]


@pytest.mark.parametrize("section", ["lemmas", "surfaces"])
def test_a_section_that_is_not_a_list_raises_configuration_error(
    tmp_path: Path, section: str
) -> None:
    payload = minimal_payload()
    payload[section] = {"not": "a list"}
    path = write_payload(tmp_path / "verbs.json", payload)
    with pytest.raises(ConfigurationError, match=f"{section} must be a list"):
        InMemoryVerbLexicon(path)


def test_a_minimal_payload_loads(tmp_path: Path) -> None:
    path = write_payload(tmp_path / "verbs.json", minimal_payload())
    lexicon = InMemoryVerbLexicon(path)
    assert len(lexicon) == 1
    assert lexicon.num_lemmas == 1
    assert lexicon.max_length == 1
    assert lexicon.lookup(("ཀློག",))[0].frame == "Erg-Abs"
    assert lexicon.provenance == {}


def test_an_empty_surface_key_is_ignored(tmp_path: Path) -> None:
    """A zero-syllable key could never be matched and would break max_length."""
    payload = minimal_payload()
    payload["surfaces"] = [[[], [0]], [["ཀློག"], [0]]]
    path = write_payload(tmp_path / "verbs.json", payload)
    lexicon = InMemoryVerbLexicon(path)
    assert len(lexicon) == 1
    assert lexicon.max_length == 1


def test_a_lexicon_with_no_surfaces_has_zero_max_length(tmp_path: Path) -> None:
    payload = minimal_payload()
    payload["surfaces"] = []
    path = write_payload(tmp_path / "verbs.json", payload)
    lexicon = InMemoryVerbLexicon(path)
    assert lexicon.max_length == 0
    assert len(lexicon) == 0


def test_a_malformed_lemma_entry_is_rejected(tmp_path: Path) -> None:
    """Model validation is not bypassed by loading from disk."""
    payload = minimal_payload()
    payload["lemmas"] = [{"lemma": "x", "transitivity": "sideways"}]
    path = write_payload(tmp_path / "verbs.json", payload)
    with pytest.raises(ValidationError):
        InMemoryVerbLexicon(path)
