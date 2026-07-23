"""Unit, lifecycle, resource-management and failure-recovery tests for the runtime.

The runtime owns routing, lifecycle, residency accounting and health, and
delegates the running of weights to an injected engine. So the tests assert on
the orchestration -- which models it loaded, in what order, when it evicted one,
how it wrapped an engine failure -- against recording and misbehaving engine
doubles, never a real model.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from teea.ai import (
    AIRuntimeSettings,
    CapabilityKind,
    Device,
    ExecutionContext,
    InferenceEngine,
    InferenceRequest,
    InMemoryCapabilityRegistry,
    InMemoryModelRegistry,
    LocalAIRuntime,
    ModelDescriptor,
    ModelState,
    RuntimeState,
)
from teea.ai.errors import (
    CapabilityUnavailableError,
    InferenceError,
    ModelLoadError,
    ModelNotFoundError,
    ModelRegistrationError,
    ResourceExhaustedError,
    RuntimeStateError,
)
from tests.ai.conftest import (
    FailingInferEngine,
    FailingLoadEngine,
    FailingUnloadEngine,
    RecordingEngine,
    descriptor,
)

FEATURES = CapabilityKind.SEMANTIC_FEATURES
GRAMMAR = CapabilityKind.GRAMMAR


def request(
    capability: CapabilityKind = FEATURES, **kwargs: Any
) -> InferenceRequest:
    return InferenceRequest(capability=capability, **kwargs)


def budgeted(engine: RecordingEngine, budget: int) -> LocalAIRuntime:
    """A running runtime with a finite memory budget."""
    return LocalAIRuntime(engine, settings=AIRuntimeSettings(memory_budget_bytes=budget))


# -- Construction and dependency injection ------------------------------------
def test_the_default_registries_are_used(engine: RecordingEngine) -> None:
    runtime = LocalAIRuntime(engine)
    runtime.register(descriptor())
    assert runtime.registered_models()[0].name == "tibert"


def test_the_injected_registries_are_used(engine: RecordingEngine) -> None:
    """Interface Segregation: either registry can be replaced."""
    models = InMemoryModelRegistry()
    capabilities = InMemoryCapabilityRegistry()
    runtime = LocalAIRuntime(
        engine, model_registry=models, capability_registry=capabilities
    )
    runtime.register(descriptor())
    assert len(models) == 1
    assert capabilities.resolve(FEATURES) is not None


def test_the_context_reflects_the_configured_device(engine: RecordingEngine) -> None:
    runtime = LocalAIRuntime(
        engine, settings=AIRuntimeSettings(default_device=Device.GPU)
    )
    assert runtime.context == ExecutionContext(device=Device.GPU)


def test_a_fresh_runtime_is_in_the_created_state(engine: RecordingEngine) -> None:
    assert LocalAIRuntime(engine).state is RuntimeState.CREATED


# -- Lifecycle -----------------------------------------------------------------
def test_start_moves_the_runtime_to_running(engine: RecordingEngine) -> None:
    runtime = LocalAIRuntime(engine)
    runtime.start()
    assert runtime.state is RuntimeState.RUNNING


def test_a_runtime_can_only_be_started_once(engine: RecordingEngine) -> None:
    runtime = LocalAIRuntime(engine)
    runtime.start()
    with pytest.raises(RuntimeStateError, match="only be started once"):
        runtime.start()


def test_stop_unloads_every_resident_model(engine: RecordingEngine) -> None:
    runtime = LocalAIRuntime(engine)
    runtime.register(descriptor())
    runtime.start()
    runtime.infer(request())
    assert engine.resident
    runtime.stop()
    assert runtime.state is RuntimeState.STOPPED
    assert not engine.resident
    assert engine.unload_calls == ["tibert:1"]


def test_stop_is_idempotent(started_runtime: LocalAIRuntime) -> None:
    started_runtime.stop()
    started_runtime.stop()
    assert started_runtime.state is RuntimeState.STOPPED


def test_a_stopped_runtime_refuses_inference(started_runtime: LocalAIRuntime) -> None:
    started_runtime.stop()
    with pytest.raises(RuntimeStateError, match="not running") as error:
        started_runtime.infer(request())
    assert error.value.code.value == "TEEA-3000"


def test_inference_before_start_is_refused(engine: RecordingEngine) -> None:
    runtime = LocalAIRuntime(engine)
    runtime.register(descriptor())
    with pytest.raises(RuntimeStateError, match="not running"):
        runtime.infer(request())


def test_the_runtime_works_as_a_context_manager(engine: RecordingEngine) -> None:
    with LocalAIRuntime(engine) as runtime:
        runtime.register(descriptor())
        assert runtime.state.value == "running"
        runtime.infer(request())
    assert runtime.state.value == "stopped"
    assert not engine.resident


# -- Registration --------------------------------------------------------------
def test_a_model_can_be_registered_before_start(engine: RecordingEngine) -> None:
    runtime = LocalAIRuntime(engine)
    runtime.register(descriptor())
    runtime.start()
    assert runtime.infer(request()).produced_by == "tibert:1"


def test_a_duplicate_registration_is_refused(started_runtime: LocalAIRuntime) -> None:
    with pytest.raises(ModelRegistrationError, match="already registered"):
        started_runtime.register(descriptor())


def test_registration_is_refused_on_a_stopped_runtime(
    started_runtime: LocalAIRuntime,
) -> None:
    started_runtime.stop()
    with pytest.raises(RuntimeStateError, match="stopped runtime"):
        started_runtime.register(descriptor(name="other"))


def test_eager_loading_loads_at_registration(engine: RecordingEngine) -> None:
    """Figure 6's non-lazy path: register a running model and it loads now."""
    runtime = LocalAIRuntime(engine, settings=AIRuntimeSettings(eager_load=True))
    runtime.start()
    runtime.register(descriptor())
    assert engine.load_calls == ["tibert:1"]


