"""Unit and evaluation tests for :mod:`teea.nlp.postagging.tagger`.

Two halves.

The first pins the contract on small, hand-checked inputs: protocol conformance,
totality, dependency inversion, and above all **span preservation** -- Stage 7
labels, it never re-segments. That invariant is what lets Stage 8 and the add-in
trust that a tagged morpheme still points at the same characters Stage 6 found.

The second is a genuine evaluation against gold annotations, using a text the
model was **not** built from. The Dictionary Repository is derived from the
Milarepa text; ``heldout_corpus`` comes from Marpa, a different work by a
different author. Reporting accuracy on held-out data measures generalisation
rather than recall of training data, and the tests assert both that the tagger
beats a most-frequent-tag baseline computed from the same repository, and that
the training text scores higher than the held-out one -- which would fail loudly
if the two fixtures were ever swapped.

Every threshold below was measured first and then set with margin; none is a
guess.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from pathlib import Path

import pytest

from teea.core.types import TextSpan, utf8_byte_offsets
from teea.nlp.morphology import (
    AffixCategory,
    Morpheme,
    MorphemeKind,
    MorphologicalAnalysis,
    TibetanMorphologicalAnalyzer,
)
from teea.nlp.postagging import (
    HmmPosTagger,
    PosCategory,
    PosTagger,
    TaggedText,
    coarse_category,
)
from teea.persistence import SENTENCE_START, InMemoryDictionaryRepository

KHYIM = "ཁྱིམ"  # "house"
MI = "མི"
GEN = "འི"  # fused genitive


# -- Helpers ------------------------------------------------------------------
def analyse(text: str) -> MorphologicalAnalysis:
    return TibetanMorphologicalAnalyzer().analyze(text)


def gold_spans(line: list[tuple[str, str]]) -> tuple[str, list[tuple[int, int, str]]]:
    """Rebuild running text for one corpus line with gold ``(start, end, tag)``."""
    text = "".join(surface for surface, _ in line)
    spans: list[tuple[int, int, str]] = []
    offset = 0
    for surface, tag in line:
        spans.append((offset, offset + len(surface), tag.split("~")[0]))
        offset += len(surface)
    return text, spans


class Evaluation:
    """Accumulated accuracy counters for one corpus."""

    def __init__(self) -> None:
        self.total = 0
        self.fine = 0
        self.coarse = 0
        self.baseline = 0
        self.ambiguous = 0
        self.ambiguous_correct = 0

    @property
    def fine_accuracy(self) -> float:
        return self.fine / self.total

    @property
    def coarse_accuracy(self) -> float:
        return self.coarse / self.total

    @property
    def baseline_accuracy(self) -> float:
        return self.baseline / self.total

    @property
    def ambiguity_resolution(self) -> float:
        return self.ambiguous_correct / max(self.ambiguous, 1)


def evaluate(
    tagger: HmmPosTagger,
    dictionary: InMemoryDictionaryRepository,
    corpus: list[list[tuple[str, str]]],
) -> Evaluation:
    """Score the Stage 6 -> 7 pipeline against gold, aligned by character offset.

    Gold tokens may span several syllables while Stage 6 emits syllable-level
    morphemes, so each morpheme inherits the tag of the gold token containing its
    start offset. That measures the pipeline as it actually runs.
    """
    analyzer = TibetanMorphologicalAnalyzer()
    result = Evaluation()

    for line in corpus:
        text, spans = gold_spans(line)
        tagged = tagger.tag(analyzer.analyze(text))

        for morpheme in tagged.morphemes:
            start = morpheme.span.char_start
            gold = next((tag for lo, hi, tag in spans if lo <= start < hi), None)
            if gold is None:
                continue

            result.total += 1
            result.fine += morpheme.tag == gold
            result.coarse += morpheme.category is coarse_category(gold)

            emissions = dictionary.lookup(morpheme.text)
            most_frequent = (
                max(emissions.items(), key=lambda item: item[1])[0] if emissions else "n.count"
            )
            result.baseline += most_frequent == gold

            if morpheme.morpheme.kind is MorphemeKind.AMBIGUOUS:
                result.ambiguous += 1
                result.ambiguous_correct += morpheme.tag == gold

    return result


class StubDictionary:
    """A deliberately tiny repository, to prove the injected one is really used."""

    def __init__(self) -> None:
        self._emissions: dict[str, Mapping[str, int]] = {
            KHYIM: {"n.count": 5},
            MI: {"n.count": 3},
            GEN: {"case.gen": 9},
        }

    @property
    def tags(self) -> frozenset[str]:
        return frozenset({"n.count", "case.gen"})

    @property
    def tag_counts(self) -> Mapping[str, int]:
        return {"n.count": 8, "case.gen": 9}

    def lookup(self, surface: str) -> Mapping[str, int] | None:
        return self._emissions.get(surface)

    def transitions(self, tag: str) -> Mapping[str, int]:
        return {"n.count": 4, "case.gen": 4}

    def __contains__(self, surface: str) -> bool:
        return surface in self._emissions


# -- Protocol conformance and configuration -----------------------------------
def test_satisfies_the_pos_tagger_protocol(pos_tagger: HmmPosTagger) -> None:
    assert isinstance(pos_tagger, PosTagger)


def test_tagset_matches_the_repository(
    pos_tagger: HmmPosTagger, dictionary: InMemoryDictionaryRepository
) -> None:
    assert set(pos_tagger.tagset) == set(dictionary.tags)
    assert list(pos_tagger.tagset) == sorted(pos_tagger.tagset)


def test_smoothing_reflects_construction() -> None:
    assert HmmPosTagger(smoothing=0.5).smoothing == 0.5


@pytest.mark.parametrize("smoothing", [0.0, -0.1, -5.0])
def test_non_positive_smoothing_is_rejected(smoothing: float) -> None:
    """Zero smoothing makes log(0) unreachable rather than merely unlikely."""
    with pytest.raises(ValueError, match="smoothing must be positive"):
        HmmPosTagger(smoothing=smoothing)


# -- Totality -----------------------------------------------------------------
def test_an_empty_analysis_yields_an_empty_result(pos_tagger: HmmPosTagger) -> None:
    analysis = MorphologicalAnalysis(source="")
    tagged = pos_tagger.tag(analysis)
    assert tagged.num_morphemes == 0
    assert tagged.source == ""


@pytest.mark.parametrize("source", ["", "   ", "།", "།།"])
def test_degenerate_text_never_raises(pos_tagger: HmmPosTagger, source: str) -> None:
    assert pos_tagger.tag(analyse(source)).num_morphemes == 0


# -- Span preservation (the architectural invariant) --------------------------
def test_every_morpheme_survives_tagging_with_its_span_intact(
    pos_tagger: HmmPosTagger, corpus_sentences: list[str]
) -> None:
    """Stage 7 labels; it never re-segments.

    Stated in ``postagging/interfaces.py`` and relied upon by Stage 8: a tagged
    morpheme must still point at exactly the characters Stage 6 found.
    """
    for sentence in corpus_sentences:
        analysis = analyse(sentence)
        tagged = pos_tagger.tag(analysis)

        assert tagged.num_morphemes == analysis.num_morphemes
        for before, after in zip(analysis.morphemes, tagged.morphemes, strict=True):
            assert after.morpheme is before
            assert after.span == before.span
            assert after.text == before.text


def test_spans_still_select_their_own_text(
    pos_tagger: HmmPosTagger, corpus_sentences: list[str]
) -> None:
    for sentence in corpus_sentences[:25]:
        tagged = pos_tagger.tag(analyse(sentence))
        encoded = sentence.encode("utf-8")
        for morpheme in tagged.morphemes:
            span = morpheme.span
            assert sentence[span.char_start : span.char_end] == morpheme.text
            assert encoded[span.byte_start : span.byte_end] == morpheme.text.encode("utf-8")


def test_source_is_preserved(pos_tagger: HmmPosTagger, corpus_sentences: list[str]) -> None:
    sentence = corpus_sentences[0]
    assert pos_tagger.tag(analyse(sentence)).source == sentence


# -- Output well-formedness ---------------------------------------------------
def test_every_emitted_tag_is_in_the_tagset(
    pos_tagger: HmmPosTagger, corpus_sentences: list[str]
) -> None:
    known = set(pos_tagger.tagset)
    for sentence in corpus_sentences[:25]:
        assert all(m.tag in known for m in pos_tagger.tag(analyse(sentence)).morphemes)


def test_category_always_agrees_with_the_tag(
    pos_tagger: HmmPosTagger, corpus_sentences: list[str]
) -> None:
    for sentence in corpus_sentences[:25]:
        for morpheme in pos_tagger.tag(analyse(sentence)).morphemes:
            assert morpheme.category is coarse_category(morpheme.tag)


def test_was_ambiguous_marks_exactly_the_stage_6_ambiguities(
    pos_tagger: HmmPosTagger, corpus_sentences: list[str]
) -> None:
    """The audit trail for the stage's stated purpose."""
    seen_any = False
    for sentence in corpus_sentences:
        analysis = analyse(sentence)
        tagged = pos_tagger.tag(analysis)
        for before, after in zip(analysis.morphemes, tagged.morphemes, strict=True):
            assert after.was_ambiguous is (before.kind is MorphemeKind.AMBIGUOUS)
            seen_any = seen_any or after.was_ambiguous
    assert seen_any, "corpus should contain at least one ambiguous morpheme"


