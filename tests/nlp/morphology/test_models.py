"""Unit tests for the Stage 6 domain models (:mod:`teea.nlp.morphology.models`).

These models carry Figure 5's three Stage-6 outputs -- extracted roots,
recognized affixes, and the grammatical function of each affix -- to every stage
that follows. The tests construct :class:`Morpheme` and
:class:`MorphologicalAnalysis` **directly** rather than through the analyzer, so
the validators themselves are what is under test.

The invariant carrying the most weight is the same one every TEEA stage
maintains: ``source[span.char_start:span.char_end] == morpheme.text``. Offsets
that lie are worse than no offsets, because the add-in uses them to place
suggestions on Word ranges.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from teea.core.types import TextSpan, utf8_byte_offsets
from teea.nlp.morphology import (
    AffixCategory,
    Morpheme,
    MorphemeKind,
    MorphologicalAnalysis,
)

# Real Tibetan; three UTF-8 bytes per code point, so any confusion between
# character and byte offsets shows up immediately.
MI = "མི"  # host syllable
GEN = "འི"  # fused genitive
MI_GEN = MI + GEN  # མིའི -- host with fused genitive
KHYIM = "ཁྱིམ"  # "house"


# -- Helpers ------------------------------------------------------------------
def span_for(source: str, start: int, end: int) -> TextSpan:
    offsets = utf8_byte_offsets(source)
    return TextSpan(
        char_start=start,
        char_end=end,
        byte_start=offsets[start],
        byte_end=offsets[end],
    )


def make_morpheme(
    source: str,
    start: int,
    end: int,
    *,
    kind: MorphemeKind = MorphemeKind.ROOT,
    categories: frozenset[AffixCategory] = frozenset(),
    is_fused: bool = False,
) -> Morpheme:
    """Build a valid Morpheme for ``source[start:end]`` with exact offsets."""
    return Morpheme(
        text=source[start:end],
        span=span_for(source, start, end),
        kind=kind,
        categories=categories,
        is_fused=is_fused,
    )


GENITIVE = frozenset({AffixCategory.GENITIVE})


# -- Enumerations -------------------------------------------------------------
def test_affix_category_values_are_unique() -> None:
    values = [member.value for member in AffixCategory]
    assert len(values) == len(set(values))


def test_morpheme_kind_values_are_unique() -> None:
    values = [member.value for member in MorphemeKind]
    assert len(values) == len(set(values))


# -- Morpheme: validation -----------------------------------------------------
def test_valid_root_constructs() -> None:
    morpheme = make_morpheme(KHYIM, 0, len(KHYIM))
    assert morpheme.text == KHYIM
    assert morpheme.kind is MorphemeKind.ROOT
    assert morpheme.categories == frozenset()


def test_valid_affix_constructs() -> None:
    morpheme = make_morpheme(
        MI_GEN, len(MI), len(MI_GEN), kind=MorphemeKind.AFFIX, categories=GENITIVE, is_fused=True
    )
    assert morpheme.text == GEN
    assert morpheme.is_fused


def test_empty_text_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must not be empty"):
        Morpheme(text="", span=span_for("", 0, 0), kind=MorphemeKind.ROOT)


def test_char_length_mismatch_is_rejected() -> None:
    with pytest.raises(ValidationError, match="does not match span char_length"):
        Morpheme(
            text=KHYIM,
            span=span_for(KHYIM, 0, len(KHYIM) - 1),
            kind=MorphemeKind.ROOT,
        )


def test_byte_length_mismatch_is_rejected() -> None:
    """Char length can agree while byte length does not -- Tibetan is 3 bytes/char."""
    assert len(KHYIM.encode("utf-8")) == 3 * len(KHYIM), "premise: 3 bytes per char"
    bad = TextSpan(char_start=0, char_end=len(KHYIM), byte_start=0, byte_end=len(KHYIM))
    with pytest.raises(ValidationError, match="UTF-8 length does not match"):
        Morpheme(text=KHYIM, span=bad, kind=MorphemeKind.ROOT)


def test_a_root_must_not_carry_categories() -> None:
    with pytest.raises(ValidationError, match="root morpheme must not carry"):
        make_morpheme(KHYIM, 0, len(KHYIM), kind=MorphemeKind.ROOT, categories=GENITIVE)


@pytest.mark.parametrize("kind", [MorphemeKind.AFFIX, MorphemeKind.AMBIGUOUS])
def test_a_non_root_must_carry_at_least_one_category(kind: MorphemeKind) -> None:
    with pytest.raises(ValidationError, match="must carry at least one category"):
        make_morpheme(GEN, 0, len(GEN), kind=kind)


def test_only_an_affix_can_be_fused() -> None:
    with pytest.raises(ValidationError, match="only an affix can be fused"):
        make_morpheme(KHYIM, 0, len(KHYIM), kind=MorphemeKind.ROOT, is_fused=True)


# -- Morpheme: behaviour ------------------------------------------------------
def test_is_affix_covers_both_confident_and_ambiguous() -> None:
    """An ambiguous surface is still a candidate affix."""
    affix = make_morpheme(GEN, 0, len(GEN), kind=MorphemeKind.AFFIX, categories=GENITIVE)
    ambiguous = make_morpheme(GEN, 0, len(GEN), kind=MorphemeKind.AMBIGUOUS, categories=GENITIVE)
    root = make_morpheme(KHYIM, 0, len(KHYIM))

    assert affix.is_affix and ambiguous.is_affix
    assert not root.is_affix
    assert ambiguous.is_ambiguous
    assert not affix.is_ambiguous
    assert not root.is_ambiguous


def test_category_returns_the_single_reading_when_unambiguous() -> None:
    morpheme = make_morpheme(GEN, 0, len(GEN), kind=MorphemeKind.AFFIX, categories=GENITIVE)
    assert morpheme.category is AffixCategory.GENITIVE


def test_category_is_none_when_syncretic() -> None:
    """``ཅིག`` is both an imperative marker and an indefinite determiner."""
    both = frozenset({AffixCategory.IMPERATIVE, AffixCategory.INDEFINITE})
    morpheme = make_morpheme(GEN, 0, len(GEN), kind=MorphemeKind.AFFIX, categories=both)
    assert morpheme.category is None
    assert len(morpheme.categories) == 2


def test_category_is_none_for_a_root() -> None:
    assert make_morpheme(KHYIM, 0, len(KHYIM)).category is None


# -- Morpheme: value semantics ------------------------------------------------
def test_morpheme_is_frozen() -> None:
    morpheme = make_morpheme(KHYIM, 0, len(KHYIM))
    with pytest.raises(ValidationError):
        morpheme.kind = MorphemeKind.AFFIX  # type: ignore[misc]


def test_morpheme_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Morpheme(
            text=KHYIM,
            span=span_for(KHYIM, 0, len(KHYIM)),
            kind=MorphemeKind.ROOT,
            unexpected="x",  # type: ignore[call-arg]
        )


def test_morphemes_compare_by_value_and_are_hashable() -> None:
    first = make_morpheme(KHYIM, 0, len(KHYIM))
    second = make_morpheme(KHYIM, 0, len(KHYIM))
    assert first == second
    assert len({first, second}) == 1


# -- MorphologicalAnalysis: validation ----------------------------------------
def test_empty_analysis_is_valid() -> None:
    analysis = MorphologicalAnalysis(source="")
    assert analysis.num_morphemes == 0
    assert len(analysis) == 0
    assert analysis.root_text == ""
    assert not analysis.has_ambiguity


def test_overlapping_morphemes_are_rejected() -> None:
    source = MI_GEN
    first = make_morpheme(source, 0, 3)
    second = make_morpheme(source, 2, 4)
    with pytest.raises(ValidationError, match="must not overlap"):
        MorphologicalAnalysis(source=source, morphemes=(first, second))


def test_span_beyond_the_source_is_rejected() -> None:
    longer = MI_GEN + KHYIM
    stray = make_morpheme(longer, 0, len(longer))
    with pytest.raises(ValidationError, match="exceeds the source text"):
        MorphologicalAnalysis(source=MI_GEN, morphemes=(stray,))


def test_span_that_does_not_select_its_own_text_is_rejected() -> None:
    """The single most important invariant in the module."""
    source = MI + KHYIM
    lying = Morpheme(
        text=KHYIM,
        span=span_for(source, 0, len(KHYIM)),  # points at MI + part of KHYIM
        kind=MorphemeKind.ROOT,
    )
    with pytest.raises(ValidationError, match="does not select its own text"):
        MorphologicalAnalysis(source=source, morphemes=(lying,))


# -- MorphologicalAnalysis: accessors -----------------------------------------
@pytest.fixture
def host_plus_genitive() -> MorphologicalAnalysis:
    """``མིའི`` analysed as root ``མི`` plus fused genitive ``འི``."""
    source = MI_GEN
    root = make_morpheme(source, 0, len(MI))
    affix = make_morpheme(
        source,
        len(MI),
        len(source),
        kind=MorphemeKind.AFFIX,
        categories=GENITIVE,
        is_fused=True,
    )
    return MorphologicalAnalysis(source=source, morphemes=(root, affix))


def test_roots_and_affixes_partition_the_morphemes(
    host_plus_genitive: MorphologicalAnalysis,
) -> None:
    analysis = host_plus_genitive
    assert len(analysis.roots) == 1
    assert len(analysis.affixes) == 1
    assert len(analysis.roots) + len(analysis.affixes) == analysis.num_morphemes


def test_root_text_strips_the_affixes(host_plus_genitive: MorphologicalAnalysis) -> None:
    """Figure 5: *root extraction*."""
    assert host_plus_genitive.root_text == MI
    assert GEN not in host_plus_genitive.root_text


def test_categories_collects_every_function_present(
    host_plus_genitive: MorphologicalAnalysis,
) -> None:
    assert host_plus_genitive.categories == GENITIVE


def test_categories_is_empty_when_there_are_no_affixes() -> None:
    source = KHYIM
    analysis = MorphologicalAnalysis(
        source=source, morphemes=(make_morpheme(source, 0, len(source)),)
    )
    assert analysis.categories == frozenset()


def test_has_ambiguity_reflects_ambiguous_morphemes() -> None:
    source = MI_GEN
    ambiguous = make_morpheme(source, 0, len(MI), kind=MorphemeKind.AMBIGUOUS, categories=GENITIVE)
    analysis = MorphologicalAnalysis(source=source, morphemes=(ambiguous,))
    assert analysis.has_ambiguity


def test_length_accessors_agree(host_plus_genitive: MorphologicalAnalysis) -> None:
    assert len(host_plus_genitive) == host_plus_genitive.num_morphemes == 2


# -- morpheme_at_char ---------------------------------------------------------
def test_morpheme_at_char_finds_the_covering_morpheme(
    host_plus_genitive: MorphologicalAnalysis,
) -> None:
    root, affix = host_plus_genitive.morphemes
    assert host_plus_genitive.morpheme_at_char(0) is root
    assert host_plus_genitive.morpheme_at_char(len(MI)) is affix


def test_morpheme_at_char_is_half_open(host_plus_genitive: MorphologicalAnalysis) -> None:
    root = host_plus_genitive.morphemes[0]
    assert host_plus_genitive.morpheme_at_char(root.span.char_start) is root
    assert host_plus_genitive.morpheme_at_char(root.span.char_end - 1) is root
    # char_end belongs to the next morpheme, not this one.
    assert host_plus_genitive.morpheme_at_char(root.span.char_end) is not root


def test_morpheme_at_char_returns_none_out_of_range(
    host_plus_genitive: MorphologicalAnalysis,
) -> None:
    assert host_plus_genitive.morpheme_at_char(len(MI_GEN)) is None
    assert host_plus_genitive.morpheme_at_char(-1) is None
    assert host_plus_genitive.morpheme_at_char(10_000) is None
