"""Unit tests for the Stage 7 domain models (:mod:`teea.nlp.postagging.models`).

Stage 7 is where the pipeline commits to an answer: Stage 6 reports that ``མི``
*could* be the negation particle, and this stage decides that here it is the noun
"person". Two things have to be true for that commitment to be usable downstream.

First, the two levels of granularity must never disagree. Every tagged morpheme
carries both the verbatim corpus tag (which Stage 8 needs, because ``case.agn``
and ``case.gen`` imply different argument structures) and the coarse Figure 5
class (which plugins and the add-in reason about). If ``category`` could drift
away from ``tag``, a grammar checker asking for the verbs would silently get the
wrong set, so :class:`TaggedMorpheme` enforces the correspondence in a validator
rather than trusting its constructor. These tests build the models **directly**,
so that validator is what is under test.

Second, the span discipline every TEEA stage maintains must survive tagging:
``source[span.char_start:span.char_end] == morpheme.text``. Offsets that lie are
worse than no offsets, because the add-in uses them to place suggestions on Word
ranges.

The mapping function gets the most attention here for one structural reason: it
is a prefix table, and the corpus contains deverbal-noun tags (``n.v.*``) whose
correct class is VERB. A naive implementation ordered by tag length, or by
insertion, maps those to NOUN, and nothing downstream would notice.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from teea.core.types import TSHEG, TextSpan, utf8_byte_offsets
from teea.nlp.morphology import (
    AffixCategory,
    Morpheme,
    MorphemeKind,
    TibetanMorphologicalAnalyzer,
)
from teea.nlp.postagging import (
    PosCategory,
    TaggedMorpheme,
    TaggedText,
    coarse_category,
)
from teea.persistence import InMemoryDictionaryRepository

# Real Tibetan; three UTF-8 bytes per code point, so any confusion between
# character and byte offsets shows up immediately.
KHYIM = "ཁྱིམ"  # "house"
MI = "མི"  # "person", and also the negation particle -- genuinely ambiguous
GEN = "འི"  # fused genitive
MI_GEN = MI + GEN  # མིའི -- host with fused genitive

GENITIVE = frozenset({AffixCategory.GENITIVE})
NEGATION = frozenset({AffixCategory.NEGATION})

#: The two corpus tags whose documented meaning is "unanalysed material".
UNANALYSED_TAGS = frozenset({"skt", "dunno"})


# -- Helpers ------------------------------------------------------------------
def span_for(source: str, start: int, end: int) -> TextSpan:
    """Build the exact span of ``source[start:end]``, characters and bytes."""
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
    """Build a valid Stage 6 Morpheme for ``source[start:end]``."""
    return Morpheme(
        text=source[start:end],
        span=span_for(source, start, end),
        kind=kind,
        categories=categories,
        is_fused=is_fused,
    )


def make_tagged(
    source: str,
    start: int,
    end: int,
    tag: str,
    *,
    kind: MorphemeKind = MorphemeKind.ROOT,
    categories: frozenset[AffixCategory] = frozenset(),
    is_fused: bool = False,
    was_ambiguous: bool = False,
) -> TaggedMorpheme:
    """Build a consistently tagged morpheme, deriving the coarse class."""
    return TaggedMorpheme(
        morpheme=make_morpheme(
            source, start, end, kind=kind, categories=categories, is_fused=is_fused
        ),
        tag=tag,
        category=coarse_category(tag),
        was_ambiguous=was_ambiguous,
    )


# -- PosCategory --------------------------------------------------------------
def test_pos_category_values_are_unique() -> None:
    values = [member.value for member in PosCategory]
    assert len(values) == len(set(values))


# -- coarse_category: the Figure 5 classes ------------------------------------
@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        # Nouns: common, proper, relational.
        ("n.count", PosCategory.NOUN),
        ("n.prop", PosCategory.NOUN),
        ("n.rel", PosCategory.NOUN),
        # Verbs, including the tense distinctions Stage 8 depends on.
        ("v.past", PosCategory.VERB),
        ("v.pres", PosCategory.VERB),
        ("v.invar", PosCategory.VERB),
        ("adj", PosCategory.ADJECTIVE),
        # "Particle & grammatical classes": case markers, converbs, clitics,
        # and negation all collapse to one class for plugin consumers.
        ("case.gen", PosCategory.PARTICLE),
        ("cv.sem", PosCategory.PARTICLE),
        ("cl.focus", PosCategory.PARTICLE),
        ("neg", PosCategory.PARTICLE),
        ("p.pers", PosCategory.PRONOUN),
        ("num.card", PosCategory.NUMERAL),
        ("adv.temp", PosCategory.ADVERB),
        ("d.dem", PosCategory.DETERMINER),
        ("d.indef", PosCategory.DETERMINER),
        ("punc", PosCategory.PUNCTUATION),
        # Deliberately not forced into a real class: guessing would mislead
        # Stage 8 more than admitting ignorance does.
        ("skt", PosCategory.UNKNOWN),
        ("dunno", PosCategory.UNKNOWN),
    ],
)
def test_corpus_tags_map_to_their_figure_5_class(tag: str, expected: PosCategory) -> None:
    assert coarse_category(tag) is expected


# -- coarse_category: longest-prefix ordering ---------------------------------
@pytest.mark.parametrize("tag", ["n.v.past", "n.v.invar"])
def test_deverbal_tags_are_verbs_not_nouns(tag: str) -> None:
    """The prefix table must be tested longest-first.

    ``n.v.*`` marks a form the corpus analyses as verbal despite the leading
    ``n.``. A prefix table that tests ``n.`` before ``n.v.`` maps these to NOUN,
    and every consumer asking for the verbs of a sentence quietly loses them.
    """
    assert coarse_category(tag) is PosCategory.VERB
    assert coarse_category(tag) is not PosCategory.NOUN


def test_the_bare_prefix_still_wins_for_ordinary_nouns() -> None:
    """The ordering fix must not overreach: plain ``n.`` tags stay nouns."""
    assert coarse_category("n.count") is PosCategory.NOUN


# -- coarse_category: graceful degradation ------------------------------------
@pytest.mark.parametrize(
    "tag",
    [
        "",  # no tag at all
        "n",  # a prefix family name without its separator
        "case",  # ditto
        "N.COUNT",  # the mapping is case-sensitive
        "wholly.invented",  # a tag from some future corpus revision
    ],
)
def test_an_unrecognised_tag_degrades_to_unknown(tag: str) -> None:
    """A corpus revision must not be able to take the daemon down."""
    assert coarse_category(tag) is PosCategory.UNKNOWN


# -- coarse_category: totality over the shipped tagset ------------------------
def test_every_shipped_tag_maps_to_a_category(
    dictionary: InMemoryDictionaryRepository,
) -> None:
    """The mapping is total over the tagset actually shipped, not a sample."""
    assert len(dictionary.tags) == 77, "premise: the shipped corpus tagset"
    assert all(isinstance(coarse_category(tag), PosCategory) for tag in dictionary.tags)


def test_every_figure_5_class_is_reachable_from_the_shipped_tagset(
    dictionary: InMemoryDictionaryRepository,
) -> None:
    """No coarse class is dead weight: the corpus witnesses all of them."""
    reached = {coarse_category(tag) for tag in dictionary.tags}
    assert reached == set(PosCategory)


# Regression guard: 'interj' once fell through the prefix loop to UNKNOWN, so 29
# analysed corpus tokens were reported to Stage 8 as unanalysable and UNKNOWN
# silently meant two different things. It now has its own class.
def test_only_the_unanalysed_markers_fall_through_to_unknown(
    dictionary: InMemoryDictionaryRepository,
) -> None:
    """UNKNOWN must mean "the corpus did not analyse this", not "we have no class"."""
    unknown = {tag for tag in dictionary.tags if coarse_category(tag) is PosCategory.UNKNOWN}
    assert unknown == UNANALYSED_TAGS


def test_interjection_has_its_own_class(dictionary: InMemoryDictionaryRepository) -> None:
    """An interjection is a real word class, not unanalysed material."""
    assert "interj" in dictionary.tags
    assert coarse_category("interj") is PosCategory.INTERJECTION


# -- TaggedMorpheme: validation -----------------------------------------------
def test_valid_tagged_morpheme_constructs() -> None:
    tagged = make_tagged(KHYIM, 0, len(KHYIM), "n.count")
    assert tagged.tag == "n.count"
    assert tagged.category is PosCategory.NOUN
    assert tagged.morpheme.kind is MorphemeKind.ROOT


def test_wrapping_a_real_stage_6_morpheme_constructs(
    morphological_analyzer: TibetanMorphologicalAnalyzer,
    corpus_sentences: list[str],
) -> None:
    """Stage 6 output feeds Stage 7 unchanged -- no re-derivation of offsets."""
    analysis = morphological_analyzer.analyze(corpus_sentences[0])
    assert analysis.morphemes, "premise: the corpus sentence analyses"
    morpheme = analysis.morphemes[0]

    tagged = TaggedMorpheme(
        morpheme=morpheme,
        tag="n.count",
        category=PosCategory.NOUN,
        was_ambiguous=morpheme.is_ambiguous,
    )

    assert tagged.morpheme is morpheme
    assert analysis.source[tagged.span.char_start : tagged.span.char_end] == tagged.text


def test_empty_tag_is_rejected() -> None:
    with pytest.raises(ValidationError, match="tag must not be empty"):
        TaggedMorpheme(
            morpheme=make_morpheme(KHYIM, 0, len(KHYIM)),
            tag="",
            category=PosCategory.UNKNOWN,
        )


@pytest.mark.parametrize(
    ("tag", "wrong_category"),
    [
        ("n.count", PosCategory.VERB),
        ("n.v.past", PosCategory.NOUN),  # the longest-prefix trap, as data
        ("case.gen", PosCategory.NOUN),
        ("punc", PosCategory.PARTICLE),
        ("skt", PosCategory.NOUN),
    ],
)
def test_a_category_inconsistent_with_its_tag_is_rejected(
    tag: str, wrong_category: PosCategory
) -> None:
    """The module's key invariant: the two granularities cannot disagree."""
    with pytest.raises(ValidationError, match="does not match tag"):
        TaggedMorpheme(
            morpheme=make_morpheme(KHYIM, 0, len(KHYIM)),
            tag=tag,
            category=wrong_category,
        )


