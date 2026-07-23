"""Invariants of the AI Runtime's value objects, and the new error codes."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from teea.ai import (
    CapabilityKind,
    Device,
    ExecutionContext,
    HealthReport,
    InferenceRequest,
    InferenceResponse,
    ModelDescriptor,
    RuntimeState,
)
from teea.core.errors import ErrorCode


# -- The new error codes -------------------------------------------------------
def test_the_ai_runtime_has_its_own_error_code_domain() -> None:
    """Stable codes cross the IPC boundary and must not be renumbered."""
    assert ErrorCode.RUNTIME_NOT_STARTED.value == "TEEA-3000"
    assert ErrorCode.RESOURCE_EXHAUSTED.value == "TEEA-3006"


def test_every_error_code_is_unique() -> None:
    values = [code.value for code in ErrorCode]
    assert len(set(values)) == len(values)


# -- CapabilityKind ------------------------------------------------------------
def test_the_capabilities_are_exactly_figure_6s_outputs() -> None:
    """Grammar, spelling, translation, summary, citation, features, similarity."""
    assert {c.value for c in CapabilityKind} == {
        "grammar",
        "spelling",
        "translation",
        "summarization",
        "citation",
        "semantic_features",
        "similarity",
    }


# -- ModelDescriptor -----------------------------------------------------------
def test_a_descriptor_reports_its_key_and_capabilities() -> None:
    descriptor = ModelDescriptor(
        name="tibert",
        version="2",
        provides={CapabilityKind.SEMANTIC_FEATURES, CapabilityKind.SIMILARITY},
        size_bytes=1_024,
    )
    assert descriptor.key == "tibert:2"
    assert descriptor.provides_capability(CapabilityKind.SIMILARITY)
    assert not descriptor.provides_capability(CapabilityKind.GRAMMAR)


def test_a_descriptor_must_have_a_name() -> None:
    with pytest.raises(ValidationError, match="must have a name"):
        ModelDescriptor(name="", version="1", provides={CapabilityKind.GRAMMAR})


def test_a_descriptor_must_have_a_version() -> None:
    with pytest.raises(ValidationError, match="must have a version"):
        ModelDescriptor(name="x", version="", provides={CapabilityKind.GRAMMAR})


def test_a_descriptor_must_provide_a_capability() -> None:
    """A model that provides nothing could never be routed to."""
    with pytest.raises(ValidationError, match="at least one capability"):
        ModelDescriptor(name="x", version="1", provides=set())


def test_a_negative_size_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ModelDescriptor(
            name="x", version="1", provides={CapabilityKind.GRAMMAR}, size_bytes=-1
        )


def test_size_defaults_to_zero_meaning_unbudgeted() -> None:
    assert ModelDescriptor(
        name="x", version="1", provides={CapabilityKind.GRAMMAR}
    ).size_bytes == 0


def test_a_descriptor_is_immutable() -> None:
    descriptor = ModelDescriptor(
        name="x", version="1", provides={CapabilityKind.GRAMMAR}
    )
    with pytest.raises(ValidationError):
        descriptor.name = "y"  # type: ignore[misc]


def test_a_descriptor_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ModelDescriptor(
            name="x",
            version="1",
            provides={CapabilityKind.GRAMMAR},
            checksum="deadbeef",  # type: ignore[call-arg]
        )


# -- ExecutionContext ----------------------------------------------------------
def test_the_context_defaults_to_auto_device() -> None:
    assert ExecutionContext().device is Device.AUTO


def test_the_context_carries_a_device_choice() -> None:
    assert ExecutionContext(device=Device.GPU).device is Device.GPU


# -- InferenceRequest / InferenceResponse -------------------------------------
def test_a_request_names_a_capability() -> None:
    request = InferenceRequest(
        capability=CapabilityKind.TRANSLATION, inputs={"text": "བཀྲ"}
    )
    assert request.capability is CapabilityKind.TRANSLATION
    assert request.preferred is None
    assert request.inputs == {"text": "བཀྲ"}


def test_requests_default_to_empty_inputs() -> None:
    assert InferenceRequest(capability=CapabilityKind.GRAMMAR).inputs == {}


def test_a_response_carries_its_provenance() -> None:
    response = InferenceResponse(
        capability=CapabilityKind.SIMILARITY,
        produced_by="tibert:2",
        outputs={"score": 0.8},
    )
    assert response.produced_by == "tibert:2"
    assert response.outputs["score"] == 0.8


def test_a_request_is_immutable() -> None:
    request = InferenceRequest(capability=CapabilityKind.GRAMMAR)
    with pytest.raises(ValidationError):
        request.capability = CapabilityKind.SPELLING  # type: ignore[misc]


# -- HealthReport --------------------------------------------------------------
def test_a_health_report_summarises_the_runtime() -> None:
    report = HealthReport(
        state=RuntimeState.RUNNING,
        registered=3,
        loaded=("a:1", "b:1"),
        capabilities=(CapabilityKind.GRAMMAR,),
        memory_used_bytes=200,
        memory_budget_bytes=500,
    )
    assert report.is_running is True
    assert report.num_loaded == 2
    assert report.memory_available_bytes == 300


def test_an_unlimited_budget_reports_no_available_figure() -> None:
    report = HealthReport(state=RuntimeState.RUNNING, registered=0)
    assert report.memory_budget_bytes is None
    assert report.memory_available_bytes is None


def test_a_stopped_runtime_is_not_running() -> None:
    assert HealthReport(state=RuntimeState.STOPPED, registered=0).is_running is False


# -- Serialization -------------------------------------------------------------
def test_a_response_round_trips_through_json() -> None:
    """Inference results cross the IPC boundary to the add-in."""
    response = InferenceResponse(
        capability=CapabilityKind.SEMANTIC_FEATURES,
        produced_by="tibert:1",
        outputs={"vector": [0.1, 0.2, 0.3]},
    )
    restored = InferenceResponse.model_validate_json(response.model_dump_json())
    assert restored == response


def test_a_health_report_dumps_to_plain_data() -> None:
    dumped = HealthReport(
        state=RuntimeState.RUNNING, registered=1, capabilities=(CapabilityKind.GRAMMAR,)
    ).model_dump(mode="json")
    assert dumped["state"] == "running"
    assert dumped["capabilities"] == ["grammar"]