def test_eager_loading_waits_for_start(engine: RecordingEngine) -> None:
    """Registered before start, an eager model still cannot load until running."""
    runtime = LocalAIRuntime(engine, settings=AIRuntimeSettings(eager_load=True))
    runtime.register(descriptor())
    assert engine.load_calls == []
    runtime.start()
    runtime.load("tibert:1")
    assert engine.load_calls == ["tibert:1"]


# -- Lazy loading and manual lifecycle ----------------------------------------
def test_a_model_loads_lazily_on_first_use(engine: RecordingEngine) -> None:
    runtime = LocalAIRuntime(engine)
    runtime.register(descriptor())
    runtime.start()
    assert engine.load_calls == []
    runtime.infer(request())
    assert engine.load_calls == ["tibert:1"]


def test_a_loaded_model_is_reused_not_reloaded(engine: RecordingEngine) -> None:
    runtime = LocalAIRuntime(engine)
    runtime.register(descriptor())
    runtime.start()
    runtime.infer(request())
    runtime.infer(request())
    assert engine.load_calls == ["tibert:1"]
    assert engine.infer_calls == ["tibert:1", "tibert:1"]


def test_a_model_can_be_loaded_and_unloaded_manually(engine: RecordingEngine) -> None:
    runtime = LocalAIRuntime(engine)
    runtime.register(descriptor())
    runtime.start()
    runtime.load("tibert:1")
    assert runtime.model_state("tibert:1") is ModelState.LOADED
    runtime.unload("tibert:1")
    assert runtime.model_state("tibert:1") is ModelState.REGISTERED
    assert engine.unload_calls == ["tibert:1"]


def test_unloading_a_model_that_is_not_loaded_is_a_no_op(
    engine: RecordingEngine,
) -> None:
    runtime = LocalAIRuntime(engine)
    runtime.register(descriptor())
    runtime.start()
    runtime.unload("tibert:1")
    assert engine.unload_calls == []


def test_loading_an_unregistered_model_is_refused(
    started_runtime: LocalAIRuntime,
) -> None:
    with pytest.raises(ModelNotFoundError, match="No model is registered"):
        started_runtime.load("absent:1")


def test_the_model_state_of_an_unknown_key_is_none(
    started_runtime: LocalAIRuntime,
) -> None:
    assert started_runtime.model_state("absent:1") is None


def test_manual_lifecycle_requires_a_running_runtime(
    engine: RecordingEngine,
) -> None:
    runtime = LocalAIRuntime(engine)
    runtime.register(descriptor())
    with pytest.raises(RuntimeStateError):
        runtime.load("tibert:1")


