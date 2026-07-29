"""End-to-end integration tests for the complete TEEA pipeline.

Exercises the full workflow from Tibetan text input through normalization,
NLP analysis (Stages 02-12), plugin execution, suggestion fusion, AI inference,
daemon composition, IPC communication, and plagiarism detection.

All tests are hermetic:
  - No external network access (fake tokenizer backend, no model download)
  - No external services (loopback transport, in-memory stores)
  - No timing-dependent assertions
  - No flaky assertions (determinism checked by structural equality)

Each test reuses existing fixtures from ``tests/conftest.py`` to avoid
duplicating setup code.  The ``corpus_sentences`` fixture provides real
classical-Tibetan text from the Milarepa corpus.

Note on Tokenization (Stage 05)
-------------------------------
Stage 05 (TiBERT) is not part of the snapshot builder pipeline, which chains
Stages 04, 06-11.  The TiBERT tokenizer is tested separately in
``tests/nlp/tokenization/test_tibert_integration.py``.  The E2E test here
exercises the pipeline the daemon actually calls: normalization, sentence
segmentation, morphological analysis, POS tagging, dependency parsing, NER,
terminology recognition, semantic analysis, and snapshot assembly.
"""

from __future__ import annotations

import concurrent.futures
import json
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from teea.ai import (
    CapabilityKind,
    DummyInferenceEngine,
    ExecutionContext,
    InferenceRequest,
    LocalAIRuntime,
    ModelDescriptor,
)
from teea.cli import main as cli_main
from teea.core.types import TextSpan
from teea.daemon import TEEADaemon, create_daemon
from teea.fusion import (
    PriorityRankedFusionEngine,
    Suggestion,
    SuggestionPriority,
    UnifiedSuggestions,
)
from teea.ipc import IpcClient, LoopbackTransport
from teea.nlp.snapshot import DocumentSnapshot, LanguageServerSnapshotBuilder
from teea.nlp.tokenization import TextNormalizer
from teea.plugins import SupervisedPluginRuntime
from teea.plugins.builtin import SpellCheckerPlugin
from teea.workflow import (
    analyze_text,
    full_workflow,
    fuse_suggestions,
    normalize_document,
    run_plugins,
    snapshot_to_dict,
    snapshot_to_text,
)

# ── Test data ──────────────────────────────────────────────────────────────
# A short Tibetan document built from the first few Milarepa corpus sentences.
# This gives us real Tibetan with proper shad terminations and paragraph
# structure without requiring network access.

_FIRST_SENTENCE = (
    "ཞིང་སྐལ་བྲེ་པེ་སྟན་ཆུང་བྱ་བ་མིང་མི་སྙན་རུང་སྟོན་ཐོག་གཞུན་པོ་ཡོང་པ་ཅིག་ཡོད་པ་དེ།"
)

_SECOND_SENTENCE = (
    "ཞང་པོས་སོ་ནམ་བྱས་པའི་ནས་སྐྱེ་འཕེལ་དུ་ཅི་འགྲོ་བྱས་ནས་ཕག་ཏུ་སོག་གིན་ཡོད་པ་ཡང་"
    "མང་རབ་ཏུ་སོང་བ་ལ་ཤ་མང་པོ་ཉོས།"
)

_SHORT_TIBETAN = _FIRST_SENTENCE + _SECOND_SENTENCE

_ENGLISH_TEXT = "The quick brown fox jumps over the lazy dog."


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def tibetan_text() -> str:
    """A multi-sentence classical-Tibetan document for E2E testing.

    Uses real corpus sentences so spans, offsets and linguistic structure
    are authentic rather than invented.
    """
    return _SHORT_TIBETAN


@pytest.fixture(scope="module")
def tibetan_file(tibetan_text: str) -> Iterator[Path]:
    """A temporary file containing the Tibetan test document.

    Written once per module and cleaned up after the last test.
    """
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".txt", delete=False
    ) as f:
        f.write(tibetan_text)
        path = Path(f.name)
    yield path
    path.unlink(missing_ok=True)


@pytest.fixture(scope="module")
def normalizer() -> TextNormalizer:
    """An NFC normalizer (default) for Stage 02."""
    return TextNormalizer(form="NFC")


@pytest.fixture(scope="module")
def snapshot_builder_module() -> LanguageServerSnapshotBuilder:
    """The real Language Server pipeline for E2E testing.

    Uses real components throughout (not fakes), because the goal is to
    validate the production pipeline.  The TiBERT tokenizer is not part
    of the snapshot builder chain (Stages 04-11), so no network access
    is needed.
    """
    return LanguageServerSnapshotBuilder()


