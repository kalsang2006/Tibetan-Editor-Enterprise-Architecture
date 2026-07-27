"""Integrity tests for the corpus-derived affix inventory.

:mod:`teea.nlp.morphology.particles` is generated from the part-of-speech
annotated Milarepa corpus rather than hand-authored, which removes the risk of
mistyped Tibetan but introduces a different one: the tables could silently drift
away from the corpus they claim to describe, or be regenerated with a bug.

These tests check the tables against the annotation itself. The tag-to-category
mapping below is written out independently here on purpose -- reusing the
generator's own mapping would make the test agree with the implementation by
construction instead of confirming it.

Note the reference sample in ``tests/data`` is an excerpt (5,015 tokens) of the
full corpus (60,544 tokens) the tables were derived from, so entries may
legitimately exist in the tables without appearing in the sample. The tests are
written in the direction that must hold regardless.
"""

from __future__ import annotations

import pytest

from teea.core.types import TSHEG_CHARS, is_tibetan_char
from teea.nlp.morphology import AffixCategory
from teea.nlp.morphology.particles import (
    AMBIGUOUS_AFFIXES,
    FUSED_AFFIXES,
    UNAMBIGUOUS_AFFIXES,
    lookup,
)

A_CHUNG = "འ"  # U+0F60

#: Independent oracle: corpus tag prefix -> the category it must map to.
TAG_TO_CATEGORY: dict[str, AffixCategory] = {
    "case.gen": AffixCategory.GENITIVE,
    "cv.gen": AffixCategory.GENITIVE,
    "case.agn": AffixCategory.AGENTIVE,
    "cv.agn": AffixCategory.AGENTIVE,
    "case.all": AffixCategory.ALLATIVE,
    "cv.all": AffixCategory.ALLATIVE,
    "case.term": AffixCategory.TERMINATIVE,
    "cv.term": AffixCategory.TERMINATIVE,
    "case.loc": AffixCategory.LOCATIVE,
    "cv.loc": AffixCategory.LOCATIVE,
    "case.abl": AffixCategory.ABLATIVE,
    "case.ela": AffixCategory.ELATIVE,
    "cv.ela": AffixCategory.ELATIVE,
    "case.ass": AffixCategory.ASSOCIATIVE,
    "cv.ass": AffixCategory.ASSOCIATIVE,
    "case.comp": AffixCategory.COMPARATIVE,
    "cv.sem": AffixCategory.SEMI_FINAL,
    "cv.impf": AffixCategory.IMPERFECTIVE,
    "cv.cont": AffixCategory.CONTINUATIVE,
    "cv.fin": AffixCategory.FINAL,
    "cv.imp": AffixCategory.IMPERATIVE,
    "cv.ques": AffixCategory.INTERROGATIVE,
    "cv.rung": AffixCategory.CONCESSIVE,
    "cl.focus": AffixCategory.FOCUS,
    "cl.quot": AffixCategory.QUOTATIVE,
    "case.nare": AffixCategory.QUOTATIVE,
    "neg": AffixCategory.NEGATION,
    "d.indef": AffixCategory.INDEFINITE,
}


def strip_tsheg(surface: str) -> str:
    return surface.rstrip("".join(TSHEG_CHARS))


# -- Table shape --------------------------------------------------------------
def test_tables_are_populated() -> None:
    assert len(UNAMBIGUOUS_AFFIXES) >= 40
    assert len(AMBIGUOUS_AFFIXES) >= 15
    assert len(FUSED_AFFIXES) >= 3


def test_the_two_tables_are_disjoint() -> None:
    """A surface is either reliably grammatical or it is not; never both."""
    overlap = set(UNAMBIGUOUS_AFFIXES) & set(AMBIGUOUS_AFFIXES)
    assert not overlap, overlap


@pytest.mark.parametrize("table_name", ["UNAMBIGUOUS_AFFIXES", "AMBIGUOUS_AFFIXES"])
def test_every_entry_maps_to_a_non_empty_category_set(table_name: str) -> None:
    table = {"UNAMBIGUOUS_AFFIXES": UNAMBIGUOUS_AFFIXES, "AMBIGUOUS_AFFIXES": AMBIGUOUS_AFFIXES}[
        table_name
    ]
    for surface, categories in table.items():
        assert categories, surface
        assert all(isinstance(c, AffixCategory) for c in categories), surface


