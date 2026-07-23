"""The AI Runtime: a capability-oriented inference orchestrator (Figure 6).

This is Figure 6's AI Runtime Core. It composes the boxes the diagram draws --
Capability Registry, Model Registry, Inference Manager, Model Loader, Memory
Manager -- into one component that a feature plugin calls to obtain intelligence,
and delegates the one thing it does not own, running the weights, to an injected
:class:`~teea.ai.interfaces.InferenceEngine` (ADR-019).

What the runtime owns, and what it does not
-------------------------------------------
It owns **routing** (capability to model, FR-6), **lifecycle** (a model is loaded
lazily on first use and unloaded on eviction or shutdown), **residency
accounting** (the Memory Manager's budget, enforced by evicting the
least-recently-used model), and **health**. It does not own weights, tensors, or
devices: those belong to the engine. This split is what lets an ONNX-backed
engine drop in behind the same protocol without the runtime changing, which is
the hot-swapping SRS 3.3 requires.

Thread safety
-------------
Unlike the stateless Plugin Runtime, this component has mutable state -- which
models are resident, and how much memory that claims -- and the daemon calls it
from many plugin threads at once (Figure 5). Every state transition is therefore
serialised behind a re-entrant lock. Inference for an already-loaded model still
holds the lock only to touch the residency bookkeeping around the engine call, so
the lock is held briefly rather than for the whole of a slow inference... except
that the engine call itself runs under it, because a concurrent eviction must not
unload a model mid-inference. The lock is re-entrant so batching can hold it
across several requests without deadlocking.

Scheduling is the daemon's, not the runtime's
---------------------------------------------
Figure 6 shows a CPU Scheduler with "Background inference". Following ADR-016 and
ADR-018, this runtime provides the *mechanism* -- synchronous, deterministic
execution -- and leaves the *policy* of when and on which thread to run to the
daemon's tiered scheduler (NFR 5.1). :meth:`infer_batch` is the one concession to
Figure 6's "Batch processing": it groups a batch by model so each loads once.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Iterable

from teea.ai.config import AIRuntimeSettings
from teea.ai.errors import (
    CapabilityUnavailableError,
    InferenceError,
    ModelLoadError,
    ModelNotFoundError,
    ResourceExhaustedError,
    RuntimeStateError,
)
from teea.ai.interfaces import CapabilityRegistry, InferenceEngine, ModelRegistry
from teea.ai.models import (
    ExecutionContext,
    HealthReport,
    InferenceRequest,
    InferenceResponse,
    ModelDescriptor,
    ModelState,
    RuntimeState,
)
from teea.ai.registry import InMemoryCapabilityRegistry, InMemoryModelRegistry


class LocalAIRuntime:
    """Orchestrates local inference for the feature plugins.

    Satisfies the informal AI Runtime contract of Figure 6. Every collaborator is
    injected, following the project-wide convention, so the runtime is testable
    without a real engine and any part is replaceable.

    Args:
        engine: The adapter that loads and runs model weights. Required: a
            runtime with no engine could route and report but never infer, which
            is not a runtime. It is the extension point SRS 3.3 mandates.
        settings: Budget, device and lazy-loading policy. Defaults to
            environment-driven :class:`~teea.ai.config.AIRuntimeSettings`.
        model_registry: Where installed models are tracked. Defaults to the
            in-memory registry.
        capability_registry: Where capabilities are routed. Defaults to the
            in-memory registry.

    Raises:
        ConfigurationError: If the default settings are invalid.
    """

    def __init__(
        self,
        engine: InferenceEngine,
        *,
        settings: AIRuntimeSettings | None = None,
        model_registry: ModelRegistry | None = None,
        capability_registry: CapabilityRegistry | None = None,
    ) -> None:
        # `is None`, not `or`: an empty registry is a legitimate, deliberately
        # empty collaborator, and would be falsy. The same defect was fixed in
        # Stages 07/09/10 and the Fusion Engine.
        self._engine = engine
        self._settings = AIRuntimeSettings() if settings is None else settings
        self._models = (
            InMemoryModelRegistry() if model_registry is None else model_registry
        )
        self._capabilities = (
            InMemoryCapabilityRegistry()
            if capability_registry is None
            else capability_registry
        )
        self._context = ExecutionContext(device=self._settings.default_device)

        self._lock = threading.RLock()
        self._state = RuntimeState.CREATED
        self._loaded: dict[str, ModelDescriptor] = {}
        self._used_bytes = 0
        self._clock = 0
        self._last_used: dict[str, int] = {}

    # -- Introspection -------------------------------------------------------
    @property
    def state(self) -> RuntimeState:
        """The runtime's lifecycle position."""
        with self._lock:
            return self._state

    @property
    def context(self) -> ExecutionContext:
        """The execution context inference runs under."""
        return self._context

    @property
    def settings(self) -> AIRuntimeSettings:
        """The runtime's configuration."""
        return self._settings

    def model_state(self, key: str) -> ModelState | None:
        """Return whether a registered model is loaded, or ``None`` if unknown."""
        with self._lock:
            if not self._models.contains(key):
                return None
            return ModelState.LOADED if key in self._loaded else ModelState.REGISTERED

    def health(self) -> HealthReport:
        """Return a snapshot of the runtime's state.

        Cheap to take and safe to serialize: it counts and names, never copying a
        model's weights.
        """
        with self._lock:
            return HealthReport(
                state=self._state,
                registered=len(self._models),
                loaded=tuple(sorted(self._loaded)),
                capabilities=tuple(
                    sorted(self._capabilities.capabilities(), key=lambda c: c.value)
                ),
                memory_used_bytes=self._used_bytes,
                memory_budget_bytes=self._settings.memory_budget_bytes,
            )

    # -- Lifecycle -----------------------------------------------------------
    def start(self) -> None:
        """Move the runtime from created to running.

        Raises:
            RuntimeStateError: If the runtime is not freshly created. Starting a
                running or stopped runtime again would be a logic error in the
                daemon, not a recoverable condition.
        """
        with self._lock:
            if self._state is not RuntimeState.CREATED:
                raise RuntimeStateError(
                    "The runtime can only be started once, from the created state.",
                    context={"state": self._state.value},
                )
            self._state = RuntimeState.RUNNING

    def stop(self) -> None:
        """Stop the runtime, unloading every resident model.

        Idempotent from the running state's perspective in one direction only:
        stopping is terminal. Every loaded model is unloaded through the engine,
        so the engine is left holding nothing. An engine that raises during
        unload does not prevent the others being unloaded or the runtime
        reaching the stopped state; there is nowhere useful for a shutdown error
        to go.
        """
        with self._lock:
            if self._state is RuntimeState.STOPPED:
                return
            for descriptor in list(self._loaded.values()):
                # A failed unload during shutdown has nowhere useful to go.
                with contextlib.suppress(Exception):
                    self._engine.unload(descriptor)
            self._loaded.clear()
            self._last_used.clear()
            self._used_bytes = 0
            self._state = RuntimeState.STOPPED

    def __enter__(self) -> LocalAIRuntime:
        """Start the runtime for use as a context manager."""
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        """Stop the runtime on leaving the context."""
        self.stop()

    # -- Registration --------------------------------------------------------
    def register(self, descriptor: ModelDescriptor) -> None:
        """Install a model.

        Permitted before or during running, never after stopping. When
        ``eager_load`` is set and the runtime is running, the model is loaded at
        once rather than on first use.

        Args:
            descriptor: The model to install.

        Raises:
            ModelRegistrationError: If the model's key is already registered.
            RuntimeStateError: If the runtime is stopped.
            ResourceExhaustedError: If eager loading cannot fit the model.
            ModelLoadError: If eager loading fails in the engine.
        """
        with self._lock:
            if self._state is RuntimeState.STOPPED:
                raise RuntimeStateError(
                    "Cannot register a model on a stopped runtime.",
                    context={"key": descriptor.key},
                )
            self._models.register(descriptor)
            self._capabilities.register(descriptor)
            if self._settings.eager_load and self._state is RuntimeState.RUNNING:
                self._ensure_loaded(descriptor)

    # -- Manual model lifecycle ----------------------------------------------
    def load(self, key: str) -> None:
        """Make a registered model resident now.

        Args:
            key: The :attr:`~teea.ai.models.ModelDescriptor.key` to load.

        Raises:
            RuntimeStateError: If the runtime is not running.
            ModelNotFoundError: If ``key`` is not registered.
            ResourceExhaustedError: If the model cannot fit the budget.
            ModelLoadError: If the engine fails to load it.
        """
        with self._lock:
            self._require_running()
            descriptor = self._require_registered(key)
            self._ensure_loaded(descriptor)

    def unload(self, key: str) -> None:
        """Release a resident model's weights.

        A no-op for a registered-but-not-loaded model. Unlike eviction, this is
        the caller's explicit choice, so an engine failure here is surfaced
        rather than swallowed.

        Args:
            key: The key to unload.

        Raises:
            RuntimeStateError: If the runtime is not running.
            ModelNotFoundError: If ``key`` is not registered.
        """
        with self._lock:
            self._require_running()
            self._require_registered(key)
            if key in self._loaded:
                self._evict(key)

    # -- Inference -----------------------------------------------------------
    def infer(self, request: InferenceRequest) -> InferenceResponse:
        """Serve one inference request.

        Routes the capability to a model, ensures it is loaded, and runs it.

        Args:
            request: The capability and inputs to serve.

        Returns:
            The model's response, tagged with the model that produced it.

        Raises:
            RuntimeStateError: If the runtime is not running.
            CapabilityUnavailableError: If no model provides the capability.
            ResourceExhaustedError: If the model cannot fit the budget.
            ModelLoadError: If the engine fails to load the model.
            InferenceError: If the engine fails while running the model.
        """
        with self._lock:
            self._require_running()
            return self._infer_locked(request)

    def infer_batch(
        self, requests: Iterable[InferenceRequest]
    ) -> tuple[InferenceResponse, ...]:
        """Serve a batch of requests, loading each model at most once.

        Figure 6's "Batch processing". Requests are grouped by the model they
        resolve to, so a model used by several requests loads a single time, and
        the whole batch runs under one lock acquisition -- no other caller can
        evict a model out from under the batch. Responses are returned in request
        order.

        The batch is all-or-nothing: the first request that cannot be served
        raises, and no partial result is returned, because a caller cannot tell
        which of an unordered partial set failed.

        Args:
            requests: The requests to serve, in any order.

        Returns:
            One response per request, in the order given.
        """
        ordered = list(requests)
        with self._lock:
            self._require_running()
            resolved = [(index, self._resolve(r), r) for index, r in enumerate(ordered)]
            # Group by model key, first-seen order, so each model loads once.
            order: list[str] = []
            groups: dict[str, list[tuple[int, ModelDescriptor, InferenceRequest]]] = {}
            for index, descriptor, request in resolved:
                if descriptor.key not in groups:
                    groups[descriptor.key] = []
                    order.append(descriptor.key)
                groups[descriptor.key].append((index, descriptor, request))

            responses: list[InferenceResponse | None] = [None] * len(ordered)
            for key in order:
                for index, descriptor, request in groups[key]:
                    responses[index] = self._run(descriptor, request)
            return tuple(response for response in responses if response is not None)

    # -- Internals -----------------------------------------------------------
    def _infer_locked(self, request: InferenceRequest) -> InferenceResponse:
        """Resolve, load and run one request. The lock must be held."""
        return self._run(self._resolve(request), request)

    def _resolve(self, request: InferenceRequest) -> ModelDescriptor:
        """Return the model that should serve ``request``, or raise."""
        descriptor = self._capabilities.resolve(request.capability, request.preferred)
        if descriptor is None:
            raise CapabilityUnavailableError(
                "No registered model provides the requested capability.",
                context={
                    "capability": request.capability.value,
                    "preferred": request.preferred,
                },
            )
        return descriptor

    def _run(
        self, descriptor: ModelDescriptor, request: InferenceRequest
    ) -> InferenceResponse:
        """Ensure ``descriptor`` is loaded, run it, and tag the response."""
        self._ensure_loaded(descriptor)
        self._touch(descriptor.key)
        try:
            outputs = self._engine.infer(descriptor, request)
        except Exception as exc:
            raise InferenceError(
                "The inference engine failed while running a model.",
                context={"key": descriptor.key, "error_type": type(exc).__name__},
                cause=exc,
            ) from exc
        return InferenceResponse(
            capability=request.capability,
            produced_by=descriptor.key,
            outputs=outputs,
        )

    def _ensure_loaded(self, descriptor: ModelDescriptor) -> None:
        """Load ``descriptor`` if it is not resident, evicting to fit. Lock held."""
        if descriptor.key in self._loaded:
            self._touch(descriptor.key)
            return
        self._make_room_for(descriptor)
        try:
            self._engine.load(descriptor, self._context)
        except Exception as exc:
            raise ModelLoadError(
                "The inference engine failed to load a model.",
                context={"key": descriptor.key, "error_type": type(exc).__name__},
                cause=exc,
            ) from exc
        self._loaded[descriptor.key] = descriptor
        self._used_bytes += descriptor.size_bytes
        self._touch(descriptor.key)

    def _make_room_for(self, descriptor: ModelDescriptor) -> None:
        """Evict least-recently-used models until ``descriptor`` fits. Lock held."""
        budget = self._settings.memory_budget_bytes
        if budget is None:
            return
        if descriptor.size_bytes > budget:
            raise ResourceExhaustedError(
                "A single model is larger than the whole memory budget.",
                context={
                    "key": descriptor.key,
                    "size_bytes": descriptor.size_bytes,
                    "budget_bytes": budget,
                },
            )
        while self._used_bytes + descriptor.size_bytes > budget and self._loaded:
            self._evict(self._least_recently_used())

    def _least_recently_used(self) -> str:
        """Return the key of the least-recently-used loaded model. Lock held."""
        return min(self._loaded, key=lambda key: self._last_used[key])

    def _evict(self, key: str) -> None:
        """Unload one model and forget its bookkeeping. Lock held.

        Eviction is the runtime's own decision, so an engine that raises on
        unload must not corrupt the accounting: the model is dropped from the
        resident set regardless, and its bytes reclaimed.
        """
        descriptor = self._loaded.pop(key)
        self._last_used.pop(key, None)
        self._used_bytes -= descriptor.size_bytes
        # Eviction already reclaimed the accounting; a failed unload in the engine
        # must not wedge the runtime, so it is suppressed.
        with contextlib.suppress(Exception):
            self._engine.unload(descriptor)

    def _touch(self, key: str) -> None:
        """Record ``key`` as most recently used. Lock held."""
        self._clock += 1
        self._last_used[key] = self._clock

    def _require_running(self) -> None:
        """Raise unless the runtime is running. Lock held."""
        if self._state is not RuntimeState.RUNNING:
            raise RuntimeStateError(
                "The runtime is not running.",
                context={"state": self._state.value},
            )

    def _require_registered(self, key: str) -> ModelDescriptor:
        """Return the descriptor for ``key`` or raise. Lock held."""
        descriptor = self._models.get(key)
        if descriptor is None:
            raise ModelNotFoundError(
                "No model is registered under this key.",
                context={"key": key},
            )
        return descriptor

    def registered_models(self) -> tuple[ModelDescriptor, ...]:
        """Every registered model, in registration order."""
        with self._lock:
            return self._models.all()


__all__ = ["LocalAIRuntime"]