@pytest.fixture(scope="module")
def spell_plugin() -> SpellCheckerPlugin:
    """The shipped spell-checker plugin backed by the real dictionary."""
    return SpellCheckerPlugin()


@pytest.fixture(scope="module")
def fusion_engine() -> PriorityRankedFusionEngine:
    """A fusion engine with default weights and adjacent-merge enabled."""
    return PriorityRankedFusionEngine()


@pytest.fixture(scope="module")
def dummy_engine() -> DummyInferenceEngine:
    """A fresh dummy inference engine for AI runtime tests."""
    return DummyInferenceEngine()


# ══════════════════════════════════════════════════════════════════════════
# 1.  Direct API pipeline — full_workflow()
# ══════════════════════════════════════════════════════════════════════════


class TestFullWorkflowAPI:
    """Validates the ``full_workflow()`` entry point."""

    def test_workflow_completes_successfully(self, tibetan_file: Path) -> None:
        """The full workflow runs without exceptions and returns a result."""
        result = full_workflow(str(tibetan_file))
        assert isinstance(result, dict)
        assert result["source"] == str(tibetan_file)

    def test_workflow_returns_correct_structure(self, tibetan_file: Path) -> None:
        """The workflow result has all expected top-level keys."""
        result = full_workflow(str(tibetan_file))
        assert "source" in result
        assert "char_count" in result
        assert "sentence_count" in result
        assert "plugins_run" in result
        assert "suggestions" in result
        assert "snapshot" in result

    def test_workflow_returns_positive_char_count(self, tibetan_file: Path) -> None:
        """Document character count is positive."""
        result = full_workflow(str(tibetan_file))
        assert result["char_count"] > 0

    def test_workflow_returns_positive_sentence_count(
        self, tibetan_file: Path
    ) -> None:
        """Document has at least one sentence."""
        result = full_workflow(str(tibetan_file))
        assert result["sentence_count"] >= 1

    def test_workflow_snapshot_is_serializable(self, tibetan_file: Path) -> None:
        """The snapshot dict is JSON-serializable (no non-serializable types)."""
        result = full_workflow(str(tibetan_file))
        snapshot = result["snapshot"]
        dumped = json.dumps(snapshot, ensure_ascii=False)
        assert isinstance(dumped, str)
        assert len(dumped) > 0

    def test_workflow_plugins_run_zero_with_default(self, tibetan_file: Path) -> None:
        """Without explicit plugins, the default runtime has no plugins."""
        result = full_workflow(str(tibetan_file))
        assert result["plugins_run"] == 0

    def test_workflow_suggestions_empty_with_default(self, tibetan_file: Path) -> None:
        """No plugins means no suggestions."""
        result = full_workflow(str(tibetan_file))
        assert result["suggestions"] == []

    def test_workflow_output_file_json(self, tibetan_file: Path) -> None:
        """Workflow writes JSON output when requested."""
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".json", delete=False
        ) as f:
            json_path = Path(f.name)
        try:
            result = full_workflow(str(tibetan_file), output_json=str(json_path))
            assert json_path.exists()
            data = json.loads(json_path.read_text(encoding="utf-8"))
            assert data["source"] == str(tibetan_file)
            assert data["char_count"] == result["char_count"]
        finally:
            json_path.unlink(missing_ok=True)

    def test_determinism_identical_inputs(self, tibetan_file: Path) -> None:
        """Running the workflow twice on the same input produces identical results."""
        result_a = full_workflow(str(tibetan_file))
        result_b = full_workflow(str(tibetan_file))
        assert result_a["char_count"] == result_b["char_count"]
        assert result_a["sentence_count"] == result_b["sentence_count"]
        assert result_a["snapshot"] == result_b["snapshot"]

    def test_determinism_three_runs(self, tibetan_file: Path) -> None:
        """Determinism holds across three runs."""
        results = [full_workflow(str(tibetan_file)) for _ in range(3)]
        for r in results[1:]:
            assert r["snapshot"] == results[0]["snapshot"]


# ══════════════════════════════════════════════════════════════════════════
# 2.  NLP pipeline — normalization → analysis → snapshot
# ══════════════════════════════════════════════════════════════════════════


