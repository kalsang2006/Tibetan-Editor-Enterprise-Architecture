"""Unit and corpus-evaluation tests for :mod:`teea.nlp.morphology.analyzer`.

Two halves.

The first pins behaviour on small, hand-checked inputs: boundary rules, the
inventory-before-splitting ordering, span exactness, and the deliberate refusals.

The second is a genuine **evaluation against gold annotations**. The reference
corpus separates every grammatical morpheme into its own token, so concatenating
the surfaces yields running Tibetan whose correct morpheme boundaries are known.
Running the analyzer over that text and comparing gives real recall and
precision rather than a set of expectations the implementation is guaranteed to
meet. The thresholds below were calibrated from measured values, and the gap is
attributed rather than waved away: 94% of missed morphemes are the fused ``ས``
and ``ར`` that the analyzer documents that it will not split without a lexicon.
"""

from __future__ import annotations

import itertools

import pytest

from teea.core.types import SHAD_CHARS
from teea.nlp.morphology import (
    AffixCategory,
    MorphemeKind,
    MorphologicalAnalysis,
    MorphologicalAnalyzer,
    TibetanMorphologicalAnalyzer,
)
from teea.nlp.tokenization import SyllableSegmenter

# Hand-checked classical Tibetan.
MI = "མི"
GEN = "འི"
MI_GEN = MI + GEN  # མིའི -- host + fused genitive
KHYIM = "ཁྱིམ"  # "house"
LA = "ལ"  # allative particle
LAS = "ལས"  # ablative particle -- NOT ལ + agentive ས
GYI = "གྱི"  # genitive allomorph
TSHEG = "་"

#: Independent oracle mapping corpus tags to categories (see test_particles).
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

#: Surfaces the analyzer documents that it will not split from a host.
UNSPLITTABLE_FUSED = {"ས", "ར"}


# -- Helpers ------------------------------------------------------------------
def assert_span_ground_truth(source: str, analysis: MorphologicalAnalysis) -> None:
    encoded = source.encode("utf-8")
    for morpheme in analysis.morphemes:
        span = morpheme.span
        assert source[span.char_start : span.char_end] == morpheme.text
        assert encoded[span.byte_start : span.byte_end] == morpheme.text.encode("utf-8")


def gold_lines(tagged: list[list[tuple[str, str]]]) -> list[tuple[str, list[tuple[int, int, str]]]]:
    """Rebuild running text per corpus line with gold ``(start, end, tag)`` spans."""
    rebuilt: list[tuple[str, list[tuple[int, int, str]]]] = []
    for line in tagged:
        text = "".join(surface for surface, _ in line)
        spans: list[tuple[int, int, str]] = []
        offset = 0
        for surface, tag in line:
            spans.append((offset, offset + len(surface), tag.split("~")[0]))
            offset += len(surface)
        rebuilt.append((text, spans))
    return rebuilt


# -- Protocol and configuration -----------------------------------------------
def test_satisfies_the_analyzer_protocol(
    morphological_analyzer: TibetanMorphologicalAnalyzer,
) -> None:
    assert isinstance(morphological_analyzer, MorphologicalAnalyzer)


def test_split_fused_affixes_reflects_construction() -> None:
    assert TibetanMorphologicalAnalyzer().split_fused_affixes is True
    assert TibetanMorphologicalAnalyzer(split_fused_affixes=False).split_fused_affixes is False


def test_an_injected_segmenter_is_used() -> None:
    shared = SyllableSegmenter()
    analyzer = TibetanMorphologicalAnalyzer(segmenter=shared)
    assert analyzer.analyze(KHYIM).num_morphemes == 1


# -- Totality -----------------------------------------------------------------
@pytest.mark.parametrize("source", ["", "   ", "\n", "།", "།།", " ། "])
def test_degenerate_input_never_raises(
    morphological_analyzer: TibetanMorphologicalAnalyzer, source: str
) -> None:
    analysis = morphological_analyzer.analyze(source)
    assert analysis.source == source
    assert analysis.num_morphemes == 0


# -- Affix recognition --------------------------------------------------------
def test_a_plain_noun_is_all_root(
    morphological_analyzer: TibetanMorphologicalAnalyzer,
) -> None:
    analysis = morphological_analyzer.analyze(KHYIM)
    assert analysis.num_morphemes == 1
    assert analysis.morphemes[0].kind is MorphemeKind.ROOT
    assert analysis.root_text == KHYIM
    assert not analysis.affixes


def test_a_standalone_particle_is_recognized(
    morphological_analyzer: TibetanMorphologicalAnalyzer,
) -> None:
    analysis = morphological_analyzer.analyze(f"{KHYIM}{TSHEG}{LA}{TSHEG}")
    categories = [m.categories for m in analysis.affixes]
    assert AffixCategory.ALLATIVE in categories[0]
    assert analysis.root_text == KHYIM


