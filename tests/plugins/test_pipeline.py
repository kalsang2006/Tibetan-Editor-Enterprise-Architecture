"""Integration tests for Figure 3's P4 -> P5 -> P6 chain.

The Level-1 Data Flow Diagram routes a document through the Language Server (P4),
into the Plugin Runtime (P5) as "Parsed Tokens / Graph", out of it as "Plugin
Results", and into the Suggestion Fusion Engine (P6), which returns "Merged
Suggestions". Every one of those three components now exists, so this module runs
the whole chain end to end on real Tibetan and checks the properties that only
appear once they are composed.

The plugins are test doubles by design. Figure 5 names eight real ones and each is
its own component; the runtime is complete without them (ADR-018), and what has
to be proven here is that the *seams* line up -- that a span a plugin computes
from the snapshot still selects the right characters after fusion applies it.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor

from teea.fusion import (
    PriorityRankedFusionEngine,
    RejectionReason,
    Suggestion,
    SuggestionPriority,
)
from teea.nlp.snapshot import DocumentSnapshot, LanguageServerSnapshotBuilder
from teea.nlp.tokenization import TextNormalizer
from teea.plugins import FeaturePlugin, SupervisedPluginRuntime
from tests.plugins.conftest import (
    CrashingPlugin,
    ImpersonatingPlugin,
    SilentPlugin,
    WellBehavedPlugin,
)

P = SuggestionPriority


class EntityHighlighter:
    """Advises on every name Stage 09 found, using document coordinates."""

    name = "citation"

    def examine(self, snapshot: DocumentSnapshot) -> Iterator[Suggestion]:
        for analysis in snapshot.analyses:
            for entity in analysis.entities.entities:
                yield Suggestion(
                    source=self.name,
                    span=analysis.document_span(entity.span),
                    replacement=None,
                    score=0.8,
                    priority=P.LOW,
                    message=f"name: {entity.text}",
                )


class PredicateRewriter:
    """Proposes an edit on the first predicate of every sentence."""

    name = "grammar"

    def examine(self, snapshot: DocumentSnapshot) -> Iterator[Suggestion]:
        for analysis in snapshot.analyses:
            for node in analysis.graph.predicates[:1]:
                yield Suggestion(
                    source=self.name,
                    span=analysis.document_span(node.span),
                    replacement="ཀ",
                    score=0.7,
                    priority=P.CRITICAL,
                )


class WholeSentenceRewriter:
    """Proposes a whole-sentence edit, guaranteeing conflicts with finer ones."""

    def __init__(self, priority: SuggestionPriority = P.MEDIUM) -> None:
        self._priority = priority

    name = "style"

    def examine(self, snapshot: DocumentSnapshot) -> Iterable[Suggestion]:
        return [
            Suggestion(
                source=self.name,
                span=analysis.span,
                replacement="ཁ",
                score=0.95,
                priority=self._priority,
            )
            for analysis in snapshot.analyses
        ]


def language_server() -> LanguageServerSnapshotBuilder:
    """P4."""
    return LanguageServerSnapshotBuilder()


# -- The full chain ------------------------------------------------------------
def test_a_document_flows_from_the_language_server_through_to_a_patch(
    corpus_document: str,
) -> None:
    """P4 -> P5 -> P6, on a real multi-paragraph document."""
    normalized = TextNormalizer(form="NFC", collapse_whitespace=False).normalize(corpus_document)
    snapshot = language_server().analyze(normalized)
    results = SupervisedPluginRuntime(
        [PredicateRewriter(), EntityHighlighter(), SilentPlugin()]
    ).dispatch(snapshot)
    unified = PriorityRankedFusionEngine().fuse(snapshot.source, results.suggestions)

    assert snapshot.num_sentences > 10
    assert results.is_healthy is True
    assert results.num_suggestions > 10
    assert unified.num_suggestions > 0
    assert unified.patch.apply() != normalized


def test_spans_survive_the_whole_chain(corpus_document: str) -> None:
    """The seam that matters: a span computed from the snapshot must still be
    correct after the Fusion Engine has ranked, merged and patched with it.

    A plugin reads sentence-relative spans out of the snapshot and translates
    them; fusion never re-derives them. If either side of that handover were
    wrong, the patch would rewrite the wrong characters -- silently.
    """
    snapshot = language_server().analyze(corpus_document)
    results = SupervisedPluginRuntime([PredicateRewriter()]).dispatch(snapshot)

    checked = 0
    for suggestion in results.suggestions:
        where = suggestion.span
        assert corpus_document[where.char_start : where.char_end]
        assert where.byte_start == len(corpus_document[: where.char_start].encode("utf-8"))
        checked += 1
    assert checked > 5

    patch = PriorityRankedFusionEngine().fuse(snapshot.source, results.suggestions).patch
    assert patch.apply() != corpus_document


def test_the_patch_applied_to_the_snapshot_source_is_reanalysable(
    corpus_sentences: list[str],
) -> None:
    """FR-4 closes the loop: the patched document goes back to the Language Server.

    Whatever the plugins and the engine agree on has to be something the pipeline
    can analyse again, or the edit could not be accepted into the document.
    """
    builder = language_server()
    document = "".join(corpus_sentences[:12])
    snapshot = builder.analyze(document)

    results = SupervisedPluginRuntime([PredicateRewriter()]).dispatch(snapshot)
    unified = PriorityRankedFusionEngine().fuse(snapshot.source, results.suggestions)
    patched = unified.patch.apply()

    reanalysed = builder.reanalyze(snapshot, patched)
    assert reanalysed.source == patched
    assert reanalysed == builder.analyze(patched)


def test_conflicting_plugins_are_resolved_by_the_engine(
    corpus_sentences: list[str],
) -> None:
    """Two plugins rewriting overlapping ranges is exactly what FR-7 is for."""
    snapshot = language_server().analyze("".join(corpus_sentences[:6]))
    conflicting: list[FeaturePlugin] = [PredicateRewriter(), WholeSentenceRewriter()]
    results = SupervisedPluginRuntime(conflicting).dispatch(snapshot)
    unified = PriorityRankedFusionEngine().fuse(snapshot.source, results.suggestions)

    assert results.num_suggestions > unified.num_suggestions
    assert unified.rejected_for(RejectionReason.SUPERSEDED)
    previous = 0
    for operation in unified.patch.operations:
        assert operation.span.char_start >= previous
        previous = operation.span.char_end


def test_advisories_reach_the_user_alongside_edits(
    corpus_sentences: list[str],
) -> None:
    """A citation notice and a grammar fix are both results, not competitors."""
    snapshot = language_server().analyze("".join(corpus_sentences[:20]))
    results = SupervisedPluginRuntime([PredicateRewriter(), EntityHighlighter()]).dispatch(snapshot)
    unified = PriorityRankedFusionEngine().fuse(snapshot.source, results.suggestions)

    assert unified.advisories
    assert unified.edits
    assert all(a.source == "citation" for a in unified.advisories)


# -- Fault isolation across the chain -----------------------------------------
def test_a_broken_plugin_does_not_stop_the_document_being_patched(
    corpus_sentences: list[str],
) -> None:
    """NFR 5.3 end to end: the user still gets everything that did work."""
    snapshot = language_server().analyze("".join(corpus_sentences[:8]))
    runtime = SupervisedPluginRuntime(
        [PredicateRewriter(), CrashingPlugin(), ImpersonatingPlugin(), SilentPlugin()]
    )
    results = runtime.dispatch(snapshot)
    unified = PriorityRankedFusionEngine().fuse(snapshot.source, results.suggestions)

    assert results.num_failed == 2
    assert results.is_healthy is False
    assert unified.num_suggestions > 0
    assert unified.patch.apply() != snapshot.source
    assert {f.plugin for f in results.failures} == {"crash", "liar"}


def test_an_impersonated_plugin_gains_nothing_from_the_impersonation(
    corpus_sentences: list[str],
) -> None:
    """The attribution check is what stops borrowed trust reaching fusion.

    The impersonator claims to be ``spell`` and proposes a Critical whole-
    sentence rewrite. If the runtime let that through, it would win the conflict
    and the honest plugin's edit would be discarded.
    """
    snapshot = language_server().analyze("".join(corpus_sentences[:4]))
    honest = SupervisedPluginRuntime([WellBehavedPlugin()]).dispatch(snapshot)
    with_liar = SupervisedPluginRuntime([WellBehavedPlugin(), ImpersonatingPlugin()]).dispatch(
        snapshot
    )

    engine = PriorityRankedFusionEngine()
    assert with_liar.suggestions == honest.suggestions
    assert engine.fuse(snapshot.source, with_liar.suggestions) == engine.fuse(
        snapshot.source, honest.suggestions
    )


def test_a_plugin_tripped_by_real_corpus_data_is_contained(
    corpus_sentences: list[str],
) -> None:
    """A fault found by running against the real corpus, not an invented one.

    A sentence made only of grammatical words -- here the demonstrative ``དེ`` and
    the focus particle ``ནི`` -- produces an *empty semantic graph*, because Stage
    11 builds nodes for content words only. The obvious plugin, one that reaches
    for ``graph.nodes[0]``, then raises ``IndexError``. Three such sentences occur
    in the first 50,000 characters of the reference corpus, so this is an ordinary
    plugin-author oversight rather than a pathological input, and it is exactly
    what NFR 5.3 exists to survive.
    """
    snapshot = language_server().analyze("".join(corpus_sentences[:8]) + "དེ་ནི།")
    assert any(a.graph.is_empty for a in snapshot.analyses), "need an empty graph"

    class Unguarded:
        name = "unguarded"

        def examine(self, snap: DocumentSnapshot) -> Iterable[Suggestion]:
            return [
                Suggestion(
                    source=self.name,
                    span=analysis.document_span(analysis.graph.nodes[0].span),
                    replacement="ཀ",
                    score=0.7,
                    priority=P.MEDIUM,
                )
                for analysis in snap.analyses
            ]

    results = SupervisedPluginRuntime([Unguarded(), PredicateRewriter()]).dispatch(snapshot)
    assert results.failures[0].error_type == "IndexError"
    assert results.outcome_of("grammar") is not None
    assert results.num_suggestions > 0, "the well-behaved plugin still delivered"


# -- Determinism and concurrency across the chain -----------------------------
def test_the_whole_chain_is_deterministic(corpus_sentences: list[str]) -> None:
    snapshot = language_server().analyze("".join(corpus_sentences[:10]))
    runtime = SupervisedPluginRuntime([PredicateRewriter(), EntityHighlighter(), CrashingPlugin()])
    engine = PriorityRankedFusionEngine()

    def run() -> object:
        return engine.fuse(snapshot.source, runtime.dispatch(snapshot).suggestions)

    assert run() == run()


def test_concurrent_plugin_execution_gives_the_same_patch(
    corpus_sentences: list[str],
) -> None:
    """Figure 5: all plugins consume the centralized snapshot concurrently."""
    snapshot = language_server().analyze("".join(corpus_sentences[:10]))
    plugins: list[FeaturePlugin] = [
        PredicateRewriter(),
        EntityHighlighter(),
        WholeSentenceRewriter(),
        CrashingPlugin(),
    ]
    sequential = SupervisedPluginRuntime(plugins).dispatch(snapshot)
    with ThreadPoolExecutor(max_workers=4) as pool:
        concurrent = SupervisedPluginRuntime(plugins, executor=pool).dispatch(snapshot)

    assert concurrent == sequential
    engine = PriorityRankedFusionEngine()
    assert engine.fuse(snapshot.source, concurrent.suggestions) == engine.fuse(
        snapshot.source, sequential.suggestions
    )


def test_plugin_weighting_composes_with_plugin_results(
    corpus_sentences: list[str],
) -> None:
    """The operator's trust in a plugin decides which of two edits survives.

    Weighting scales confidence, and confidence only decides *within* a priority
    class -- the Priority Manager is applied last and dominates (ADR-017). So
    both plugins here are Critical, which is the case where trust is what is
    left to decide the conflict.
    """
    snapshot = language_server().analyze("".join(corpus_sentences[:6]))
    plugins: list[FeaturePlugin] = [
        PredicateRewriter(),
        WholeSentenceRewriter(P.CRITICAL),
    ]
    results = SupervisedPluginRuntime(plugins).dispatch(snapshot)

    trusting = PriorityRankedFusionEngine(plugin_weights={"style": 1.0})
    distrusting = PriorityRankedFusionEngine(plugin_weights={"style": 0.01})
    assert trusting.fuse(snapshot.source, results.suggestions) != distrusting.fuse(
        snapshot.source, results.suggestions
    )
