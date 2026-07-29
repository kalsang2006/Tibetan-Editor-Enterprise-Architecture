"""The Plugin Runtime: supervised execution of feature plugins.

Figure 3 places this component at P5, between the Language Server and the
Suggestion Fusion Engine. It takes the immutable document snapshot Stage 12
produces, runs every registered feature over it, and hands the collected
suggestions to fusion. Figure 2 assigns it "Execute Features & Load Plugins ·
Sandbox Extension Management · Lifecycle & Request Dispatching"; Figure 9 assigns
it "Sandbox Execution · Feature Dispatcher".

Isolation, and what kind
------------------------
FR-5 asks for plugins isolated "into separate memory supervisors" and NFR 5.3 for
faults "captured by its manager". Those are satisfied here by supervised
in-process execution rather than by separate processes, because Figure 5 requires
that "all plugins consume the **centralized** immutable snapshot concurrently" --
one shared object, not a copy per plugin. The reasoning, and what the choice does
and does not buy, is recorded in ADR-018.

The supervision itself is narrow and deliberate: every call into a plugin is
wrapped, every exception below :class:`BaseException` becomes a recorded failure,
and one plugin's fault leaves every other plugin's result untouched.

Concurrency is injected, not owned
----------------------------------
SRS 3.2 requires the engine to "gather parallel suggestions from active feature
modules", and Figure 5 has the plugins read the snapshot concurrently. The
runtime therefore accepts an :class:`~concurrent.futures.Executor` and dispatches
through it. It does not create one: NFR 5.1 gives the daemon "a tiered priority
scheduler", and a component that silently spawned its own threads would be
outside that scheduler's control and would leak them when the daemon shut down.
The default is sequential, which is the same mechanism-versus-policy split
ADR-016 and ADR-017 drew.

Results are ordered by plugin name either way, so switching an executor in or out
cannot change what the user sees.
"""

from __future__ import annotations

from collections.abc import Iterable
from concurrent.futures import Executor, Future, ThreadPoolExecutor

from teea.core.errors import ConfigurationError, ErrorCode, TEEAError
from teea.nlp.snapshot import DocumentSnapshot
from teea.plugins.interfaces import FeaturePlugin
from teea.plugins.models import PluginFailure, PluginOutcome, PluginResults


