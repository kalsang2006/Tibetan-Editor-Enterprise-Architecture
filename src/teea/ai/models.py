"""Immutable domain models of the AI Runtime.

Figure 6 is a dedicated diagram for this component. These are its value objects:
what a model *is* (:class:`ModelDescriptor`), what a plugin *asks* for
(:class:`InferenceRequest`), what it gets *back* (:class:`InferenceResponse`),
the *conditions* execution runs under (:class:`ExecutionContext`), and the
runtime's own *state* (:class:`RuntimeState`, :class:`HealthReport`).

The runtime speaks capabilities, not tensors
--------------------------------------------
Figure 6's Outputs box enumerates seven things a model can produce -- grammar and
spell suggestions, translation, summary, citations, semantic features, similarity
scores -- and :class:`CapabilityKind` is exactly that list. A request names a
capability, and the Capability Registry routes it to a model that provides it
(FR-6). The *content* of the inputs and outputs is deliberately left as an opaque
:class:`~collections.abc.Mapping`, because the tensor schema is a property of a
concrete model and its engine, neither of which this component defines (ADR-019).
Fixing a schema here would be inventing one.

No ``model_``-prefixed field names appear on these models, so Pydantic's
protected-namespace machinery stays out of the way; ``ModelDescriptor`` is named
for what it describes, not for a field.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


@enum.unique
class CapabilityKind(enum.Enum):
    """A kind of intelligence a model can provide.

    Exactly Figure 6's Outputs: the seven things the AI Runtime returns to the
    feature plugins that call it. The set is closed to what the diagram names;
    adding a member is adding a documented capability, not inventing one.
    """

    GRAMMAR = "grammar"
    SPELLING = "spelling"
    TRANSLATION = "translation"
    SUMMARIZATION = "summarization"
    CITATION = "citation"
    SEMANTIC_FEATURES = "semantic_features"
    SIMILARITY = "similarity"


@enum.unique
class Device(enum.Enum):
    """Where a model should run.

    Figure 6 separates a GPU Resource Manager from a CPU Scheduler; this is the
    policy that chooses between them, carried to the inference engine in the
    :class:`ExecutionContext`. The runtime does not manage hardware itself -- it
    states the preference and leaves the mechanism to the engine (ADR-019).
    """

    #: Run on the CPU.
    CPU = "cpu"
    #: Run on the GPU, if the engine has one.
    GPU = "gpu"
    #: Let the engine choose.
    AUTO = "auto"


@enum.unique
class RuntimeState(enum.Enum):
    """The lifecycle position of the runtime.

    A strict, non-cyclic progression: a runtime is created, started once, and
    stopped once. ``STOPPED`` is terminal, so a stopped runtime cannot be
    restarted into an inconsistent state with models half-loaded.
    """

    CREATED = "created"
    RUNNING = "running"
    STOPPED = "stopped"


@enum.unique
class ModelState(enum.Enum):
    """Whether a registered model's weights are currently resident."""

    #: Known to the registry, weights not loaded.
    REGISTERED = "registered"
    #: Weights loaded by the engine and ready for inference.
    LOADED = "loaded"


