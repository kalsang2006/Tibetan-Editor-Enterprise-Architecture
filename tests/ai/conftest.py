"""Inference-engine doubles and fixtures for the AI Runtime suite.

The runtime ships no engine, so every test injects one. These doubles record what
the runtime asked them to do -- which models it loaded, in what order, how many
times -- so the tests can assert on the *orchestration* without a real model. The
misbehaving ones (loads that fail, inference that raises) exist to prove the
runtime wraps an adapter's failure into a typed error.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from typing import Any

import pytest

from teea.ai import (
    CapabilityKind,
    ExecutionContext,
    InferenceRequest,
    LocalAIRuntime,
    ModelDescriptor,
)


class RecordingEngine:
    """A well-behaved engine that echoes the request and records every call.

    Thread-safe, because the concurrency tests drive it from many threads at
    once; its counters would otherwise race and give misleading assertions.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.load_calls: list[str] = []
        self.infer_calls: list[str] = []
        self.unload_calls: list[str] = []
        self.resident: set[str] = set()
        self.contexts: list[ExecutionContext] = []

    def load(self, descriptor: ModelDescriptor, context: ExecutionContext) -> None:
        with self._lock:
            self.load_calls.append(descriptor.key)
            self.contexts.append(context)
            self.resident.add(descriptor.key)

    def infer(self, descriptor: ModelDescriptor, request: InferenceRequest) -> Mapping[str, Any]:
        with self._lock:
            self.infer_calls.append(descriptor.key)
            assert descriptor.key in self.resident, "the runtime ran an unloaded model"
        return {"model": descriptor.key, "echo": dict(request.inputs)}

    def unload(self, descriptor: ModelDescriptor) -> None:
        with self._lock:
            self.unload_calls.append(descriptor.key)
            self.resident.discard(descriptor.key)


class FailingLoadEngine:
    """Raises when asked to load, to exercise the load-failure path."""

    def __init__(self, error: Exception | None = None) -> None:
        self._error = error or RuntimeError("weights unavailable")

    def load(self, descriptor: ModelDescriptor, context: ExecutionContext) -> None:
        raise self._error

    def infer(self, descriptor: ModelDescriptor, request: InferenceRequest) -> Mapping[str, Any]:
        raise AssertionError("infer should be unreachable")  # pragma: no cover

    def unload(self, descriptor: ModelDescriptor) -> None:
        raise AssertionError("unload should be unreachable")  # pragma: no cover


class FailingInferEngine:
    """Loads fine but raises during inference."""

    def __init__(self, error: Exception | None = None) -> None:
        self._error = error or ValueError("bad tensor shape")

    def load(self, descriptor: ModelDescriptor, context: ExecutionContext) -> None:
        return None

    def infer(self, descriptor: ModelDescriptor, request: InferenceRequest) -> Mapping[str, Any]:
        raise self._error

    def unload(self, descriptor: ModelDescriptor) -> None:
        return None


class FailingUnloadEngine:
    """Loads and runs, but raises on unload, to prove eviction is robust."""

    def load(self, descriptor: ModelDescriptor, context: ExecutionContext) -> None:
        return None

    def infer(self, descriptor: ModelDescriptor, request: InferenceRequest) -> Mapping[str, Any]:
        return {"model": descriptor.key}

    def unload(self, descriptor: ModelDescriptor) -> None:
        raise RuntimeError("gpu handle already gone")


def descriptor(
    name: str = "tibert",
    version: str = "1",
    provides: set[CapabilityKind] | None = None,
    size_bytes: int = 0,
) -> ModelDescriptor:
    """Build a descriptor with sensible defaults."""
    return ModelDescriptor(
        name=name,
        version=version,
        provides=frozenset(provides or {CapabilityKind.SEMANTIC_FEATURES}),
        size_bytes=size_bytes,
    )


@pytest.fixture
def engine() -> RecordingEngine:
    """A well-behaved, recording inference engine."""
    return RecordingEngine()


@pytest.fixture
def make_descriptor() -> Callable[..., ModelDescriptor]:
    """Factory for model descriptors."""
    return descriptor


@pytest.fixture
def started_runtime(engine: RecordingEngine) -> LocalAIRuntime:
    """A running runtime with one semantic-features model registered."""
    runtime = LocalAIRuntime(engine)
    runtime.register(descriptor())
    runtime.start()
    return runtime