@pytest.mark.parametrize(
    "allomorph", ["འི", "ཀྱི", "གྱི", "གི", "ཡི"]
)
def test_all_genitive_allomorphs_map_to_one_category(
    morphological_analyzer: TibetanMorphologicalAnalyzer, allomorph: str
) -> None:
    """Inflection analysis: sandhi variants are the same grammatical function."""
    analysis = morphological_analyzer.analyze(f"{KHYIM}{TSHEG}{allomorph}{TSHEG}")
    assert any(AffixCategory.GENITIVE in m.categories for m in analysis.affixes)


def test_an_ambiguous_surface_is_not_committed_to(
    morphological_analyzer: TibetanMorphologicalAnalyzer,
) -> None:
    """``ལས`` is the ablative in 63% of corpus uses and the noun 'work' in 35%."""
    analysis = morphological_analyzer.analyze(f"{KHYIM}{TSHEG}{LAS}{TSHEG}")
    ablative = [m for m in analysis.morphemes if AffixCategory.ABLATIVE in m.categories]
    assert ablative
    assert ablative[0].kind is MorphemeKind.AMBIGUOUS
    assert analysis.has_ambiguity


def test_inventory_is_consulted_before_fused_splitting(
    morphological_analyzer: TibetanMorphologicalAnalyzer,
) -> None:
    """The ordering that keeps ``ལས`` from being read as ``ལ`` + agentive."""
    analysis = morphological_analyzer.analyze(LAS)
    assert analysis.num_morphemes == 1
    assert analysis.morphemes[0].text == LAS
    assert AffixCategory.ABLATIVE in analysis.morphemes[0].categories


# -- Fused affixes ------------------------------------------------------------
def test_a_fused_genitive_is_split_from_its_host(
    morphological_analyzer: TibetanMorphologicalAnalyzer,
) -> None:
    analysis = morphological_analyzer.analyze(MI_GEN)
    assert analysis.num_morphemes == 2
    root, affix = analysis.morphemes
    assert root.text == MI and root.kind is MorphemeKind.ROOT
    assert affix.text == GEN and affix.is_fused
    assert affix.category is AffixCategory.GENITIVE
    assert analysis.root_text == MI
    assert_span_ground_truth(MI_GEN, analysis)


def test_fused_splitting_can_be_disabled() -> None:
    analyzer = TibetanMorphologicalAnalyzer(split_fused_affixes=False)
    analysis = analyzer.analyze(MI_GEN)
    assert analysis.num_morphemes == 1
    assert analysis.morphemes[0].text == MI_GEN


def test_a_bare_fused_sequence_is_not_split(
    morphological_analyzer: TibetanMorphologicalAnalyzer,
) -> None:
    """``འི`` alone is the standalone genitive, not an empty host plus an affix."""
    analysis = morphological_analyzer.analyze(GEN)
    assert analysis.num_morphemes == 1
    assert not analysis.morphemes[0].is_fused


@pytest.mark.parametrize("consonant", sorted(UNSPLITTABLE_FUSED))
def test_consonantal_fusions_are_deliberately_left_intact(
    morphological_analyzer: TibetanMorphologicalAnalyzer, consonant: str
) -> None:
    """Documented refusal: splitting these needs a lexicon.

    ``བུས`` really is ``བུ`` + agentive, but ``སངས`` is a root and ``ལས`` is a
    particle. The analyzer does not guess.
    """
    fused_form = MI + consonant
    analysis = morphological_analyzer.analyze(fused_form)
    assert analysis.num_morphemes == 1
    assert analysis.morphemes[0].text == fused_form
    assert analysis.morphemes[0].kind is MorphemeKind.ROOT


# -- Spans --------------------------------------------------------------------
def test_spans_are_exact_over_real_sentences(
    morphological_analyzer: TibetanMorphologicalAnalyzer, corpus_sentences: list[str]
) -> None:
    for sentence in corpus_sentences:
        assert_span_ground_truth(sentence, morphological_analyzer.analyze(sentence))


def test_byte_offsets_diverge_from_char_offsets(
    morphological_analyzer: TibetanMorphologicalAnalyzer, corpus_sentences: list[str]
) -> None:
    """Guards the assertion above from being trivially satisfiable."""
    analysis = morphological_analyzer.analyze(corpus_sentences[0])
    assert any(m.span.byte_start != m.span.char_start for m in analysis.morphemes)


def test_morphemes_are_ordered_and_non_overlapping(
    morphological_analyzer: TibetanMorphologicalAnalyzer, corpus_sentences: list[str]
) -> None:
    for sentence in corpus_sentences[:25]:
        morphemes = morphological_analyzer.analyze(sentence).morphemes
        for previous, current in itertools.pairwise(morphemes):
            assert previous.span.char_end <= current.span.char_start


def test_no_content_is_dropped(
    morphological_analyzer: TibetanMorphologicalAnalyzer, corpus_sentences: list[str]
) -> None:
    """Uncovered characters may only be delimiters, never letters."""
    for sentence in corpus_sentences[:25]:
        analysis = morphological_analyzer.analyze(sentence)
        covered = bytearray(len(sentence))
        for morpheme in analysis.morphemes:
            for index in range(morpheme.span.char_start, morpheme.span.char_end):
                covered[index] = 1
        uncovered = {sentence[i] for i, flag in enumerate(covered) if not flag}
        assert all(c.isspace() or c in SHAD_CHARS or c == TSHEG for c in uncovered), uncovered