# -- TaggedMorpheme: delegation and defaults ----------------------------------
def test_text_and_span_delegate_to_the_wrapped_morpheme() -> None:
    morpheme = make_morpheme(
        MI_GEN, len(MI), len(MI_GEN), kind=MorphemeKind.AFFIX, categories=GENITIVE, is_fused=True
    )
    tagged = TaggedMorpheme(morpheme=morpheme, tag="case.gen", category=PosCategory.PARTICLE)

    assert tagged.text == morpheme.text == GEN
    assert tagged.span == morpheme.span


def test_was_ambiguous_defaults_to_false() -> None:
    assert not make_tagged(KHYIM, 0, len(KHYIM), "n.count").was_ambiguous


@pytest.mark.parametrize("was_ambiguous", [True, False])
def test_was_ambiguous_round_trips(was_ambiguous: bool) -> None:
    """The audit trail recording that this stage made a real choice."""
    tagged = make_tagged(
        MI,
        0,
        len(MI),
        "n.count",
        kind=MorphemeKind.AMBIGUOUS,
        categories=NEGATION,
        was_ambiguous=was_ambiguous,
    )
    assert tagged.was_ambiguous is was_ambiguous


# -- TaggedMorpheme: value semantics ------------------------------------------
def test_tagged_morpheme_is_frozen() -> None:
    tagged = make_tagged(KHYIM, 0, len(KHYIM), "n.count")
    with pytest.raises(ValidationError):
        tagged.tag = "v.past"  # type: ignore[misc]