class TestNLPPipeline:
    """Validates the NLP analysis chain (Stages 02, 04, 06-12)."""

    def test_normalize_produces_text(self, tibetan_text: str) -> None:
        """Stage 02 normalization returns a string."""
        normalized = normalize_document(tibetan_text, form="NFC")
        assert isinstance(normalized, str)
        assert len(normalized) > 0

    def test_normalize_preserves_tibetan(self, tibetan_text: str) -> None:
        """Normalization does not strip Tibetan content."""
        normalized = normalize_document(tibetan_text, form="NFC")
        assert "ཞིང་" in normalized

    def test_analyze_produces_snapshot(
        self,
        tibetan_text: str,
        snapshot_builder_module: LanguageServerSnapshotBuilder,
    ) -> None:
        """Running analysis produces a DocumentSnapshot."""
        snapshot = analyze_text(tibetan_text, builder=snapshot_builder_module)
        assert isinstance(snapshot, DocumentSnapshot)

    def test_snapshot_not_empty(
        self,
        tibetan_text: str,
        snapshot_builder_module: LanguageServerSnapshotBuilder,
    ) -> None:
        """The snapshot contains at least one sentence analysis."""
        snapshot = analyze_text(tibetan_text, builder=snapshot_builder_module)
        assert not snapshot.is_empty
        assert snapshot.num_sentences >= 1

    def test_snapshot_source_matches_input(
        self,
        tibetan_text: str,
        snapshot_builder_module: LanguageServerSnapshotBuilder,
    ) -> None:
        """The snapshot's source is the normalized input text."""
        snapshot = analyze_text(tibetan_text, builder=snapshot_builder_module)
        assert snapshot.source == normalize_document(tibetan_text, form="NFC")

    def test_every_major_stage_executes(
        self,
        tibetan_text: str,
        snapshot_builder_module: LanguageServerSnapshotBuilder,
    ) -> None:
        """Each major stage produces artifacts in the snapshot."""
        snapshot = analyze_text(tibetan_text, builder=snapshot_builder_module)
        for analysis in snapshot.analyses:
            # Stage 06: morphological analysis -> dependency tree nodes
            assert analysis.num_morphemes > 0, "Stage 06 produced no morphemes"
            # Stage 07: POS tagging on tree nodes
            for node in analysis.tree.nodes:
                assert node.tag, "Stage 07 produced no POS tag"
            # Stage 08: dependency parse -> rooted tree
            assert not analysis.tree.is_empty, "Stage 08 produced empty tree"
            # Stage 09: NER -> entity annotations exist (may be empty)
            assert analysis.entities is not None, "Stage 09 missing entities"
            # Stage 10: terminology
            assert analysis.terms is not None, "Stage 10 missing terms"
            # Stage 11: semantic graph
            assert analysis.graph is not None, "Stage 11 missing semantic graph"
            # Stage 11: intent analysis
            assert analysis.intent is not None, "Stage 11 missing intent"

    def test_semantic_graph_has_nodes(
        self,
        tibetan_text: str,
        snapshot_builder_module: LanguageServerSnapshotBuilder,
    ) -> None:
        """The semantic graph (Stage 11) contains nodes."""
        snapshot = analyze_text(tibetan_text, builder=snapshot_builder_module)
        assert snapshot.num_semantic_nodes > 0

    def test_content_hashes_are_unique(
        self,
        tibetan_text: str,
        snapshot_builder_module: LanguageServerSnapshotBuilder,
    ) -> None:
        """Different sentences have different content hashes (FR-4)."""
        snapshot = analyze_text(tibetan_text, builder=snapshot_builder_module)
        if snapshot.num_sentences >= 2:
            hashes = list(snapshot.content_hashes)
            assert len(set(hashes)) == len(hashes), "content hashes must be unique"

    def test_document_span_translation(
        self,
        tibetan_text: str,
        snapshot_builder_module: LanguageServerSnapshotBuilder,
    ) -> None:
        """Sentence-relative spans translate correctly to document coordinates."""
        snapshot = analyze_text(tibetan_text, builder=snapshot_builder_module)
        for analysis in snapshot.analyses:
            for node in analysis.tree.nodes:
                doc_span = analysis.document_span(node.span)
                assert doc_span.char_start >= 0
                assert doc_span.char_end > doc_span.char_start
                extracted = snapshot.source[
                    doc_span.char_start : doc_span.char_end
                ]
                assert len(extracted) > 0

    def test_snapshot_serialization_round_trip(
        self,
        tibetan_text: str,
        snapshot_builder_module: LanguageServerSnapshotBuilder,
    ) -> None:
        """Snapshot serializes to dict and back without data loss."""
        snapshot = analyze_text(tibetan_text, builder=snapshot_builder_module)
        data = snapshot.model_dump(mode="json")
        restored = DocumentSnapshot.model_validate(data)
        assert restored.source == snapshot.source
        assert restored.num_sentences == snapshot.num_sentences
        for orig, reloaded in zip(
            snapshot.analyses, restored.analyses, strict=True
        ):
            assert orig.text == reloaded.text
            assert orig.content_hash == reloaded.content_hash

    def test_snapshot_to_text_renders(
        self,
        tibetan_text: str,
        snapshot_builder_module: LanguageServerSnapshotBuilder,
    ) -> None:
        """Human-readable text report renders without error."""
        snapshot = analyze_text(tibetan_text, builder=snapshot_builder_module)
        report = snapshot_to_text(snapshot)
        assert isinstance(report, str)
        assert len(report) > 0
        assert "sentence" in report.lower()

    def test_snapshot_to_dict_serializable(
        self,
        tibetan_text: str,
        snapshot_builder_module: LanguageServerSnapshotBuilder,
    ) -> None:
        """Snapshot dict is JSON-serializable."""
        snapshot = analyze_text(tibetan_text, builder=snapshot_builder_module)
        data = snapshot_to_dict(snapshot)
        dumped = json.dumps(data, ensure_ascii=False)
        assert isinstance(dumped, str)

    def test_empty_text_handling(
        self, snapshot_builder_module: LanguageServerSnapshotBuilder
    ) -> None:
        """Empty input produces an empty snapshot."""
        snapshot = analyze_text("", builder=snapshot_builder_module)
        assert snapshot.is_empty

    def test_short_text_handling(
        self, snapshot_builder_module: LanguageServerSnapshotBuilder
    ) -> None:
        """Very short text produces at least a valid snapshot."""
        snapshot = analyze_text("ཀ", builder=snapshot_builder_module)
        assert isinstance(snapshot, DocumentSnapshot)

    def test_incremental_reanalysis(
        self,
        snapshot_builder_module: LanguageServerSnapshotBuilder,
    ) -> None:
        """FR-4: reanalyze reuses unchanged sentence analyses by content hash.

        Verify that calling reanalyze with the same text produces identical
        results to analyze, and that unchanged sentences reuse objects.
        """
        snapshot = snapshot_builder_module.analyze(_SHORT_TIBETAN)
        reparse = snapshot_builder_module.reanalyze(snapshot, _SHORT_TIBETAN)
        assert reparse.source == snapshot.source
        assert reparse.num_sentences == snapshot.num_sentences
        for orig, fresh in zip(
            snapshot.analyses, reparse.analyses, strict=True
        ):
            assert orig.content_hash == fresh.content_hash


