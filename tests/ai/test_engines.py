"""Tests for the concrete inference engines shipped with TEEA.

The DummyInferenceEngine is a shipped, no-op engine that implements the
InferenceEngine protocol so the AI Runtime can be wired and tested without
real model weights (ADR-013, ADR-019).  These tests verify protocol
conformance, deterministic behaviour, thread safety, and the recording API.
"""

from __future__ import annotations

import threading
from typing import Any

from teea.ai import (
    CapabilityKind,
    DummyInferenceEngine,
    ExecutionContext,
    InferenceEngine,
    InferenceRequest,
    LocalAIRuntime,
    ModelDescriptor,
)
from teea.daemon import TEEADaemon


def _descriptor(
    name: str = "dummy",
    version: str = "1",
    *,
    capabilities: set[CapabilityKind] | None = None,
    size_bytes: int = 0,
) -> ModelDescriptor:
    return ModelDescriptor(
        name=name,
        version=version,
        provides=frozenset(capabilities or {CapabilityKind.SEMANTIC_FEATURES}),
        size_bytes=size_bytes,
    )


def _request(
    capability: CapabilityKind = CapabilityKind.SEMANTIC_FEATURES,
    **inputs: Any,
) -> InferenceRequest:
    return InferenceRequest(capability=capability, inputs=inputs)


# -- Protocol conformance ------------------------------------------------------


def test_the_engine_satisfies_the_protocol() -> None:
    """The DummyInferenceEngine must be recognised as an InferenceEngine."""
    assert isinstance(DummyInferenceEngine(), InferenceEngine)


# -- Construction and initial state --------------------------------------------


def test_a_fresh_engine_has_no_calls() -> None:
    engine = DummyInferenceEngine()
    assert engine.load_calls == []
    assert engine.infer_calls == []
    assert engine.unload_calls == []
    assert engine.contexts == []
    assert engine.resident == set()
    assert engine.load_count == 0
    assert engine.infer_count == 0
    assert engine.unload_count == 0


# -- Load ----------------------------------------------------------------------


def test_load_records_the_model_key() -> None:
    engine = DummyInferenceEngine()
    desc = _descriptor()
    ctx = ExecutionContext()
    engine.load(desc, ctx)
    assert engine.load_calls == ["dummy:1"]
    assert engine.load_count == 1
    assert engine.resident == {"dummy:1"}
    assert engine.contexts == [ctx]


def test_load_records_the_execution_context() -> None:
    engine = DummyInferenceEngine()
    engine.load(_descriptor(), ExecutionContext(device="cpu"))
    assert engine.contexts[0].device.value == "cpu"


def test_load_is_idempotent_for_the_same_descriptor() -> None:
    """Multiple load calls for the same key are recorded individually."""
    engine = DummyInferenceEngine()
    desc = _descriptor()
    engine.load(desc, ExecutionContext())
    engine.load(desc, ExecutionContext())
    assert engine.load_calls == ["dummy:1", "dummy:1"]
    assert engine.load_count == 2


def test_multiple_models_can_be_loaded() -> None:
    engine = DummyInferenceEngine()
    engine.load(_descriptor("a"), ExecutionContext())
    engine.load(_descriptor("b"), ExecutionContext())
    assert engine.load_calls == ["a:1", "b:1"]
    assert engine.resident == {"a:1", "b:1"}


# -- Infer ---------------------------------------------------------------------


def test_infer_echoes_the_inputs() -> None:
    engine = DummyInferenceEngine()
    desc = _descriptor()
    engine.load(desc, ExecutionContext())
    output = engine.infer(desc, _request(text="བཀྲ་ཤིས་"))
    assert output["text"] == "བཀྲ་ཤིས་"
    assert output["_dummy"] is True


def test_infer_records_the_inference_call() -> None:
    engine = DummyInferenceEngine()
    desc = _descriptor()
    engine.load(desc, ExecutionContext())
    engine.infer(desc, _request())
    assert engine.infer_calls == ["dummy:1"]
    assert engine.infer_count == 1


def test_infer_preserves_all_inputs() -> None:
    engine = DummyInferenceEngine()
    desc = _descriptor()
    engine.load(desc, ExecutionContext())
    output = engine.infer(desc, _request(a=1, b="two", c=[3.0]))
    assert output["a"] == 1
    assert output["b"] == "two"
    assert output["c"] == [3.0]
    assert output["_dummy"] is True


def test_infer_with_empty_inputs() -> None:
    engine = DummyInferenceEngine()
    desc = _descriptor()
    engine.load(desc, ExecutionContext())
    output = engine.infer(desc, _request())
    assert output == {"_dummy": True}


def test_infer_does_not_mutate_the_request() -> None:
    """The engine must not modify the request object."""
    engine = DummyInferenceEngine()
    desc = _descriptor()
    engine.load(desc, ExecutionContext())
    req = _request(text="original")
    original_inputs = dict(req.inputs)
    engine.infer(desc, req)
    assert dict(req.inputs) == original_inputs


def test_infer_does_not_mutate_the_engine_after_return() -> None:
    """The returned mapping must be independent of the engine's internals."""
    engine = DummyInferenceEngine()
    desc = _descriptor()
    engine.load(desc, ExecutionContext())
    output = engine.infer(desc, _request(text="test"))
    # Mutate the returned dict locally to prove it is independent
    mutated = dict(output)
    mutated["text"] = "mutated"
    # The engine's own state should not have changed
    second = engine.infer(desc, _request(text="test"))
    assert second["text"] == "test"


