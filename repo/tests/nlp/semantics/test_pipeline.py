"""Integration tests for the complete language pipeline, Stages 2 -> 11.

Stage 11 closes Figure 5's analysis chain: normalization, sentence segmentation,
morphology, part-of-speech tagging, dependency parsing, named entity recognition,
terminology recognition and finally semantic analysis. This module runs that
whole chain on real classical Tibetan and pins the properties that only appear
once the stages are composed.

Individually correct stages can still compose wrongly, and here the failure would
be silent: offsets that no longer address the document, a graph whose nodes have
drifted from the morphemes Stage 6 found, or an entity boundary that Stage 11
quietly disagrees with. All three are checked against the document text rather
than assumed.

The tokenizer is exercised through the fake backend, so the module is hermetic --
no model download, no network.
"""

from __future__ import annotations

import collections
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor

from teea.nlp.dependency import (
    DependencyRelation,
    DependencyTree,
    TibetanDependencyParser,
)
from teea.nlp.morphology import TibetanMorphologicalAnalyzer
from teea.nlp.ner import TibetanEntityRecognizer
from teea.nlp.postagging import HmmPosTagger
from teea.nlp.segmentation import TibetanSentenceSegmenter
from teea.nlp.semantics import (
    RoleEvidence,
    SemanticGraph,
    SemanticRole,
    SentenceMood,
    TibetanSemanticAnalyzer,
)
from teea.nlp.terminology import GlossaryTerminologyRecognizer
from teea.nlp.tokenization import TextNormalizer, TiBERTTokenizer
from teea.persistence import VerbFrame, VerbLexiconRepository, default_verb_lexicon


class Pipeline:
    """Stages 6 -> 11 wired together, for tests that need the whole chain."""

    def __init__(self, analyzer: TibetanSemanticAnalyzer) -> None:
        self.morphology = TibetanMorphologicalAnalyzer()
        self.tagger = HmmPosTagger()
        self.parser = TibetanDependencyParser()
        self.ner = TibetanEntityRecognizer()
        self.terminology = GlossaryTerminologyRecognizer()
        self.semantics = analyzer

    def tree(self, sentence: str) -> DependencyTree:
        """Run Stages 6 -> 8."""
        return self.parser.parse(self.tagger.tag(self.morphology.analyze(sentence)))

    def graph(self, sentence: str) -> SemanticGraph:
        """Run Stages 6 -> 11."""
        tree = self.tree(sentence)
        return self.semantics.analyze(
            tree,
            entities=self.ner.recognize(tree),
            terms=self.terminology.recognize(tree),
        )


class CountingVerbLexicon:
    """Wraps the shipped lexicon and counts lookups, for a work-based budget."""

    def __init__(self) -> None:
        self._inner = default_verb_lexicon()
        self.lookups = 0

    @property
    def max_length(self) -> int:
        return self._inner.max_length

    def lookup(self, syllables: Sequence[str]) -> tuple[VerbFrame, ...]:
        self.lookups += 1
        return self._inner.lookup(syllables)

    def __len__(self) -> int:
        return len(self._inner)


# -- Whole-pipeline composition ------------------------------------------------
def test_a_document_flows_through_every_stage(
    sentence_segmenter: TibetanSentenceSegmenter,
    semantic_analyzer: TibetanSemanticAnalyzer,
    corpus_document: str,
) -> None:
    """Stage 2 -> 4 -> 6 -> 7 -> 8 -> 9 -> 10 -> 11 on a real document."""
    pipeline = Pipeline(semantic_analyzer)
    normalized = TextNormalizer(form="NFC", collapse_whitespace=False).normalize(corpus_document)
    segmented = sentence_segmenter.segment(normalized)
    assert segmented.num_sentences > 10

    graphs = nodes = edges = 0
    for sentence in segmented.sentences:
        graph = pipeline.graph(sentence.text)
        assert graph.source == sentence.text
        graphs += 1
        nodes += graph.num_nodes
        edges += graph.num_edges

    assert graphs == segmented.num_sentences
    assert nodes > 300
    assert edges > 200


def test_semantic_offsets_compose_to_document_offsets(
    sentence_segmenter: TibetanSentenceSegmenter,
    semantic_analyzer: TibetanSemanticAnalyzer,
    corpus_document: str,
) -> None:
    """The arithmetic the add-in performs to place a suggestion.

    A node's span is relative to its sentence; the sentence's span is relative to
    the document. Their sum must select the same characters in the document, or a
    semantic suggestion would be painted onto the wrong Word range.
    """
    pipeline = Pipeline(semantic_analyzer)
    segmented = sentence_segmenter.segment(corpus_document)
    checked = 0

    for sentence in segmented.sentences[:25]:
        for node in pipeline.graph(sentence.text).nodes:
            start = sentence.span.char_start + node.span.char_start
            end = sentence.span.char_start + node.span.char_end
            assert corpus_document[start:end] == node.text
            checked += 1

    assert checked > 100


