"""TEEA AI Runtime.

Figure 6 specifies this component: a "modular orchestrator managing capability
registration, ONNX inference execution, resource allocation, and storage
persistence" through which feature plugins invoke local intelligence. Figure 1
places it in the Runtime Layer beside the Language Server, the Plugin Runtime and
the Suggestion Fusion Engine; SRS 3.3 and FR-6 require it to route requests
through a capability registry and to hold models behind swappable adapters.

It ships the orchestration and **no model**. The actual loading and running of
weights sits behind the :class:`InferenceEngine` protocol -- the adapter SRS 3.3
mandates -- and no concrete engine exists here, because no model exists to run
yet (ADR-013, ADR-019). This mirrors the Plugin Runtime shipping no plugin
(ADR-018) and persistence shipping no SQLite (ADR-006).

Public API:

* :class:`AIRuntime`-shaped :class:`LocalAIRuntime` -- the orchestrator.
* :class:`InferenceEngine` -- the extension point a future ONNX (or other)
  adapter implements.
* :class:`ModelRegistry`, :class:`CapabilityRegistry` -- the registry contracts,
  with :class:`InMemoryModelRegistry` and :class:`InMemoryCapabilityRegistry`.
* Domain models: :class:`ModelDescriptor`, :class:`InferenceRequest`,
  :class:`InferenceResponse`, :class:`ExecutionContext`, :class:`HealthReport`,
  :class:`CapabilityKind`, :class:`Device`, :class:`RuntimeState`,
  :class:`ModelState`.
* Configuration: :class:`AIRuntimeSettings`, :func:`load_ai_settings`.
* Errors: :class:`AIRuntimeError` and its subclasses.

The runtime depends on :mod:`teea.core` alone. It never imports the Language
Server, the Plugin Runtime or the Fusion Engine: a plugin holds a runtime and
calls it, so the dependency runs from the plugin to here, not the reverse. The
constraint is enforced by ``tests/test_architecture.py``.

Typical usage, a plugin obtaining semantic features::

    from teea.ai import (
        CapabilityKind, InferenceRequest, LocalAIRuntime, ModelDescriptor,
    )

    runtime = LocalAIRuntime(engine)          # engine is the injected adapter
    runtime.register(ModelDescriptor(
        name="tibert", version="1", provides={CapabilityKind.SEMANTIC_FEATURES},
    ))
    runtime.start()

    response = runtime.infer(InferenceRequest(
        capability=CapabilityKind.SEMANTIC_FEATURES, inputs={"text": sentence},
    ))
    response.produced_by       # "tibert:1"
    response.outputs           # what the model returned

    runtime.health()           # what is registered, loaded, and how much memory
    runtime.stop()             # unloads every resident model
"""

from __future__ import annotations

from teea.ai.config import AIRuntimeSettings, load_ai_settings
from teea.ai.errors import (
    AIRuntimeError,
    CapabilityUnavailableError,
    InferenceError,
    ModelLoadError,
    ModelNotFoundError,
    ModelRegistrationError,
    ResourceExhaustedError,
    RuntimeStateError,
)
from teea.ai.interfaces import CapabilityRegistry, InferenceEngine, ModelRegistry
from teea.ai.models import (
    CapabilityKind,
    Device,
    ExecutionContext,
    HealthReport,
    InferenceRequest,
    InferenceResponse,
    ModelDescriptor,
    ModelState,
    RuntimeState,
)
from teea.ai.registry import InMemoryCapabilityRegistry, InMemoryModelRegistry
from teea.ai.runtime import LocalAIRuntime

__all__ = [
    "AIRuntimeError",
    "AIRuntimeSettings",
    "CapabilityKind",
    "CapabilityRegistry",
    "CapabilityUnavailableError",
    "Device",
    "ExecutionContext",
    "HealthReport",
    "InMemoryCapabilityRegistry",
    "InMemoryModelRegistry",
    "InferenceEngine",
    "InferenceError",
    "InferenceRequest",
    "InferenceResponse",
    "LocalAIRuntime",
    "ModelDescriptor",
    "ModelLoadError",
    "ModelNotFoundError",
    "ModelRegistrationError",
    "ModelRegistry",
    "ModelState",
    "ResourceExhaustedError",
    "RuntimeState",
    "RuntimeStateError",
    "load_ai_settings",
]