# -- Unload --------------------------------------------------------------------


def test_unload_records_the_model_key() -> None:
    engine = DummyInferenceEngine()
    desc = _descriptor()
    engine.load(desc, ExecutionContext())
    engine.unload(desc)
    assert engine.unload_calls == ["dummy:1"]
    assert engine.unload_count == 1
    assert "dummy:1" not in engine.resident


def test_unload_of_a_non_resident_model_is_a_no_op() -> None:
    """Unload should not raise when called for a model that is not resident."""
    engine = DummyInferenceEngine()
    engine.unload(_descriptor("absent"))
    assert engine.unload_calls == ["absent:1"]
    assert engine.resident == set()


def test_unload_is_idempotent() -> None:
    engine = DummyInferenceEngine()
    desc = _descriptor()
    engine.load(desc, ExecutionContext())
    engine.unload(desc)
    engine.unload(desc)
    assert engine.unload_calls == ["dummy:1", "dummy:1"]


# -- Lifecycle integration -----------------------------------------------------


def test_full_lifecycle_is_recorded_in_order() -> None:
    engine = DummyInferenceEngine()
    desc = _descriptor()
    ctx = ExecutionContext()

    engine.load(desc, ctx)
    engine.infer(desc, _request())
    engine.infer(desc, _request())
    engine.unload(desc)

    assert engine.load_calls == ["dummy:1"]
    assert engine.infer_calls == ["dummy:1", "dummy:1"]
    assert engine.unload_calls == ["dummy:1"]
    assert engine.resident == set()


def test_the_engine_works_with_the_local_ai_runtime() -> None:
    """End-to-end: the DummyInferenceEngine should work inside LocalAIRuntime."""
    engine = DummyInferenceEngine()
    runtime = LocalAIRuntime(engine)
    runtime.register(_descriptor())
    runtime.start()

    response = runtime.infer(
        InferenceRequest(
            capability=CapabilityKind.SEMANTIC_FEATURES,
            inputs={"text": "བཀྲ་ཤིས་བདེ་ལེགས།"},
        )
    )

    assert response.produced_by == "dummy:1"
    assert response.outputs["_dummy"] is True
    assert response.outputs["text"] == "བཀྲ་ཤིས་བདེ་ལེགས།"
    assert engine.load_count == 1
    assert engine.infer_count == 1

    runtime.stop()


def test_the_engine_echoes_through_the_daemon_composition_root() -> None:
    """DummyInferenceEngine should compose through the daemon's TEEADaemon."""
    daemon = TEEADaemon(ai_engine=DummyInferenceEngine())
    daemon.start()

    ai = daemon.ai_runtime
    assert ai is not None
    assert ai.health().is_running

    # The daemon does not auto-register models; register one for the test.
    ai.register(
        ModelDescriptor(
            name="dummy",
            version="1",
            provides=frozenset({CapabilityKind.SEMANTIC_FEATURES}),
        )
    )
    response = ai.infer(
        InferenceRequest(
            capability=CapabilityKind.SEMANTIC_FEATURES,
            inputs={"text": "test"},
        )
    )
    assert response.outputs["_dummy"] is True
    assert response.outputs["text"] == "test"

    daemon.stop()
    assert not ai.health().is_running


# -- Thread safety -------------------------------------------------------------


def test_concurrent_inference_is_thread_safe() -> None:
    """Many threads must be able to call infer without corrupting state."""
    engine = DummyInferenceEngine()
    desc = _descriptor()
    ctx = ExecutionContext()
    engine.load(desc, ctx)

    errors: list[BaseException] = []
    count = 20
    barrier = threading.Barrier(count)

    def call_infer(index: int) -> None:
        barrier.wait()
        try:
            result = engine.infer(desc, _request(index=index))
            assert result["index"] == index
            assert result["_dummy"] is True
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [
        threading.Thread(target=call_infer, args=(i,)) for i in range(count)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"concurrent inference raised: {errors[0]}"
    assert engine.infer_count == count


def test_concurrent_load_is_thread_safe() -> None:
    """Many threads loading different models must not corrupt state."""
    engine = DummyInferenceEngine()
    errors: list[BaseException] = []
    count = 20
    barrier = threading.Barrier(count)

    def call_load(index: int) -> None:
        barrier.wait()
        try:
            engine.load(
                _descriptor(name=f"m{index}", version="1"),
                ExecutionContext(),
            )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [
        threading.Thread(target=call_load, args=(i,)) for i in range(count)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"concurrent load raised: {errors[0]}"
    assert engine.load_count == count
    assert len(engine.resident) == count


# -- Determinism ---------------------------------------------------------------


def test_inference_is_deterministic() -> None:
    """Same inputs always produce the same outputs."""
    engine = DummyInferenceEngine()
    desc = _descriptor()
    engine.load(desc, ExecutionContext())

    first = engine.infer(desc, _request(text="བཀྲ་ཤིས་"))
    second = engine.infer(desc, _request(text="བཀྲ་ཤིས་"))
    assert first == second


def test_the_engine_holds_no_cross_call_state() -> None:
    """Each inference is independent."""
    engine = DummyInferenceEngine()
    desc = _descriptor()
    engine.load(desc, ExecutionContext())

    a = engine.infer(desc, _request(a=1))
    b = engine.infer(desc, _request(b=2))
    assert a == {"a": 1, "_dummy": True}
    assert b == {"b": 2, "_dummy": True}