def test_stage_11_neither_drops_nor_invents_morphemes(
    semantic_analyzer: TibetanSemanticAnalyzer, corpus_sentences: list[str]
) -> None:
    """Stage 11 interprets Stage 8's output; it never re-segments or re-tags.

    Every morpheme a node carries must be exactly the one at that index in the
    tree, and the nodes must tile the tree's indices without overlapping.
    """
    pipeline = Pipeline(semantic_analyzer)
    for sentence in corpus_sentences:
        tree = pipeline.tree(sentence)
        graph = pipeline.graph(sentence)

        previous_end = 0
        for node in graph.nodes:
            assert node.start_index >= previous_end
            assert node.end_index <= tree.num_nodes
            for offset, morpheme in enumerate(node.morphemes):
                original = tree.nodes[node.start_index + offset].morpheme
                assert morpheme == original
            previous_end = node.end_index


def test_every_graph_is_an_acyclic_forest(
    semantic_analyzer: TibetanSemanticAnalyzer, corpus_sentences: list[str]
) -> None:
    """The guarantee a plugin walking the graph relies on.

    Acyclicity is enforced by the model, so what is checked here is the stronger
    property the analyser's contraction actually produces: no node has two
    governors, which makes the graph a forest.
    """
    pipeline = Pipeline(semantic_analyzer)
    for sentence in corpus_sentences:
        graph = pipeline.graph(sentence)
        targets = [edge.target for edge in graph.edges]
        assert len(targets) == len(set(targets)), sentence


def test_names_and_terms_survive_into_the_graph_as_whole_concepts(
    semantic_analyzer: TibetanSemanticAnalyzer, corpus_sentences: list[str]
) -> None:
    """Stage 9's and Stage 10's spans must be reproduced exactly, not re-derived."""
    pipeline = Pipeline(semantic_analyzer)
    matched = 0
    for sentence in corpus_sentences:
        tree = pipeline.tree(sentence)
        entities = pipeline.ner.recognize(tree)
        graph = pipeline.semantics.analyze(tree, entities=entities)
        anchored = {node.span: node for node in graph.named_entities}
        for entity in entities.entities:
            assert entity.span in anchored, entity.text
            assert anchored[entity.span].text == entity.text
            matched += 1
    assert matched > 5, "the corpus should contain recognisable names"


def test_the_pipeline_and_the_tokenizer_agree_on_the_same_sentences(
    sentence_segmenter: TibetanSentenceSegmenter,
    semantic_analyzer: TibetanSemanticAnalyzer,
    tokenizer: TiBERTTokenizer,
    corpus_document: str,
) -> None:
    """Stage 5 and Stage 11 are parallel consumers of Stage 4's sentences."""
    pipeline = Pipeline(semantic_analyzer)
    for sentence in sentence_segmenter.segment(corpus_document).sentences[:20]:
        encoded = tokenizer.encode(sentence.text)
        graph = pipeline.graph(sentence.text)
        assert encoded.source == sentence.text == graph.source


# -- Linguistic behaviour on authentic text ------------------------------------
def test_most_sentences_receive_a_predicate(
    semantic_analyzer: TibetanSemanticAnalyzer, corpus_sentences: list[str]
) -> None:
    """Figure 5's *Meaning Representation*, measured on real sentences."""
    pipeline = Pipeline(semantic_analyzer)
    with_predicate = sum(1 for sentence in corpus_sentences if pipeline.graph(sentence).predicates)
    assert with_predicate / len(corpus_sentences) >= 0.80, with_predicate


def test_most_predicates_resolve_to_a_dictionary_lemma(
    semantic_analyzer: TibetanSemanticAnalyzer, corpus_sentences: list[str]
) -> None:
    """Lemmatisation is what makes a predicate an identity rather than a surface.

    Measured against the shipped lexicon, so a payload regression shows up here.
    """
    pipeline = Pipeline(semantic_analyzer)
    total = lemmatized = 0
    for sentence in corpus_sentences:
        for predicate in pipeline.graph(sentence).predicates:
            total += 1
            lemmatized += predicate.lemma is not None
    assert total > 20
    assert lemmatized / total >= 0.60, f"{lemmatized}/{total}"