def test_analysis_is_deterministic(
    morphological_analyzer: TibetanMorphologicalAnalyzer, corpus_sentences: list[str]
) -> None:
    sentence = corpus_sentences[3]
    assert morphological_analyzer.analyze(sentence) == morphological_analyzer.analyze(sentence)


# -- Evaluation against gold annotations --------------------------------------
def evaluate(
    analyzer: TibetanMorphologicalAnalyzer, tagged: list[list[tuple[str, str]]]
) -> tuple[int, int, int, int, int]:
    """Return ``(gold, recalled, missed_unsplittable, confident, confident_correct)``."""
    gold = recalled = missed_unsplittable = confident = confident_correct = 0

    for text, spans in gold_lines(tagged):
        analysis = analyzer.analyze(text)
        grammatical_spans = {(s, e) for s, e, tag in spans if tag in TAG_TO_CATEGORY}

        for start, end, tag in spans:
            expected = TAG_TO_CATEGORY.get(tag)
            if expected is None:
                continue
            gold += 1
            hit = any(
                m.is_affix
                and expected in m.categories
                and m.span.char_start < end
                and start < m.span.char_end
                for m in analysis.morphemes
            )
            if hit:
                recalled += 1
            elif text[start:end].rstrip(TSHEG) in UNSPLITTABLE_FUSED:
                missed_unsplittable += 1

        for morpheme in analysis.morphemes:
            if morpheme.kind is not MorphemeKind.AFFIX:
                continue
            confident += 1
            if any(
                s < morpheme.span.char_end and morpheme.span.char_start < e
                for s, e in grammatical_spans
            ):
                confident_correct += 1

    return gold, recalled, missed_unsplittable, confident, confident_correct


def test_gold_evaluation_has_a_meaningful_sample(
    tagged_corpus: list[list[tuple[str, str]]],
) -> None:
    gold, *_ = evaluate(TibetanMorphologicalAnalyzer(), tagged_corpus)
    assert gold > 1000, gold


def test_recall_against_gold_annotations(
    morphological_analyzer: TibetanMorphologicalAnalyzer,
    tagged_corpus: list[list[tuple[str, str]]],
) -> None:
    """Measured at 80.2% when calibrated; the floor allows for data refresh."""
    gold, recalled, _, _, _ = evaluate(morphological_analyzer, tagged_corpus)
    assert recalled / gold >= 0.78, f"recall {recalled / gold:.1%} ({recalled}/{gold})"


def test_recall_is_near_total_once_the_documented_gap_is_excluded(
    morphological_analyzer: TibetanMorphologicalAnalyzer,
    tagged_corpus: list[list[tuple[str, str]]],
) -> None:
    """The honest measure of what the analyzer claims to do.

    Excluding the fused ``ས``/``ར`` it explicitly refuses to split, measured
    recall is 98.7%.
    """
    gold, recalled, missed_unsplittable, _, _ = evaluate(morphological_analyzer, tagged_corpus)
    attempted = gold - missed_unsplittable
    assert recalled / attempted >= 0.95, f"{recalled}/{attempted}"


def test_the_recall_gap_is_dominated_by_the_documented_limitation(
    morphological_analyzer: TibetanMorphologicalAnalyzer,
    tagged_corpus: list[list[tuple[str, str]]],
) -> None:
    """Attributes the gap instead of merely tolerating it.

    If a lexicon-backed analyzer later splits ``ས``/``ར``, this test will fail
    and should be retired along with the limitation.
    """
    gold, recalled, missed_unsplittable, _, _ = evaluate(morphological_analyzer, tagged_corpus)
    total_missed = gold - recalled
    assert total_missed > 0
    assert missed_unsplittable / total_missed >= 0.85, (
        f"{missed_unsplittable}/{total_missed} of misses are the known gap"
    )


def test_precision_of_confident_affixes(
    morphological_analyzer: TibetanMorphologicalAnalyzer,
    tagged_corpus: list[list[tuple[str, str]]],
) -> None:
    """Over-tagging would poison Stage 7; measured at 92.1%."""
    _, _, _, confident, confident_correct = evaluate(morphological_analyzer, tagged_corpus)
    assert confident > 500
    assert confident_correct / confident >= 0.90, f"{confident_correct}/{confident}"


def test_disabling_fused_splitting_lowers_recall(
    tagged_corpus: list[list[tuple[str, str]]],
) -> None:
    """Confirms the fused-affix rules actually contribute."""
    with_split = TibetanMorphologicalAnalyzer()
    without = TibetanMorphologicalAnalyzer(split_fused_affixes=False)
    _, recalled_with, _, _, _ = evaluate(with_split, tagged_corpus)
    _, recalled_without, _, _, _ = evaluate(without, tagged_corpus)
    assert recalled_with > recalled_without