def test_tagging_is_deterministic(pos_tagger: HmmPosTagger, corpus_sentences: list[str]) -> None:
    analysis = analyse(corpus_sentences[4])
    assert pos_tagger.tag(analysis) == pos_tagger.tag(analysis)


# -- Dependency inversion -----------------------------------------------------
def test_an_empty_injected_repository_is_not_silently_replaced(tmp_path: Path) -> None:
    """Regression guard for a dependency-injection defect.

    The default was selected with ``dictionary or default_dictionary()``. An
    empty repository is falsy because it defines ``__len__``, so injecting one
    silently loaded the shipped 77-tag model instead -- a wrong-data failure the
    caller could not observe.
    """
    payload = tmp_path / "empty.json"
    payload.write_text(
        json.dumps({"tags": [], "tag_counts": {}, "emissions": {}, "transitions": {}}),
        encoding="utf-8",
    )
    tagger = HmmPosTagger(dictionary=InMemoryDictionaryRepository(payload))
    assert tagger.tagset == ()


def test_an_injected_repository_is_used_instead_of_the_default() -> None:
    """The tagger must depend on the protocol, not the shipped data."""
    tagger = HmmPosTagger(dictionary=StubDictionary())
    assert set(tagger.tagset) == {"n.count", "case.gen"}

    tagged = tagger.tag(analyse(f"{KHYIM}་{MI}{GEN}་"))
    assert tagged.num_morphemes > 0
    assert all(m.tag in {"n.count", "case.gen"} for m in tagged.morphemes)