def test_most_roles_rest_on_a_case_particle_or_the_lexicon(
    semantic_analyzer: TibetanSemanticAnalyzer, corpus_sentences: list[str]
) -> None:
    """The quality signal for this stage.

    A role backed by ``STRUCTURE`` is only Stage 8's reading relabelled; one
    backed by ``CASE`` or ``LEXICON`` rests on a resource. The share of the
    latter is what Stage 11 contributes, and pinning it means a change that
    quietly stopped consulting the lexicon fails here.
    """
    pipeline = Pipeline(semantic_analyzer)
    evidence: collections.Counter[RoleEvidence] = collections.Counter()
    for sentence in corpus_sentences:
        evidence.update(edge.evidence for edge in pipeline.graph(sentence).edges)

    total = sum(evidence.values())
    assert total > 200
    grounded = evidence[RoleEvidence.CASE] + evidence[RoleEvidence.LEXICON]
    assert grounded / total >= 0.40, evidence


def test_few_roles_are_left_unspecified(
    semantic_analyzer: TibetanSemanticAnalyzer, corpus_sentences: list[str]
) -> None:
    """Unresolved roles are recorded rather than guessed, and stay rare."""
    pipeline = Pipeline(semantic_analyzer)
    total = unspecified = 0
    for sentence in corpus_sentences:
        graph = pipeline.graph(sentence)
        total += graph.num_edges
        unspecified += graph.num_unspecified
    assert total > 200
    assert unspecified / total <= 0.10, f"{unspecified}/{total}"


def count_reclassified(pipeline: Pipeline, sentence: str) -> int:
    """How many arguments Stage 8 read as ``arg1`` this stage relabels PATIENT.

    Counts *changes*, not *corrections*: it says the lexicon overrode Stage 8's
    structural reading, not that the new label is right. See
    ``test_the_reclassification_is_corroborated_by_the_gold_annotation`` for what
    can actually be validated.
    """
    tree = pipeline.tree(sentence)
    graph = pipeline.graph(sentence)
    return sum(
        1
        for edge in graph.edges
        if tree.nodes[graph.nodes[edge.target].head_index].relation is DependencyRelation.ARG1
        and edge.role is SemanticRole.PATIENT
        and edge.evidence is RoleEvidence.LEXICON
    )


def test_the_lexicon_reclassifies_absolutive_arguments_stage_8_read_as_subjects(
    semantic_analyzer: TibetanSemanticAnalyzer, corpus_sentences: list[str]
) -> None:
    """The substantive change Stage 11 makes, measured on real text.

    ADR-010 records that Stage 8 reads the object of a transitive clause as its
    subject whenever the agentive is the fused ``ས``/``ར`` Stage 6 will not
    split. Stage 11 decides from the verb's own attested frame instead. If this
    count fell to zero the lexicon would no longer be doing any work.

    This asserts only that the override happens. Whether it happens *correctly*
    is a separate question, and the test below is as far as the available data
    lets it be answered.
    """
    pipeline = Pipeline(semantic_analyzer)
    assert sum(count_reclassified(pipeline, s) for s in corpus_sentences) > 20


def test_the_reclassification_is_corroborated_by_the_gold_annotation(
    sentence_segmenter: TibetanSentenceSegmenter,
    semantic_analyzer: TibetanSemanticAnalyzer,
    tagged_corpus: list[list[tuple[str, str]]],
) -> None:
    """How far the reclassification can be validated, rather than asserted.

    No gold semantic-role annotation exists for Tibetan in this repository, so
    no precision figure is obtainable for the relabelling itself. What *is*
    obtainable is corroboration of the judgement it rests on. The reclassification
    fires exactly when the verb's frame says the clause is transitive but the
    pipeline saw no agentive. The gold corpus annotates the agentive as its own
    token, so where the gold annotation for the same sentence *does* contain
    ``case.agn``, the clause really is transitive and Stage 8's reading really
    was wrong.

    Gold tags are aligned to the analysis by character offset, which is the
    method ADR-007 established for Stage 7.

    The measured share is a **lower bound, not precision**: Tibetan drops
    arguments freely, so a transitive verb with no written agent anywhere is
    ordinary, and the remainder is *undecidable from this evidence* rather than
    wrong. The threshold is set well below the measured value so the test pins
    the property, not the number.
    """
    pipeline = Pipeline(semantic_analyzer)
    reclassified = corroborated = 0
    gold_agentive_sentences = pipeline_missed = 0

    for line in tagged_corpus:
        text = "".join(surface for surface, _ in line)
        is_agentive: list[bool] = []
        for surface, tag in line:
            is_agentive.extend([tag == "case.agn"] * len(surface))

        for sentence in sentence_segmenter.segment(text).sentences:
            gold_has_agentive = any(is_agentive[sentence.span.char_start : sentence.span.char_end])
            here = count_reclassified(pipeline, sentence.text)
            reclassified += here
            corroborated += here if gold_has_agentive else 0

            if gold_has_agentive:
                gold_agentive_sentences += 1
                tree = pipeline.tree(sentence.text)
                pipeline_missed += not any(node.tag == "case.agn" for node in tree.nodes)

    assert reclassified > 100, reclassified
    assert corroborated / reclassified >= 0.20, (corroborated, reclassified)

    # The upstream gap that makes the reclassification necessary, measured here
    # rather than taken from ADR-010: the agentive is in the gold annotation and
    # the pipeline does not see it, because Stage 6 does not split the fused form.
    assert gold_agentive_sentences > 50
    assert pipeline_missed / gold_agentive_sentences >= 0.50, (
        pipeline_missed,
        gold_agentive_sentences,
    )


