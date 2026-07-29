"""End-to-end integration test for AI-assisted spelling correction.

Demonstrates the complete flow:

    Unknown word
    ↓
    AI correction (via CorrectionProvider + mock scorer)
    ↓
    Suggestion with replacement
    ↓
    Fusion Engine → DocumentPatch with edit operations

All tests use mock scoring — no real TiBERT model is required.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from teea.core.types import TextSpan, utf8_byte_offsets
from teea.fusion import PriorityRankedFusionEngine, SuggestionPriority
from teea.nlp.dependency import DependencyNode, DependencyRelation, DependencyTree
from teea.nlp.morphology import Morpheme, MorphemeKind
from teea.nlp.ner import EntityAnnotation
from teea.nlp.postagging import TaggedMorpheme
from teea.nlp.segmentation import Sentence
from teea.nlp.semantics import SemanticGraph, SentenceIntent
from teea.nlp.snapshot import DocumentSnapshot, SentenceAnalysis
from teea.nlp.snapshot.hashing import sentence_hash
from teea.nlp.terminology import TerminologyAnnotation
from teea.plugins import SupervisedPluginRuntime
from teea.plugins.builtin.correction import CorrectionProvider
from teea.plugins.builtin.spelling import SpellCheckerPlugin


# -- Helpers -------------------------------------------------------------------


class SelectiveDictionary:
    """A dictionary that knows only a fixed set of words."""

    def __init__(self, known: set[str]) -> None:
        self._known = known

    @property
    def tags(self) -> frozenset[str]:
        return frozenset()

    @property
    def tag_counts(self) -> Mapping[str, int]:
        return {}

    def lookup(self, surface: str) -> Mapping[str, int] | None:
        return {"n.count": 1} if surface in self._known else None

    def transitions(self, tag: str) -> Mapping[str, int]:
        return {}

    def __contains__(self, surface: str) -> bool:
        return surface in self._known


def _make_root_morpheme(text: str, span: TextSpan) -> TaggedMorpheme:
    return TaggedMorpheme(
        morpheme=Morpheme(text=text, span=span, kind=MorphemeKind.ROOT),
        tag="n.count",
        category="noun",
    )


def _make_single_node_snapshot(text: str) -> DocumentSnapshot:
    """Build a snapshot with one sentence containing one ROOT node."""
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
    analysis = SentenceAnalysis(
        sentence=sent,
        tree=tree,
        entities=entities,
        terms=terms,
        graph=graph,
        content_hash=sentence_hash(text),
    )
    return DocumentSnapshot(source=text, analyses=(analysis,))


def _make_two_node_snapshot(
    text: str,
    node1_text: str,
    node2_text: str,
) -> DocumentSnapshot:
    """Build a snapshot with one sentence containing two ROOT+DEP nodes."""
    byte_offsets = utf8_byte_offsets(text)
    n1_end = len(node1_text)

    span1 = TextSpan(
        char_start=0,
        char_end=n1_end,
        byte_start=byte_offsets[0],
        byte_end=byte_offsets[n1_end],
    )
    span2 = TextSpan(
        char_start=n1_end,
        char_end=n1_end + len(node2_text),
        byte_start=byte_offsets[n1_end],
        byte_end=byte_offsets[n1_end + len(node2_text)],
    )

    m1 = _make_root_morpheme(node1_text, span1)
    m2 = _make_root_morpheme(node2_text, span2)
    nodes = (
        DependencyNode(index=0, head=-1, relation=DependencyRelation.ROOT, morpheme=m1),
        DependencyNode(index=1, head=0, relation=DependencyRelation.DEP, morpheme=m2),
    )

    sent_span = TextSpan(
        char_start=0,
        char_end=len(text),
        byte_start=byte_offsets[0],
        byte_end=byte_offsets[len(text)],
    )
    sent = Sentence(text=text, index=0, span=sent_span, terminator="")
    tree = DependencyTree(source=text, nodes=nodes)
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


# -- Mock scorer ---------------------------------------------------------------


def mock_scorer(
    sentence: str, word_start: int, word_end: int, candidates: list[str]
) -> dict[str, float]:
    """Return a high score for the first candidate, low for others."""
    scores: dict[str, float] = {}
    for i, c in enumerate(candidates):
        scores[c] = 0.95 - i * 0.1
    return scores


# -- Integration tests ---------------------------------------------------------


class TestSpellCheckerWithCorrection:
    """SpellCheckerPlugin with CorrectionProvider returns edits."""

    def test_unknown_word_gets_correction(self) -> None:
        """An unknown word is corrected when a provider is available."""
        known = {"good"}
        unknown = "baad"
        vocab = frozenset({"good", "bad", "bead", "band"})

        provider = CorrectionProvider(
            mock_scorer, vocab, confidence_threshold=0.5
        )
        plugin = SpellCheckerPlugin(
            dictionary=SelectiveDictionary(known),
            correction_provider=provider,
        )

        snapshot = _make_single_node_snapshot(unknown)
        suggestions = list(plugin.examine(snapshot))

        assert len(suggestions) == 1
        sug = suggestions[0]
        assert sug.source == "teea.spelling"
        assert sug.replacement is not None  # correction provided
        assert sug.replacement in vocab
        assert sug.score == 0.92
        assert sug.priority is SuggestionPriority.HIGH
        assert "Correction" in sug.message

    def test_without_provider_falls_back_to_advisory(self) -> None:
        """Without a correction provider, behaviour is the original advisory."""
        plugin = SpellCheckerPlugin(
            dictionary=SelectiveDictionary(set()),
            correction_provider=None,
        )

        snapshot = _make_single_node_snapshot("unknown")
        suggestions = list(plugin.examine(snapshot))

        assert len(suggestions) == 1
        assert suggestions[0].replacement is None
        assert suggestions[0].priority is SuggestionPriority.MEDIUM
        assert "Unknown word" in suggestions[0].message

    def test_provider_returning_none_falls_back_to_advisory(self) -> None:
        """When the provider can't find a correction, the advisory is emitted."""
        def no_candidates_scorer(
            s: str, ws: int, we: int, c: list[str]
        ) -> dict[str, float]:
            return {c_: 0.1 for c_ in c}  # all below threshold

        provider = CorrectionProvider(
            no_candidates_scorer,
            frozenset({"far_away_word"}),  # too distant from "unknown"
            confidence_threshold=0.5,
        )
        plugin = SpellCheckerPlugin(
            dictionary=SelectiveDictionary(set()),
            correction_provider=provider,
        )

        snapshot = _make_single_node_snapshot("unknown")
        suggestions = list(plugin.examine(snapshot))

        assert len(suggestions) == 1
        assert suggestions[0].replacement is None


