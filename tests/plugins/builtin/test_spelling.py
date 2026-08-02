"""Tests for the built-in SpellCheckerPlugin.

Tests cover unit behaviour (empty doc, known words, unknown words), thread
safety, and integration with the Plugin Runtime, Fusion Engine, workflow,
and TEEADaemon.
"""

from __future__ import annotations

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor

import pytest

from teea.core.types import TextSpan, utf8_byte_offsets
from teea.daemon import TEEADaemon
from teea.fusion import PriorityRankedFusionEngine, SuggestionPriority
from teea.nlp.dependency import DependencyNode, DependencyRelation, DependencyTree
from teea.nlp.morphology import Morpheme, MorphemeKind
from teea.nlp.ner import EntityAnnotation
from teea.nlp.postagging import TaggedMorpheme
from teea.nlp.segmentation import Sentence
from teea.nlp.semantics import SemanticGraph, SentenceIntent
from teea.nlp.snapshot import (
    DocumentSnapshot,
    LanguageServerSnapshotBuilder,
    SentenceAnalysis,
)
from teea.nlp.snapshot.hashing import sentence_hash
from teea.nlp.terminology import TerminologyAnnotation
from teea.plugins import SupervisedPluginRuntime
from teea.plugins.builtin.spelling import SpellCheckerPlugin
from teea.plugins.interfaces import FeaturePlugin

# -- Dictionary test doubles ----------------------------------------------------


class AlwaysEmptyDictionary:
    """A dictionary that knows no surface forms at all -- every word is unknown."""

    @property
    def tags(self) -> frozenset[str]:
        return frozenset()

    @property
    def tag_counts(self) -> Mapping[str, int]:
        return {}

    def lookup(self, surface: str) -> Mapping[str, int] | None:
        return None

    def transitions(self, tag: str) -> Mapping[str, int]:
        return {}

    def __contains__(self, surface: str) -> bool:
        return False


class EverythingKnownDictionary:
    """A dictionary that accepts every surface form -- no unknown words."""

    @property
    def tags(self) -> frozenset[str]:
        return frozenset({"n.count"})

    @property
    def tag_counts(self) -> Mapping[str, int]:
        return {"n.count": 1}

    def lookup(self, surface: str) -> Mapping[str, int] | None:
        return {"n.count": 1}

    def transitions(self, tag: str) -> Mapping[str, int]:
        return {}

    def __contains__(self, surface: str) -> bool:
        return True


class SelectivelyEmptyDictionary:
    """Accepts only a known set of words."""

    def __init__(self, known: set[str]) -> None:
        self._known = known

    @property
    def tags(self) -> frozenset[str]:
        return frozenset()

    @property
    def tag_counts(self) -> Mapping[str, int]:
        return {}

    def lookup(self, surface: str) -> Mapping[str, int] | None:
        return None if surface not in self._known else {"n.count": 1}

    def transitions(self, tag: str) -> Mapping[str, int]:
        return {}

    def __contains__(self, surface: str) -> bool:
        return surface in self._known


# -- Snapshot builder helpers ---------------------------------------------------


def _make_root_morpheme(text: str, span: TextSpan) -> TaggedMorpheme:
    """Build a tagged root morpheme for testing with exact byte offsets."""
    return TaggedMorpheme(
        morpheme=Morpheme(text=text, span=span, kind=MorphemeKind.ROOT),
        tag="n.count",
        category="noun",
    )