# -- Routing -------------------------------------------------------------------
def test_a_request_routes_to_the_model_that_provides_it(
    engine: RecordingEngine,
) -> None:
    runtime = LocalAIRuntime(engine)
    runtime.register(descriptor(name="mt", provides={CapabilityKind.TRANSLATION}))
    runtime.register(descriptor(name="tibert", provides={FEATURES}))
    runtime.start()
    assert runtime.infer(request(CapabilityKind.TRANSLATION)).produced_by == "mt:1"
    assert runtime.infer(request(FEATURES)).produced_by == "tibert:1"


def test_a_preferred_model_is_honoured(engine: RecordingEngine) -> None:
    runtime = LocalAIRuntime(engine)
    runtime.register(descriptor(name="fast", provides={FEATURES}))
    runtime.register(descriptor(name="accurate", provides={FEATURES}))
    runtime.start()
    assert runtime.infer(
        request(preferred="accurate")
    ).produced_by == "accurate:1"


def test_an_unprovided_capability_is_refused(started_runtime: LocalAIRuntime) -> None:
    with pytest.raises(CapabilityUnavailableError, match="No registered model") as e:
        started_runtime.infer(request(CapabilityKind.TRANSLATION))
    assert e.value.context["capability"] == "translation"


def test_the_response_echoes_the_engine_output(
    started_runtime: LocalAIRuntime,
) -> None:
    response = started_runtime.infer(request(inputs={"text": "བཀྲ"}))
    assert response.capability is FEATURES
    assert response.produced_by == "tibert:1"
    assert response.outputs == {"model": "tibert:1", "echo": {"text": "བཀྲ"}}


def test_the_configured_device_reaches_the_engine(engine: RecordingEngine) -> None:
    runtime = LocalAIRuntime(
        engine, settings=AIRuntimeSettings(default_device=Device.CPU)
    )
    runtime.register(descriptor())
    runtime.start()
    runtime.infer(request())
    assert engine.contexts[0].device is Device.CPU


# -- Resource management (the Memory Manager) ---------------------------------
def test_an_unlimited_budget_never_evicts(engine: RecordingEngine) -> None:
    runtime = LocalAIRuntime(engine)
    for i in range(5):
        runtime.register(descriptor(name=f"m{i}", size_bytes=10_000))
    runtime.start()
    for i in range(5):
        runtime.load(f"m{i}:1")
    assert runtime.health().num_loaded == 5
    assert engine.unload_calls == []


def test_loading_over_budget_evicts_the_least_recently_used(
    engine: RecordingEngine,
) -> None:
    runtime = budgeted(engine, 250)
    for i in range(3):
        runtime.register(descriptor(name=f"m{i}", provides={GRAMMAR}, size_bytes=100))
    runtime.start()
    runtime.load("m0:1")
    runtime.load("m1:1")
    runtime.load("m2:1")  # 300 > 250 -> evict m0, the least recently used
    assert set(runtime.health().loaded) == {"m1:1", "m2:1"}
    assert engine.unload_calls == ["m0:1"]
    assert runtime.health().memory_used_bytes == 200


def test_use_refreshes_recency(engine: RecordingEngine) -> None:
    """Touching m0 makes m1 the least recently used, so m1 is evicted instead."""
    runtime = budgeted(engine, 250)
    for i in range(3):
        runtime.register(descriptor(name=f"m{i}", provides={GRAMMAR}, size_bytes=100))
    runtime.start()
    runtime.load("m0:1")
    runtime.load("m1:1")
    runtime.infer(request(GRAMMAR, preferred="m0"))  # m0 is now most recent
    runtime.load("m2:1")
    assert set(runtime.health().loaded) == {"m0:1", "m2:1"}
    assert engine.unload_calls == ["m1:1"]


def test_a_model_larger_than_the_whole_budget_is_refused(
    engine: RecordingEngine,
) -> None:
    runtime = budgeted(engine, 100)
    runtime.register(descriptor(size_bytes=101))
    runtime.start()
    with pytest.raises(ResourceExhaustedError, match="larger than the whole") as error:
        runtime.load("tibert:1")
    assert error.value.context["size_bytes"] == 101


def test_a_model_exactly_filling_the_budget_loads(engine: RecordingEngine) -> None:
    runtime = budgeted(engine, 100)
    runtime.register(descriptor(size_bytes=100))
    runtime.start()
    runtime.load("tibert:1")
    assert runtime.health().memory_used_bytes == 100
    assert runtime.health().memory_available_bytes == 0