class TestEndToEndPipeline:
    """Full pipeline: Plugin Runtime → SpellChecker with AI → Fusion Engine."""

    def test_correction_flows_through_full_pipeline(self) -> None:
        """
        End-to-end:
            Unknown word → AI correction → Suggestion with replacement → Fusion Engine
        """
        # -- Setup --
        known_word = "good"
        unknown_word = "baad"
        doc_text = known_word + unknown_word
        vocab = frozenset({"good", "bad", "bead", "band"})

        provider = CorrectionProvider(
            mock_scorer, vocab, confidence_threshold=0.3
        )
        plugin = SpellCheckerPlugin(
            dictionary=SelectiveDictionary({known_word}),
            correction_provider=provider,
        )

        # -- Plugin Runtime dispatch --
        snapshot = _make_two_node_snapshot(doc_text, known_word, unknown_word)
        runtime = SupervisedPluginRuntime([plugin])
        results = runtime.dispatch(snapshot)

        # Runtime should be healthy and produce suggestions.
        assert results.is_healthy is True
        assert results.num_plugins == 1
        assert results.num_suggestions == 1

        outcome = results.outcome_of("teea.spelling")
        assert outcome is not None
        assert outcome.succeeded is True
        sug = outcome.suggestions[0]

        # The suggestion should carry a replacement (AI correction).
        assert sug.replacement is not None
        assert sug.replacement in vocab
        assert sug.is_edit is True

        # -- Fusion Engine --
        engine = PriorityRankedFusionEngine()
        unified = engine.fuse(doc_text, results.suggestions)

        # The correction should survive fusion as an edit.
        assert unified.num_suggestions == 1
        assert len(unified.edits) == 1
        assert unified.edits[0].replacement == sug.replacement

        # The patch should have one edit operation.
        assert unified.patch.num_operations == 1
        op = unified.patch.operations[0]
        assert op.replacement == sug.replacement

        # Applying the patch should produce the corrected document.
        corrected = unified.patch.apply()
        assert unknown_word not in corrected
        assert sug.replacement in corrected

    def test_advisory_flows_through_fusion_without_patch(self) -> None:
        """
        Without a correction provider, advisories flow through fusion
        and produce no patch (existing behaviour preserved).
        """
        plugin = SpellCheckerPlugin(
            dictionary=SelectiveDictionary(set()),
            correction_provider=None,
        )
        snapshot = _make_single_node_snapshot("unknown")
        runtime = SupervisedPluginRuntime([plugin])
        results = runtime.dispatch(snapshot)

        engine = PriorityRankedFusionEngine()
        unified = engine.fuse("unknown", results.suggestions)

        # Advisory survives fusion.
        assert unified.num_suggestions == 1
        assert unified.advisories[0].is_advisory is True
        # No patch operations for advisories.
        assert unified.patch.is_empty