def _make_single_node_snapshot(text: str) -> DocumentSnapshot:
    """Build a snapshot with one sentence containing one ROOT dependency node.

    The sentence text equals the node text.  Only ROOT relation is valid for
    a single-node tree per the DependencyNode validator.

    Args:
        text: The document text (also used as the single node's text).

    Returns:
        A valid DocumentSnapshot.
    """
    byte_offsets = utf8_byte_offsets(text)
    span = TextSpan(
        char_start=0,
        char_end=len(text),
        byte_start=byte_offsets[0],
        byte_end=byte_offsets[len(text)],
    )
    morpheme = _make_root_morpheme(text, span)
    node = DependencyNode(
        index=0, head=-1, relation=DependencyRelation.ROOT, morpheme=morpheme
    )
    sent_span = TextSpan(
        char_start=0,
        char_end=len(text),
        byte_start=byte_offsets[0],
        byte_end=byte_offsets[len(text)],
    )
    sent = Sentence(text=text, index=0, span=sent_span, terminator="")
    tree = DependencyTree(source=text, nodes=(node,))
    entities = EntityAnnotation(source=text, entities=())
    terms = TerminologyAnnotation(source=text, terms=())
    graph = SemanticGraph(
        source=text,
        intent=SentenceIntent(mood="declarative", polarity="affirmative"),
        nodes=(),
        edges=(),
    )
    hsh = sentence_hash(text)
    analysis = SentenceAnalysis(
        sentence=sent,
        tree=tree,
        entities=entities,
        terms=terms,
        graph=graph,
        content_hash=hsh,
    )
    return DocumentSnapshot(source=text, analyses=(analysis,))


def _make_two_node_snapshot(
    text: str,
    node1_text: str,
    node2_text: str,
    node2_relation: DependencyRelation = DependencyRelation.DEP,
) -> DocumentSnapshot:
    """Build a snapshot with one sentence containing two dependency nodes.

    Node 0 is the ROOT.  Node 1 is a child (``head=0``) with the given relation.
    The text is ``node1_text + node2_text`` (no separator), so positions are
    trivially contiguous.
    """
    sent_text = text
    byte_offsets = utf8_byte_offsets(sent_text)
    n1_end = len(node1_text)
    n2_start = n1_end
    n2_end = n2_start + len(node2_text)

    span1 = TextSpan(
        char_start=0,
        char_end=n1_end,
        byte_start=byte_offsets[0],
        byte_end=byte_offsets[n1_end],
    )
    span2 = TextSpan(
        char_start=n2_start,
        char_end=n2_end,
        byte_start=byte_offsets[n2_start],
        byte_end=byte_offsets[n2_end],
    )

    n1 = _make_root_morpheme(node1_text, span1)
    n2 = _make_root_morpheme(node2_text, span2)
    nodes = [
        DependencyNode(index=0, head=-1, relation=DependencyRelation.ROOT, morpheme=n1),
        DependencyNode(index=1, head=0, relation=node2_relation, morpheme=n2),
    ]

    sent_span = TextSpan(
        char_start=0,
        char_end=len(sent_text),
        byte_start=byte_offsets[0],
        byte_end=byte_offsets[len(sent_text)],
    )
    sent = Sentence(text=sent_text, index=0, span=sent_span, terminator="")
    tree = DependencyTree(source=sent_text, nodes=tuple(nodes))
    entities = EntityAnnotation(source=sent_text, entities=())
    terms = TerminologyAnnotation(source=sent_text, terms=())
    graph = SemanticGraph(
        source=sent_text,
        intent=SentenceIntent(mood="declarative", polarity="affirmative"),
        nodes=(),
        edges=(),
    )
    hsh = sentence_hash(sent_text)
    analysis = SentenceAnalysis(
        sentence=sent,
        tree=tree,
        entities=entities,
        terms=terms,
        graph=graph,
        content_hash=hsh,
    )
    return DocumentSnapshot(source=sent_text, analyses=(analysis,))


# -- Basic unit tests -----------------------------------------------------------


def test_plugin_has_a_name() -> None:
    plugin = SpellCheckerPlugin()
    assert plugin.name == "teea.spelling"


def test_plugin_satisfies_the_feature_plugin_protocol() -> None:
    assert isinstance(SpellCheckerPlugin(), FeaturePlugin)


def test_empty_document_yields_no_suggestions() -> None:
    plugin = SpellCheckerPlugin()
    suggestions = list(plugin.examine(DocumentSnapshot(source="", analyses=())))
    assert suggestions == []


def test_document_with_no_analyses_yields_no_suggestions() -> None:
    plugin = SpellCheckerPlugin()
    suggestions = list(plugin.examine(DocumentSnapshot(source="some text", analyses=())))
    assert suggestions == []


# -- Dictionary dependency -----------------------------------------------------


