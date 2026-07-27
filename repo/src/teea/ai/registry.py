"""In-memory model and capability registries.

Figure 6 draws a "Model Registry DB" in the Persistent Storage Layer, but ADR-006
already settled that TEEA's registries ship in memory until a feature needs a
storage engine, and nothing here does: these hold descriptors registered at
runtime, not data shipped with the package. Both satisfy their protocols, so a
persistent registry can replace either without the runtime changing.

Neither class is internally synchronised. The runtime that owns them serialises
every access behind its own lock, which keeps the registries simple and avoids a
second, redundant layer of locking. A registry used directly, outside a runtime,
is therefore a single-thread object.
"""

from __future__ import annotations

from teea.ai.errors import ModelRegistrationError
from teea.ai.models import CapabilityKind, ModelDescriptor


class InMemoryModelRegistry:
    """Tracks installed models by key, preserving registration order.

    Satisfies the :class:`~teea.ai.interfaces.ModelRegistry` protocol.
    """

    def __init__(self) -> None:
        self._by_key: dict[str, ModelDescriptor] = {}

    def register(self, descriptor: ModelDescriptor) -> None:
        """Add ``descriptor``.

        Raises:
            ModelRegistrationError: If a model with the same key is already
                present. Silently replacing it would strand whatever the
                capability registry and the engine hold for the old one.
        """
        if descriptor.key in self._by_key:
            raise ModelRegistrationError(
                "A model with this name and version is already registered.",
                context={"key": descriptor.key},
            )
        self._by_key[descriptor.key] = descriptor

    def get(self, key: str) -> ModelDescriptor | None:
        """Return the model with ``key``, or ``None``."""
        return self._by_key.get(key)

    def contains(self, key: str) -> bool:
        """Whether ``key`` is registered."""
        return key in self._by_key

    def all(self) -> tuple[ModelDescriptor, ...]:
        """Every registered model, in registration order."""
        return tuple(self._by_key.values())

    def versions(self, name: str) -> tuple[ModelDescriptor, ...]:
        """Every registered version of ``name``, in registration order."""
        return tuple(d for d in self._by_key.values() if d.name == name)

    def __len__(self) -> int:
        """How many models are registered."""
        return len(self._by_key)


class InMemoryCapabilityRegistry:
    """Routes capabilities to the models that provide them.

    Satisfies the :class:`~teea.ai.interfaces.CapabilityRegistry` protocol.

    When more than one model provides a capability, :meth:`resolve` prefers a
    caller-named model, and otherwise picks the **highest version**, ties broken
    by key. That makes version management observable: registering a newer version
    of a model changes what an unqualified request resolves to, and the rule is
    deterministic so the same registry always routes the same way.
    """

    def __init__(self) -> None:
        self._by_capability: dict[CapabilityKind, list[ModelDescriptor]] = {}

    def register(self, descriptor: ModelDescriptor) -> None:
        """Index ``descriptor`` under each capability it provides."""
        for capability in descriptor.provides:
            providers = self._by_capability.setdefault(capability, [])
            providers.append(descriptor)

    def resolve(
        self, capability: CapabilityKind, preferred: str | None = None
    ) -> ModelDescriptor | None:
        """Return the model that should serve ``capability``, or ``None``."""
        providers = self._by_capability.get(capability)
        if not providers:
            return None
        if preferred is not None:
            named = [d for d in providers if d.name == preferred]
            if named:
                return max(named, key=lambda d: (d.version, d.key))
        return max(providers, key=lambda d: (d.version, d.key))

    def providers(self, capability: CapabilityKind) -> tuple[ModelDescriptor, ...]:
        """Every model providing ``capability``, in registration order."""
        return tuple(self._by_capability.get(capability, ()))

    def capabilities(self) -> frozenset[CapabilityKind]:
        """Every capability at least one registered model provides."""
        return frozenset(
            capability for capability, providers in self._by_capability.items() if providers
        )


__all__ = ["InMemoryCapabilityRegistry", "InMemoryModelRegistry"]