class TestTibetanEndToEnd:
    """Tibetan-specific end-to-end correction."""

    def test_tibetan_correction_pipeline(self) -> None:
        # Vocabulary of correct Tibetan words.
        vocab = frozenset({"བཀྲ་ཤིས་", "བདེ་ལེགས།"})
        known = {"བདེ་ལེགས།"}
        misspelled = "བཀྲ་ཤིམ་"  # edit distance 1 from བཀྲ་ཤིས་

        doc_text = misspelled + "བདེ་ལེགས།"

        provider = CorrectionProvider(
            mock_scorer, vocab, confidence_threshold=0.3
        )
        plugin = SpellCheckerPlugin(
            dictionary=SelectiveDictionary(known),
            correction_provider=provider,
        )

        snapshot = _make_two_node_snapshot(doc_text, misspelled, "བདེ་ལེགས།")
        runtime = SupervisedPluginRuntime([plugin])
        results = runtime.dispatch(snapshot)

        assert results.is_healthy is True
        assert results.num_suggestions == 1

        sug = results.suggestions[0]
        assert sug.replacement is not None
        assert sug.replacement in vocab
        assert "Correction" in sug.message

        # Fusion produces a patch.
        engine = PriorityRankedFusionEngine()
        unified = engine.fuse(doc_text, results.suggestions)
        assert unified.patch.num_operations == 1

        corrected = unified.patch.apply()
        assert misspelled not in corrected


class TestDemoExamples:
    """Verifies the hackathon demo examples."""

    def test_demo_examples_corrected(self) -> None:
        import json
        from pathlib import Path

        demo_file = Path(__file__).parent.parent.parent.parent / "tests" / "demo_spelling_examples.json"
        examples = json.loads(demo_file.read_text("utf-8"))

        vocab = frozenset(ex["correct"] for ex in examples)
        known = set()

        provider = CorrectionProvider(
            mock_scorer, vocab, confidence_threshold=0.3
        )
        plugin = SpellCheckerPlugin(
            dictionary=SelectiveDictionary(known),
            correction_provider=provider,
        )

        for ex in examples:
            wrong = ex["wrong"]
            correct = ex["correct"]
            
            snapshot = _make_single_node_snapshot(wrong)
            suggestions = list(plugin.examine(snapshot))
            
            assert len(suggestions) == 1, f"Expected 1 suggestion for {wrong}, got {len(suggestions)}"
            assert suggestions[0].replacement == correct, f"Expected {correct} for {wrong}, got {suggestions[0].replacement}"