def test_tagged_morpheme_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        TaggedMorpheme(
            morpheme=make_morpheme(KHYIM, 0, len(KHYIM)),
            tag="n.count",
            category=PosCategory.NOUN,
            confidence=0.9,  # type: ignore[call-arg]
        )


def test_tagged_morphemes_compare_by_value_and_are_hashable() -> None:
    first = make_tagged(KHYIM, 0, len(KHYIM), "n.count")
    second = make_tagged(KHYIM, 0, len(KHYIM), "n.count")
    other = make_tagged(KHYIM, 0, len(KHYIM), "n.prop")

    assert first == second
    assert first != other
    assert len({first, second, other}) == 2


# -- TaggedText: validation ---------------------------------------------------
def test_empty_tagged_text_is_valid() -> None:
    """An empty sentence must yield an empty result, not an error."""
    tagged_text = TaggedText(source="")
    assert len(tagged_text) == 0
    assert tagged_text.num_morphemes == 0
    assert tagged_text.tags == ()
    assert tagged_text.categories == ()
    assert tagged_text.num_resolved == 0


def test_overlapping_morphemes_are_rejected() -> None:
    first = make_tagged(MI_GEN, 0, 3, "n.count")
    second = make_tagged(MI_GEN, 2, 4, "case.gen")
    with pytest.raises(ValidationError, match="must not overlap"):
        TaggedText(source=MI_GEN, morphemes=(first, second))


def test_span_beyond_the_source_is_rejected() -> None:
    longer = MI_GEN + KHYIM
    stray = make_tagged(longer, 0, len(longer), "n.count")
    with pytest.raises(ValidationError, match="exceeds the source text"):
        TaggedText(source=MI_GEN, morphemes=(stray,))


def test_span_that_does_not_select_its_own_text_is_rejected() -> None:
    """The invariant the add-in's range mapping rests on."""
    source = MI + KHYIM
    lying = TaggedMorpheme(
        morpheme=Morpheme(
            text=KHYIM,
            span=span_for(source, 0, len(KHYIM)),  # points at MI + part of KHYIM
            kind=MorphemeKind.ROOT,
        ),
        tag="n.count",
        category=PosCategory.NOUN,
    )
    with pytest.raises(ValidationError, match="does not select its own text"):
        TaggedText(source=source, morphemes=(lying,))


