"""Tests for TiBERTInferenceEngine.

All tests use a mock model — no real TiBERT weights are loaded.
The mock validates that the engine correctly:
- Implements the InferenceEngine protocol
- Builds masked inputs from sentence + word offsets
- Scores candidates and converts log-probs to [0, 1] confidence
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from teea.ai.interfaces import InferenceEngine
from teea.ai.models import (
    CapabilityKind,
    ExecutionContext,
    InferenceRequest,
    ModelDescriptor,
)
from teea.ai.tibert_engine import TiBERTInferenceEngine

# -- Fixtures ------------------------------------------------------------------

DESCRIPTOR = ModelDescriptor(
    name="tibert",
    version="1",
    provides=frozenset({CapabilityKind.SPELLING}),
)
CONTEXT = ExecutionContext()


def _make_mock_tokenizer() -> MagicMock:
    """Create a mock tokenizer that produces deterministic outputs."""
    tok = MagicMock()
    tok.mask_token = "[MASK]"
    tok.mask_token_id = 103

    def tokenizer_call(
        text: str,
        add_special_tokens: bool = True,
        return_tensors: str = "pt",
        return_offsets_mapping: bool = False,
        truncation: bool = False,
        max_length: int = 512,
    ) -> dict[str, Any]:
        import torch

        # Simple mock: each character is a token, plus [CLS] and [SEP].
        n = len(text)
        ids = [101] + list(range(200, 200 + n)) + [102]
        offsets = [(0, 0)] + [(i, i + 1) for i in range(n)] + [(0, 0)]
        result: dict[str, Any] = {
            "input_ids": torch.tensor([ids]),
        }
        if return_offsets_mapping:
            result["offset_mapping"] = torch.tensor([offsets])
        return result

    tok.__call__ = tokenizer_call
    tok.__len__ = MagicMock(return_value=30000)
    return tok


def _make_mock_model() -> MagicMock:
    """Create a mock model that returns predictable logits."""
    import pytest
    pytest.importorskip("torch")
    import torch

    model = MagicMock()
    model.eval = MagicMock(return_value=model)
    model.to = MagicMock(return_value=model)

    def forward(input_ids: Any) -> MagicMock:
        seq_len = input_ids.shape[1]
        vocab_size = 30000
        # Logits: uniform distribution (log_softmax → each ~= -10.3 for 30k vocab).
        # For the actual token, boost its logit so it's clearly preferred.
        logits = torch.zeros(1, seq_len, vocab_size)
        # Set the actual token's logit high so log_softmax gives a good score.
        for pos in range(seq_len):
            token_id = input_ids[0, pos].item()
            if token_id != 103:  # Not a mask
                logits[0, pos, token_id] = 10.0  # High confidence for actual token
            else:
                # For masked positions, give moderate confidence to a range.
                logits[0, pos, 200:250] = 5.0

        result = MagicMock()
        result.logits = logits
        return result

    model.__call__ = forward
    return model


# -- Protocol compliance -------------------------------------------------------


class TestProtocolCompliance:
    def test_satisfies_inference_engine_protocol(self) -> None:
        engine = TiBERTInferenceEngine()
        assert isinstance(engine, InferenceEngine)


# -- Load / Unload tests -------------------------------------------------------


class TestLoadUnload:
    def test_load_sets_model_and_tokenizer(self) -> None:
        engine = TiBERTInferenceEngine()
        mock_model = _make_mock_model()
        mock_tok = _make_mock_tokenizer()

        with patch.dict("sys.modules", {
            "transformers": MagicMock(
                AutoModelForMaskedLM=MagicMock(from_pretrained=MagicMock(return_value=mock_model)),
                AutoTokenizer=MagicMock(from_pretrained=MagicMock(return_value=mock_tok)),
            ),
        }):
            engine.load(DESCRIPTOR, CONTEXT)

        assert engine._model is not None
        assert engine._tokenizer is not None
        assert DESCRIPTOR.key in engine._loaded_keys

    def test_unload_clears_state(self) -> None:
        engine = TiBERTInferenceEngine()
        engine._model = _make_mock_model()
        engine._tokenizer = _make_mock_tokenizer()
        engine._loaded_keys = {DESCRIPTOR.key}

        with patch.dict("sys.modules", {"torch": MagicMock()}):
            engine.unload(DESCRIPTOR)

        assert engine._model is None
        assert engine._tokenizer is None
        assert DESCRIPTOR.key not in engine._loaded_keys


# -- Inference tests -----------------------------------------------------------


class TestInference:
    def _make_loaded_engine(self) -> TiBERTInferenceEngine:
        """Create an engine with mock model and tokenizer already loaded."""
        engine = TiBERTInferenceEngine()
        engine._model = _make_mock_model()
        engine._tokenizer = _make_mock_tokenizer()
        engine._loaded_keys = {DESCRIPTOR.key}

        import torch

        engine._device = torch.device("cpu")
        return engine

    def test_infer_returns_scores_for_all_candidates(self) -> None:
        engine = self._make_loaded_engine()
        request = InferenceRequest(
            capability=CapabilityKind.SPELLING,
            inputs={
                "sentence": "hello world",
                "word_start": 6,
                "word_end": 11,
                "candidates": ["world", "words"],
            },
        )
        result = engine.infer(DESCRIPTOR, request)
        scores = result["scores"]
        assert "world" in scores
        assert "words" in scores
        assert all(0.0 <= s <= 1.0 for s in scores.values())

    def test_scores_are_in_unit_interval(self) -> None:
        engine = self._make_loaded_engine()
        request = InferenceRequest(
            capability=CapabilityKind.SPELLING,
            inputs={
                "sentence": "test",
                "word_start": 0,
                "word_end": 4,
                "candidates": ["test", "tess", "text"],
            },
        )
        result = engine.infer(DESCRIPTOR, request)
        for score in result["scores"].values():
            assert 0.0 <= score <= 1.0

    def test_empty_candidates_returns_empty_scores(self) -> None:
        engine = self._make_loaded_engine()
        request = InferenceRequest(
            capability=CapabilityKind.SPELLING,
            inputs={
                "sentence": "test",
                "word_start": 0,
                "word_end": 4,
                "candidates": [],
            },
        )
        result = engine.infer(DESCRIPTOR, request)
        assert result["scores"] == {}

    def test_single_candidate(self) -> None:
        engine = self._make_loaded_engine()
        request = InferenceRequest(
            capability=CapabilityKind.SPELLING,
            inputs={
                "sentence": "hello world",
                "word_start": 0,
                "word_end": 5,
                "candidates": ["hallo"],
            },
        )
        result = engine.infer(DESCRIPTOR, request)
        assert "hallo" in result["scores"]
        assert isinstance(result["scores"]["hallo"], float)