def test_a_genitive_after_a_noun_is_tagged_as_a_particle(
    pos_tagger: HmmPosTagger,
) -> None:
    """Hand-checked: ``མིའི`` is the noun ``མི`` plus the genitive ``འི``."""
    tagged = pos_tagger.tag(analyse(f"{MI}{GEN}་{KHYIM}་"))
    by_text = {m.text: m for m in tagged.morphemes}
    assert by_text[GEN].category is PosCategory.PARTICLE
    assert by_text[KHYIM].category is PosCategory.NOUN


# -- Evaluation against gold annotations --------------------------------------
def test_held_out_evaluation_has_a_meaningful_sample(
    pos_tagger: HmmPosTagger,
    dictionary: InMemoryDictionaryRepository,
    heldout_corpus: list[list[tuple[str, str]]],
) -> None:
    result = evaluate(pos_tagger, dictionary, heldout_corpus)
    assert result.total > 2000, result.total


def test_fine_tag_accuracy_on_held_out_text(
    pos_tagger: HmmPosTagger,
    dictionary: InMemoryDictionaryRepository,
    heldout_corpus: list[list[tuple[str, str]]],
) -> None:
    """Marpa was not used to build the model. Measured 73.2%."""
    result = evaluate(pos_tagger, dictionary, heldout_corpus)
    assert result.fine_accuracy >= 0.70, f"{result.fine_accuracy:.2%}"


def test_coarse_accuracy_on_held_out_text(
    pos_tagger: HmmPosTagger,
    dictionary: InMemoryDictionaryRepository,
    heldout_corpus: list[list[tuple[str, str]]],
) -> None:
    """The Figure 5 classes plugins actually consume. Measured 83.5%."""
    result = evaluate(pos_tagger, dictionary, heldout_corpus)
    assert result.coarse_accuracy >= 0.80, f"{result.coarse_accuracy:.2%}"