# -- TaggedText: accessors ----------------------------------------------------
@pytest.fixture
def house_of_the_person() -> TaggedText:
    """``ཁྱིམ་མིའི`` -- two nouns and a fused genitive, with a tsheg gap.

    ``མི`` is exactly the case Stage 7 exists for: Stage 6 flagged it as a
    possible negation particle and refused to guess, and this stage resolved it
    to the noun "person", recording that a real decision was made.
    """
    source = KHYIM + TSHEG + MI_GEN
    house = make_tagged(source, 0, len(KHYIM), "n.count")
    person = make_tagged(
        source,
        len(KHYIM) + 1,
        len(KHYIM) + 1 + len(MI),
        "n.count",
        kind=MorphemeKind.AMBIGUOUS,
        categories=NEGATION,
        was_ambiguous=True,
    )
    genitive = make_tagged(
        source,
        len(KHYIM) + 1 + len(MI),
        len(source),
        "case.gen",
        kind=MorphemeKind.AFFIX,
        categories=GENITIVE,
        is_fused=True,
    )
    return TaggedText(source=source, morphemes=(house, person, genitive))


def test_length_accessors_agree(house_of_the_person: TaggedText) -> None:
    assert len(house_of_the_person) == house_of_the_person.num_morphemes == 3


def test_tags_and_categories_agree_and_preserve_order(
    house_of_the_person: TaggedText,
) -> None:
    """Both granularities are exposed per morpheme, in document order."""
    assert house_of_the_person.tags == ("n.count", "n.count", "case.gen")
    assert house_of_the_person.categories == (
        PosCategory.NOUN,
        PosCategory.NOUN,
        PosCategory.PARTICLE,
    )
    assert house_of_the_person.categories == tuple(
        coarse_category(tag) for tag in house_of_the_person.tags
    )


def test_num_resolved_counts_only_the_ambiguous_morphemes(
    house_of_the_person: TaggedText,
) -> None:
    """The stage's own report of how much work it actually did."""
    assert house_of_the_person.num_resolved == 1
    assert house_of_the_person.num_resolved < house_of_the_person.num_morphemes


def test_of_category_returns_that_class_in_order(house_of_the_person: TaggedText) -> None:
    house, person, genitive = house_of_the_person.morphemes

    assert house_of_the_person.of_category(PosCategory.NOUN) == (house, person)
    assert house_of_the_person.of_category(PosCategory.PARTICLE) == (genitive,)


def test_of_category_is_empty_for_an_absent_class(house_of_the_person: TaggedText) -> None:
    """A grammar checker asking for verbs of a verbless phrase gets nothing, not None."""
    assert house_of_the_person.of_category(PosCategory.VERB) == ()


def test_of_category_partitions_the_morphemes(house_of_the_person: TaggedText) -> None:
    total = sum(len(house_of_the_person.of_category(category)) for category in PosCategory)
    assert total == house_of_the_person.num_morphemes


# -- TaggedText: morpheme_at_char ---------------------------------------------
def test_morpheme_at_char_finds_the_covering_morpheme(
    house_of_the_person: TaggedText,
) -> None:
    house, person, genitive = house_of_the_person.morphemes

    assert house_of_the_person.morpheme_at_char(0) is house
    assert house_of_the_person.morpheme_at_char(person.span.char_start) is person
    assert house_of_the_person.morpheme_at_char(genitive.span.char_start) is genitive


def test_morpheme_at_char_is_half_open_at_both_boundaries(
    house_of_the_person: TaggedText,
) -> None:
    """char_start is inside; char_end belongs to whatever comes next."""
    _, person, genitive = house_of_the_person.morphemes

    assert house_of_the_person.morpheme_at_char(person.span.char_start) is person
    assert house_of_the_person.morpheme_at_char(person.span.char_end - 1) is person
    assert house_of_the_person.morpheme_at_char(person.span.char_end) is genitive


def test_morpheme_at_char_returns_none_in_a_delimiter_gap(
    house_of_the_person: TaggedText,
) -> None:
    """The tsheg between two syllables belongs to no morpheme."""
    gap = len(KHYIM)
    assert house_of_the_person.source[gap] == TSHEG, "premise: the gap is the tsheg"
    assert house_of_the_person.morpheme_at_char(gap) is None


@pytest.mark.parametrize("offset", [-1, -10_000])
def test_morpheme_at_char_returns_none_for_negative_offsets(
    house_of_the_person: TaggedText, offset: int
) -> None:
    """Never index backwards from the end, the way a bare slice would."""
    assert house_of_the_person.morpheme_at_char(offset) is None


def test_morpheme_at_char_returns_none_past_the_end(house_of_the_person: TaggedText) -> None:
    end = len(house_of_the_person.source)
    assert house_of_the_person.morpheme_at_char(end) is None
    assert house_of_the_person.morpheme_at_char(10_000) is None