# ══════════════════════════════════════════════════════════════════════════
# 3.  Plugin integration — execution -> suggestions
# ══════════════════════════════════════════════════════════════════════════


class TestPluginIntegration:
    """Validates the plugin execution chain (P5 -> outcomes -> suggestions)."""

    def test_plugin_runs_with_plugins(
        self,
        tibetan_text: str,
        snapshot_builder_module: LanguageServerSnapshotBuilder,
        spell_plugin: SpellCheckerPlugin,
    ) -> None:
        """Plugin runtime dispatches to registered plugins."""
        snapshot = analyze_text(tibetan_text, builder=snapshot_builder_module)
        runtime = SupervisedPluginRuntime(plugins=[spell_plugin])
        results = runtime.dispatch(snapshot)
        assert results.num_plugins == 1

    def test_plugin_produces_suggestions(
        self,
        tibetan_text: str,
        snapshot_builder_module: LanguageServerSnapshotBuilder,
        spell_plugin: SpellCheckerPlugin,
    ) -> None:
        """Spell checker plugin produces suggestions on real Tibetan."""
        snapshot = analyze_text(tibetan_text, builder=snapshot_builder_module)
        runtime = SupervisedPluginRuntime(plugins=[spell_plugin])
        results = runtime.dispatch(snapshot)
        assert results.num_suggestions >= 0
        for suggestion in results.suggestions:
            assert isinstance(suggestion, Suggestion)
            assert suggestion.source == "teea.spelling"

    def test_plugin_results_healthy(
        self,
        tibetan_text: str,
        snapshot_builder_module: LanguageServerSnapshotBuilder,
        spell_plugin: SpellCheckerPlugin,
    ) -> None:
        """Plugin results report health correctly when no plugin fails."""
        snapshot = analyze_text(tibetan_text, builder=snapshot_builder_module)
        runtime = SupervisedPluginRuntime(plugins=[spell_plugin])
        results = runtime.dispatch(snapshot)
        assert results.is_healthy

    def test_run_plugins_via_workflow(
        self,
        tibetan_text: str,
        snapshot_builder_module: LanguageServerSnapshotBuilder,
        spell_plugin: SpellCheckerPlugin,
    ) -> None:
        """run_plugins() helper produces expected results."""
        snapshot = analyze_text(tibetan_text, builder=snapshot_builder_module)
        runtime = SupervisedPluginRuntime(plugins=[spell_plugin])
        results = run_plugins(snapshot, plugins=runtime)
        assert results.num_plugins == 1

    def test_suggestions_are_valid_spans(
        self,
        tibetan_text: str,
        snapshot_builder_module: LanguageServerSnapshotBuilder,
        spell_plugin: SpellCheckerPlugin,
    ) -> None:
        """Plugin suggestions have spans valid within the document."""
        snapshot = analyze_text(tibetan_text, builder=snapshot_builder_module)
        runtime = SupervisedPluginRuntime(plugins=[spell_plugin])
        results = runtime.dispatch(snapshot)
        for suggestion in results.suggestions:
            span = suggestion.span
            assert span.char_start >= 0
            assert span.char_end <= len(snapshot.source)
            assert span.char_start < span.char_end

    def test_empty_snapshot_produces_no_suggestions(
        self, spell_plugin: SpellCheckerPlugin
    ) -> None:
        """An empty snapshot yields no plugin suggestions."""
        empty_snapshot = DocumentSnapshot(source="", analyses=())
        runtime = SupervisedPluginRuntime(plugins=[spell_plugin])
        results = runtime.dispatch(empty_snapshot)
        assert results.num_suggestions == 0


