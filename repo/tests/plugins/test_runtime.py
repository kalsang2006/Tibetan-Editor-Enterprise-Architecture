"""Unit, regression and edge-case tests for the supervised Plugin Runtime.

The requirement under test throughout is NFR 5.3: "a system fault or unhandled
error inside a particular feature plugin must be captured by its manager without
causing the host Word interface or other running tools to crash". Every
misbehaviour a plugin can exhibit is exercised, and each one is asserted to be
contained *and recorded* -- containment alone would leave the add-in unable to
tell a quiet plugin from a broken one.
"""

from __future__ import annotations

from collections.abc import Iterable
from concurrent.futures import Executor, Future, ThreadPoolExecutor

import pytest

from teea.core.errors import ConfigurationError, ErrorCode
from teea.fusion import Suggestion
from teea.nlp.snapshot import DocumentSnapshot
from teea.plugins import (
    FeaturePlugin,
    PluginResults,
    PluginRuntime,
    SupervisedPluginRuntime,
)
from tests.plugins.conftest import (
    CrashingPlugin,
    ImpersonatingPlugin,
    LateCrashingPlugin,
    MisconfiguredPlugin,
    NamelessPlugin,
    SilentPlugin,
    UnnameablePlugin,
    WellBehavedPlugin,
)


class RecordingExecutor(Executor):
    """Runs work immediately on the calling thread, counting submissions."""

    def __init__(self) -> None:
        self.submissions = 0

    def submit(self, fn, /, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.submissions += 1
        future: Future[object] = Future()
        future.set_result(fn(*args, **kwargs))
        return future


class ExhaustedExecutor(Executor):
    """Refuses work, the way a shut-down pool does."""

    def submit(self, fn, /, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("cannot schedule new futures after shutdown")


# -- Contract and registration -------------------------------------------------
def test_satisfies_the_plugin_runtime_protocol() -> None:
    assert isinstance(SupervisedPluginRuntime(), PluginRuntime)


def test_the_doubles_satisfy_the_feature_plugin_protocol() -> None:
    assert isinstance(WellBehavedPlugin(), FeaturePlugin)
    assert isinstance(CrashingPlugin(), FeaturePlugin)


def test_a_runtime_with_no_plugins_is_valid(plugin_snapshot: DocumentSnapshot) -> None:
    """The microkernel is complete before any extension is installed."""
    runtime = SupervisedPluginRuntime()
    assert runtime.plugins == ()
    results = runtime.dispatch(plugin_snapshot)
    assert results.num_plugins == 0
    assert results.is_healthy is True


def test_registration_preserves_the_order_it_was_given() -> None:
    runtime = SupervisedPluginRuntime(
        [WellBehavedPlugin("b"), WellBehavedPlugin("a"), SilentPlugin()]
    )
    assert runtime.plugins == ("b", "a", "quiet")


def test_registration_accepts_any_iterable() -> None:
    runtime = SupervisedPluginRuntime(WellBehavedPlugin(f"p{index}") for index in range(3))
    assert runtime.plugins == ("p0", "p1", "p2")


def test_a_nameless_plugin_is_refused() -> None:
    """A fault it raised later could not be attributed to anything."""
    with pytest.raises(ConfigurationError, match="empty name") as error:
        SupervisedPluginRuntime([NamelessPlugin()])
    assert error.value.code is ErrorCode.CONFIGURATION_INVALID
    assert error.value.context["position"] == 0


def test_a_plugin_that_cannot_report_its_name_is_refused() -> None:
    """Registration is a plugin boundary too, so it is guarded like dispatch."""
    with pytest.raises(ConfigurationError, match="failed to report its name") as error:
        SupervisedPluginRuntime([SilentPlugin(), UnnameablePlugin()])
    assert error.value.context == {"position": 1, "error_type": "RuntimeError"}


def test_duplicate_plugin_names_are_refused() -> None:
    """Two plugins under one name would misattribute both output and faults."""
    with pytest.raises(ConfigurationError, match="share the same name") as error:
        SupervisedPluginRuntime([WellBehavedPlugin("spell"), WellBehavedPlugin("spell")])
    assert error.value.context["name"] == "spell"


def test_the_name_is_read_once_at_registration(
    plugin_snapshot: DocumentSnapshot,
) -> None:
    """A plugin must not be able to change identity between registration and use."""

    class Shifty:
        def __init__(self) -> None:
            self.reads = 0

        @property
        def name(self) -> str:
            self.reads += 1
            return "stable" if self.reads == 1 else "changed"

        def examine(self, snapshot: DocumentSnapshot) -> Iterable[Suggestion]:
            return ()

    plugin = Shifty()
    runtime = SupervisedPluginRuntime([plugin])
    assert runtime.plugins == ("stable",)
    assert runtime.dispatch(plugin_snapshot).outcomes[0].plugin == "stable"


# -- Dispatch: the happy path --------------------------------------------------
def test_a_well_behaved_plugin_produces_suggestions(
    plugin_snapshot: DocumentSnapshot,
) -> None:
    results = SupervisedPluginRuntime([WellBehavedPlugin()]).dispatch(plugin_snapshot)
    assert results.is_healthy is True
    assert results.num_suggestions == plugin_snapshot.num_sentences
    assert {s.source for s in results.suggestions} == {"spell"}


def test_a_silent_plugin_succeeds_with_nothing(
    plugin_snapshot: DocumentSnapshot,
) -> None:
    results = SupervisedPluginRuntime([SilentPlugin()]).dispatch(plugin_snapshot)
    assert results.is_healthy is True
    assert results.num_suggestions == 0
    assert results.num_succeeded == 1


def test_every_registered_plugin_gets_an_outcome(
    plugin_snapshot: DocumentSnapshot,
) -> None:
    """Reporting only successes would hide which plugins never ran."""
    runtime = SupervisedPluginRuntime([WellBehavedPlugin(), SilentPlugin(), CrashingPlugin()])
    results = runtime.dispatch(plugin_snapshot)
    assert {o.plugin for o in results.outcomes} == {"spell", "quiet", "crash"}
    assert results.num_plugins == 3


def test_outcomes_are_ordered_by_plugin_name(
    plugin_snapshot: DocumentSnapshot,
) -> None:
    runtime = SupervisedPluginRuntime(
        [WellBehavedPlugin("zeta"), WellBehavedPlugin("alpha"), SilentPlugin()]
    )
    names = [o.plugin for o in runtime.dispatch(plugin_snapshot).outcomes]
    assert names == sorted(names) == ["alpha", "quiet", "zeta"]


def test_a_plugin_may_return_a_generator(
    plugin_snapshot: DocumentSnapshot,
) -> None:
    """``examine`` returns an Iterable, so a lazy plugin must work."""
    results = SupervisedPluginRuntime([WellBehavedPlugin()]).dispatch(plugin_snapshot)
    assert results.num_suggestions > 0


# -- Dispatch: fault isolation (NFR 5.3) --------------------------------------
def test_a_crashing_plugin_does_not_raise(
    plugin_snapshot: DocumentSnapshot,
) -> None:
    """The requirement in one line: the fault reaches the caller as data."""
    results = SupervisedPluginRuntime([CrashingPlugin()]).dispatch(plugin_snapshot)
    assert results.is_healthy is False
    assert results.num_failed == 1
    recorded = results.failures[0]
    assert recorded.plugin == "crash"
    assert recorded.error_type == "RuntimeError"
    assert recorded.message == "the plugin exploded"
    assert recorded.code is ErrorCode.PLUGIN_EXECUTION_FAILED


def test_one_plugins_crash_leaves_the_others_untouched(
    plugin_snapshot: DocumentSnapshot,
) -> None:
    """ "...without causing the host Word interface or other running tools to crash"."""
    runtime = SupervisedPluginRuntime([CrashingPlugin(), WellBehavedPlugin(), SilentPlugin()])
    results = runtime.dispatch(plugin_snapshot)
    alone = SupervisedPluginRuntime([WellBehavedPlugin()]).dispatch(plugin_snapshot)

    assert results.num_failed == 1
    assert results.num_succeeded == 2
    assert results.suggestions == alone.suggestions


def test_a_typed_error_keeps_its_own_code(
    plugin_snapshot: DocumentSnapshot,
) -> None:
    """A misconfigured plugin is a different problem from a crashing one."""
    results = SupervisedPluginRuntime([MisconfiguredPlugin()]).dispatch(plugin_snapshot)
    recorded = results.failures[0]
    assert recorded.code is ErrorCode.CONFIGURATION_INVALID
    assert recorded.error_type == "ConfigurationError"


def test_an_impersonating_plugin_is_contained(
    plugin_snapshot: DocumentSnapshot,
) -> None:
    """Breaking the contract is a plugin fault, contained on the same path."""
    results = SupervisedPluginRuntime([ImpersonatingPlugin()]).dispatch(plugin_snapshot)
    assert results.is_healthy is False
    recorded = results.failures[0]
    assert recorded.plugin == "liar"
    assert recorded.code is ErrorCode.PLUGIN_CONTRACT_VIOLATED
    assert results.num_suggestions == 0


def test_output_produced_before_a_crash_is_discarded(
    plugin_snapshot: DocumentSnapshot,
) -> None:
    """Partial output from a failed run is not trustworthy."""
    results = SupervisedPluginRuntime([LateCrashingPlugin()]).dispatch(plugin_snapshot)
    assert results.is_healthy is False
    assert results.num_suggestions == 0
    assert results.failures[0].error_type == "ValueError"


def test_an_exception_with_no_message_is_still_recorded(
    plugin_snapshot: DocumentSnapshot,
) -> None:
    class Terse:
        name = "terse"

        def examine(self, snapshot: DocumentSnapshot) -> Iterable[Suggestion]:
            raise RuntimeError

    results = SupervisedPluginRuntime([Terse()]).dispatch(plugin_snapshot)
    assert results.failures[0].message == ""
    assert results.failures[0].error_type == "RuntimeError"


@pytest.mark.parametrize("raised", [KeyboardInterrupt, SystemExit], ids=["interrupt", "exit"])
def test_operator_signals_are_not_swallowed(
    plugin_snapshot: DocumentSnapshot, raised: type[BaseException]
) -> None:
    """Catching these would make the daemon unkillable.

    They are the operator shutting the process down, not a plugin misbehaving,
    so they sit outside the sandbox NFR 5.3 asks for.
    """

    class Interrupting:
        name = "interrupting"

        def examine(self, snapshot: DocumentSnapshot) -> Iterable[Suggestion]:
            raise raised

    with pytest.raises(raised):
        SupervisedPluginRuntime([Interrupting()]).dispatch(plugin_snapshot)


# -- Concurrency (Figure 5, SRS 3.2) ------------------------------------------
def test_the_default_runtime_is_sequential() -> None:
    assert SupervisedPluginRuntime().is_concurrent is False


def test_an_injected_executor_is_used(plugin_snapshot: DocumentSnapshot) -> None:
    """The runtime dispatches through the caller's scheduler, never its own."""
    executor = RecordingExecutor()
    runtime = SupervisedPluginRuntime(
        [WellBehavedPlugin(), SilentPlugin(), CrashingPlugin()], executor=executor
    )
    assert runtime.is_concurrent is True
    runtime.dispatch(plugin_snapshot)
    assert executor.submissions == 3


def test_concurrent_dispatch_matches_sequential_dispatch(
    plugin_snapshot: DocumentSnapshot,
) -> None:
    """Switching an executor in must not change what the user sees."""

    def build(executor: Executor | None) -> PluginResults:
        runtime = SupervisedPluginRuntime(
            [
                WellBehavedPlugin("spell"),
                WellBehavedPlugin("style"),
                SilentPlugin(),
                CrashingPlugin(),
                ImpersonatingPlugin(),
            ],
            executor=executor,
        )
        return runtime.dispatch(plugin_snapshot)

    sequential = build(None)
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert build(pool) == sequential


def test_a_refused_submission_is_not_treated_as_a_plugin_fault(
    plugin_snapshot: DocumentSnapshot,
) -> None:
    """NFR 5.3 isolates plugins, not the scheduler the caller supplied."""
    runtime = SupervisedPluginRuntime([WellBehavedPlugin()], executor=ExhaustedExecutor())
    with pytest.raises(RuntimeError, match="after shutdown"):
        runtime.dispatch(plugin_snapshot)


def test_many_documents_dispatch_concurrently_against_one_runtime(
    plugin_snapshot: DocumentSnapshot,
) -> None:
    """The daemon shares one runtime across documents."""
    runtime = SupervisedPluginRuntime([WellBehavedPlugin(), SilentPlugin(), CrashingPlugin()])
    serial = [runtime.dispatch(plugin_snapshot) for _ in range(16)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        concurrent = list(pool.map(runtime.dispatch, [plugin_snapshot] * 16))
    assert concurrent == serial


# -- Determinism ---------------------------------------------------------------
def test_dispatch_is_deterministic(plugin_snapshot: DocumentSnapshot) -> None:
    runtime = SupervisedPluginRuntime([WellBehavedPlugin(), CrashingPlugin(), SilentPlugin()])
    assert runtime.dispatch(plugin_snapshot) == runtime.dispatch(plugin_snapshot)


def test_the_runtime_holds_no_state_between_dispatches(
    plugin_snapshot: DocumentSnapshot,
) -> None:
    runtime = SupervisedPluginRuntime([WellBehavedPlugin(), CrashingPlugin()])
    first = runtime.dispatch(plugin_snapshot)
    assert runtime.dispatch(plugin_snapshot) == first


def test_registration_order_does_not_change_the_results(
    plugin_snapshot: DocumentSnapshot,
) -> None:
    """Outcomes are keyed by name, so the registry's order is presentational."""
    forward = SupervisedPluginRuntime(
        [WellBehavedPlugin(), SilentPlugin(), CrashingPlugin()]
    ).dispatch(plugin_snapshot)
    reversed_ = SupervisedPluginRuntime(
        [CrashingPlugin(), SilentPlugin(), WellBehavedPlugin()]
    ).dispatch(plugin_snapshot)
    assert forward == reversed_


def test_the_snapshot_is_not_mutated_by_dispatch(
    plugin_snapshot: DocumentSnapshot,
) -> None:
    """Every plugin reads the same object; none of them may change it."""
    before = plugin_snapshot.model_dump_json()
    SupervisedPluginRuntime(
        [WellBehavedPlugin(), CrashingPlugin(), ImpersonatingPlugin()]
    ).dispatch(plugin_snapshot)
    assert plugin_snapshot.model_dump_json() == before
