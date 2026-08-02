"""Grammar Correction Plugin using fine-tuned TiBERT.

This plugin integrates the grammar correction model into the TEEA pipeline.
"""

from typing import Iterable, Optional

from teea.core.logging import get_logger
from teea.fusion import Suggestion, SuggestionPriority
from teea.nlp.snapshot import DocumentSnapshot

logger = get_logger(__name__)


class GrammarCorrectionPlugin:
    """Plugin that provides AI-based grammar corrections."""

    def __init__(
        self,
        model_path: str = "./models/llama2_gec_lora",
        base_model_path: str = "./models/Tibetan-Llama2-7B",
    ):
        self._name = "teea.grammar_correction"
        self._model_path = model_path
        self._base_model_path = base_model_path
        self._engine = None
        self._enabled = True

    @property
    def name(self) -> str:
        return self._name

    def _get_engine(self):
        """Lazy-load the grammar correction engine."""
        import os
        import torch

        # Avoid freezing CPU RAM / segfaulting PyTorch CPU embeddings during standard tests
        allow_llm = os.environ.get("TEEA_ENABLE_LLM_GEC", "0") == "1" or torch.cuda.is_available()
        if not allow_llm:
            self._enabled = False
            return None

        if self._engine is None and self._enabled:
            try:
                from teea.ai.grammar_correction_engine import GrammarCorrectionEngine

                engine = GrammarCorrectionEngine(
                    model_path=self._model_path,
                    base_model_path=self._base_model_path,
                )
                if engine.is_available():
                    self._engine = engine
                else:
                    self._enabled = False
                    logger.info("grammar_correction_plugin_disabled_model_not_ready")
            except Exception as e:
                logger.warning("grammar_correction_engine_init_failed", error=str(e))
                self._enabled = False
                self._engine = None
        return self._engine

    def examine(self, snapshot: DocumentSnapshot) -> Iterable[Suggestion]:
        """Run grammar correction on each sentence in the snapshot.

        Args:
            snapshot: Document snapshot containing sentences to correct.

        Yields:
            Suggestion objects for each correction.
        """
        if not self._enabled:
            return

        engine = self._get_engine()
        if engine is None:
            return

        for analysis in snapshot.analyses:
            original = analysis.text

            if not original or not original.strip():
                continue

            if len(original.strip()) < 5:
                continue

            try:
                corrected = engine.correct(original)
            except Exception as e:
                logger.warning("grammar_correction_failed", sentence=original, error=str(e))
                continue

            if corrected and corrected != original:
                if len(corrected.strip()) < 2:
                    continue

                yield Suggestion(
                    source=self._name,
                    span=analysis.span,
                    replacement=corrected,
                    score=0.85,
                    priority=SuggestionPriority.MEDIUM,
                    message=f"AI Grammar Correction: '{original}' → '{corrected}'",
                    error_type="GRAMMAR_AI",
                )