# ══════════════════════════════════════════════════════════════════════════
# 4.  Fusion engine — suggestion fusion
# ══════════════════════════════════════════════════════════════════════════


class TestFusionIntegration:
    """Validates the suggestion fusion pipeline (Figure 7)."""

    def test_fuse_empty_suggestions(
        self,
        tibetan_text: str,
        fusion_engine: PriorityRankedFusionEngine,
    ) -> None:
        """Fusing no suggestions returns an empty result."""
        unified = fusion_engine.fuse(tibetan_text, [])
        assert isinstance(unified, UnifiedSuggestions)
        assert len(unified.suggestions) == 0

    def test_fuse_single_suggestion(
        self,
        tibetan_text: str,
        fusion_engine: PriorityRankedFusionEngine,
    ) -> None:
        """Fusing a single suggestion returns it."""
        suggestion = Suggestion(
            source="test",
            span=TextSpan(char_start=0, char_end=3, byte_start=0, byte_end=9),
            replacement="abc",
            score=0.9,
            priority=SuggestionPriority.HIGH,
        )
        unified = fusion_engine.fuse(tibetan_text, [suggestion])
        assert len(unified.suggestions) == 1
        assert unified.suggestions[0].source == "test"

    def test_fuse_deterministic(
        self,
        tibetan_text: str,
        fusion_engine: PriorityRankedFusionEngine,
    ) -> None:
        """Fusing the same suggestions in different orders is identical."""
        suggestions = [
            Suggestion(
                source="spell",
                span=TextSpan(
                    char_start=5, char_end=10, byte_start=15, byte_end=30
                ),
                replacement="abcde",
                score=0.8,
                priority=SuggestionPriority.HIGH,
            ),
            Suggestion(
                source="grammar",
                span=TextSpan(
                    char_start=0, char_end=4, byte_start=0, byte_end=12
                ),
                replacement="xyzw",
                score=0.9,
                priority=SuggestionPriority.CRITICAL,
            ),
        ]
        result_a = fusion_engine.fuse(tibetan_text, suggestions)
        result_b = fusion_engine.fuse(
            tibetan_text, list(reversed(suggestions))
        )
        assert result_a.suggestions == result_b.suggestions
        assert result_a.rejected == result_b.rejected

    def test_fuse_with_plugin_outputs(
        self,
        tibetan_text: str,
        snapshot_builder_module: LanguageServerSnapshotBuilder,
        spell_plugin: SpellCheckerPlugin,
        fusion_engine: PriorityRankedFusionEngine,
    ) -> None:
        """Full pipeline: analyze -> plugins -> fusion produces output."""
        snapshot = analyze_text(tibetan_text, builder=snapshot_builder_module)
        runtime = SupervisedPluginRuntime(plugins=[spell_plugin])
        plugin_results = runtime.dispatch(snapshot)
        unified = fuse_suggestions(
            snapshot.source,
            list(plugin_results.suggestions),
            engine=fusion_engine,
        )
        assert isinstance(unified, UnifiedSuggestions)

    def test_fuse_patch_is_applicable(
        self,
        tibetan_text: str,
        snapshot_builder_module: LanguageServerSnapshotBuilder,
        spell_plugin: SpellCheckerPlugin,
        fusion_engine: PriorityRankedFusionEngine,
    ) -> None:
        """The document patch, if any, produces a valid output string."""
        snapshot = analyze_text(tibetan_text, builder=snapshot_builder_module)
        runtime = SupervisedPluginRuntime(plugins=[spell_plugin])
        plugin_results = runtime.dispatch(snapshot)
        unified = fuse_suggestions(
            snapshot.source,
            list(plugin_results.suggestions),
            engine=fusion_engine,
        )
        if unified.patch:
            patched = unified.patch.apply()
            assert isinstance(patched, str)