def test_everything_known_yields_no_suggestions() -> None:
    plugin = SpellCheckerPlugin(dictionary=EverythingKnownDictionary())
    snapshot = _make_single_node_snapshot("known_word")
    suggestions = list(plugin.examine(snapshot))
    assert suggestions == []


def test_unknown_words_are_flagged() -> None:
    plugin = SpellCheckerPlugin(dictionary=AlwaysEmptyDictionary())
    snapshot = _make_single_node_snapshot("བཀྲ་ཤིས་")
    suggestions = list(plugin.examine(snapshot))
    assert len(suggestions) == 1
    sug = suggestions[0]
    assert sug.source == "teea.spelling"
    assert sug.replacement is None
    assert sug.score == 0.85
    assert sug.priority is SuggestionPriority.MEDIUM
    assert "Unknown word" in sug.message
    assert "བཀྲ་ཤིས་" in sug.message


def test_unknown_words_have_correct_spans() -> None:
    doc_text = "བཀྲ་ཤིས་བདེ་ལེགས།"
    plugin = SpellCheckerPlugin(dictionary=SelectivelyEmptyDictionary(known={"བདེ་ལེགས།"}))
    snapshot = _make_two_node_snapshot(doc_text, "བཀྲ་ཤིས་", "བདེ་ལེགས།")
    suggestions = list(plugin.examine(snapshot))
    assert len(suggestions) == 1
    sug = suggestions[0]
    span = sug.span
    assert doc_text[span.char_start : span.char_end] == "བཀྲ་ཤིས་"


# -- Relation-type filtering --------------------------------------------------


@pytest.mark.parametrize(
    "relation",
    [DependencyRelation.PUNCT, DependencyRelation.CASE,
     DependencyRelation.AUX, DependencyRelation.MARK, DependencyRelation.NEG],
)
def test_pipeline_artifacts_are_skipped(relation: DependencyRelation) -> None:
    """Grammatical/pipeline relations must not be spell-checked."""
    # The ROOT node's text is known; only the artifact child is unknown.
    # The child should be skipped because its relation is one of the filtered
    # pipeline artifacts (punct, case, aux, mark, neg).
    known = {"root"}
    plugin = SpellCheckerPlugin(dictionary=SelectivelyEmptyDictionary(known=known))
    snapshot = _make_two_node_snapshot(
        "rootchild", "root", "child", node2_relation=relation,
    )
    suggestions = list(plugin.examine(snapshot))
    assert len(suggestions) == 0


def test_content_relations_are_checked() -> None:
    """Root relations should be checked."""
    plugin = SpellCheckerPlugin(dictionary=AlwaysEmptyDictionary())
    snapshot = _make_single_node_snapshot("text")
    suggestions = list(plugin.examine(snapshot))
    assert len(suggestions) == 1


# -- Empty dependency tree fallback -------------------------------------------


def _make_empty_tree_snapshot(text: str) -> DocumentSnapshot:
    """Build a snapshot whose dependency tree has no nodes (no parse)."""
    byte_offsets = utf8_byte_offsets(text)
    sent_span = TextSpan(
        char_start=0,
        char_end=len(text),
        byte_start=byte_offsets[0],
        byte_end=byte_offsets[len(text)],
    )
    sent = Sentence(text=text, index=0, span=sent_span, terminator="")
    tree = DependencyTree(source=text, nodes=())
    entities = EntityAnnotation(source=text, entities=())
    terms = TerminologyAnnotation(source=text, terms=())
    graph = SemanticGraph(
        source=text,
        intent=SentenceIntent(mood="declarative", polarity="affirmative"),
        nodes=(),
        edges=(),
    )
    analysis = SentenceAnalysis(
        sentence=sent,
        tree=tree,
        entities=entities,
        terms=terms,
        graph=graph,
        content_hash=sentence_hash(text),
    )
    return DocumentSnapshot(source=text, analyses=(analysis,))