def test_eviction_reclaims_memory(engine: RecordingEngine) -> None:
    runtime = budgeted(engine, 100)
    runtime.register(descriptor(name="a", provides={GRAMMAR}, size_bytes=100))
    runtime.register(descriptor(name="b", provides={GRAMMAR}, size_bytes=100))
    runtime.start()
    runtime.load("a:1")
    runtime.load("b:1")  # evicts a
    assert runtime.health().memory_used_bytes == 100
    assert runtime.health().loaded == ("b:1",)


# -- Failure recovery ----------------------------------------------------------
def test_a_load_failure_is_wrapped(engine: RecordingEngine) -> None:
    runtime = LocalAIRuntime(FailingLoadEngine())
    runtime.register(descriptor())
    runtime.start()
    with pytest.raises(ModelLoadError, match="failed to load") as error:
        runtime.infer(request())
    assert error.value.code.value == "TEEA-3004"
    assert isinstance(error.value.__cause__, RuntimeError)


def test_a_failed_load_leaves_no_phantom_residency() -> None:
    """A model that failed to load must not count against the budget."""
    runtime = LocalAIRuntime(FailingLoadEngine())
    runtime.register(descriptor(size_bytes=100))
    runtime.start()
    with pytest.raises(ModelLoadError):
        runtime.load("tibert:1")
    assert runtime.health().num_loaded == 0
    assert runtime.health().memory_used_bytes == 0
    assert runtime.model_state("tibert:1") is ModelState.REGISTERED


def test_an_inference_failure_is_wrapped() -> None:
    runtime = LocalAIRuntime(FailingInferEngine())
    runtime.register(descriptor())
    runtime.start()
    with pytest.raises(InferenceError, match="failed while running") as error:
        runtime.infer(request())
    assert error.value.code.value == "TEEA-3005"
    assert isinstance(error.value.__cause__, ValueError)


def test_the_model_stays_loaded_after_an_inference_failure() -> None:
    """A transient inference error must not force a reload on the next call."""
    runtime = LocalAIRuntime(FailingInferEngine())
    runtime.register(descriptor())
    runtime.start()
    with pytest.raises(InferenceError):
        runtime.infer(request())
    assert runtime.model_state("tibert:1") is ModelState.LOADED


def test_an_engine_that_fails_to_unload_does_not_wedge_eviction() -> None:
    """Eviction is the runtime's decision; a failed unload must not corrupt state."""
    runtime = LocalAIRuntime(
        FailingUnloadEngine(), settings=AIRuntimeSettings(memory_budget_bytes=100)
    )
    runtime.register(descriptor(name="a", provides={GRAMMAR}, size_bytes=100))
    runtime.register(descriptor(name="b", provides={GRAMMAR}, size_bytes=100))
    runtime.start()
    runtime.load("a:1")
    runtime.load("b:1")  # evicts a; the engine raises on unload, swallowed
    assert runtime.health().loaded == ("b:1",)
    assert runtime.health().memory_used_bytes == 100


def test_an_engine_that_fails_to_unload_does_not_block_shutdown() -> None:
    runtime = LocalAIRuntime(FailingUnloadEngine())
    runtime.register(descriptor())
    runtime.start()
    runtime.load("tibert:1")
    runtime.stop()  # must not raise
    assert runtime.state is RuntimeState.STOPPED


# -- Health --------------------------------------------------------------------
def test_health_reports_the_full_picture(engine: RecordingEngine) -> None:
    runtime = budgeted(engine, 1_000)
    runtime.register(descriptor(name="a", provides={GRAMMAR, FEATURES}, size_bytes=100))
    runtime.register(descriptor(name="b", provides={CapabilityKind.TRANSLATION}))
    runtime.start()
    runtime.load("a:1")
    report = runtime.health()
    assert report.state is RuntimeState.RUNNING
    assert report.registered == 2
    assert report.loaded == ("a:1",)
    assert report.capabilities == (
        GRAMMAR,
        FEATURES,
        CapabilityKind.TRANSLATION,
    ) or set(report.capabilities) == {GRAMMAR, FEATURES, CapabilityKind.TRANSLATION}
    assert report.memory_used_bytes == 100
    assert report.memory_available_bytes == 900


def test_health_is_available_in_every_state(engine: RecordingEngine) -> None:
    runtime = LocalAIRuntime(engine)
    assert runtime.health().state is RuntimeState.CREATED
    runtime.start()
    assert runtime.health().state is RuntimeState.RUNNING
    runtime.stop()
    assert runtime.health().state is RuntimeState.STOPPED
    assert runtime.health().num_loaded == 0