def test_the_corpus_exercises_every_kind_of_intent(
    semantic_analyzer: TibetanSemanticAnalyzer, corpus_sentences: list[str]
) -> None:
    """Figure 5's *Intent Analysis*, measured on real narrative Tibetan.

    Milarepa's life story is dialogue-heavy, so it contains questions and
    commands as well as statements. Finding all three confirms the classifier is
    reading real morphology rather than defaulting.
    """
    pipeline = Pipeline(semantic_analyzer)
    moods: collections.Counter[SentenceMood] = collections.Counter()
    negative = 0
    for sentence in corpus_sentences:
        intent = pipeline.graph(sentence).intent
        moods[intent.mood] += 1
        negative += intent.polarity.value == "negative"

    assert set(moods) == set(SentenceMood), moods
    assert moods[SentenceMood.DECLARATIVE] > moods[SentenceMood.INTERROGATIVE]
    assert negative > 0


def test_entity_and_term_grouping_reduces_the_node_count(
    semantic_analyzer: TibetanSemanticAnalyzer, corpus_sentences: list[str]
) -> None:
    """The measurable benefit of running Stages 9 and 10 first."""
    pipeline = Pipeline(semantic_analyzer)
    ungrouped = grouped = 0
    for sentence in corpus_sentences:
        tree = pipeline.tree(sentence)
        ungrouped += pipeline.semantics.analyze(tree).num_nodes
        grouped += pipeline.graph(sentence).num_nodes
    assert grouped < ungrouped, (grouped, ungrouped)


# -- Determinism, concurrency and cost -----------------------------------------
def test_the_whole_pipeline_is_deterministic(
    sentence_segmenter: TibetanSentenceSegmenter,
    semantic_analyzer: TibetanSemanticAnalyzer,
    corpus_document: str,
) -> None:
    pipeline = Pipeline(semantic_analyzer)

    def run() -> list[SemanticGraph]:
        return [
            pipeline.graph(sentence.text)
            for sentence in sentence_segmenter.segment(corpus_document).sentences[:30]
        ]

    assert run() == run()


def test_concurrent_analysis_matches_serial_analysis(
    semantic_analyzer: TibetanSemanticAnalyzer, corpus_sentences: list[str]
) -> None:
    """The daemon analyses many sentences at once against one analyser.

    Every component claims to be safe to share for read-only use; this is the
    check that the claim holds through the whole chain.
    """
    pipeline = Pipeline(semantic_analyzer)
    serial = [pipeline.graph(sentence) for sentence in corpus_sentences]
    with ThreadPoolExecutor(max_workers=8) as pool:
        concurrent = list(pool.map(pipeline.graph, corpus_sentences))
    assert concurrent == serial


def test_the_shared_lexicon_is_loaded_once_for_many_analyzers() -> None:
    """Cold start matters: the daemon must not re-parse the payload per request."""
    first = TibetanSemanticAnalyzer()
    second = TibetanSemanticAnalyzer()
    assert first.analyze(DependencyTree(source="")) == second.analyze(DependencyTree(source=""))
    assert default_verb_lexicon() is default_verb_lexicon()


def test_the_lexicon_is_consulted_at_most_twice_per_verb(
    corpus_sentences: list[str],
) -> None:
    """A work-based latency budget, in place of a wall-clock assertion.

    NFR 5.1 allows 50 ms for an interactive edit. Timing is not a stable way to
    defend that in a test suite -- an earlier stage found a 4x swing between an
    isolated run and an in-suite one -- so what is pinned instead is the amount
    of work: the analyser must never scan the lexicon, only address it, at most
    once for a whole run and once for its head.
    """
    counting = CountingVerbLexicon()
    pipeline = Pipeline(TibetanSemanticAnalyzer(verbs=counting))
    verbal = 0
    for sentence in corpus_sentences:
        graph = pipeline.graph(sentence)
        verbal += sum(1 for node in graph.nodes if node.head.category.value == "verb")

    assert verbal > 50
    assert counting.lookups <= 2 * verbal, (counting.lookups, verbal)


def test_a_counting_lexicon_satisfies_the_repository_protocol() -> None:
    assert isinstance(CountingVerbLexicon(), VerbLexiconRepository)