@pytest.mark.parametrize("table_name", ["UNAMBIGUOUS_AFFIXES", "AMBIGUOUS_AFFIXES"])
def test_surfaces_are_pure_tibetan_without_a_trailing_tsheg(table_name: str) -> None:
    """Lookup keys are stored stripped; a trailing tsheg would break every lookup.

    An *internal* tsheg is legitimate: a handful of attested particles span more
    than one syllable.
    """
    table = {"UNAMBIGUOUS_AFFIXES": UNAMBIGUOUS_AFFIXES, "AMBIGUOUS_AFFIXES": AMBIGUOUS_AFFIXES}[
        table_name
    ]
    for surface in table:
        assert surface, "empty surface"
        assert surface[0] not in TSHEG_CHARS, surface
        assert surface[-1] not in TSHEG_CHARS, surface
        assert all(is_tibetan_char(c) for c in surface), surface


def test_multi_syllable_entries_are_a_known_unreachable_limitation() -> None:
    """Documents a real gap rather than hiding it.

    A few attested particles span two syllables (``ན་རེ``, ``ཞེས་པ``). The
    analyzer keys its lookup on syllables, and the segmenter splits at every
    tsheg, so these entries can never match. They are kept in the tables because
    they are genuine corpus-derived data, and matching them needs longest-match
    disambiguation against the far more frequent single-syllable ``ན``
    (locative, n=606 vs n=64) -- a frequency judgement that belongs with Stage
    7's context model, not here.

    This test pins the current extent of the gap: if it grows, that is a signal
    to implement multi-syllable matching.
    """
    all_surfaces = set(UNAMBIGUOUS_AFFIXES) | set(AMBIGUOUS_AFFIXES)
    unreachable = {s for s in all_surfaces if set(s) & TSHEG_CHARS}
    assert len(unreachable) <= 4, unreachable
    # Every other entry is a single syllable and therefore reachable.
    assert len(all_surfaces - unreachable) >= 55


# -- Fused affixes ------------------------------------------------------------
def test_fused_affixes_all_begin_with_a_chung() -> None:
    """Their shape is what makes stripping them safe.

    A-chung carrying only a vowel sign cannot begin an independent syllable, so
    a trailing occurrence is necessarily an affix rather than the start of a new
    root.
    """
    for sequence, _ in FUSED_AFFIXES:
        assert sequence.startswith(A_CHUNG), sequence
        assert len(sequence) == 2, sequence


def test_fused_sequences_are_mutually_exclusive() -> None:
    """No sequence may be a suffix of another, or splitting would be order-dependent."""
    sequences = [sequence for sequence, _ in FUSED_AFFIXES]
    assert len(sequences) == len(set(sequences))
    for outer in sequences:
        for inner in sequences:
            if outer is not inner:
                assert not outer.endswith(inner), (outer, inner)


def test_the_fused_genitive_is_also_attested_standalone() -> None:
    """``འི`` appears both fused and as its own token in the corpus."""
    genitive = next(seq for seq, cat in FUSED_AFFIXES if cat is AffixCategory.GENITIVE)
    assert lookup(genitive) == (frozenset({AffixCategory.GENITIVE}), False)


@pytest.mark.parametrize("consonant", ["ས", "ར"])
def test_ambiguous_consonantal_affixes_are_deliberately_not_fused(consonant: str) -> None:
    """The agentive ``ས`` and terminative ``ར`` fuse too, but cannot be split safely.

    ``ལས`` is the ablative particle rather than ``ལ`` + agentive, and ``སངས`` is
    a root. Resolving them needs the Dictionary Repository that Figure 2 places
    in the Persistence layer, which is not yet implemented.
    """
    assert consonant not in {sequence for sequence, _ in FUSED_AFFIXES}
    # They remain recognisable as free-standing particles, however.
    assert lookup(consonant) is not None


# -- lookup() -----------------------------------------------------------------
def test_lookup_reports_unambiguous_entries_as_confident() -> None:
    for surface, categories in UNAMBIGUOUS_AFFIXES.items():
        assert lookup(surface) == (categories, False)


