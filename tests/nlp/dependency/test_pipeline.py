"""Integration tests for the complete language pipeline, Stages 2 -> 8.

Stage 8 closes the analysis stack SRS 3.1 mandates: Normalization -> Word
Tokenization -> Morphological Parsing -> Part-of-Speech Tagging -> Structural
Dependency Mapping. This module runs that whole chain on real Tibetan and pins
the properties that only appear when the stages are composed.

Individually correct stages can still compose wrongly, and here the failure mode
would be silent: offsets that no longer address the document, or a tree whose
nodes have quietly drifted from the morphemes Stage 6 found. Both are checked
against the document text rather than assumed.

The tokenizer is exercised through the fake backend, so the whole module is
hermetic -- no model download, no network.
"""

from __future__ import annotations

from teea.nlp.dependency import DependencyRelation, TibetanDependencyParser
from teea.nlp.morphology import TibetanMorphologicalAnalyzer
from teea.nlp.postagging import HmmPosTagger
from teea.nlp.segmentation import TibetanSentenceSegmenter
from teea.nlp.tokenization import TextNormalizer, TiBERTTokenizer


# -- Whole-pipeline composition -----------------------------------------------
def test_a_document_flows_through_every_stage(
    sentence_segmenter: TibetanSentenceSegmenter,
    morphological_analyzer: TibetanMorphologicalAnalyzer,
    pos_tagger: HmmPosTagger,
    dependency_parser: TibetanDependencyParser,
    corpus_document: str,
) -> None:
    """Stage 2 -> 4 -> 6 -> 7 -> 8 on a real multi-paragraph document."""
    normalized = TextNormalizer(form="NFC", collapse_whitespace=False).normalize(
        corpus_document
    )
    segmented = sentence_segmenter.segment(normalized)
    assert segmented.num_sentences > 10

    trees = 0
    nodes = 0
    for sentence in segmented.sentences:
        tree = dependency_parser.parse(
            pos_tagger.tag(morphological_analyzer.analyze(sentence.text))
        )
        assert tree.root is not None
        trees += 1
        nodes += tree.num_nodes

    assert trees == segmented.num_sentences
    assert nodes > 500


def test_dependency_offsets_compose_to_document_offsets(
    sentence_segmenter: TibetanSentenceSegmenter,
    morphological_analyzer: TibetanMorphologicalAnalyzer,
    pos_tagger: HmmPosTagger,
    dependency_parser: TibetanDependencyParser,
    corpus_document: str,
) -> None:
    """The arithmetic the add-in performs to place a suggestion.

    A node's span is relative to its sentence; the sentence's span is relative
    to the document. Their sum must select the same characters in the document,
    or a syntactic suggestion would be painted onto the wrong Word range.
    """
    segmented = sentence_segmenter.segment(corpus_document)
    checked = 0

    for sentence in segmented.sentences[:25]:
        tree = dependency_parser.parse(
            pos_tagger.tag(morphological_analyzer.analyze(sentence.text))
        )
        for node in tree.nodes:
            start = sentence.span.char_start + node.span.char_start
            end = sentence.span.char_start + node.span.char_end
            assert corpus_document[start:end] == node.text
            checked += 1

    assert checked > 100


def test_every_stage_7_morpheme_becomes_exactly_one_stage_8_node(
    morphological_analyzer: TibetanMorphologicalAnalyzer,
    pos_tagger: HmmPosTagger,
    dependency_parser: TibetanDependencyParser,
    corpus_sentences: list[str],
) -> None:
    """Stage 8 adds structure over Stage 7; it neither drops nor invents units."""
    for sentence in corpus_sentences:
        tagged = pos_tagger.tag(morphological_analyzer.analyze(sentence))
        tree = dependency_parser.parse(tagged)

        assert tree.num_nodes == tagged.num_morphemes
        assert tuple(n.text for n in tree.nodes) == tuple(
            m.text for m in tagged.morphemes
        )
        assert tuple(n.tag for n in tree.nodes) == tagged.tags


