"""TiBERT-backed inference engine for TEEA.

Implements the :class:`~teea.ai.interfaces.InferenceEngine` protocol using
the TiBERT masked language model (``CMLI-NLP/TiBERT``).  This is the concrete
engine that bridges the AI Runtime's capability routing to actual model
inference -- the hot-swapping adapter SRS 3.3 mandates.

The engine supports one capability: :attr:`~teea.ai.models.CapabilityKind.SPELLING`.
Given a sentence, the character offsets of an unknown word, and a list of
candidate corrections, it scores each candidate using masked-LM
pseudo-log-likelihood: for each token the candidate produces, the token is
masked and the model's confidence in the true token is recorded.  The average
log-probability is converted to a ``[0, 1]`` confidence value.

Thread safety
-------------
The engine is stateless after :meth:`load` completes (the model and tokenizer
are read-only).  The PyTorch model's ``forward()`` is thread-safe for read-only
inference, and the AI Runtime serialises load/unload behind its own lock, so
concurrent infer calls are safe.

Dependencies
------------
Requires ``torch`` and ``transformers``, which are optional extras
(``pip install teea[ai]``).  Both are imported lazily so that importing this
module without them installed does not fail.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from teea.ai.models import ExecutionContext, InferenceRequest, ModelDescriptor
from teea.core.logging import get_logger

_logger = get_logger(__name__)

# Scale factor for converting average log-probability to [0, 1] confidence.
# avg_log_prob = 0  →  confidence = 1.0  (perfect prediction)
# avg_log_prob = -5 →  confidence = 0.5
# avg_log_prob ≤ -10 → confidence = 0.0  (very unlikely)
_LOG_PROB_SCALE = 10.0


class TiBERTInferenceEngine:
    """Loads and runs the TiBERT masked language model.

    Satisfies the :class:`~teea.ai.interfaces.InferenceEngine` protocol.
    The engine loads the model once at :meth:`load` and keeps it resident
    until :meth:`unload`.

    The ``infer`` method expects:

    * ``request.inputs["sentence"]`` -- the sentence containing the unknown word.
    * ``request.inputs["word_start"]`` -- character offset of the word start.
    * ``request.inputs["word_end"]`` -- character offset of the word end.
    * ``request.inputs["candidates"]`` -- list of candidate corrections.

    It returns ``{"scores": {candidate: confidence, ...}}``.

    Args:
        model_id: Hugging Face model identifier.  Defaults to the public
            TiBERT checkpoint.
        local_path: If set, load from this local directory instead of
            downloading from the Hub.
    """

    def __init__(
        self,
        model_id: str = "./TiBERT",
        *,
        local_path: Path | None = None,
    ) -> None:
        self._model_id = model_id
        self._local_path = local_path
        self._model: Any = None
        self._tokenizer: Any = None
        self._device: Any = None
        self._loaded_keys: set[str] = set()

    # -- InferenceEngine protocol -------------------------------------------

    def load(self, descriptor: ModelDescriptor, context: ExecutionContext) -> None:
        """Load TiBERT model weights and tokenizer.

        Args:
            descriptor: The model to load.
            context: The execution context (device preference).

        Raises:
            ImportError: If ``torch`` or ``transformers`` is not installed.
        """
        try:
            import torch  # noqa: PLC0415
            from transformers import AutoModelForMaskedLM, AutoTokenizer  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "TiBERT inference requires 'torch' and 'transformers'. "
                "Install with: pip install teea[ai]"
            ) from exc

        source = str(self._local_path) if self._local_path else self._model_id
        _logger.info(
            "tibert_loading",
            source=source,
            device=context.device.value,
        )

        extra_kwargs: dict[str, Any] = {}
        if self._local_path:
            extra_kwargs["local_files_only"] = True

        self._tokenizer = AutoTokenizer.from_pretrained(
            source,
            do_lower_case=False,
            strip_accents=False,
            use_fast=True,
            **extra_kwargs,
        )
        self._model = AutoModelForMaskedLM.from_pretrained(source, **extra_kwargs)

        # Resolve device.
        device_str = context.device.value
        if device_str == "auto":
            device_str = "cuda" if torch.cuda.is_available() else "cpu"
        self._device = torch.device(device_str)
        self._model.to(self._device)
        self._model.eval()
        self._loaded_keys.add(descriptor.key)

        _logger.info(
            "tibert_loaded",
            key=descriptor.key,
            device=str(self._device),
            vocab_size=len(self._tokenizer),
        )

    def infer(
        self, descriptor: ModelDescriptor, request: InferenceRequest
    ) -> Mapping[str, Any]:
        """Score candidate corrections using masked-LM pseudo-log-likelihood.

        Args:
            descriptor: The loaded model descriptor.
            request: Must contain ``sentence``, ``word_start``, ``word_end``,
                and ``candidates`` in its ``inputs``.

        Returns:
            ``{"scores": {candidate: confidence}}`` where confidence is in
            ``[0, 1]``.
        """
        import torch  # noqa: PLC0415

        inputs = request.inputs
        sentence: str = inputs["sentence"]
        word_start: int = inputs["word_start"]
        word_end: int = inputs["word_end"]
        candidates: list[str] = list(inputs["candidates"])

        if not candidates:
            return {"scores": {}}

        # Build modified sentences for all candidates
        modified_sentences = [
            sentence[:word_start] + candidate + sentence[word_end:] 
            for candidate in candidates
        ]

        # Tokenize as a batch
        encoding = self._tokenizer(
            modified_sentences,
            add_special_tokens=True,
            return_tensors="pt",
            return_offsets_mapping=True,
            padding=True,
            truncation=True,
            max_length=512,
        )
        
        input_ids = encoding["input_ids"].to(self._device)
        attention_mask = encoding["attention_mask"].to(self._device)
        
        # Create masked inputs by replacing all candidate tokens with [MASK]
        masked_input_ids = input_ids.clone()
        mask_id = self._tokenizer.mask_token_id
        
        batch_candidate_positions: list[list[int]] = []
        
        for i, candidate in enumerate(candidates):
            offsets = encoding["offset_mapping"][i].tolist()
            cand_char_end = word_start + len(candidate)
            
            candidate_positions: list[int] = []
            for pos, (start, end) in enumerate(offsets):
                # Non-zero span that overlaps the candidate range.
                if start != end and start >= word_start and end <= cand_char_end:
                    candidate_positions.append(pos)
                    # HACKATHON OPTIMIZATION: Mask ALL candidate tokens simultaneously
                    # to prevent target leakage (where the model sees parts of the candidate).
                    masked_input_ids[i, pos] = mask_id
            
            batch_candidate_positions.append(candidate_positions)

        # Single forward pass for the entire batch
        with torch.no_grad():
            outputs = self._model(
                input_ids=masked_input_ids,
                attention_mask=attention_mask
            )
            batch_logits = outputs.logits

        unk_token = self._tokenizer.unk_token_id
        scores: dict[str, float] = {}
        for i, candidate in enumerate(candidates):
            candidate_positions = batch_candidate_positions[i]
            if not candidate_positions:
                scores[candidate] = 0.0
                continue
            
            total_log_prob = 0.0
            for pos in candidate_positions:
                actual_token = input_ids[i, pos].item()
                if actual_token == unk_token:
                    # Heavily penalize UNK tokens so OOV candidates
                    # don't steal the high P([UNK]) mass
                    total_log_prob += -100.0
                    continue
                logits = batch_logits[i, pos]
                log_probs = torch.log_softmax(logits, dim=-1)
                total_log_prob += log_probs[actual_token].item()

            avg_log_prob = total_log_prob / len(candidate_positions)
            scores[candidate] = max(0.0, min(1.0, 1.0 + avg_log_prob / _LOG_PROB_SCALE))

        return {"scores": scores}

    def unload(self, descriptor: ModelDescriptor) -> None:
        """Release the model weights from memory.

        Args:
            descriptor: The model to unload.
        """
        self._loaded_keys.discard(descriptor.key)
        if not self._loaded_keys and self._model is not None:
            _logger.info("tibert_unloading", key=descriptor.key)
            del self._model
            del self._tokenizer
            self._model = None
            self._tokenizer = None
            # Free GPU memory if available.
            try:
                import torch  # noqa: PLC0415

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:  # pragma: no cover
                pass

__all__ = ["TiBERTInferenceEngine"]