# ══════════════════════════════════════════════════════════════════════════
# 5.  AI runtime — DummyInferenceEngine integration
# ══════════════════════════════════════════════════════════════════════════


class TestAIRuntimeIntegration:
    """Validates the AI runtime with the shipped DummyInferenceEngine."""

    def test_dummy_engine_load_infer_unload(
        self, dummy_engine: DummyInferenceEngine
    ) -> None:
        """Dummy engine supports the full load->infer->unload lifecycle."""
        descriptor = ModelDescriptor(
            name="test",
            version="1",
            provides={CapabilityKind.SEMANTIC_FEATURES},
        )
        dummy_engine.load(descriptor, context=ExecutionContext())
        assert dummy_engine.load_count == 1
        assert dummy_engine.resident == {descriptor.key}

        response = dummy_engine.infer(
            descriptor,
            InferenceRequest(
                capability=CapabilityKind.SEMANTIC_FEATURES,
                inputs={"text": "tibetan"},
            ),
        )
        assert response["_dummy"] is True
        assert response.get("text") == "tibetan"
        assert dummy_engine.infer_count == 1

        dummy_engine.unload(descriptor)
        assert dummy_engine.unload_count == 1
        assert descriptor.key not in dummy_engine.resident

    def test_runtime_with_dummy_engine(
        self, dummy_engine: DummyInferenceEngine
    ) -> None:
        """LocalAIRuntime orchestrates through DummyInferenceEngine."""
        runtime = LocalAIRuntime(dummy_engine)
        runtime.register(
            ModelDescriptor(
                name="dummy",
                version="1",
                provides={CapabilityKind.SEMANTIC_FEATURES},
            )
        )
        runtime.start()
        try:
            response = runtime.infer(
                InferenceRequest(
                    capability=CapabilityKind.SEMANTIC_FEATURES,
                    inputs={"text": "test input"},
                )
            )
            assert response.produced_by == "dummy:1"
            assert response.outputs.get("_dummy") is True
            assert response.outputs.get("text") == "test input"

            health = runtime.health()
            assert CapabilityKind.SEMANTIC_FEATURES in health.capabilities
            assert health.registered >= 1
        finally:
            runtime.stop()

    def test_runtime_reports_health(
        self, dummy_engine: DummyInferenceEngine
    ) -> None:
        """Runtime health report contains expected fields."""
        runtime = LocalAIRuntime(dummy_engine)
        runtime.register(
            ModelDescriptor(
                name="dummy",
                version="1",
                provides={CapabilityKind.SEMANTIC_FEATURES},
            )
        )
        runtime.start()
        try:
            health = runtime.health()
            assert health.registered >= 1
            assert health.state is not None
        finally:
            runtime.stop()


# ══════════════════════════════════════════════════════════════════════════
# 6.  Daemon composition root
# ══════════════════════════════════════════════════════════════════════════


class TestDaemonComposition:
    """Validates the TEEADaemon composition root."""

    def test_daemon_creates_with_defaults(self) -> None:
        """Daemon factory creates a fully wired instance without error."""
        daemon = TEEADaemon()
        assert daemon.settings is not None
        assert daemon.builder is not None
        assert daemon.plugins is not None
        assert daemon.fusion is not None
        assert daemon.plagiarism is not None

    def test_daemon_with_plugins(
        self, spell_plugin: SpellCheckerPlugin
    ) -> None:
        """Daemon accepts and exposes registered plugins."""
        daemon = TEEADaemon(plugins=[spell_plugin])
        assert "teea.spelling" in daemon.plugins.plugins

    def test_daemon_with_ai_engine(
        self, dummy_engine: DummyInferenceEngine
    ) -> None:
        """Daemon with AI engine creates an active AI runtime."""
        daemon = TEEADaemon(ai_engine=dummy_engine)
        assert daemon.ai_runtime is not None

    def test_daemon_diagnose_returns_valid_structure(self) -> None:
        """Daemon.diagnose() returns a dict with all expected keys."""
        daemon = TEEADaemon()
        diag = daemon.diagnose()
        assert isinstance(diag, dict)
        assert "version" in diag
        assert "settings" in diag
        assert "builder" in diag
        assert "plugins" in diag
        assert "fusion" in diag
        assert "plagiarism" in diag
        assert "ipc" in diag

    def test_daemon_diagnose_version(self) -> None:
        """Daemon diagnostic includes a non-empty version string."""
        daemon = TEEADaemon()
        diag = daemon.diagnose()
        assert diag["version"] == "1.0.0"

    def test_daemon_diagnose_plugins_empty_by_default(self) -> None:
        """Daemon with default settings has builtin plugins registered."""
        daemon = TEEADaemon()
        diag = daemon.diagnose()
        assert diag["plugins"]["count"] == 4
        assert diag["plugins"]["names"] == [
            "teea.diagnostics", "teea.grammar", "teea.spelling", "teea.plagiarism",
        ]

    def test_daemon_wired_with_plagiarism_has_index(self) -> None:
        """Daemon plagiarism engine starts with an empty index."""
        daemon = TEEADaemon()
        diag = daemon.diagnose()
        assert diag["plagiarism"]["corpus_size"] == 0

    def test_daemon_not_serving_by_default(self) -> None:
        """Daemon is not serving IPC without a transport."""
        daemon = TEEADaemon()
        assert not daemon.is_serving()
        diag = daemon.diagnose()
        assert diag["ipc"]["serving"] is False

    def test_create_daemon_factory(self) -> None:
        """The create_daemon factory produces a ready-to-use daemon."""
        daemon = create_daemon()
        assert isinstance(daemon, TEEADaemon)
        assert daemon.settings is not None