# -- Batch ---------------------------------------------------------------------
def test_a_batch_returns_a_response_per_request_in_order(
    engine: RecordingEngine,
) -> None:
    runtime = LocalAIRuntime(engine)
    runtime.register(descriptor(name="mt", provides={CapabilityKind.TRANSLATION}))
    runtime.register(descriptor(name="tibert", provides={FEATURES}))
    runtime.start()
    responses = runtime.infer_batch(
        [
            request(CapabilityKind.TRANSLATION),
            request(FEATURES),
            request(CapabilityKind.TRANSLATION),
        ]
    )
    assert [r.produced_by for r in responses] == ["mt:1", "tibert:1", "mt:1"]


def test_a_batch_loads_each_model_once(engine: RecordingEngine) -> None:
    """Figure 6's "Batch processing": grouping by model avoids reloading."""
    runtime = LocalAIRuntime(engine)
    runtime.register(descriptor(name="mt", provides={CapabilityKind.TRANSLATION}))
    runtime.start()
    runtime.infer_batch([request(CapabilityKind.TRANSLATION) for _ in range(5)])
    assert engine.load_calls == ["mt:1"]
    assert len(engine.infer_calls) == 5


def test_an_empty_batch_returns_nothing(started_runtime: LocalAIRuntime) -> None:
    assert started_runtime.infer_batch([]) == ()


def test_a_batch_is_all_or_nothing(started_runtime: LocalAIRuntime) -> None:
    """One bad request fails the batch; a partial unordered result is useless."""
    with pytest.raises(CapabilityUnavailableError):
        started_runtime.infer_batch(
            [request(FEATURES), request(CapabilityKind.SPELLING)]
        )


def test_a_batch_requires_a_running_runtime(engine: RecordingEngine) -> None:
    runtime = LocalAIRuntime(engine)
    runtime.register(descriptor())
    with pytest.raises(RuntimeStateError):
        runtime.infer_batch([request()])


# -- Determinism and concurrency ----------------------------------------------
def test_inference_is_deterministic(started_runtime: LocalAIRuntime) -> None:
    first = started_runtime.infer(request(inputs={"n": 1}))
    second = started_runtime.infer(request(inputs={"n": 1}))
    assert first == second


def test_concurrent_inference_is_consistent(engine: RecordingEngine) -> None:
    """The daemon calls one runtime from many plugin threads at once."""
    runtime = LocalAIRuntime(engine)
    for i in range(4):
        runtime.register(descriptor(name=f"m{i}", provides={GRAMMAR}))
    runtime.start()

    def call(index: int) -> str:
        return runtime.infer(request(GRAMMAR, preferred=f"m{index % 4}")).produced_by

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(call, range(200)))
    assert set(results) == {f"m{i}:1" for i in range(4)}
    assert runtime.health().num_loaded == 4


def test_concurrent_eviction_keeps_accounting_consistent(
    engine: RecordingEngine,
) -> None:
    """Under a tight budget, many threads loading and evicting must not corrupt
    the residency total."""
    runtime = budgeted(engine, 200)
    for i in range(8):
        runtime.register(descriptor(name=f"m{i}", provides={GRAMMAR}, size_bytes=100))
    runtime.start()

    barrier = threading.Barrier(8)

    def hammer(index: int) -> None:
        barrier.wait()
        runtime.infer(request(GRAMMAR, preferred=f"m{index}"))

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(hammer, range(8)))

    report = runtime.health()
    assert report.memory_used_bytes <= 200
    assert report.memory_used_bytes == 100 * report.num_loaded


def test_the_runtime_holds_no_cross_call_state(
    started_runtime: LocalAIRuntime,
) -> None:
    started_runtime.infer(request(inputs={"a": 1}))
    assert started_runtime.infer(request(inputs={"b": 2})).outputs["echo"] == {"b": 2}


def test_a_custom_engine_satisfies_the_protocol() -> None:
    class Minimal:
        def load(self, d: ModelDescriptor, c: ExecutionContext) -> None: ...
        def infer(
            self, d: ModelDescriptor, r: InferenceRequest
        ) -> Mapping[str, Any]:
            return {}

        def unload(self, d: ModelDescriptor) -> None: ...

    assert isinstance(Minimal(), InferenceEngine)
