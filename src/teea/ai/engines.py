"""Concrete inference-engine implementations shipped with TEEA.

The :class:`~teea.ai.interfaces.InferenceEngine` protocol defines what the AI
Runtime needs from a model adapter (SRS 3.3).  This module supplies the concrete
implementations that ship with the package.

Currently shipped
-----------------
* :class:`DummyInferenceEngine` -- a no-op engine that echoes inputs back as
  outputs.  It is the "dummy" the Development Roadmap (Phase 2) calls for: a
  shipped engine the AI Runtime can be wired to even when no model weights
  exist (ADR-013, ADR-019).  It records every call the runtime makes, so it
  doubles as a diagnostic probe for the orchestration layer.

What does *not* ship
--------------------
Real model adapters (ONNX, llama.cpp, Ollama, etc.) are future work.  Each will
be its own class in this module, implementing the same protocol so the runtime
never changes -- the hot-swapping SRS 3.3 requires.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from typing import Any

from teea.ai.models import ExecutionContext, InferenceRequest, ModelDescriptor

__all__ = ["DummyInferenceEngine"]


class DummyInferenceEngine:
    """A no-op inference engine that echoes inputs as outputs.

    This is the concrete engine the AI Runtime can be wired to when no real
    model weights exist (ADR-013, ADR-019).  It implements the full
    :class:`~teea.ai.interfaces.InferenceEngine` protocol:

    * **load** -- does nothing; there are no weights to load.
    * **infer** -- returns the request's ``inputs`` mapping unchanged as the
      ``outputs`` payload, tagged with a ``_dummy`` key set to ``True`` so
      callers can distinguish a dummy response from a real one.
    * **unload** -- does nothing; no resources to release.

    The engine records every call on thread-safe counters so callers (tests,
    diagnostics, health checks) can inspect what the runtime asked it to do.

    Thread safety
    -------------
    Every mutation is serialised behind a :class:`threading.Lock`, so the engine
    is safe to drive from many plugin threads at once -- the same concurrency
    the Plugin Runtime provides through an executor (Figure 5).

    Typical usage::

        engine = DummyInferenceEngine()
        runtime = LocalAIRuntime(engine)
        runtime.register(ModelDescriptor(
            name="dummy", version="1",
            provides={CapabilityKind.SEMANTIC_FEATURES},
        ))
        runtime.start()

        response = runtime.infer(InferenceRequest(
            capability=CapabilityKind.SEMANTIC_FEATURES,
            inputs={"text": "tibetan text here"},
        ))
        response.outputs  # {"text": "tibetan text here", "_dummy": True}
        engine.infer_count  # 1
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        #: Keys of models that :meth:`load` has been called for, in call order.
        self.load_calls: list[str] = []
        #: Keys of models that :meth:`infer` has been called for, in call order.
        self.infer_calls: list[str] = []
        #: Keys of models that :meth:`unload` has been called for, in call order.
        self.unload_calls: list[str] = []
        #: The :class:`ExecutionContext` values passed to each :meth:`load` call.
        self.contexts: list[ExecutionContext] = []
        #: The set of keys that are currently considered resident.
        self.resident: set[str] = set()

    @property
    def load_count(self) -> int:
        """How many models have been loaded."""
        return len(self.load_calls)

    @property
    def infer_count(self) -> int:
        """How many inferences have been performed."""
        return len(self.infer_calls)

    @property
    def unload_count(self) -> int:
        """How many models have been unloaded."""
        return len(self.unload_calls)

    def load(self, descriptor: ModelDescriptor, context: ExecutionContext) -> None:
        """Record the load call.

        Args:
            descriptor: The model to load.
            context: The conditions to load it under.
        """
        with self._lock:
            self.load_calls.append(descriptor.key)
            self.contexts.append(context)
            self.resident.add(descriptor.key)

    def infer(self, descriptor: ModelDescriptor, request: InferenceRequest) -> Mapping[str, Any]:
        """Echo the request inputs back as the dummy output.

        Args:
            descriptor: The model to run; currently loaded.
            request: The capability and inputs to serve.

        Returns:
            The request's ``inputs`` mapping with a ``_dummy`` sentinel added.
        """
        with self._lock:
            self.infer_calls.append(descriptor.key)
        # Return a new dict so callers cannot accidentally mutate the engine's
        # stored reference.  Start from the request's inputs and add the sentinel.
        outputs = dict(request.inputs)
        outputs["_dummy"] = True
        return outputs

    def unload(self, descriptor: ModelDescriptor) -> None:
        """Record the unload call.

        Args:
            descriptor: The model to release; currently loaded.
        """
        with self._lock:
            self.unload_calls.append(descriptor.key)
            self.resident.discard(descriptor.key)
