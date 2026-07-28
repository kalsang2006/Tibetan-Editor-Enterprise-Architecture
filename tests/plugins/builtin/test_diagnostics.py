"""Tests for the built-in document diagnostics plugin."""

from __future__ import annotations

from teea.core.types import TextSpan
from teea.nlp.dependency import DependencyNode, DependencyRelation, DependencyTree
from teea.nlp.morphology.models import Morpheme, MorphemeKind
from teea.nlp.ner import EntityAnnotation
from teea.nlp.postagging.models import PosCategory, TaggedMorpheme
from teea.nlp.segmentation import Sentence
from teea.nlp.semantics import SemanticGraph
from teea.nlp.snapshot import DocumentSnapshot, SentenceAnalysis
from teea.nlp.snapshot.hashing import sentence_hash
from teea.nlp.terminology import TerminologyAnnotation
from teea.plugins.builtin.diagnostics import DocumentDiagnosticsPlugin


def test_plugin_name() -> None:
    plugin = DocumentDiagnosticsPlugin()
    assert plugin.name == "teea.diagnostics"


def test_examine_empty_snapshot() -> None:
    plugin = DocumentDiagnosticsPlugin()
    snapshot = DocumentSnapshot(source="")
    results = list(plugin.examine(snapshot))
    assert len(results) == 1
    suggestion = results[0]
    assert suggestion.source == "teea.diagnostics"
    assert suggestion.replacement is None
    assert "sentence_count=0" in suggestion.message


def test_examine_with_analyses_has_stats() -> None:
    plugin = DocumentDiagnosticsPlugin()

    text = "བཀྲ"
    span = TextSpan(char_start=0, char_end=3, byte_start=0, byte_end=9)
    sent = Sentence(index=0, text=text, span=span)
    morpheme = Morpheme(text=text, span=span, kind=MorphemeKind.ROOT)
    tagged = TaggedMorpheme(morpheme=morpheme, tag="n.count", category=PosCategory.NOUN)
    node = DependencyNode(index=0, head=-1, relation=DependencyRelation.ROOT, morpheme=tagged)
    tree = DependencyTree(source=text, nodes=(node,))
    entities = EntityAnnotation(source=text)
    terms = TerminologyAnnotation(source=text)
    graph = SemanticGraph(source=text)
    analysis = SentenceAnalysis(
        sentence=sent,
        tree=tree,
        entities=entities,
        terms=terms,
        graph=graph,
        content_hash=sentence_hash(text),
    )
    snapshot = DocumentSnapshot(source=text, analyses=(analysis,))
    results = list(plugin.examine(snapshot))
    assert len(results) == 1
    suggestion = results[0]
    assert "sentence_count=1" in suggestion.message
    assert "token_count=1" in suggestion.message