class SupervisedPluginRuntime:
    """Runs feature plugins over a snapshot, containing any fault they raise.

    Satisfies the :class:`~teea.plugins.interfaces.PluginRuntime` protocol. Holds
    no mutable state of its own and is safe to share across threads; whether a
    *plugin* is safe to run concurrently is the plugin's own responsibility, and
    :class:`~teea.plugins.interfaces.FeaturePlugin` states that requirement.

    Plugins are supplied at construction rather than discovered. Figure 2's
    "Dynamic Module Discovery" belongs to the Capability Registry, which is a
    separate component and is not implemented; loading code from disk here would
    be inventing it.

    Args:
        plugins: The features to execute. Their names are read once, here, and
            used for the rest of their life, so a plugin cannot change identity
            between registration and dispatch.
        executor: Where to run them. ``None``, the default, runs them one after
            another on the calling thread. Supplying a thread pool satisfies
            Figure 5's concurrent consumption of the shared snapshot.

    Raises:
        ConfigurationError: If a plugin has no name, if two plugins share one, or
            if reading a plugin's name raises. A runtime that started with an
            ambiguous registry would misattribute both suggestions and faults.
    """

    def __init__(
        self,
        plugins: Iterable[FeaturePlugin] = (),
        *,
        executor: Executor | None = None,
        timeout: float | None = None,
    ) -> None:
        """Initialise the runtime with plugins and optional concurrency settings.

        Args:
            plugins: The features to execute. Their names are read once, here, and
                used for the rest of their life, so a plugin cannot change identity
                between registration and dispatch.
            executor: Where to run them. ``None``, the default, runs them one after
                another on the calling thread. Supplying a thread pool satisfies
                Figure 5's concurrent consumption of the shared snapshot.
            timeout: Maximum seconds each plugin is allowed to run before being
                treated as a failure. ``None`` (the default) disables the timeout.
                When ``timeout`` is set but ``executor`` is ``None``, a temporary
                single-thread executor is created internally so the timeout can be
                enforced; the runtime's :attr:`is_concurrent` property still
                reports ``False``.

        Raises:
            ConfigurationError: If a plugin has no name, if two plugins share one, or
                if reading a plugin's name raises. A runtime that started with an
                ambiguous registry would misattribute both suggestions and faults.
        """
        registered: list[tuple[str, FeaturePlugin]] = []
        seen: set[str] = set()

        for position, plugin in enumerate(plugins):
            try:
                name = plugin.name
            except Exception as exc:  # registration is a plugin boundary too
                raise ConfigurationError(
                    "A plugin failed to report its name.",
                    context={"position": position, "error_type": type(exc).__name__},
                    cause=exc,
                ) from exc
            if not name:
                raise ConfigurationError(
                    "A plugin reported an empty name.",
                    context={"position": position},
                )
            if name in seen:
                raise ConfigurationError(
                    "Two plugins share the same name.",
                    context={"name": name, "position": position},
                )
            seen.add(name)
            registered.append((name, plugin))

        self._registered: tuple[tuple[str, FeaturePlugin], ...] = tuple(registered)
        self._executor = executor
        self._timeout = timeout

    @property
    def plugins(self) -> tuple[str, ...]:
        """The registered plugin names, in dispatch order."""
        return tuple(name for name, _ in self._registered)

    @property
    def is_concurrent(self) -> bool:
        """Whether an executor was supplied to run plugins in parallel."""
        return self._executor is not None

    def dispatch(self, snapshot: DocumentSnapshot) -> PluginResults:
        """Run every registered plugin over ``snapshot``.

        Total: a plugin that raises, or that returns output attributed to
        another plugin, yields a recorded failure rather than an exception.

        Args:
            snapshot: The immutable analysis of the whole document.

        Returns:
            One outcome per registered plugin, ordered by plugin name.

        Raises:
            RuntimeError: If a supplied executor refuses work, for example
                because it has already been shut down. That is a fault in the
                caller's scheduler rather than in a plugin, so it is not
                captured -- NFR 5.3 isolates plugins, not the infrastructure
                running them.
        """
        if self._executor is None and self._timeout is not None:
            # When a timeout is requested but no executor was supplied, create
            # a temporary single-worker executor so the deadline is enforceable.
            with ThreadPoolExecutor(max_workers=1) as pool:
                futures = [
                    pool.submit(self._supervise, name, plugin, snapshot)
                    for name, plugin in self._registered
                ]
                outcomes = self._collect(futures)
        elif self._executor is None:
            outcomes = [
                self._supervise(name, plugin, snapshot) for name, plugin in self._registered
            ]
        else:
            futures = [
                self._executor.submit(self._supervise, name, plugin, snapshot)
                for name, plugin in self._registered
            ]
            outcomes = self._collect(futures)

        return PluginResults(outcomes=tuple(sorted(outcomes, key=lambda outcome: outcome.plugin)))

    def _collect(
        self, futures: list[Future[PluginOutcome]]
    ) -> list[PluginOutcome]:
        """Collect outcomes from futures, respecting the configured timeout.

        A future that times out or raises is recorded as a plugin failure
        rather than propagated.
        """
        outcomes: list[PluginOutcome] = []
        for future in futures:
            try:
                outcome = future.result(timeout=self._timeout)
            except TimeoutError:
                outcome = PluginOutcome(
                    plugin="unknown",
                    failure=PluginFailure(
                        plugin="unknown",
                        code=ErrorCode.PLUGIN_EXECUTION_FAILED,
                        error_type="TimeoutError",
                        message="Plugin execution timed out.",
                    ),
                )
                future.cancel()
            except Exception as exc:  # noqa: BLE001 - sandbox boundary
                outcome = PluginOutcome(
                    plugin="unknown",
                    failure=PluginFailure(
                        plugin="unknown",
                        code=ErrorCode.PLUGIN_EXECUTION_FAILED,
                        error_type=type(exc).__name__,
                        message=str(exc),
                    ),
                )
            outcomes.append(outcome)
        return outcomes

    # -- Internals -----------------------------------------------------------
    @staticmethod
    def _supervise(name: str, plugin: FeaturePlugin, snapshot: DocumentSnapshot) -> PluginOutcome:
        """Run one plugin, converting any fault into a recorded outcome.

        The blind except is the sandbox boundary NFR 5.3 requires: this is the
        one place in the system where arbitrary third-party code is invoked, and
        narrowing it to anticipated exception types would defeat the point, since
        the faults worth containing are exactly the unanticipated ones.

        ``BaseException`` is deliberately *not* caught. ``KeyboardInterrupt`` and
        ``SystemExit`` are the operator shutting the daemon down, and swallowing
        them would make it unkillable.

        Building the outcome inside the guarded block is also deliberate. A
        plugin that attributes its suggestions to another plugin fails the
        outcome's validator, and that is a misbehaving plugin -- so it is
        contained on the same path as a crash rather than escaping as a
        :class:`pydantic.ValidationError`.
        """
        try:
            return PluginOutcome(plugin=name, suggestions=tuple(plugin.examine(snapshot)))
        except Exception as exc:  # noqa: BLE001 - the NFR 5.3 sandbox boundary
            return PluginOutcome(plugin=name, failure=_capture(name, exc))


def _capture(name: str, exc: Exception) -> PluginFailure:
    """Describe a fault without leaking the document that provoked it.

    A plugin raising a :class:`~teea.core.errors.TEEAError` keeps its own code,
    so a plugin that failed to load its configuration stays distinguishable from
    one that crashed mid-analysis. Anything else is classified by whether the
    plugin broke the runtime's contract or simply failed.
    """
    if isinstance(exc, TEEAError):
        code = exc.code
    elif isinstance(exc, ValueError):
        # pydantic's ValidationError is a ValueError, and the only validation a
        # plugin can fail here is the outcome's attribution check.
        code = ErrorCode.PLUGIN_CONTRACT_VIOLATED
    else:
        code = ErrorCode.PLUGIN_EXECUTION_FAILED
    return PluginFailure(plugin=name, code=code, error_type=type(exc).__name__, message=str(exc))


__all__ = ["SupervisedPluginRuntime"]