def test_empty_tree_sentence_is_tokenized_by_tsheg() -> None:
    """A sentence with an empty dependency tree is spell-checked per token.

    Regression: with no fallback, an empty tree used to skip the whole
    sentence, so the fused unknown token could never be reported.
    """
    known = {"ང", "ཚོས", "སློབ"}
    plugin = SpellCheckerPlugin(dictionary=SelectivelyEmptyDictionary(known=known))
    text = "ང་ཚོས་སློབ་སྦྱངབྱེད།"
    snapshot = _make_empty_tree_snapshot(text)

    suggestions = list(plugin.examine(snapshot))

    assert len(suggestions) == 1
    sug = suggestions[0]
    assert sug.error_type == "SPELLING"
    assert text[sug.span.char_start : sug.span.char_end] == "སྦྱངབྱེད།"
    assert "སྦྱངབྱེད" in sug.message


def test_empty_tree_sentence_flags_each_unknown_token() -> None:
    """Every tsheg-delimited token of an empty-tree sentence is examined."""
    plugin = SpellCheckerPlugin(dictionary=AlwaysEmptyDictionary())
    text = "ང་ཚོས་སློབ་སྦྱངབྱེད།"
    snapshot = _make_empty_tree_snapshot(text)

    suggestions = list(plugin.examine(snapshot))
    spans = {(s.span.char_start, s.span.char_end) for s in suggestions}

    # The final fallback token includes the trailing shad (no separate PUNCT
    # node exists for a manually tokenized sentence), so it spans 9 chars.
    assert spans == {(0, 1), (2, 5), (6, 10), (11, 20)}


# -- Multiple sentences --------------------------------------------------------


def test_multiple_sentences_are_checked() -> None:
    plugin = SpellCheckerPlugin(dictionary=AlwaysEmptyDictionary())
    text = "word1aword1bword2a"

    def make_analysis(
        sent_text: str, node_texts: list[str], idx: int, start: int
    ) -> SentenceAnalysis:
        end = start + len(sent_text)
        byte_offsets = utf8_byte_offsets(sent_text)
        nodes: list[DependencyNode] = []
        pos = 0
        for ni, nt in enumerate(node_texts):
            span = TextSpan(
                char_start=pos,
                char_end=pos + len(nt),
                byte_start=byte_offsets[pos],
                byte_end=byte_offsets[pos + len(nt)],
            )
            m = _make_root_morpheme(nt, span)
            head = -1 if ni == 0 else 0
            rel = DependencyRelation.ROOT if ni == 0 else DependencyRelation.DEP
            nodes.append(
                DependencyNode(index=ni, head=head, relation=rel, morpheme=m)
            )
            pos += len(nt)
        sent_span = TextSpan(
            char_start=start,
            char_end=end,
            byte_start=byte_offsets[0],
            byte_end=byte_offsets[len(sent_text)],
        )
        sent = Sentence(text=sent_text, index=idx, span=sent_span, terminator="")
        tree = DependencyTree(source=sent_text, nodes=tuple(nodes))
        entities = EntityAnnotation(source=sent_text, entities=())
        terms = TerminologyAnnotation(source=sent_text, terms=())
        graph = SemanticGraph(
            source=sent_text,
            intent=SentenceIntent(mood="declarative", polarity="affirmative"),
            nodes=(),
            edges=(),
        )
        return SentenceAnalysis(
            sentence=sent,
            tree=tree,
            entities=entities,
            terms=terms,
            graph=graph,
            content_hash=sentence_hash(sent_text),
        )

    snapshot = DocumentSnapshot(
        source=text,
        analyses=(
            make_analysis("word1aword1b", ["word1a", "word1b"], 0, 0),
            make_analysis("word2a", ["word2a"], 1, 12),
        ),
    )
    suggestions = list(plugin.examine(snapshot))
    assert len(suggestions) == 3


# -- Custom dictionary injection -----------------------------------------------


def test_the_default_dictionary_is_used() -> None:
    """Uses the shipped dictionary by default (not AlwaysEmpty)."""
    plugin = SpellCheckerPlugin()
    assert plugin._dictionary is not None


def test_injected_dictionary_is_respected() -> None:
    plugin = SpellCheckerPlugin(dictionary=SelectivelyEmptyDictionary(known={"foo"}))
    snapshot = _make_two_node_snapshot("foobar", "foo", "bar")
    suggestions = list(plugin.examine(snapshot))
    assert len(suggestions) == 1
    assert "bar" in suggestions[0].message