class ModelDescriptor(BaseModel):
    """Everything the registry knows about one model, without its weights.

    This is Figure 6's Model Registry content -- "Track installed models · Model
    metadata · Version management" -- and nothing here touches tensors. The
    weights live in the inference engine; the descriptor is the metadata the
    runtime routes and budgets by.

    Attributes:
        name: The model's stable name, shared across its versions.
        version: This model's version. ``(name, version)`` is unique in a
            registry, which is what makes version management possible.
        provides: The capabilities this model can serve. Non-empty: a model that
            provides nothing could never be routed to.
        size_bytes: The resident memory this model claims when loaded, used by
            the runtime's memory budget. Zero means "unknown / unbudgeted", which
            is the honest default when a model has not declared its footprint.
        description: Free-form human-readable note.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    version: str
    provides: frozenset[CapabilityKind]
    size_bytes: int = Field(default=0, ge=0)
    description: str = ""

    @model_validator(mode="after")
    def _validate_consistency(self) -> ModelDescriptor:
        if not self.name:
            raise ValueError("a model must have a name")
        if not self.version:
            raise ValueError("a model must have a version")
        if not self.provides:
            raise ValueError("a model must provide at least one capability")
        return self

    @property
    def key(self) -> str:
        """The registry key, ``"name:version"``.

        Unique per descriptor, and the identity the inference engine loads,
        infers and unloads by.
        """
        return f"{self.name}:{self.version}"

    def provides_capability(self, capability: CapabilityKind) -> bool:
        """Whether this model can serve ``capability``."""
        return capability in self.provides


class ExecutionContext(BaseModel):
    """The conditions one inference runs under.

    Passed to the inference engine so it can honour the runtime's resource
    policy. Kept small on purpose: it carries the *decision* (which device),
    while the engine owns the *mechanism* (scheduling, allocation). Figure 6's
    GPU Resource Manager and CPU Scheduler are that mechanism, and the runtime
    does not reimplement them (ADR-019).

    Attributes:
        device: Where the model should run.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    device: Device = Device.AUTO


class InferenceRequest(BaseModel):
    """A plugin's request for one piece of intelligence.

    Attributes:
        capability: What is being asked for. The Capability Registry routes on
            this (FR-6).
        preferred: An optional model name to prefer when several provide the
            capability. ``None`` lets the registry choose, which it does by
            version. It is a *name*, not a key: a caller wants "the translation
            model", and version selection stays the registry's job.
        inputs: The model's input, as an opaque mapping. Its schema belongs to
            the model, not to the runtime (ADR-019); values should be
            JSON-serializable so a response can cross the IPC boundary.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    capability: CapabilityKind
    preferred: str | None = None
    inputs: Mapping[str, Any] = Field(default_factory=dict)


class InferenceResponse(BaseModel):
    """The result of one inference, with its provenance.

    Attributes:
        capability: The capability that was served.
        produced_by: The :attr:`ModelDescriptor.key` of the model that produced
            it, so a consumer can tell which model -- and which version -- spoke.
        outputs: The model's output, as an opaque mapping (ADR-019).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    capability: CapabilityKind
    produced_by: str
    outputs: Mapping[str, Any] = Field(default_factory=dict)


class HealthReport(BaseModel):
    """A snapshot of the runtime's state, for monitoring.

    Figure 1 places the AI Runtime inside the always-on Desktop Daemon, so an
    operator needs to see what it is doing without stopping it. Every field is a
    plain count or name -- nothing here holds a model's weights -- so the report
    is cheap to take and safe to serialize.

    Attributes:
        state: The lifecycle position.
        registered: How many models the registry holds.
        loaded: The keys of the models currently resident, sorted.
        capabilities: The capabilities at least one registered model provides,
            sorted by value.
        memory_used_bytes: The declared footprint of the loaded models.
        memory_budget_bytes: The residency budget, or ``None`` for unlimited.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    state: RuntimeState
    registered: int = Field(ge=0)
    loaded: tuple[str, ...] = ()
    capabilities: tuple[CapabilityKind, ...] = ()
    memory_used_bytes: int = Field(default=0, ge=0)
    memory_budget_bytes: int | None = None

    @property
    def is_running(self) -> bool:
        """Whether the runtime is accepting inference."""
        return self.state is RuntimeState.RUNNING

    @property
    def num_loaded(self) -> int:
        """How many models are resident."""
        return len(self.loaded)

    @property
    def memory_available_bytes(self) -> int | None:
        """Remaining budget, or ``None`` when the budget is unlimited."""
        if self.memory_budget_bytes is None:
            return None
        return self.memory_budget_bytes - self.memory_used_bytes


__all__ = [
    "CapabilityKind",
    "Device",
    "ExecutionContext",
    "HealthReport",
    "InferenceRequest",
    "InferenceResponse",
    "ModelDescriptor",
    "ModelState",
    "RuntimeState",
]
