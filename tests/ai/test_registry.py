"""Tests for the in-memory model and capability registries.

These are Figure 6's Model Registry and Capability Registry. Version management
lives here: registering a newer version of a model changes what an unqualified
capability request routes to, and the tie-breaks are deterministic so the same
registry always routes the same way.
"""

from __future__ import annotations

import pytest

from teea.ai import (
    CapabilityKind,
    InMemoryCapabilityRegistry,
    InMemoryModelRegistry,
    ModelDescriptor,
    ModelRegistry,
)
from teea.ai.errors import ModelRegistrationError
from teea.ai.interfaces import CapabilityRegistry

GRAMMAR = CapabilityKind.GRAMMAR
FEATURES = CapabilityKind.SEMANTIC_FEATURES


def descriptor(name: str, version: str, *caps: CapabilityKind) -> ModelDescriptor:
    return ModelDescriptor(
        name=name, version=version, provides=frozenset(caps or (GRAMMAR,))
    )


# -- Protocol conformance ------------------------------------------------------
def test_the_registries_satisfy_their_protocols() -> None:
    assert isinstance(InMemoryModelRegistry(), ModelRegistry)
    assert isinstance(InMemoryCapabilityRegistry(), CapabilityRegistry)


# -- Model registry ------------------------------------------------------------
def test_a_registered_model_can_be_looked_up() -> None:
    registry = InMemoryModelRegistry()
    model = descriptor("tibert", "1")
    registry.register(model)
    assert registry.get("tibert:1") is model
    assert registry.contains("tibert:1")
    assert len(registry) == 1


def test_an_unknown_key_returns_none() -> None:
    registry = InMemoryModelRegistry()
    assert registry.get("absent:1") is None
    assert not registry.contains("absent:1")


def test_registering_a_duplicate_key_is_refused() -> None:
    """Silently replacing would strand what the engine holds for the old one."""
    registry = InMemoryModelRegistry()
    registry.register(descriptor("tibert", "1"))
    with pytest.raises(ModelRegistrationError, match="already registered") as error:
        registry.register(descriptor("tibert", "1", FEATURES))
    assert error.value.context["key"] == "tibert:1"


def test_two_versions_of_a_model_coexist() -> None:
    registry = InMemoryModelRegistry()
    registry.register(descriptor("tibert", "1"))
    registry.register(descriptor("tibert", "2"))
    assert len(registry) == 2
    assert {d.version for d in registry.versions("tibert")} == {"1", "2"}
    assert registry.versions("absent") == ()


def test_all_preserves_registration_order() -> None:
    registry = InMemoryModelRegistry()
    for name in ("c", "a", "b"):
        registry.register(descriptor(name, "1"))
    assert [d.name for d in registry.all()] == ["c", "a", "b"]


# -- Capability registry -------------------------------------------------------
def test_a_capability_routes_to_its_provider() -> None:
    registry = InMemoryCapabilityRegistry()
    model = descriptor("mt", "1", CapabilityKind.TRANSLATION)
    registry.register(model)
    assert registry.resolve(CapabilityKind.TRANSLATION) is model
    assert registry.capabilities() == frozenset({CapabilityKind.TRANSLATION})


def test_an_unprovided_capability_resolves_to_none() -> None:
    registry = InMemoryCapabilityRegistry()
    assert registry.resolve(CapabilityKind.SIMILARITY) is None
    assert registry.providers(CapabilityKind.SIMILARITY) == ()


def test_the_highest_version_wins_by_default() -> None:
    """Version management: a newer model takes over an unqualified request."""
    registry = InMemoryCapabilityRegistry()
    registry.register(descriptor("tibert", "1", FEATURES))
    registry.register(descriptor("tibert", "3", FEATURES))
    registry.register(descriptor("tibert", "2", FEATURES))
    resolved = registry.resolve(FEATURES)
    assert resolved is not None and resolved.version == "3"


def test_a_preferred_model_name_wins_over_version() -> None:
    """A caller asking for a specific model gets it, at its highest version."""
    registry = InMemoryCapabilityRegistry()
    registry.register(descriptor("small", "9", FEATURES))
    registry.register(descriptor("large", "1", FEATURES))
    registry.register(descriptor("large", "2", FEATURES))
    resolved = registry.resolve(FEATURES, preferred="large")
    assert resolved is not None
    assert resolved.name == "large"
    assert resolved.version == "2"


def test_an_absent_preference_falls_back_to_the_default_rule() -> None:
    registry = InMemoryCapabilityRegistry()
    registry.register(descriptor("a", "1", FEATURES))
    registry.register(descriptor("b", "2", FEATURES))
    resolved = registry.resolve(FEATURES, preferred="absent")
    assert resolved is not None and resolved.version == "2"


def test_a_model_is_indexed_under_every_capability_it_provides() -> None:
    registry = InMemoryCapabilityRegistry()
    registry.register(descriptor("multi", "1", GRAMMAR, FEATURES))
    by_grammar = registry.resolve(GRAMMAR)
    by_features = registry.resolve(FEATURES)
    assert by_grammar is not None and by_grammar.name == "multi"
    assert by_features is not None and by_features.name == "multi"
    assert registry.capabilities() == frozenset({GRAMMAR, FEATURES})


def test_providers_lists_every_model_for_a_capability() -> None:
    registry = InMemoryCapabilityRegistry()
    registry.register(descriptor("a", "1", GRAMMAR))
    registry.register(descriptor("b", "1", GRAMMAR))
    assert {d.name for d in registry.providers(GRAMMAR)} == {"a", "b"}


def test_resolution_is_deterministic() -> None:
    registry = InMemoryCapabilityRegistry()
    registry.register(descriptor("a", "1", GRAMMAR))
    registry.register(descriptor("b", "1", GRAMMAR))
    assert registry.resolve(GRAMMAR) is registry.resolve(GRAMMAR)
