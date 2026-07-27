"""The AI Runtime abstractions (interfaces) for TEEA.

Figure 6 draws the AI Runtime as a set of collaborating boxes. These protocols
are the seams between them, stated so each can be replaced without the others
changing -- Interface Segregation and Dependency Inversion, the same discipline
the persistence layer applies to the Dictionary Repository.

The load-bearing one is :class:`InferenceEngine`. SRS 3.3 requires target models
to sit "behind clear abstract API adapters, enabling immediate hot-swapping
between local configurations (e.g., ONNX runtimes)". That adapter is this
protocol: the runtime orchestrates through it and never touches a tensor, so a
future ONNX-backed engine, or any other, drops in without the runtime changing.
No concrete engine ships in this repository -- there is no model to run yet
(ADR-013, ADR-019).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from teea.ai.models import (
    CapabilityKind,
    ExecutionContext,
    InferenceRequest,
    ModelDescriptor,
)


@runtime_checkable
class InferenceEngine(Protocol):
    """Loads model weights and runs them: Figure 6's Model Loader + ONNX Runtime.

    This is the extension point SRS 3.3 mandates. An implementation owns the
    actual weights -- keyed by :attr:`ModelDescriptor.key` -- and the runtime
    holds only metadata, so the two never duplicate state. Implementations must
    be safe to call from the runtime's worker threads.

    All three methods may raise; the runtime wraps a failure into a typed
    :class:`~teea.ai.errors.AIRuntimeError` so a caller sees a stable code rather
    than an engine-specific exception.
    """

    def load(self, descriptor: ModelDescriptor, context: ExecutionContext) -> None:
        """Make ``descriptor``'s weights resident and ready for inference.

        Figure 6's Model Loader: "Lazy loading · Model initialization". The
        runtime calls this at most once per model between loads, and guarantees
        it will call :meth:`unload` before loading the same key again.

        Args:
            descriptor: The model to load.
            context: The conditions to load it under, e.g. the target device.
        """
        ...

    def infer(self, descriptor: ModelDescriptor, request: InferenceRequest) -> Mapping[str, Any]:
        """Run the loaded model named by ``descriptor`` over ``request``.

        The runtime guarantees the model is loaded before calling this. The
        return value becomes an :class:`~teea.ai.models.InferenceResponse`'s
        outputs unchanged.

        Args:
            descriptor: The model to run; already loaded.
            request: The capability and inputs to serve.

        Returns:
            The model's output, as an opaque mapping.
        """
        ...

    def unload(self, descriptor: ModelDescriptor) -> None:
        """Release ``descriptor``'s weights.

        Figure 6's Memory Manager: "Memory cleanup". Called when the runtime
        evicts a model to stay within budget, and for every loaded model when the
        runtime stops.

        Args:
            descriptor: The model to release; currently loaded.
        """
        ...


@runtime_checkable
class ModelRegistry(Protocol):
    """Tracks installed models and their versions: Figure 6's Model Registry.

    Implementations need not be internally thread-safe; the runtime serialises
    access to them.
    """

    def register(self, descriptor: ModelDescriptor) -> None:
        """Add a model. Raises if its key is already present."""
        ...

    def get(self, key: str) -> ModelDescriptor | None:
        """Return the model with this key, or ``None``."""
        ...

    def contains(self, key: str) -> bool:
        """Whether a model with this key is registered."""
        ...

    def all(self) -> tuple[ModelDescriptor, ...]:
        """Every registered model, in a stable order."""
        ...

    def versions(self, name: str) -> tuple[ModelDescriptor, ...]:
        """Every registered version of a named model, newest-registered last."""
        ...

    def __len__(self) -> int:
        """How many models are registered."""
        ...


@runtime_checkable
class CapabilityRegistry(Protocol):
    """Routes capabilities to models: Figure 6's Capability Registry.

    "Register capabilities · Route requests · Feature discovery." Implementations
    need not be internally thread-safe; the runtime serialises access.
    """

    def register(self, descriptor: ModelDescriptor) -> None:
        """Index a model under each capability it provides."""
        ...

    def resolve(
        self, capability: CapabilityKind, preferred: str | None = None
    ) -> ModelDescriptor | None:
        """Return the model that should serve ``capability``, or ``None``.

        When several models provide it, ``preferred`` (a model *name*) wins if it
        is among them; otherwise the choice is deterministic and stated by the
        implementation.
        """
        ...

    def providers(self, capability: CapabilityKind) -> tuple[ModelDescriptor, ...]:
        """Every model that provides ``capability``, in a stable order."""
        ...

    def capabilities(self) -> frozenset[CapabilityKind]:
        """Every capability at least one registered model provides."""
        ...


__all__ = ["CapabilityRegistry", "InferenceEngine", "ModelRegistry"]