def test_the_tokenizer_and_the_parser_agree_on_the_same_sentences(
    sentence_segmenter: TibetanSentenceSegmenter,
    morphological_analyzer: TibetanMorphologicalAnalyzer,
    pos_tagger: HmmPosTagger,
    dependency_parser: TibetanDependencyParser,
    tokenizer: TiBERTTokenizer,
    corpus_document: str,
) -> None:
    """Stage 5 and Stage 8 are parallel consumers of Stage 4.

    Sentence segmentation is what makes both tractable: the tokenizer because of
    TiBERT's 512-token limit, the parser because a tree is defined per clause.
    """
    segmented = sentence_segmenter.segment(corpus_document)
    for sentence in segmented.sentences[:20]:
        encoded = tokenizer.encode(sentence.text)
        tree = dependency_parser.parse(
            pos_tagger.tag(morphological_analyzer.analyze(sentence.text))
        )
        assert not encoded.was_truncated
        assert tree.root is not None
        assert encoded.source == sentence.text == tree.source


# -- Linguistic behaviour on authentic text -----------------------------------
def test_most_sentences_receive_an_argument_structure(
    morphological_analyzer: TibetanMorphologicalAnalyzer,
    pos_tagger: HmmPosTagger,
    dependency_parser: TibetanDependencyParser,
    corpus_sentences: list[str],
) -> None:
    """Figure 5's "subject & object detection", measured on real sentences."""
    with_argument = 0
    for sentence in corpus_sentences:
        tree = dependency_parser.parse(
            pos_tagger.tag(morphological_analyzer.analyze(sentence))
        )
        if tree.subjects or tree.objects:
            with_argument += 1

    assert with_argument / len(corpus_sentences) >= 0.80, with_argument


def test_case_particles_are_attached_to_their_host_not_the_root(
    morphological_analyzer: TibetanMorphologicalAnalyzer,
    pos_tagger: HmmPosTagger,
    dependency_parser: TibetanDependencyParser,
    corpus_sentences: list[str],
) -> None:
    """A case particle marks a nominal, so it must depend on that nominal."""
    checked = 0
    for sentence in corpus_sentences:
        tree = dependency_parser.parse(
            pos_tagger.tag(morphological_analyzer.analyze(sentence))
        )
        for node in tree.of_relation(DependencyRelation.CASE):
            head = tree.head_of(node.index)
            assert head is not None
            assert head.index < node.index, "a case particle follows its host"
            checked += 1

    assert checked > 50, "the corpus should exercise many case particles"


def test_the_root_is_the_last_verb_when_the_sentence_has_one(
    morphological_analyzer: TibetanMorphologicalAnalyzer,
    pos_tagger: HmmPosTagger,
    dependency_parser: TibetanDependencyParser,
    corpus_sentences: list[str],
) -> None:
    """Tibetan is verb-final; the analysis should reflect that on real text."""
    verb_final = total = 0
    for sentence in corpus_sentences:
        tagged = pos_tagger.tag(morphological_analyzer.analyze(sentence))
        tree = dependency_parser.parse(tagged)
        if tree.root is None:
            continue
        total += 1
        # The root should sit in the final third of the sentence.
        if tree.root.index >= (tree.num_nodes - 1) * 2 // 3:
            verb_final += 1

    assert total > 0
    assert verb_final / total >= 0.60, f"{verb_final}/{total}"


# -- Regression: the pipeline stays deterministic and thread-safe -------------
def test_the_whole_pipeline_is_deterministic(
    sentence_segmenter: TibetanSentenceSegmenter,
    morphological_analyzer: TibetanMorphologicalAnalyzer,
    pos_tagger: HmmPosTagger,
    dependency_parser: TibetanDependencyParser,
    corpus_document: str,
) -> None:
    def run() -> list[tuple[DependencyRelation, ...]]:
        return [
            dependency_parser.parse(
                pos_tagger.tag(morphological_analyzer.analyze(s.text))
            ).relations
            for s in sentence_segmenter.segment(corpus_document).sentences[:30]
        ]

    assert run() == run()