# -- Integration with PluginRuntime --------------------------------------------


def test_plugin_runs_under_supervision() -> None:
    plugin = SpellCheckerPlugin(dictionary=AlwaysEmptyDictionary())
    runtime = SupervisedPluginRuntime([plugin])

    snapshot = _make_single_node_snapshot("text")
    results = runtime.dispatch(snapshot)

    assert results.is_healthy is True
    assert results.num_plugins == 1
    assert results.num_suggestions == 1

    outcome = results.outcome_of("teea.spelling")
    assert outcome is not None
    assert outcome.succeeded is True
    assert len(outcome.suggestions) == 1
    assert outcome.suggestions[0].source == "teea.spelling"


def test_plugin_fault_isolation() -> None:
    """A failing dictionary must not crash other plugins."""

    class BrokenDictionary:
        def __contains__(self, _: str) -> bool:
            raise RuntimeError("dictionary broke")

    plugin = SpellCheckerPlugin(dictionary=BrokenDictionary())  # type: ignore[arg-type]
    snapshot = _make_single_node_snapshot("text")

    runtime = SupervisedPluginRuntime([plugin])
    results = runtime.dispatch(snapshot)

    assert results.is_healthy is False
    outcome = results.outcome_of("teea.spelling")
    assert outcome is not None
    assert outcome.succeeded is False
    assert outcome.failure is not None
    assert outcome.failure.plugin == "teea.spelling"


def test_concurrent_dispatch_is_safe() -> None:
    """Many threads dispatching the same plugin must not corrupt state."""
    plugin = SpellCheckerPlugin(dictionary=AlwaysEmptyDictionary())
    runtime = SupervisedPluginRuntime([plugin], executor=ThreadPoolExecutor(max_workers=4))

    snapshot = _make_single_node_snapshot("text")
    results = [runtime.dispatch(snapshot) for _ in range(10)]

    for r in results:
        assert r.is_healthy is True
        assert r.num_suggestions == 1


# -- Integration with Fusion Engine --------------------------------------------


def test_suggestions_flow_through_fusion() -> None:
    plugin = SpellCheckerPlugin(dictionary=AlwaysEmptyDictionary())
    snapshot = _make_single_node_snapshot("text")
    results = SupervisedPluginRuntime([plugin]).dispatch(snapshot)

    engine = PriorityRankedFusionEngine()
    unified = engine.fuse(snapshot.source, results.suggestions)

    assert unified.num_suggestions == 1
    assert unified.advisories
    assert unified.advisories[0].source == "teea.spelling"
    assert unified.advisories[0].is_advisory is True


# -- Integration with Workflow -------------------------------------------------


def test_spell_checker_plugin_works_with_full_workflow() -> None:
    """End-to-end: a real snapshot from the Language Server passes through
    plugins and fusion without crashing, using the shipped dictionary."""
    text = "བཀྲ་ཤིས་བདེ་ལེགས།  ཚེས་གཉིས་ལ་བཀྲ་ཤིས་ཤོག"
    snapshot = LanguageServerSnapshotBuilder().analyze(text)

    plugin = SpellCheckerPlugin()
    runtime = SupervisedPluginRuntime([plugin])
    results = runtime.dispatch(snapshot)

    engine = PriorityRankedFusionEngine()
    unified = engine.fuse(text, results.suggestions)

    assert results.is_healthy is True
    assert unified.patch.is_empty  # all advisories, no edits


# -- Integration with TEEADaemon -----------------------------------------------


def test_spell_checker_plugin_works_with_daemon() -> None:
    """The SpellCheckerPlugin must be registrable on TEEADaemon and composable."""
    plugin = SpellCheckerPlugin(dictionary=AlwaysEmptyDictionary())
    daemon = TEEADaemon(plugins=[plugin])
    daemon.start()

    snapshot = _make_single_node_snapshot("text")
    results = daemon.plugins.dispatch(snapshot)

    assert results.is_healthy is True
    assert results.num_plugins == 1
    outcome = results.outcome_of("teea.spelling")
    assert outcome is not None
    assert outcome.succeeded is True
    assert len(outcome.suggestions) == 1

    daemon.stop()