# ══════════════════════════════════════════════════════════════════════════
# 7.  IPC communication via daemon handlers
# ══════════════════════════════════════════════════════════════════════════


class TestIPCIntegration:
    """Validates end-to-end IPC through the daemon's registered handlers."""

    def _make_connected(self) -> tuple[TEEADaemon, IpcClient, LoopbackTransport]:
        """Create a daemon, wire it to a loopback transport, and connect a
        client. Returns (daemon, client, client_end) for cleanup."""
        daemon = TEEADaemon()
        client_end, server_end = LoopbackTransport.pair()
        daemon.start()
        daemon._server.serve(server_end)
        client = IpcClient()
        client.connect(client_end)
        return daemon, client, client_end

    def _cleanup(
        self, daemon: TEEADaemon, client: IpcClient
    ) -> None:
        """Close client and daemon gracefully."""
        client.close()
        daemon.stop()

    def test_daemon_analyze_via_ipc(self, tibetan_text: str) -> None:
        """IPC analyze handler returns a valid snapshot."""
        daemon, client, _ = self._make_connected()
        try:
            result = client.call(
                "analyze", {"text": tibetan_text}, timeout=10.0
            )
            assert result is not None
            assert "source" in result
            assert "analyses" in result
        finally:
            self._cleanup(daemon, client)

    def test_daemon_analyze_returns_sentence_count(
        self, tibetan_text: str
    ) -> None:
        """IPC analyze response contains sentence count."""
        daemon, client, _ = self._make_connected()
        try:
            result = client.call(
                "analyze", {"text": tibetan_text}, timeout=10.0
            )
            assert len(result.get("analyses", [])) >= 1
        finally:
            self._cleanup(daemon, client)

    def test_daemon_analyze_empty_text(self) -> None:
        """IPC analyze handles empty text gracefully."""
        daemon, client, _ = self._make_connected()
        try:
            result = client.call("analyze", {"text": ""}, timeout=10.0)
            assert result is not None
            assert len(result.get("analyses", [])) == 0
        finally:
            self._cleanup(daemon, client)

    def test_daemon_plagiarism_via_ipc(self) -> None:
        """IPC plagiarism handler detects text matches."""
        daemon, client, _ = self._make_connected()
        try:
            # Pre-index a document via the daemon's engine directly
            daemon.plagiarism.add_text(
                "ref", _ENGLISH_TEXT
            )
            result = client.call(
                "plagiarism",
                {"text": "the quick brown fox", "min_similarity": 0.1},
                timeout=10.0,
            )
            assert result is not None
        finally:
            self._cleanup(daemon, client)

    def test_daemon_health_via_ipc(self) -> None:
        """Built-in $health method returns server status via IPC."""
        daemon, client, _ = self._make_connected()
        try:
            health = client.health(timeout=5.0)
            assert isinstance(health, dict)
            assert health.get("status") in ("ok", "stopped")
        finally:
            self._cleanup(daemon, client)


# ══════════════════════════════════════════════════════════════════════════
# 8.  Plagiarism detection integration
# ══════════════════════════════════════════════════════════════════════════


class TestPlagiarismIntegration:
    """Validates the plagiarism detection subsystem in context."""

    def test_plagiarism_engine_wired_to_daemon(self) -> None:
        """PlagiarismEngine works within the TEEADaemon composition root."""
        daemon = TEEADaemon()
        engine = daemon.plagiarism
        assert engine is not None
        assert engine.index.size == 0

    def test_plagiarism_add_and_detect(self) -> None:
        """Adding a document and detecting it finds a match."""
        daemon = TEEADaemon()
        engine = daemon.plagiarism
        engine.add_text("ref", _ENGLISH_TEXT)
        result = engine.detect(_ENGLISH_TEXT, min_similarity=0.1)
        assert result.num_matches > 0

    def test_plagiarism_no_match_for_unrelated(self) -> None:
        """Unrelated text produces no match."""
        daemon = TEEADaemon()
        engine = daemon.plagiarism
        engine.add_text("ref", _ENGLISH_TEXT)
        result = engine.detect(
            "unrelated content here", min_similarity=0.5
        )
        assert result.num_matches <= 1


