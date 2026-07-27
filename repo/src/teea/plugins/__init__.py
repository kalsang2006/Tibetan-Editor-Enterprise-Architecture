"""TEEA Plugin Runtime.

SRS 2.1 describes the product as "a microkernel-based plugin engine", and this is
the microkernel. Figure 1 places it in the Runtime Layer beside the Language
Server and the Suggestion Fusion Engine; Figure 3 places it at P5, receiving
"Parsed Tokens / Graph" from the Language Server and emitting "Plugin Results" to
the Fusion Engine; Figure 2 gives it "Execute Features & Load Plugins · Sandbox
Extension Management · Lifecycle & Request Dispatching".

It closes the loop between the two components already built: a
:class:`~teea.nlp.snapshot.DocumentSnapshot` goes in, and the
:class:`~teea.fusion.Suggestion` list the Fusion Engine consumes comes out.

Public API:

* :class:`FeaturePlugin` -- the contract an extension implements.
* :class:`PluginRuntime` -- the contract the daemon calls.
* :class:`SupervisedPluginRuntime` -- the shipped implementation.
* Domain models: :class:`PluginResults`, :class:`PluginOutcome`,
  :class:`PluginFailure`.

**No concrete plugin ships here.** Figure 5 names eight, and each is a component
in its own right with its own requirements and data. The runtime is complete
without them, in the same way the Fusion Engine is (ADR-017).

Typical usage, the whole daemon pipeline::

    from teea.fusion import PriorityRankedFusionEngine
    from teea.nlp.snapshot import LanguageServerSnapshotBuilder
    from teea.nlp.tokenization import TextNormalizer
    from teea.plugins import SupervisedPluginRuntime

    normalizer = TextNormalizer(form="NFC", collapse_whitespace=False)
    language_server = LanguageServerSnapshotBuilder()
    runtime = SupervisedPluginRuntime(my_plugins)
    fusion = PriorityRankedFusionEngine()

    snapshot = language_server.analyze(normalizer.normalize(document))
    results = runtime.dispatch(snapshot)
    unified = fusion.fuse(snapshot.source, results.suggestions)

    results.is_healthy      # did every plugin complete?
    results.failures        # what the ones that did not reported
    unified.patch.apply()   # the rewritten document

A plugin that raises never reaches the caller: NFR 5.3 requires the fault to be
captured by its manager, so it becomes a recorded
:class:`PluginFailure` and every other plugin's result is unaffected.
"""

from __future__ import annotations

from teea.plugins.interfaces import FeaturePlugin, PluginRuntime
from teea.plugins.models import PluginFailure, PluginOutcome, PluginResults
from teea.plugins.runtime import SupervisedPluginRuntime

__all__ = [
    "FeaturePlugin",
    "PluginFailure",
    "PluginOutcome",
    "PluginResults",
    "PluginRuntime",
    "SupervisedPluginRuntime",
]