def test_lookup_reports_mixed_entries_as_ambiguous() -> None:
    for surface, categories in AMBIGUOUS_AFFIXES.items():
        assert lookup(surface) == (categories, True)


def test_lookup_returns_none_for_unattested_surfaces() -> None:
    assert lookup("ཁྱིམ") is None  # "house", a plain noun
    assert lookup("") is None
    assert lookup("zzz") is None


def test_lookup_does_not_strip_tsheg_itself() -> None:
    """Callers normalise before lookup; documenting that contract explicitly."""
    genitive = next(seq for seq, cat in FUSED_AFFIXES if cat is AffixCategory.GENITIVE)
    assert lookup(genitive) is not None
    assert lookup(genitive + "་") is None


# -- Agreement with the annotated corpus --------------------------------------
def test_every_table_entry_agrees_with_the_corpus_annotation(
    tagged_corpus: list[list[tuple[str, str]]],
) -> None:
    """Where a table surface occurs in the sample, categories must line up.

    This is the check that the generated tables still describe the data they
    were derived from.
    """
    checked = 0
    for line in tagged_corpus:
        for surface, tag in line:
            key = strip_tsheg(surface)
            base = tag.split("~")[0]
            expected = TAG_TO_CATEGORY.get(base)
            if expected is None:
                continue
            entry = lookup(key)
            if entry is None:
                continue
            categories, _ = entry
            assert expected in categories, (key, base, categories)
            checked += 1

    assert checked > 500, f"expected substantial overlap with the sample, got {checked}"


def test_frequent_corpus_particles_are_all_in_the_inventory(
    tagged_corpus: list[list[tuple[str, str]]],
) -> None:
    """Recall check: nothing common may be missing from the tables."""
    counts: dict[str, int] = {}
    for line in tagged_corpus:
        for surface, tag in line:
            if tag.split("~")[0] in TAG_TO_CATEGORY:
                key = strip_tsheg(surface)
                counts[key] = counts.get(key, 0) + 1

    missing = sorted(s for s, n in counts.items() if n >= 10 and lookup(s) is None)
    assert not missing, missing


def test_the_ambiguous_table_really_is_ambiguous_in_the_corpus(
    tagged_corpus: list[list[tuple[str, str]]],
) -> None:
    """Every AMBIGUOUS entry must be observed with a non-grammatical tag.

    Otherwise it belongs in the confident table and is being under-reported.
    """
    observed: dict[str, set[str]] = {}
    for line in tagged_corpus:
        for surface, tag in line:
            observed.setdefault(strip_tsheg(surface), set()).add(tag.split("~")[0])

    # Purity was measured over the full 60,544-token corpus; this 5,015-token
    # excerpt need not exhibit every surface's non-grammatical use. What must
    # hold is that the phenomenon is real and visible in the sample.
    mixed_in_sample = [
        surface
        for surface in AMBIGUOUS_AFFIXES
        if (tags := observed.get(surface))
        and any(tag in TAG_TO_CATEGORY for tag in tags)
        and any(tag not in TAG_TO_CATEGORY for tag in tags)
    ]
    assert len(mixed_in_sample) >= 5, mixed_in_sample


def test_confident_entries_are_never_mixed_in_the_sample(
    tagged_corpus: list[list[tuple[str, str]]],
) -> None:
    """The converse guard: nothing in the confident table is badly impure here.

    A confident surface may still show the occasional non-grammatical tag -- the
    threshold is 90%, not 100% -- so this checks the rate rather than forbidding
    it outright.
    """
    grammatical: dict[str, int] = {}
    total: dict[str, int] = {}
    for line in tagged_corpus:
        for surface, tag in line:
            key = strip_tsheg(surface)
            total[key] = total.get(key, 0) + 1
            if tag.split("~")[0] in TAG_TO_CATEGORY:
                grammatical[key] = grammatical.get(key, 0) + 1

    offenders = [
        (surface, grammatical.get(surface, 0), total[surface])
        for surface in UNAMBIGUOUS_AFFIXES
        if total.get(surface, 0) >= 20 and grammatical.get(surface, 0) / total[surface] < 0.75
    ]
    assert not offenders, offenders