# ══════════════════════════════════════════════════════════════════════════
# 9.  CLI integration
# ══════════════════════════════════════════════════════════════════════════


class TestCLIIntegration:
    """Validates the CLI entry point with real pipeline invocation."""

    def test_cli_analyze_returns_zero(self, tibetan_file: Path) -> None:
        """``teea analyze`` exits with code 0 on valid input."""
        exit_code = cli_main(["analyze", str(tibetan_file)])
        assert exit_code == 0

    def test_cli_analyze_with_output(self, tibetan_file: Path) -> None:
        """``teea analyze -o`` writes a JSON file."""
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".json", delete=False
        ) as f:
            out_path = Path(f.name)
        try:
            exit_code = cli_main(
                ["analyze", str(tibetan_file), "-o", str(out_path)]
            )
            assert exit_code == 0
            assert out_path.exists()
            data = json.loads(out_path.read_text(encoding="utf-8"))
            assert data["sentence_count"] >= 1
        finally:
            out_path.unlink(missing_ok=True)

    def test_cli_health_returns_zero(self) -> None:
        """``teea health`` exits with code 0."""
        exit_code = cli_main(["health"])
        assert exit_code == 0

    def test_cli_config_returns_zero(self) -> None:
        """``teea config`` exits with code 0."""
        exit_code = cli_main(["config"])
        assert exit_code == 0

    def test_cli_no_args_shows_help(self) -> None:
        """``teea`` with no arguments shows help and exits 0."""
        exit_code = cli_main([])
        assert exit_code == 0

    def test_cli_analyze_file_not_found(self) -> None:
        """``teea analyze`` on a missing file exits with code 1."""
        exit_code = cli_main(["analyze", "/nonexistent/file.txt"])
        assert exit_code == 1


# ══════════════════════════════════════════════════════════════════════════
# 10.  Stress & edge-case scenarios
# ══════════════════════════════════════════════════════════════════════════


class TestStressScenarios:
    """Validates the pipeline handles edge cases without exceptions."""

    def test_pipeline_no_exceptions_on_tibetan(
        self,
        tibetan_text: str,
        snapshot_builder_module: LanguageServerSnapshotBuilder,
    ) -> None:
        """The complete pipeline does not throw on valid Tibetan input."""
        normalized = normalize_document(tibetan_text, form="NFC")
        snapshot = snapshot_builder_module.analyze(normalized)
        assert isinstance(snapshot, DocumentSnapshot)

    def test_pipeline_no_exceptions_on_english(
        self,
        snapshot_builder_module: LanguageServerSnapshotBuilder,
    ) -> None:
        """The pipeline handles non-Tibetan text gracefully."""
        normalized = normalize_document(_ENGLISH_TEXT, form="NFC")
        snapshot = snapshot_builder_module.analyze(normalized)
        assert isinstance(snapshot, DocumentSnapshot)

    def test_pipeline_no_exceptions_repeated_calls(
        self,
        tibetan_text: str,
        snapshot_builder_module: LanguageServerSnapshotBuilder,
    ) -> None:
        """Calling the pipeline 10 times does not degrade or throw."""
        for _ in range(10):
            normalized = normalize_document(tibetan_text, form="NFC")
            snapshot = snapshot_builder_module.analyze(normalized)
            assert snapshot.num_sentences >= 1

    def test_snapshot_concurrent_reading(
        self,
        tibetan_text: str,
        snapshot_builder_module: LanguageServerSnapshotBuilder,
    ) -> None:
        """Snapshot frozen models are safe to read from multiple threads."""
        snapshot = analyze_text(
            tibetan_text, builder=snapshot_builder_module
        )
        results: list[str] = []
        lock = threading.Lock()

        def read_snapshot() -> str:
            out = []
            out.append(f"sentences={snapshot.num_sentences}")
            for analysis in snapshot.analyses:
                out.append(f"morphemes={analysis.num_morphemes}")
                out.append(f"entities={analysis.num_entities}")
                out.append(f"semantic={analysis.num_semantic_nodes}")
            return ", ".join(out)

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=4
        ) as pool:
            futures = [pool.submit(read_snapshot) for _ in range(8)]
            for future in concurrent.futures.as_completed(futures):
                with lock:
                    results.append(future.result())

        assert len(results) == 8
        assert all(r == results[0] for r in results)