def test_the_hmm_beats_a_most_frequent_tag_baseline(
    pos_tagger: HmmPosTagger,
    dictionary: InMemoryDictionaryRepository,
    heldout_corpus: list[list[tuple[str, str]]],
) -> None:
    """What justifies Viterbi over a plain lookup.

    The baseline uses the *same* repository on the *same* data, so the only
    difference measured is the context model. Measured 73.2% versus 62.0%.
    """
    result = evaluate(pos_tagger, dictionary, heldout_corpus)
    assert result.fine_accuracy > result.baseline_accuracy
    assert result.fine_accuracy - result.baseline_accuracy >= 0.05


def test_stage_6_ambiguities_are_resolved_correctly(
    pos_tagger: HmmPosTagger,
    dictionary: InMemoryDictionaryRepository,
    heldout_corpus: list[list[tuple[str, str]]],
) -> None:
    """Stage 7's stated purpose, measured on held-out text at 85.2%."""
    result = evaluate(pos_tagger, dictionary, heldout_corpus)
    assert result.ambiguous > 100, result.ambiguous
    assert result.ambiguity_resolution >= 0.78, f"{result.ambiguity_resolution:.1%}"


def test_training_text_scores_higher_than_held_out_text(
    pos_tagger: HmmPosTagger,
    dictionary: InMemoryDictionaryRepository,
    tagged_corpus: list[list[tuple[str, str]]],
    heldout_corpus: list[list[tuple[str, str]]],
) -> None:
    """Guards the fixtures from being silently swapped.

    If ``heldout_corpus`` ever pointed at the training text, or the model were
    rebuilt from Marpa, this ordering would invert and the held-out figures above
    would quietly stop measuring generalisation.
    """
    training = evaluate(pos_tagger, dictionary, tagged_corpus)
    held_out = evaluate(pos_tagger, dictionary, heldout_corpus)
    assert training.fine_accuracy > held_out.fine_accuracy


# -- Smoothing behaviour ------------------------------------------------------
def test_smoothing_changes_predictions_but_not_structure(
    corpus_sentences: list[str],
) -> None:
    """A different constant may retag, but must never re-segment."""
    lenient = HmmPosTagger(smoothing=2.0)
    strict = HmmPosTagger(smoothing=0.01)
    sentence = corpus_sentences[7]

    a = lenient.tag(analyse(sentence))
    b = strict.tag(analyse(sentence))
    assert isinstance(a, TaggedText) and isinstance(b, TaggedText)
    assert [m.span for m in a.morphemes] == [m.span for m in b.morphemes]


def test_stage_6_categories_constrain_an_unknown_surface() -> None:
    """The documented Stage 6 -> 7 integration point.

    When the lexicon has never seen a surface, the candidate set would otherwise
    be the entire tagset. If Stage 6 recognized the morpheme as an affix, its
    grammatical categories narrow the candidates instead -- the two stages
    composing rather than Stage 7 discarding Stage 6's work.
    """
    unseen = "ཀྵུ"
    stub = StubDictionary()
    assert stub.lookup(unseen) is None, "premise: the surface must be unknown"

    offsets = utf8_byte_offsets(unseen)
    span = TextSpan(char_start=0, char_end=len(unseen), byte_start=0, byte_end=offsets[len(unseen)])
    analysis = MorphologicalAnalysis(
        source=unseen,
        morphemes=(
            Morpheme(
                text=unseen,
                span=span,
                kind=MorphemeKind.AFFIX,
                categories=frozenset({AffixCategory.GENITIVE}),
            ),
        ),
    )

    tagged = HmmPosTagger(dictionary=stub).tag(analysis)
    # Constrained to the genitive reading rather than the open-class default.
    assert tagged.morphemes[0].tag == "case.gen"
    assert tagged.morphemes[0].category is PosCategory.PARTICLE


# -- Performance (NFR 5.1) ----------------------------------------------------
def test_transition_probabilities_are_never_recomputed_during_decoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression guard for a measured NFR 5.1 violation.

    An out-of-vocabulary surface has no observed emissions, so the candidate set
    is the entire tagset and Viterbi evaluates |tags|^2 transitions per morpheme.
    Recomputing each one cost 3.8 ms per morpheme, so a short phrase of embedded
    Latin -- ordinary in Tibetan academic writing -- exceeded the 50 ms
    interactive budget at just 14 morphemes. Precomputing the table cut it to
    0.68 ms with bit-identical output.

    The assertion counts logarithms rather than milliseconds. Wall-clock in a
    test suite is not a reliable instrument: the same code measured 0.76 ms per
    morpheme in isolation and 2.97 ms inside the full suite, because garbage
    collection scales with the heap the rest of the suite has accumulated.
    Counting the work done is deterministic, machine-independent, and tests the
    mechanism that was actually fixed -- an all-out-of-vocabulary sentence must
    require **no** logarithms at all, against roughly 332,000 before.
    """
    calls = 0
    real_log = math.log

    def counting_log(value: float) -> float:
        nonlocal calls
        calls += 1
        return real_log(value)

    tagger = HmmPosTagger()
    analysis = analyse("abcd efgh ijkl mnop qrst uvwx yz12 " * 8)
    assert analysis.num_morphemes >= 50, "premise: a realistically long OOV run"

    monkeypatch.setattr("teea.nlp.postagging.tagger.math.log", counting_log)
    tagger.tag(analysis)

    assert calls == 0, f"{calls} logarithms recomputed during decoding"


def test_in_vocabulary_decoding_only_computes_emission_probabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The complement: known surfaces still need their own emissions.

    Those are per (surface, tag) and cannot be precomputed from the repository
    alone, so a small number is expected -- but it must stay proportional to the
    sentence, not to |tags|^2.
    """
    calls = 0
    real_log = math.log

    def counting_log(value: float) -> float:
        nonlocal calls
        calls += 1
        return real_log(value)

    tagger = HmmPosTagger()
    analysis = analyse("བཀྲ་ཤིས་བདེ་ལེགས་ཞིང་སྐལ་" * 8)

    monkeypatch.setattr("teea.nlp.postagging.tagger.math.log", counting_log)
    tagger.tag(analysis)

    assert 0 < calls < 50 * analysis.num_morphemes, calls


def test_precomputed_tables_cover_every_reachable_predecessor() -> None:
    """The optimisation is only safe because the table is total.

    Viterbi indexes the transition table by every tag it may carry forward, plus
    the sentence-start marker. A missing key would surface as a KeyError partway
    through decoding a real document.
    """
    tagger = HmmPosTagger()
    table = tagger._transition_logp_table
    assert SENTENCE_START in table
    for tag in tagger.tagset:
        assert tag in table, tag
        assert set(table[tag]) == set(tagger.tagset)


def test_categories_unknown_to_the_repository_fall_back_to_the_full_tagset() -> None:
    """Guards against an empty candidate set, which would break Viterbi.

    If Stage 6 reports a category whose tags this repository has never seen, the
    constrained set is empty. Falling back to the full tagset keeps decoding
    well-defined instead of leaving a layer with no candidates.
    """
    unseen = "ཀྵུ"
    stub = StubDictionary()  # knows only n.count and case.gen
    offsets = utf8_byte_offsets(unseen)
    analysis = MorphologicalAnalysis(
        source=unseen,
        morphemes=(
            Morpheme(
                text=unseen,
                span=TextSpan(
                    char_start=0,
                    char_end=len(unseen),
                    byte_start=0,
                    byte_end=offsets[len(unseen)],
                ),
                kind=MorphemeKind.AFFIX,
                # cv.sem is not among the stub's tags.
                categories=frozenset({AffixCategory.SEMI_FINAL}),
            ),
        ),
    )

    tagged = HmmPosTagger(dictionary=stub).tag(analysis)
    assert tagged.num_morphemes == 1
    assert tagged.morphemes[0].tag in {"n.count", "case.gen"}


def test_an_out_of_vocabulary_surface_still_receives_a_tag(
    pos_tagger: HmmPosTagger, dictionary: InMemoryDictionaryRepository
) -> None:
    """Unknown words must not crash or be dropped."""
    invented = "ཀྵུ"
    assert dictionary.lookup(invented) is None
    offsets = utf8_byte_offsets(invented)
    analysis = MorphologicalAnalysis(
        source=invented,
        morphemes=(
            Morpheme(
                text=invented,
                span=TextSpan(
                    char_start=0,
                    char_end=len(invented),
                    byte_start=0,
                    byte_end=offsets[len(invented)],
                ),
                kind=MorphemeKind.ROOT,
            ),
        ),
    )
    tagged = pos_tagger.tag(analysis)
    assert tagged.num_morphemes == 1
    assert tagged.morphemes[0].tag in set(pos_tagger.tagset)
